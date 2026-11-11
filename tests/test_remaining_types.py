"""Wire-format and behavior comparisons against independent PyMongo types."""

from collections.abc import Callable  # ruff: ignore[typing-only-standard-library-import] - helper annotation
import datetime as dt
import decimal
import gc
import importlib
import operator
import random
import re
import struct
from typing import Any
import weakref

import pytest

import elune as m

try:  # ruff: ignore[too-many-statements-in-try-clause]
    import _p_bson as b
    from _p_bson.code import Code as BCode
    from _p_bson.codec_options import CodecOptions as BOptions
    from _p_bson.codec_options import DatetimeConversion as BConversion
    from _p_bson.datetime_ms import DatetimeMS as BDatetimeMS
    from _p_bson.decimal128 import Decimal128 as BDecimal
    from _p_bson.max_key import MaxKey as BMaxKey
    from _p_bson.min_key import MinKey as BMinKey
    from _p_bson.regex import Regex as BRegex
    from _p_bson.timestamp import Timestamp as BTimestamp
except ImportError:
    b = None


def document(tag: int, payload: bytes) -> bytes:
    body = bytes([tag]) + b"x\x00" + payload + b"\x00"
    return struct.pack("<i", len(body) + 4) + body


def assert_pair(actual: Any, reference: Any) -> Any:  # ruff: ignore[any-type] - independent BSON types
    assert b is not None
    data = m.encode({"x": actual})
    assert data == b.encode({"x": reference})
    decoded = m.decode(data)["x"]
    expected = b.decode(data)["x"]  # pyright: ignore[reportUnknownMemberType]
    assert type(decoded).__name__ == type(expected).__name__
    assert m.encode({"x": decoded}) == data
    if isinstance(decoded, m.Regex):
        assert decoded.pattern == expected.pattern
        assert decoded.flags == expected.flags
    else:
        assert repr(decoded) == repr(expected)
    assert m.decode_all(data + data) == [{"x": decoded}, {"x": decoded}]
    return decoded


@pytest.mark.skipif(b is None, reason="PyMongo reference not installed")
def test_datetime_values_and_timezones() -> None:
    assert b is not None
    rng = random.Random(102)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - deterministic test data
    values = [
        dt.datetime.min,  # ruff: ignore[datetime-min-max] - naive boundary fixture
        dt.datetime.max,  # ruff: ignore[datetime-min-max] - naive boundary fixture
        dt.datetime(1970, 1, 1),  # ruff: ignore[call-datetime-without-tzinfo] - intentional naive datetime fixture
        dt.datetime(1969, 12, 31, 23, 59, 59, 999999),  # ruff: ignore[call-datetime-without-tzinfo] - intentional naive datetime fixture
    ]
    for _ in range(200):
        values.append(  # ruff: ignore[manual-list-comprehension] - multiline datetime fixture
            dt.datetime(
                rng.randrange(2, 9999),
                rng.randrange(1, 13),
                rng.randrange(1, 29),
                rng.randrange(24),
                rng.randrange(60),
                rng.randrange(60),
                rng.randrange(1000000),
                tzinfo=dt.timezone(
                    dt.timedelta(
                        seconds=rng.randrange(-86399, 86400),
                        microseconds=rng.randrange(1000000),
                    ),
                ),
            ),
        )
    for value in values:
        assert_pair(value, value)
        assert int(m.DatetimeMS(value)) == int(BDatetimeMS(value))  # pyright: ignore[reportCallIssue]
        data = m.encode({"x": value})
        assert m.decode(
            data, codec_options=m.CodecOptions(tz_aware=True),
        ) == b.decode(  # pyright: ignore[reportUnknownMemberType]
            data,
            BOptions[dict[str, Any]](tz_aware=True),  # pyright: ignore[reportUnknownArgumentType]
        )


@pytest.mark.skipif(b is None, reason="PyMongo reference not installed")
def test_datetime_conversion_modes() -> None:
    assert b is not None
    for mode in (
        m.DatetimeConversion.DATETIME,
        m.DatetimeConversion.DATETIME_CLAMP,
        m.DatetimeConversion.DATETIME_MS,
        m.DatetimeConversion.DATETIME_AUTO,
    ):
        assert m.CodecOptions(
            datetime_conversion=mode,
        ).datetime_conversion == int(mode)
        assert m.CodecOptions().with_options(
            datetime_conversion=mode,
        ).datetime_conversion == int(mode)
    for value in [
        -(2**63),
        -62135596800001,
        -62135596800000,
        -1,
        0,
        1,
        253402300799999,
        253402300800000,
        2**63 - 1,
    ]:
        data = m.encode({"x": m.DatetimeMS(value)})  # pyright: ignore[reportCallIssue]
        assert data == b.encode({"x": BDatetimeMS(value)})
        for mode in range(1, 5):
            for aware in (False, True):
                opts = m.CodecOptions(datetime_conversion=mode, tz_aware=aware)
                refopts: BOptions[dict[str, Any]] = BOptions(
                    datetime_conversion=BConversion(mode),
                    tz_aware=aware,
                )
                try:
                    expected: Any = b.decode(data, refopts)["x"]  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
                except b.errors.InvalidBSON:  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
                    with pytest.raises(m.InvalidBSON):
                        m.decode(data, codec_options=opts)
                else:
                    actual: Any = m.decode(data, codec_options=opts)["x"]
                    assert type(actual).__name__ == type(expected).__name__
                    actual_value = (
                        int(actual)
                        if isinstance(actual, m.DatetimeMS)
                        else actual
                    )
                    expected_value = (
                        int(expected)
                        if isinstance(expected, BDatetimeMS)
                        else expected
                    )
                    assert actual_value == expected_value
    for value in [-(2**63) - 1, 2**63, "1", 1.5, None]:
        assert_same_error(m.DatetimeMS, BDatetimeMS, value)
    assert m.DatetimeMS(0).as_datetime() == BDatetimeMS(0).as_datetime()  # pyright: ignore[reportCallIssue]
    for op in (
        operator.eq,
        operator.ne,
        operator.lt,
        operator.le,
        operator.gt,
        operator.ge,
    ):
        assert op(m.DatetimeMS(1), 2) == op(BDatetimeMS(1), 2)  # pyright: ignore[reportCallIssue]


def assert_same_error(
    actual: Callable[..., object],
    reference: Callable[..., object],
    *args: object,
) -> None:
    with pytest.raises(Exception) as expected:  # ruff: ignore[pytest-raises-too-broad] - compare error types
        reference(*args)
    with pytest.raises(Exception) as result:  # ruff: ignore[pytest-raises-too-broad] - compare error types
        actual(*args)
    assert type(result.value).__name__ == type(expected.value).__name__


@pytest.mark.skipif(b is None, reason="PyMongo reference not installed")
def test_timestamps() -> None:
    assert b is not None
    for time in (
        0,
        1,
        2**31,
        2**32 - 1,
        dt.datetime(2000, 1, 1),  # ruff: ignore[call-datetime-without-tzinfo] - intentional naive datetime fixture
        dt.datetime(2024, 1, 1, tzinfo=dt.timezone(dt.timedelta(hours=3))),
    ):
        for inc in (0, 1, 2**32 - 1):
            actual, ref = (m.Timestamp(time, inc), BTimestamp(time, inc))
            assert_pair(actual, ref)
            assert (
                actual.time,
                actual.inc,
                actual.as_datetime(),
                hash(actual),
            ) == (ref.time, ref.inc, ref.as_datetime(), hash(ref))
    for args in [
        (-1, 0),
        (2**32, 0),
        (0, -1),
        (0, 2**32),
        ("1", 0),
        (0, 1.5),
        (dt.datetime(1960, 1, 1), 0),  # ruff: ignore[call-datetime-without-tzinfo] - intentional naive datetime fixture
    ]:
        assert_same_error(m.Timestamp, BTimestamp, *args)
    for op in (
        operator.eq,
        operator.ne,
        operator.lt,
        operator.le,
        operator.gt,
        operator.ge,
    ):
        for a, c in [((1, 2), (2, 0)), ((1, 3), (1, 2)), ((0, 0), (0, 0))]:
            assert op(m.Timestamp(*a), m.Timestamp(*c)) == op(
                BTimestamp(*a),
                BTimestamp(*c),
            )


@pytest.mark.skipif(b is None, reason="PyMongo reference not installed")
def test_min_max_keys() -> None:
    assert b is not None
    for actual, reference in [(m.MinKey, BMinKey), (m.MaxKey, BMaxKey)]:
        assert_pair(actual(), reference())
        assert hash(actual()) == hash(reference())
        for op in (
            operator.eq,
            operator.ne,
            operator.lt,
            operator.le,
            operator.gt,
            operator.ge,
        ):
            for x, y in [
                (actual(), reference()),
                (None, None),
                (42, 42),
                ("abc", "abc"),
            ]:
                assert op(actual(), x) == op(reference(), y)  # pyright: ignore[reportArgumentType]


@pytest.mark.skipif(b is None, reason="PyMongo reference not installed")
def test_regex() -> None:
    assert b is not None
    for pattern in ("", "a.*", "привет", b"abc", "(?<name>x)"):
        for flags in (0, 2, 8, 127, "im", "ilmsux", "unknown"):
            assert_pair(m.Regex(pattern, flags), BRegex(pattern, flags))  # pyright: ignore[reportArgumentType]
    for native in (
        re.compile(r"abc"),
        re.compile(r"abc", re.IGNORECASE | re.MULTILINE),
        re.compile(rb"abc", re.IGNORECASE),
    ):
        assert_pair(native, native)
        actual, ref = (m.Regex.from_native(native), BRegex.from_native(native))  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        assert actual.pattern == ref.pattern  # pyright: ignore[reportUnknownMemberType]
        assert actual.flags == ref.flags
        assert actual.try_compile() == ref.try_compile()
    for args in [(1,), (None,), ("x", None), ("x", 1.5)]:
        assert_same_error(m.Regex, BRegex, *args)
    with pytest.raises(m.InvalidDocument):
        m.encode({"x": m.Regex("a\x00b")})


@pytest.mark.skipif(b is None, reason="PyMongo reference not installed")
def test_code_scope() -> None:
    assert b is not None
    for text in ("", "return 1", "return 'привет'", "a\x00b"):
        for scope in (None, {}, {"a": 1, "nested": [{"b": 2}]}):
            assert_pair(m.Code(text, scope), BCode(text, scope))
    actual = m.Code("x", {"a": 1}, b=2)
    ref = BCode("x", {"a": 1}, b=2)
    assert actual.scope == ref.scope
    assert str(actual) == str(ref)
    actual2, ref2 = (m.Code(actual, {"c": 3}), BCode(ref, {"c": 3}))
    assert actual2.scope == ref2.scope
    assert actual.scope == ref.scope
    assert actual != "x"
    invalid_args: list[tuple[Any, ...]] = [(1,), (b"a",), ("x", 1), ("x", [])]
    for args in invalid_args:
        assert_same_error(m.Code, BCode, *args)
    nested = m.Code("outer", {"x": m.Code("inner", {"y": m.Timestamp(1, 2)})})
    reference = BCode("outer", {"x": BCode("inner", {"y": BTimestamp(1, 2)})})
    assert_pair(nested, reference)


@pytest.mark.skipif(b is None, reason="PyMongo reference not installed")
def test_scope_cycles_depth_and_boundaries() -> None:
    assert b is not None
    scope: dict[str, Any] = {}
    scope["cycle"] = m.Code("x", scope)
    with pytest.raises(m.InvalidDocument):
        m.encode(scope)
    value = 1
    for _ in range(101):
        value = m.Code("x", {"x": value})
    with pytest.raises(RecursionError):
        m.encode({"x": value})
    value = BCode("x", {})
    for _ in range(101):
        value = BCode("x", {"x": value})
    with pytest.raises(m.InvalidBSON):
        m.decode(b.encode({"x": value}))
    valid = m.encode({"x": m.Code("x", {"y": 1}), "z": 2})
    for length in (-1, 0, 13, 14, 10000):
        damaged = bytearray(valid)
        struct.pack_into("<i", damaged, 7, length)
        with pytest.raises(m.InvalidBSON):
            m.decode(damaged)
    for end in range(len(valid)):
        with pytest.raises(m.InvalidBSON):
            m.decode(valid[:end])


@pytest.mark.skipif(b is None, reason="PyMongo reference not installed")
def test_decimal128() -> None:
    assert b is not None
    values = [
        "0",
        "-0",
        "1.0",
        "-123.456",
        "1E-6176",
        "1E+6144",
        "0E-9999",
        "0E+9999",
        "9.999999999999999999999999999999999E+6144",
        "Infinity",
        "-Infinity",
        "NaN",
        "-NaN",
        "sNaN",
        "-sNaN",
    ]
    rng = random.Random(330)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - deterministic test data
    values += [
        f"{rng.randrange(-(10**33), 10**33)}E{rng.randrange(-6100, 6100)}"
        for _ in range(200)
    ]
    for value in values:
        actual, reference = (m.Decimal128(value), BDecimal(value))
        assert actual.bid == reference.bid
        assert str(actual.to_decimal()) == str(reference.to_decimal())
        assert_pair(actual, reference)
        assert m.Decimal128(decimal.Decimal(value)).bid == reference.bid
    for value in (
        "1E-6177",
        "1E+6145",
        "1.2345678901234567890123456789012345",
        "NaN123",
        "bad",
        1,
        None,
    ):
        assert_same_error(m.Decimal128, BDecimal, value)
    assert m.Decimal128("NaN") == m.Decimal128("NaN")
    assert m.Decimal128("1") != m.Decimal128("1.0")
    for value in (m.Decimal128("1"), m.Regex("x"), m.Code("x")):
        with pytest.raises(TypeError):
            hash(value)
    for value in (b"", bytes(15), bytes(17), bytearray(16), "x"):
        assert_same_error(m.Decimal128.from_bid, BDecimal.from_bid, value)


@pytest.mark.skipif(b is None, reason="PyMongo reference not installed")
def test_arbitrary_bid() -> None:
    assert b is not None
    rng = random.Random(1234)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - deterministic test data
    for _ in range(300):
        bid = rng.randbytes(16)
        actual, reference = (
            m.Decimal128.from_bid(bid),
            BDecimal.from_bid(bid),
        )
        assert actual.bid == reference.bid
        assert m.decode(m.encode({"x": actual}))["x"].bid == bid
        try:
            expected = reference.to_decimal()
        except Exception as error:  # ruff: ignore[blind-except] - reproduce reference errors
            with pytest.raises(type(error)):
                actual.to_decimal()
        else:
            assert str(actual.to_decimal()) == str(expected)


@pytest.mark.skipif(b is None, reason="PyMongo reference not installed")
def test_decimal_context() -> None:
    assert b is not None
    from _p_bson.decimal128 import create_decimal128_context  # ruff: ignore[import-outside-top-level] - optional reference dependency

    actual, reference = (
        m.create_decimal128_context(),
        create_decimal128_context(),
    )
    for value in (
        "1E-6177",
        "1E+6145",
        "1.2345678901234567890123456789012345",
    ):
        assert str(actual.create_decimal(value)) == str(
            reference.create_decimal(value),
        )


@pytest.mark.skipif(b is None, reason="PyMongo reference not installed")
def test_exports() -> None:
    assert b is not None
    for module, name in [
        ("timestamp", "Timestamp"),
        ("regex", "Regex"),
        ("code", "Code"),
        ("decimal128", "Decimal128"),
        ("datetime_ms", "DatetimeMS"),
        ("min_key", "MinKey"),
        ("max_key", "MaxKey"),
    ]:
        assert getattr(
            importlib.import_module("elune." + module),
            name,
        ) is getattr(m, name)


@pytest.mark.skipif(b is None, reason="PyMongo reference not installed")
def test_gc_collects_scope_cycles() -> None:

    assert b is not None

    class Scope(dict[str, Any]):  # ruff: ignore[subclass-builtin] - weak-referenceable dict
        pass

    scope = Scope()
    value = m.Code("x", scope)
    scope["cycle"] = value
    ref = weakref.ref(scope)
    del scope, value
    gc.collect()
    assert ref() is None


@pytest.mark.skipif(b is None, reason="PyMongo reference not installed")
def test_mixed_nested_documents() -> None:
    assert b is not None
    rng = random.Random(782)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - deterministic test data
    actual = [
        m.MinKey(),
        m.MaxKey(),
        m.Timestamp(7, 9),
        m.Decimal128("12.50"),
        m.Regex("a.*", "im"),
        m.Code("x", {"t": m.Timestamp(1, 2)}),
        dt.datetime(2025, 1, 2),  # ruff: ignore[call-datetime-without-tzinfo] - intentional naive datetime fixture
        None,
        True,
        42,
        "abc",
    ]
    reference = [
        BMinKey(),
        BMaxKey(),
        BTimestamp(7, 9),
        BDecimal("12.50"),
        BRegex("a.*", "im"),
        BCode("x", {"t": BTimestamp(1, 2)}),
        dt.datetime(2025, 1, 2),  # ruff: ignore[call-datetime-without-tzinfo] - intentional naive datetime fixture
        None,
        True,
        42,
        "abc",
    ]
    for _ in range(100):
        indices = [rng.randrange(len(actual)) for _ in range(20)]
        left = {"array": [{"value": actual[i]} for i in indices]}
        right = {"array": [{"value": reference[i]} for i in indices]}
        assert m.encode(left) == b.encode(right)
        assert m.decode(m.encode(left)) == left


@pytest.mark.skipif(b is None, reason="PyMongo reference not installed")
def test_malformed_new_types_match_reference_errors() -> None:
    assert b is not None
    malformed = [
        document(11, b"abc"),
        document(11, b"\xff\x00\x00"),
        document(13, struct.pack("<i", -1)),
        document(13, struct.pack("<i", 2) + b"xx"),
        document(15, struct.pack("<i", 13) + bytes(9)),
        document(15, struct.pack("<i", 10000) + bytes(20)),
    ]
    for tag, size in [(9, 8), (17, 8), (19, 16)]:
        malformed.extend(
            document(tag, bytes(length)) for length in range(size)
        )
    for data in malformed:
        with pytest.raises(b.errors.InvalidBSON):  # pyright: ignore[reportAttributeAccessIssue, reportUnknownArgumentType, reportUnknownMemberType]
            b.decode(data)  # pyright: ignore[reportUnknownMemberType]
        with pytest.raises(m.InvalidBSON):
            m.decode(data)


@pytest.mark.skipif(b is None, reason="PyMongo reference not installed")
def test_truncated_scalar_payloads() -> None:
    assert b is not None
    for tag, payload in [
        (9, bytes(8)),
        (17, bytes(8)),
        (19, bytes(16)),
        (11, b"x\x00i\x00"),
        (13, b"\x02\x00\x00\x00x\x00"),
    ]:
        for end in range(len(payload)):
            with pytest.raises(m.InvalidBSON):
                m.decode(document(tag, payload[:end]))


def test_all_native_types_roundtrip() -> None:
    values = [
        m.MinKey(),
        m.MaxKey(),
        m.Timestamp(1, 2),
        m.Decimal128("1.25"),
        m.Regex("x", "im"),
        m.Code("x"),
        m.Code("x", {"v": 1}),
        dt.datetime(2024, 1, 1),  # ruff: ignore[call-datetime-without-tzinfo] - intentional naive datetime fixture
    ]
    for value in values:
        assert m.decode(m.encode({"x": value}))["x"] == value
    opts = m.CodecOptions(datetime_conversion=m.DatetimeConversion.DATETIME_MS)
    assert m.decode(
        m.encode({"x": m.DatetimeMS(-(2**63))}), codec_options=opts,  # pyright: ignore[reportCallIssue]
    )["x"] == m.DatetimeMS(-(2**63))  # pyright: ignore[reportCallIssue]
