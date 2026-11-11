import struct

import pytest

from elune import Int64, decode, decode_all, encode
from elune.int64 import Int64 as ModuleInt64

try:
    from _p_bson import Int64 as ReferenceInt64
    from _p_bson import decode as reference_decode  # pyright: ignore[reportUnknownVariableType]
    from _p_bson import encode as reference_encode
except ImportError:
    ReferenceInt64 = None


def test_exports_and_builtin_behavior():
    assert Int64 is ModuleInt64
    assert isinstance(Int64(42), int)
    assert Int64() == 0
    assert Int64("ff", 16) == 255
    assert Int64(b"123") == 123
    assert Int64(1.9) == 1
    assert Int64(True) == 1  # ruff: ignore[boolean-positional-value-in-call]
    assert Int64(2**100) == 2**100
    assert repr(Int64(42)) == "42"
    assert str(Int64(42)) == "42"
    assert hash(Int64(42)) == hash(42)
    assert {Int64(42): "value"}[42] == "value"  # pyright: ignore[reportArgumentType]
    assert type(Int64(1) + Int64(2)) is int
    assert Int64(1) + 2 == 3
    with pytest.raises(AttributeError):
        Int64(1).extra = 1  # pyright: ignore[reportAttributeAccessIssue]


def test_force_int64_and_roundtrip():
    for value in (0, 1, -1, -(2**31), 2**31 - 1, -(2**63), 2**63 - 1):
        encoded = encode({"x": Int64(value)})
        assert (
            encoded == b"\x10\0\0\0\x12x\0" + struct.pack("<q", value) + b"\0"
        )
        result = decode(encoded)["x"]
        assert type(result) is Int64
        assert result == value
        assert encode(decode(encoded)) == encoded
        assert type(decode_all(encoded)[0]["x"]) is Int64
    assert type(decode(encode({"x": 1}))["x"]) is int


def test_nested_and_subclasses():
    class CustomInt64(Int64):
        pass

    result = decode(encode({"a": [Int64(0), {"x": CustomInt64(1)}]}))
    assert type(result["a"][0]) is Int64
    assert type(result["a"][1]["x"]) is Int64

    class FakeMarker(int):
        _type_marker = 18

    assert type(decode(encode({"x": FakeMarker(1)}))["x"]) is int


def test_overflow_on_encode_not_construction():
    for value in (2**63, -(2**63) - 1, 2**100):
        assert Int64(value) == value
        with pytest.raises(OverflowError):
            encode({"x": Int64(value)})


@pytest.mark.skipif(
    ReferenceInt64 is None, reason="PyMongo reference not installed",
)
def test_pymongo_differential():
    for value in (-(2**63), -(2**31), -1, 0, 1, 2**31, 2**63 - 1):
        data = encode({"x": Int64(value)})
        assert data == reference_encode({"x": ReferenceInt64(value)})  # pyright: ignore[reportOptionalCall]
        assert (
            type(decode(data)["x"]).__name__
            == type(reference_decode(data)["x"]).__name__
        )
