"""Regression tests for the thin package wrapper and native implementation."""

import importlib
import importlib.machinery
from pathlib import Path
import types
from typing import Any
from unittest.mock import patch
from uuid import UUID

import pytest

import bson


def test_no_custom_pickle_hooks():
    for cls in (
        bson.Binary,
        bson.Int64,
        bson.Code,
        bson.DatetimeMS,
        bson.Decimal128,
        bson.MinKey,
        bson.MaxKey,
        bson.Regex,
        bson.Timestamp,
        bson.ObjectId,
    ):
        for name in (
            "__reduce__",
            "__reduce_ex__",
            "__getnewargs__",
            "__getnewargs_ex__",
            "__getstate__",
            "__setstate__",
        ):
            assert name not in vars(cls), (cls.__name__, name)


def test_native_module_and_thin_wrapper():
    assert bson.__name__ == "bson"
    assert bson.__spec__.name == "bson"
    native = importlib.import_module("bson._bson")
    assert native.__name__ == "bson._bson"
    assert bson.encode == native.encode
    assert native.__file__ is not None
    assert any(
        native.__file__.endswith(suffix)
        for suffix in importlib.machinery.EXTENSION_SUFFIXES
    )
    package = Path(__file__).resolve().parents[1] / "bson"
    assert {path.name for path in package.glob("*.py")} == {
        "__init__.py",
        "binary.py",
        "code.py",
        "codec_options.py",
        "datetime_ms.py",
        "decimal128.py",
        "errors.py",
        "int64.py",
        "max_key.py",
        "min_key.py",
        "objectid.py",
        "regex.py",
        "timestamp.py",
        "dbref.py",
    }
    assert list(package.glob("*.pyi")) == []


def test_submodule_exports():
    for name, exports in {
        "binary": (
            "Binary",
            "UuidRepresentation",
            "BINARY_SUBTYPE",
            "UUID_SUBTYPE",
        ),
        "int64": ("Int64",),
        "objectid": ("ObjectId",),
        "dbref": ("DBRef",),
        "codec_options": ("CodecOptions", "DEFAULT_CODEC_OPTIONS"),
        "errors": ("BSONError", "InvalidBSON", "InvalidDocument", "InvalidId"),
    }.items():
        module = importlib.import_module(f"bson.{name}")
        assert getattr(bson, name) == module
        for export in exports:
            assert getattr(module, export) == getattr(bson, export)


def test_public_exports():
    native = importlib.import_module("bson._bson")
    assert bson.__all__ == native.__all__  # pyright: ignore[reportUnknownMemberType]
    assert len(bson.__all__) == len(set(bson.__all__))  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
    assert set(bson.__all__) == {  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
        "BINARY_SUBTYPE",
        "UUID_SUBTYPE",
        "DEFAULT_CODEC_OPTIONS",
        "BSONError",
        "InvalidBSON",
        "InvalidDocument",
        "InvalidId",
        "Binary",
        "Code",
        "CodecOptions",
        "DatetimeConversion",
        "DatetimeMS",
        "DBRef",
        "Decimal128",
        "Int64",
        "MaxKey",
        "MinKey",
        "ObjectId",
        "Regex",
        "Timestamp",
        "UuidRepresentation",
        "create_decimal128_context",
        "decode",
        "decode_all",
        "encode",
    }
    namespace: dict[str, Any] = {}
    exec("from bson import *", namespace)  # ruff: ignore[exec-builtin]
    assert set(namespace) - {"__builtins__"} == set(bson.__all__)  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
    for name in bson.__all__:  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
        assert namespace[name] == getattr(native, name)  # pyright: ignore[reportUnknownArgumentType]


def test_no_duplicate_constants():
    for module in (bson, bson.binary):
        for name in (
            "OLD_BINARY_SUBTYPE",
            "OLD_UUID_SUBTYPE",
            "UNSPECIFIED",
            "STANDARD",
            "PYTHON_LEGACY",
            "JAVA_LEGACY",
            "CSHARP_LEGACY",
        ):
            assert not hasattr(module, name)
    assert bson.UuidRepresentation.STANDARD == 4
    assert bson.BINARY_SUBTYPE == 0
    assert bson.UUID_SUBTYPE == 4


def test_no_unused_native_protocol():
    native = importlib.import_module("bson._bson")
    for cls in (bson.Int64, bson.Binary):
        assert not hasattr(cls, "_type_marker")
    for name in ("_uuid_to_binary", "_binary_as_uuid", "__path__"):
        assert not hasattr(native, name)


def test_codec_uses_registered_types():
    integer, binary = bson.Int64, bson.Binary
    expected = {"i": integer(1), "b": binary(b"abc", 128)}
    wire = bson.encode(expected)
    with (
        patch.object(bson.int64, "Int64", int),
        patch.object(bson.binary, "Binary", bytes),
    ):
        assert bson.encode(expected) == wire
        result = bson.decode(wire)
        assert type(result["i"]) == integer  # ruff: ignore[type-comparison]
        assert type(result["b"]) == binary  # ruff: ignore[type-comparison]
        assert result == expected


def test_builtin_subclasses_share_wire_handlers():
    class Integer(int):
        pass

    class Text(str):  # ruff: ignore[no-slots-in-str-subclass, subclass-builtin]
        pass

    class Data(bytes):
        pass

    class Document(dict[str, Any]):  # ruff: ignore[subclass-builtin]
        pass

    class Array(list[Any]):  # ruff: ignore[subclass-builtin]
        pass

    class Tuple(tuple[Any]):  # ruff: ignore[no-slots-in-tuple-subclass]
        pass

    class Float(float):
        pass

    actual = {
        "i": Integer(42),
        "s": Text("hello"),
        "b": Data(b"abc"),
        "d": Document(x=1),
        "a": Array([1, 2]),
        "t": Tuple((3, 4)),
        "f": Float(1.5),
    }
    expected = {
        "i": 42,
        "s": "hello",
        "b": b"abc",
        "d": {"x": 1},
        "a": [1, 2],
        "t": (3, 4),
        "f": 1.5,
    }
    assert bson.encode(actual) == bson.encode(expected)


def test_decoder_binary_factory_skips_public_argument_parser():
    wire = bson.encode({"b": bson.Binary(b"abc", 128)})
    with patch.object(
        bson.Binary,
        "__new__",
        side_effect=AssertionError("public constructor called"),
    ):
        result = bson.decode(wire)["b"]
    assert type(result) == bson.Binary  # ruff: ignore[type-comparison]
    assert bytes(result) == b"abc"
    assert result.subtype == 128


def test_methods_are_not_python_functions():
    assert isinstance(bson.Binary.__eq__, types.MethodDescriptorType)
    assert isinstance(bson.Binary.as_uuid, types.MethodDescriptorType)
    assert isinstance(bson.Binary.from_uuid, types.BuiltinMethodType)
    assert not hasattr(bson.Binary.__new__, "__code__")
    assert not hasattr(bson.Binary.__eq__, "__code__")


def test_native_method_argument_validation():
    value = bson.Binary(b"a", 4)
    for call in (
        value.__eq__,
        lambda: value.__hash__(1),  # ruff: ignore[unnecessary-dunder-call] # pyright: ignore[reportCallIssue, reportUnknownLambdaType]
        lambda: value.as_uuid(unknown=4),  # pyright: ignore[reportCallIssue, reportUnknownLambdaType]
        lambda: value.as_uuid(4, uuid_representation=4),  # pyright: ignore[reportCallIssue, reportUnknownLambdaType]
        lambda: bson.Binary.from_uuid(UUID(int=0), uuid=UUID(int=1)),  # pyright: ignore[reportCallIssue, reportUnknownLambdaType]
        lambda: bson.Binary.__eq__(b"a", value),  # ruff: ignore[unnecessary-dunder-call] # pyright: ignore[reportArgumentType]
    ):
        with pytest.raises(TypeError):
            call()  # pyright: ignore[reportCallIssue]


def test_binary_subclass_native_methods():
    class CustomBinary(bson.Binary):
        pass

    value = CustomBinary.from_uuid(UUID(int=42))
    assert type(value) == CustomBinary  # ruff: ignore[type-comparison]
    assert value.as_uuid() == UUID(int=42)
    assert value == bson.Binary.from_uuid(UUID(int=42))


def test_keyword_construction_and_buffer():
    value = bson.Binary(data=memoryview(b"abc"), subtype=128)
    assert memoryview(value).tobytes() == b"abc"
    assert value.subtype == 128
    uuid = UUID(int=42)
    assert bson.Binary.from_uuid(uuid=uuid).as_uuid() == uuid
    with pytest.raises(TypeError):
        bson.Binary(b"a", data=b"b")  # pyright: ignore[reportCallIssue]
