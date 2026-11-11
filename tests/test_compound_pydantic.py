import json
import re
from typing import Any, Literal, cast

from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic_core import PydanticSerializationError
import pytest

from elune import (
    Binary,
    Code,
    DatetimeMS,
    DBRef,
    Decimal128,
    Int64,
    MaxKey,
    MinKey,
    ObjectId,
    Regex,
    Timestamp,
)

CASES: list[tuple[type[Any], dict[str, Any], object]] = [
    (
        Binary,
        {"data": "AAEC/w==", "subtype": 128},
        Binary(b"\x00\x01\x02\xff", 128),
    ),
    (Timestamp, {"time": 2**32 - 1, "inc": 0}, Timestamp(2**32 - 1, 0)),
    (
        Regex,
        {"pattern": "(?server-only)", "flags": 10},
        Regex("(?server-only)", 10),
    ),
    (Regex, {"pattern": {"base64": "YWJj"}, "flags": -1}, Regex(b"abc", -1)),
    (
        Code,
        {"code": "return x\0", "scope": {"x": 1}},
        Code("return x\0", {"x": 1}),
    ),
    (Code, {"code": "", "scope": None}, Code("")),
    (Code, {"code": "", "scope": {}}, Code("", {})),
    (
        DBRef,
        {"$ref": "", "$id": None, "$db": "", "extra": [1]},
        DBRef("", None, "", extra=[1]),
    ),
    (MinKey, {"$minKey": 1}, MinKey()),
    (MaxKey, {"$maxKey": 1}, MaxKey()),
]


@pytest.mark.parametrize(("cls", "wire", "expected"), CASES)
def test_roundtrip(cls: type[Any], wire: Any, expected: Any):  # ruff: ignore[any-type] - heterogeneous BSON contract
    adapter = TypeAdapter(cls)
    for value in (
        adapter.validate_python(wire),
        adapter.validate_json(json.dumps(wire)),
    ):
        assert type(value) is cls
        assert value == expected
        assert adapter.validate_python(value) is value
        assert adapter.dump_python(value) is value
        assert adapter.dump_python(value, mode="json") == wire
        assert json.loads(adapter.dump_json(value)) == wire
        assert adapter.validate_json(adapter.dump_json(value)) == value


@pytest.mark.parametrize(
    ("cls", "wire", "output"),
    [
        (Binary, {"data": ""}, {"data": "", "subtype": 0}),
        (Regex, {"pattern": ""}, {"pattern": "", "flags": 0}),
        (Code, {"code": "x"}, {"code": "x", "scope": None}),
        (DBRef, {"$ref": "c", "$id": 1, "$db": None}, {"$ref": "c", "$id": 1}),
    ],
)
def test_defaults(cls: type[Any], wire: Any, output: Any):  # ruff: ignore[any-type] - heterogeneous BSON contract
    adapter = TypeAdapter(cls)
    assert (
        adapter.dump_python(adapter.validate_python(wire), mode="json")
        == output
    )


@pytest.mark.parametrize(
    ("cls", "wire"),
    [
        (Binary, {}),
        (Binary, {"data": "?"}),
        (Binary, {"data": "YQ"}),
        (Binary, {"data": "YQ==\n"}),
        (Binary, {"data": "", "subtype": True}),
        (Binary, {"data": "", "subtype": 256}),
        (Binary, {"data": "", "subtype": -1}),
        (Binary, {"data": "", "extra": 1}),
        (Timestamp, {"time": 0}),
        (Timestamp, {"time": -1, "inc": 0}),
        (Timestamp, {"time": 2**32, "inc": 0}),
        (Timestamp, {"time": 0, "inc": 2**32}),
        (Timestamp, {"time": True, "inc": 0}),
        (Timestamp, {"time": 0, "inc": 1.0}),
        (Timestamp, {"time": "1", "inc": 0}),
        (Timestamp, {"time": 1, "inc": 0, "extra": 1}),
        (Regex, {}),
        (Regex, {"pattern": "x\0"}),
        (Regex, {"pattern": {"base64": "AA=="}}),
        (Regex, {"pattern": {"base64": "/w=="}}),
        (Regex, {"pattern": {"base64": "?"}}),
        (Regex, {"pattern": "x", "flags": "im"}),
        (Regex, {"pattern": "x", "flags": True}),
        (Regex, {"pattern": "x", "flags": 2**63}),
        (Regex, {"pattern": "x", "extra": 1}),
        (Code, {}),
        (Code, {"code": 1}),
        (Code, {"code": "x", "scope": []}),
        (Code, {"code": "x", "scope": {"x\0": 1}}),
        (Code, {"code": "x", "extra": 1}),
        (DBRef, {"$ref": "c"}),
        (DBRef, {"$ref": 1, "$id": 0}),
        (DBRef, {"$ref": "c", "$id": 0, "$db": 1}),
        (DBRef, {"$ref": "c", "$id": 0, "x\0": 1}),
        (MinKey, {"$minKey": True}),
        (MinKey, {"$minKey": 1.0}),
        (MinKey, {"$minKey": 0}),
        (MinKey, {"$minKey": 1, "extra": 1}),
        (MaxKey, {"$maxKey": True}),
        (MaxKey, {"$maxKey": 1.0}),
        (MaxKey, {"$minKey": 1}),
    ],
)
def test_invalid_wire(cls: type[Any], wire: Any):  # ruff: ignore[any-type] - heterogeneous BSON contract
    adapter = TypeAdapter(cls)
    with pytest.raises(ValidationError):
        adapter.validate_python(wire)
    with pytest.raises(ValidationError):
        adapter.validate_json(json.dumps(wire))


@pytest.mark.parametrize(
    "cls",
    [Binary, Timestamp, Regex, Code, DBRef, MinKey, MaxKey],
)
@pytest.mark.parametrize("value", [None, True, 1, [], "not-an-object"])
def test_invalid_top_level(cls: type[Any], value: Any):  # ruff: ignore[any-type] - heterogeneous BSON contract
    adapter = TypeAdapter(cls)
    # Plain strings are an additional Python input for Code only.
    if cls is not Code or not isinstance(value, str):
        with pytest.raises(ValidationError):
            adapter.validate_python(value)
    with pytest.raises(ValidationError):
        adapter.validate_json(json.dumps(value))


@pytest.mark.parametrize(
    "value",
    [b"abc", bytearray(b"abc"), memoryview(b"abc")],
)
def test_binary_buffer(value: object):
    result = TypeAdapter(Binary).validate_python(value)
    assert type(result) is Binary
    assert bytes(result) == b"abc"
    assert result.subtype == 0


def test_native_regex_and_code():
    native = re.compile(rb"abc", re.IGNORECASE)
    result = TypeAdapter(Regex).validate_python(native)
    assert result.pattern == native.pattern
    assert result.flags == native.flags
    value = TypeAdapter(Code).validate_python("x")
    assert type(value) is Code
    assert value.scope is None


def test_mutated_instances():
    regex = Regex("x")
    regex.pattern = 123  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(ValidationError):
        TypeAdapter(Regex).validate_python(regex)
    for invalid in (True, -1, 256, "1"):
        binary = Binary(b"abc")
        binary._subtype = invalid  # pyright: ignore[reportAttributeAccessIssue]
        with pytest.raises(ValidationError):
            TypeAdapter(Binary).validate_python(binary)
    code = Code("x", {})
    assert code.scope is not None
    code.scope["x\0"] = 1
    with pytest.raises(ValidationError):
        TypeAdapter(Code).validate_python(code)
    for key in ("$ref", "$id", "$db"):
        with pytest.raises(ValidationError):
            TypeAdapter(DBRef).validate_python(
                DBRef("c", 1, _extra={key: "overwrite"}),
            )


def test_nested_bson_serialization():
    oid = ObjectId("507f1f77bcf86cd799439011")
    code = Code(
        "x",
        {
            "oid": oid,
            "binary": Binary(b"\xff", 128),
            "decimal": Decimal128("-sNaN"),
            "ms": DatetimeMS(2**63 - 1),
            "int": Int64(2**63 - 1),
            "array": [Timestamp(1, 2), Regex(b"abc", 10), MinKey(), MaxKey()],
            "ref": DBRef("c", oid, nested=Code("inner", {})),
        },
    )
    dumped = TypeAdapter(Code).dump_python(code, mode="json")
    assert dumped == {
        "code": "x",
        "scope": {
            "oid": str(oid),
            "binary": {"data": "/w==", "subtype": 128},
            "decimal": "-sNaN",
            "ms": 2**63 - 1,
            "int": 2**63 - 1,
            "array": [
                {"time": 1, "inc": 2},
                {"pattern": {"base64": "YWJj"}, "flags": 10},
                {"$minKey": 1},
                {"$maxKey": 1},
            ],
            "ref": {
                "$ref": "c",
                "$id": str(oid),
                "nested": {"code": "inner", "scope": {}},
            },
        },
    }
    assert json.loads(TypeAdapter(Code).dump_json(code)) == dumped
    ref = DBRef("c", code, metadata={"nested": Binary(b"a", 1)})
    assert TypeAdapter(DBRef).dump_python(ref, mode="json")["$id"] == dumped
    restored = TypeAdapter(DBRef).validate_json(
        TypeAdapter(DBRef).dump_json(ref),
    )
    identifier = restored.id
    assert isinstance(identifier, dict)
    assert cast("dict[str, Any]", identifier)["scope"]["oid"] == str(oid)


def test_cycles_and_unknown_values():
    scope: dict[str, Any] = {}
    code = Code("x", scope)
    scope["self"] = code
    with pytest.raises(PydanticSerializationError):
        TypeAdapter(Code).dump_json(code)
    with pytest.raises(PydanticSerializationError):
        TypeAdapter(Code).dump_json(Code("x", {"unknown": object()}))
    identifier: dict[str, Any] = {}
    ref = DBRef("c", identifier)
    identifier["ref"] = ref
    with pytest.raises(PydanticSerializationError):
        TypeAdapter(DBRef).dump_json(ref)
    shared = {"x": 1}
    assert TypeAdapter(Code).dump_python(
        Code("x", {"a": shared, "b": shared}),
        mode="json",
    )["scope"] == {"a": shared, "b": shared}


@pytest.mark.parametrize("mode", ["validation", "serialization"])
def test_schema_contract(mode: Literal["validation", "serialization"]):
    schemas = {
        cls: TypeAdapter(cls).json_schema(mode=mode)
        for cls in (Binary, Timestamp, Regex, Code, DBRef, MinKey, MaxKey)
    }
    for cls, schema in schemas.items():
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is (cls is DBRef)
    assert schemas[Binary]["required"] == ["data"]
    assert schemas[Binary]["properties"]["subtype"]["default"] == 0
    assert schemas[Timestamp]["required"] == ["time", "inc"]
    assert schemas[Timestamp]["properties"]["inc"]["maximum"] == 2**32 - 1
    assert schemas[Regex]["properties"]["flags"]["minimum"] == -(2**63)
    assert schemas[Code]["properties"]["scope"]["default"] is None
    assert schemas[DBRef]["required"] == ["$ref", "$id"]
    assert schemas[MinKey]["properties"]["$minKey"]["maximum"] == 1
    assert schemas[MaxKey]["properties"]["$maxKey"]["minimum"] == 1


def test_model():
    class Document(BaseModel):
        binary: Binary
        timestamp: Timestamp
        regex: Regex
        code: Code
        ref: DBRef
        minimum: MinKey
        maximum: MaxKey
        optional: Binary | None = None

    wire: dict[str, object] = {
        "binary": {"data": "YWJj", "subtype": 128},
        "timestamp": {"time": 1, "inc": 2},
        "regex": {"pattern": "x", "flags": 10},
        "code": {"code": "x", "scope": {}},
        "ref": {"$ref": "c", "$id": None},
        "minimum": {"$minKey": 1},
        "maximum": {"$maxKey": 1},
        "optional": None,
    }
    model = Document.model_validate(wire)
    assert model.model_dump()["binary"] is model.binary
    assert model.model_dump()["code"] is model.code
    assert model.model_dump(mode="json") == wire
    assert Document.model_validate_json(model.model_dump_json()) == model
    for mode in ("validation", "serialization"):
        assert (
            Document.model_json_schema(mode=mode)["properties"]["binary"][
                "type"
            ]
            == "object"
        )


def test_subclasses():
    class CustomBinary(Binary):
        pass

    class CustomCode(Code):
        pass

    class CustomRef(DBRef):
        pass

    cases: list[tuple[type[Any], dict[str, object]]] = [
        (CustomBinary, {"data": "YWJj"}),
        (CustomCode, {"code": "x", "scope": {}}),
        (CustomRef, {"$ref": "c", "$id": 1}),
    ]
    for cls, wire in cases:
        adapter = TypeAdapter(cls)
        value = adapter.validate_python(wire)
        assert type(value) is cls
        assert adapter.validate_python(value) is value
        assert type(adapter.validate_json(adapter.dump_json(value))) is cls


def test_unions():
    adapter = TypeAdapter(
        MinKey | MaxKey | Code | Binary | Timestamp | Regex | DBRef,
    )
    for _, wire, expected in CASES:
        value = cast(
            "MinKey | MaxKey | Code | Binary | Timestamp | Regex | DBRef",
            expected,
        )
        assert adapter.dump_python(value, mode="json") == wire
        assert json.loads(adapter.dump_json(value)) == wire
        restored = adapter.validate_json(adapter.dump_json(value))
        assert type(restored) is type(value)
        assert restored == value


def test_nested_cycle_and_nonstring_keys():
    scope: dict[str, object] = {}
    scope["self"] = scope
    with pytest.raises(PydanticSerializationError):
        TypeAdapter(Code).dump_json(Code("x", scope))
    invalid = DBRef("c", 1, _extra={1: "not a string"})  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValidationError):
        TypeAdapter(DBRef).validate_python(invalid)
    with pytest.raises(PydanticSerializationError):
        TypeAdapter(DBRef).dump_json(invalid)


def test_subclass_inputs_preserve_metadata():
    class CustomCode(Code):
        pass

    class CustomBinary(Binary):
        pass

    code = TypeAdapter(CustomCode).validate_python(Code("x", {"a": 1}))
    assert type(code) is CustomCode
    assert code.scope == {"a": 1}
    binary = TypeAdapter(CustomBinary).validate_python(Binary(b"abc", 128))
    assert type(binary) is CustomBinary
    assert binary.subtype == 128
