"""BSON wire format, validation, and differential encoder tests."""

from collections import UserDict
import random
import struct
from typing import Any, Never, cast

import pytest

from bson import ObjectId, encode
from bson.errors import BSONError, InvalidDocument

try:
    import _p_bson as reference
except ImportError:
    reference = None


def test_empty_and_scalar_wire_format() -> None:
    assert encode({}) == b"\x05\0\0\0\0"
    cases: list[tuple[Any, int, bytes]] = [
        (None, 10, b""),
        (True, 8, b"\1"),
        (False, 8, b"\0"),
        (42, 16, struct.pack("<i", 42)),
        (2**31, 18, struct.pack("<q", 2**31)),
        (1.5, 1, struct.pack("<d", 1.5)),
        ("a\0?", 2, struct.pack("<i", 4) + b"a\0?\0"),
        (b"a\0", 5, struct.pack("<i", 2) + b"\0" + b"a\0"),
        (ObjectId(bytes(range(12))), 7, bytes(range(12))),
    ]
    for value, tag, payload in cases:
        body = bytes([tag]) + b"x\0" + payload + b"\0"
        assert encode({"x": value}) == struct.pack("<i", len(body) + 4) + body


def test_integer_encoding_and_overflow() -> None:
    for value in (
        -(2**63),
        -(2**31) - 1,
        -(2**31),
        -1,
        0,
        2**31 - 1,
        2**31,
        2**63 - 1,
    ):
        assert encode({"x": value})[4] == (
            16 if -(2**31) <= value < 2**31 else 18
        )
    for value in (-(2**63) - 1, 2**63, 2**1000):
        with pytest.raises(OverflowError):
            encode({"x": value})


def test_key_validation() -> None:
    invalid_keys: tuple[dict[Any, Any], ...] = (
        {1: 1},
        {None: 1},
        {"x": {1: 1}},
        {"x": [{1: 1}]},
    )
    for doc in invalid_keys:
        with pytest.raises(InvalidDocument):
            encode(doc)
    for doc in ({"a\0b": 1}, {"x": {"\0": 1}}):
        with pytest.raises(InvalidDocument):
            encode(doc, check_keys=False)
        with pytest.raises(InvalidDocument):
            encode(doc, check_keys=True)
    for doc in ({"$a": 1}, {"a.b": 1}, {"x": [{"a.b": 1}]}):
        encode(doc)
        with pytest.raises(InvalidDocument):
            encode(doc, check_keys=True)
    encode({"": 1, "a$b": 2, "???": "ok"}, check_keys=True)
    assert issubclass(InvalidDocument, BSONError)


def test_strict_unicode_and_invalid_types() -> None:
    for doc in ({"\ud800": 1}, {"x": "\udfff"}):
        with pytest.raises(UnicodeEncodeError):
            encode(doc)
    invalid_documents: tuple[object, ...] = (
        None,
        [],
        (),
        UserDict({"x": 1}),
        "x",
    )
    for invalid in invalid_documents:
        with pytest.raises(TypeError):
            encode(invalid)  # pyright: ignore[reportArgumentType]
    for value in (object(), bytearray(12), memoryview(b"x"), {1, 2}):
        with pytest.raises(InvalidDocument):
            encode({"x": value})


def test_arrays_cycles_and_shared_containers() -> None:
    assert encode({"x": [1, 2]}) == encode({"x": (1, 2)})
    assert encode({"x": []}) == bytes.fromhex("0d000000047800050000000000")
    assert encode({"x": {}})[4] == 3
    assert encode({"x": []})[4] == 4
    data = encode({"x": list(range(110))})
    assert b"\x1010\0" + struct.pack("<i", 10) in data
    assert b"\x10100\0" + struct.pack("<i", 100) in data
    root: dict[str, Any] = {}
    root["x"] = root
    cyclic: list[Any] = []
    cyclic.append(cyclic)
    mixed: dict[str, Any] = {"x": []}
    mixed["x"].append(mixed)
    for doc in (root, {"x": cyclic}, mixed):
        with pytest.raises(InvalidDocument):
            encode(doc)
    shared = {"x": [1, 2]}
    assert encode({"a": shared, "b": shared}) == encode(
        {"a": {"x": [1, 2]}, "b": {"x": [1, 2]}},
    )


def test_depth_limit_and_root_id() -> None:
    doc: dict[str, Any] = {}
    for _ in range(99):
        doc = {"x": doc}
    encode(doc)
    with pytest.raises(RecursionError):
        encode({"x": doc})
    doc = {"a": 1, "_id": None, "b": {"a": 2, "_id": 3}}
    original = repr(doc)
    wire = encode(doc)
    assert wire[4:9] == b"\x0a_id\0"
    assert repr(doc) == original


def test_builtin_subclasses() -> None:
    class Integer(int):
        pass

    class Text(str):  # ruff: ignore[no-slots-in-str-subclass, subclass-builtin] - test builtin subclass
        pass

    class Document(dict[str, Any]):  # ruff: ignore[subclass-builtin] - test builtin subclass
        def items(self) -> Never:  # ruff: ignore[no-self-use] - override test
            message = "items() must not be called"
            raise AssertionError(message)

    assert encode(Document({Text("x"): Integer(42)})) == encode({"x": 42})


@pytest.mark.skipif(
    reference is None,
    reason="PyMongo reference not installed",
)
def test_seeded_differential_documents() -> None:  # ruff: ignore[complex-structure] - recursive generator
    assert reference is not None
    rng = random.Random(2026)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - reproducible test data
    scalars: list[Any] = [
        None,
        True,
        False,
        0,
        1,
        -(2**31) - 1,
        2**31,
        -(2**63),
        2**63 - 1,
        "",
        "?\0??",
        b"",
        b"\0\xff",
        ObjectId(bytes(12)),
    ]

    def convert(value: Any) -> Any:  # ruff: ignore[any-type] - heterogeneous BSON
        assert reference is not None
        if isinstance(value, ObjectId):
            return reference.ObjectId(value.binary)
        if isinstance(value, dict):
            mapping = cast("dict[str, Any]", value)
            return {key: convert(item) for key, item in mapping.items()}
        if isinstance(value, (tuple, list)):
            return [
                convert(item)
                for item in cast("list[Any] | tuple[Any, ...]", value)
            ]
        return value

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

    for _ in range(200):
        doc = {f"key{i}": value(0) for i in range(rng.randrange(8))}
        assert encode(doc) == reference.encode(convert(doc))
