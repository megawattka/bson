import datetime as dt

import pytest

from elune import BSONError, InvalidId, ObjectId


def test_exports_and_construction():
    assert ObjectId.__module__ == "elune.objectid"
    assert issubclass(InvalidId, BSONError)
    text = "0123456789abcdefABCDEF01"
    oid = ObjectId(oid=text)
    assert str(oid) == text.lower()
    assert repr(oid) == f"ObjectId('{text.lower()}')"
    assert oid.binary == bytes.fromhex(text)
    assert ObjectId(oid) == oid
    assert ObjectId(bytes.fromhex(text)) == oid
    assert str(ObjectId(b"foo-bar-quux")) == "666f6f2d6261722d71757578"
    for text in ("0" * 24, "f" * 24):
        assert str(ObjectId(text)) == text


def test_invalid_values_and_is_valid():
    for value in ("", "0" * 23, "0" * 25, "g" * 24, "é" * 24, " " * 24):
        with pytest.raises(InvalidId):
            ObjectId(value)
    for value in (  # pyright: ignore[reportUnknownVariableType]
        b"",
        b"x" * 11,
        b"x" * 13,
        bytearray(12),
        memoryview(bytes(12)),
        1,
        [],
        {},
    ):
        with pytest.raises(TypeError):
            ObjectId(value)  # pyright: ignore[reportArgumentType]
    for value in (ObjectId(), bytes(12), "0123456789abcdefABCDEF01"):
        assert ObjectId.is_valid(value)
    for value in (  # pyright: ignore[reportUnknownVariableType]
        None,
        "",
        b"",
        0,
        False,
        [],
        {},
        "g" * 24,
        bytes(11),
        bytearray(12),
    ):
        assert not ObjectId.is_valid(value)  # pyright: ignore[reportUnknownArgumentType]


def test_from_datetime():
    for value in (
        dt.datetime(1970, 1, 1),  # ruff: ignore[call-datetime-without-tzinfo]
        dt.datetime(2020, 2, 29, 12, 30, 1, 999999),  # ruff: ignore[call-datetime-without-tzinfo]
        dt.datetime(2020, 2, 29, 12, 30, tzinfo=dt.UTC),
        dt.datetime(
            2020,
            2,
            29,
            12,
            30,
            tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)),
        ),
    ):
        oid = ObjectId.from_datetime(generation_time=value)
        assert len(oid.binary) == 12
        assert oid.binary[4:] == bytes(8)
    with pytest.raises(TypeError):
        ObjectId.from_datetime("2020-01-01")  # pyright: ignore[reportArgumentType]


def test_comparison_and_properties():
    a = ObjectId(bytes(12))
    b = ObjectId(bytes([1]) + bytes(11))
    assert a < b
    assert a == ObjectId(bytes(12))
    assert hash(a) == hash(bytes(12))
    for name, value in (("binary", bytes(12)), ("generation_time", None)):
        with pytest.raises(AttributeError):
            setattr(a, name, value)
