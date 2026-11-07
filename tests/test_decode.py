"""BSON decoding, boundary validation, and reference differential tests."""

import array
import math
import random
import struct
from typing import Any, cast

import pytest

from bson import Binary, Int64, ObjectId, decode, decode_all, encode
from bson.errors import BSONError, InvalidBSON

try:
    import _p_bson as reference
except ImportError:
    reference = None


def document(body: bytes) -> bytes:
    return struct.pack("<i", len(body) + 5) + body + b"\0"


def element(tag: int, payload: bytes = b"", name: bytes = b"x") -> bytes:
    return bytes([tag]) + name + b"\0" + payload


def test_empty_and_public_errors() -> None:
    assert decode(b"\x05\0\0\0\0") == {}
    assert decode_all(b"") == []
    assert issubclass(InvalidBSON, BSONError)
    assert InvalidBSON.__module__ == "bson.errors"


def test_scalars_exact_types_and_wire_roundtrip() -> None:
    cases: list[tuple[int, bytes, Any]] = [
        (10, b"", None),
        (8, b"\0", False),
        (8, b"\1", True),
        (16, struct.pack("<i", -(2**31)), -(2**31)),
        (16, struct.pack("<i", 2**31 - 1), 2**31 - 1),
        (18, struct.pack("<q", -(2**63)), Int64(-(2**63))),
        (18, struct.pack("<q", 2**63 - 1), Int64(2**63 - 1)),
        (1, struct.pack("<d", 1.25), 1.25),
        (2, struct.pack("<i", 1) + b"\0", ""),
        (5, struct.pack("<i", 0) + b"\0", b""),
        (7, bytes(range(12)), ObjectId(bytes(range(12)))),
    ]
    for tag, payload, expected in cases:
        actual = decode(document(element(tag, payload)))["x"]
        assert actual == expected
        assert type(actual) is type(expected)


def test_float_special_values() -> None:
    for value in (0.0, -0.0, math.inf, -math.inf, math.nan):
        result = decode(document(element(1, struct.pack("<d", value))))["x"]
        assert (
            math.isnan(result)
            if math.isnan(value)
            else struct.pack("<d", result) == struct.pack("<d", value)
        )


def test_nested_and_root_id_order() -> None:
    doc: dict[str, Any] = {
        "before": 1,
        "_id": ObjectId(bytes(12)),
        "": "",
        "unicode": "??????\0??",
        "binary": bytes(range(256)),
        "children": [{"a": [1, True, None]}, {}, []],
    }
    data = encode(doc)
    result = decode(data)
    assert result == doc
    assert list(result) == [
        "_id",
        "before",
        "",
        "unicode",
        "binary",
        "children",
    ]
    assert encode(result) == data


def test_arrays_and_duplicate_fields() -> None:
    child = document(
        element(16, struct.pack("<i", 1), b"hello")
        + element(16, struct.pack("<i", 2), b"\xff"),
    )
    assert decode(document(element(4, child))) == {"x": [1, 2]}
    data = document(
        element(16, struct.pack("<i", 1)) + element(16, struct.pack("<i", 2)),
    )
    assert decode(data) == {"x": 2}


def test_buffer_protocol_inputs() -> None:
    data = encode({"x": [1, "?", bytes(12)]})
    interleaved = b"".join(bytes([byte, 255]) for byte in data)
    for value in (
        data,
        bytearray(data),
        memoryview(data),
        memoryview(bytearray(data)),
        array.array("B", data),
        memoryview(interleaved)[::2],
        memoryview(data[::-1])[::-1],
    ):
        assert decode(value) == decode(data)
        assert decode_all(value) == [decode(data)]
    invalid_inputs: tuple[object, ...] = (None, [], "bytes", 123, object())
    for invalid in invalid_inputs:
        for fn in (decode, decode_all):
            with pytest.raises((TypeError, BufferError)):
                fn(invalid)  # pyright: ignore[reportArgumentType]


def test_decode_all_concatenation_and_trailing_data() -> None:
    docs: list[dict[str, Any]] = [
        {},
        {"x": 1},
        {"_id": ObjectId(bytes(12)), "items": [{"y": [False]}]},
    ]
    encoded = [encode(doc) for doc in docs]
    assert decode_all(b"".join(encoded)) == docs
    assert decode_all(b"".join(encoded * 30)) == docs * 30
    assert decode_all(b"") == []
    for suffix in (b"x", b"\0", encode({})[:-1]):
        with pytest.raises(InvalidBSON):
            decode_all(b"".join(encoded) + suffix)


def test_all_truncation_points() -> None:
    data = encode(
        {
            "_id": ObjectId(bytes(12)),
            "x": ["text", bytes(20), True, 2**40, 1.25, {"y": 1}],
        },
    )
    for end in range(len(data)):
        with pytest.raises(InvalidBSON):
            decode(data[:end])
        if end:
            with pytest.raises(InvalidBSON):
                decode_all(data[:end])


def test_malformed_documents() -> None:
    malformed = [
        struct.pack("<i", n) + b"\0"
        for n in (-(2**31), -1, 0, 1, 4, 6, 2**31 - 1)
    ]
    malformed += [
        b"\x05\0\0\0\1",
        document(b"\0"),
        document(b"\x10unterminated"),
    ]
    malformed += [
        document(element(16, b"\1")),
        document(element(18, bytes(7))),
        document(element(1, bytes(7))),
        document(element(7, bytes(11))),
        document(element(8, b"\2")),
        document(element(8, b"\xff")),
    ]
    malformed += [
        document(element(2, struct.pack("<i", n) + b"\0"))
        for n in (-1, 0, 100, 2**31 - 1)
    ]
    malformed += [
        document(element(2, struct.pack("<i", 2) + b"ab")),
        document(element(2, struct.pack("<i", 2) + b"\xff\0")),
        document(element(10, name=b"\xff")),
        document(element(5, struct.pack("<i", -1) + b"\0")),
        document(element(5, struct.pack("<i", 100) + b"\0abc")),
        document(element(3, struct.pack("<i", 100) + b"\0")),
    ]
    for data in malformed:
        with pytest.raises(InvalidBSON):
            decode(data)
        with pytest.raises(InvalidBSON):
            decode_all(data)


def test_unsupported_types_and_binary_subtypes() -> None:
    for tag in (6, 12, 14, 128):
        with pytest.raises(InvalidBSON, match="unsupported BSON type"):
            decode(document(element(tag)))
    for subtype in (1, 3, 4, 128):
        result = decode(
            document(element(5, struct.pack("<i", 0) + bytes([subtype]))),
        )
        assert result == {"x": Binary(b"", subtype)}


def test_depth_limit_and_random_corrupt_input_safety() -> None:
    data = encode({})
    for _ in range(99):
        data = document(element(3, data))
    assert (
        decode(data) == {"x": {"x": {}}}
        if False
        else isinstance(decode(data), dict)
    )
    with pytest.raises(InvalidBSON):
        decode(document(element(3, data)))
    rng = random.Random(815)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - reproducible test data
    for _ in range(800):
        raw = bytearray(rng.randbytes(rng.randrange(5, 80)))
        struct.pack_into("<i", raw, 0, len(raw))
        raw[-1] = 0
        try:
            result = decode(raw)
        except InvalidBSON:
            continue
        assert isinstance(result, dict)


@pytest.mark.skipif(
    reference is None,
    reason="PyMongo reference not installed",
)
def test_reference_randomized_documents() -> None:  # ruff: ignore[complex-structure] - recursive generator
    assert reference is not None
    rng = random.Random(4026)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - reproducible test data
    scalars: list[Any] = [
        None,
        True,
        False,
        0,
        2**31,
        -(2**63),
        2**63 - 1,
        "",
        "?\0??",
        b"",
        bytes(range(20)),
        reference.ObjectId(bytes(12)),
    ]

    def value(depth: int) -> Any:  # ruff: ignore[any-type] - recursive BSON values
        choice = rng.randrange(5 if depth < 4 else 3)
        if choice == 0:
            return rng.choice(scalars)
        if choice == 1:
            return rng.uniform(-1e10, 1e10)
        if choice == 2:
            return rng.randrange(-(2**63), 2**63)
        if choice == 3:
            return [value(depth + 1) for _ in range(rng.randrange(5))]
        return {f"k{i}": value(depth + 1) for i in range(rng.randrange(5))}

    def normalize(item: Any) -> Any:  # ruff: ignore[any-type] - heterogeneous BSON
        assert reference is not None
        if isinstance(item, (ObjectId, reference.ObjectId)):
            return item.binary
        if isinstance(item, dict):
            mapping = cast("dict[str, Any]", item)
            return {key: normalize(value) for key, value in mapping.items()}
        if isinstance(item, (list, tuple)):
            return [
                normalize(value)
                for value in cast("list[Any] | tuple[Any, ...]", item)
            ]
        return item

    for _ in range(100):
        doc = {f"key{i}": value(0) for i in range(rng.randrange(8))}
        data = reference.encode(doc)
        assert encode(decode(data)) == data
        # The reference stub leaves its array buffer parameter unparameterized.
        assert normalize(decode(data)) == normalize(reference.decode(data))  # pyright: ignore[reportUnknownMemberType]
