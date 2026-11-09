import json
from typing import Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError
import pytest

from bson import ObjectId

HEX = "0123456789abcdefABCDEF01"


@pytest.fixture
def adapter() -> TypeAdapter[ObjectId]:
    return TypeAdapter(ObjectId)


@pytest.mark.parametrize("value", [HEX, bytes.fromhex(HEX)])
def test_validate_python(adapter: TypeAdapter[ObjectId], value: str | bytes):
    result = adapter.validate_python(value)
    assert type(result) is ObjectId
    assert str(result) == HEX.lower()


def test_existing_instance(adapter: TypeAdapter[ObjectId]):
    value = ObjectId(HEX)
    assert adapter.validate_python(value) is value
    assert adapter.dump_python(value) is value
    assert adapter.dump_python(value, mode="json") == HEX.lower()
    assert adapter.dump_json(value) == json.dumps(HEX.lower()).encode()


def test_validate_json(adapter: TypeAdapter[ObjectId]):
    result = adapter.validate_json(json.dumps(HEX))
    assert type(result) is ObjectId
    assert result == ObjectId(HEX)
    assert adapter.validate_json(adapter.dump_json(result)) == result


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        1,
        1.5,
        [],
        {},
        "",
        "a" * 23,
        "a" * 25,
        "a" * 24 + "\n",
        "g" * 24,
        "é" * 24,
        " " * 24,
    ],
)
def test_invalid_values(adapter: TypeAdapter[ObjectId], value: object):
    with pytest.raises(ValidationError):
        adapter.validate_python(value)
    with pytest.raises(ValidationError):
        adapter.validate_json(json.dumps(value))


@pytest.mark.parametrize(
    "value",
    [
        b"",
        bytes(11),
        bytes(13),
        HEX.encode(),
        bytearray(12),
        memoryview(bytes(12)),
    ],
)
def test_invalid_binary(adapter: TypeAdapter[ObjectId], value: object):
    with pytest.raises(ValidationError):
        adapter.validate_python(value)


@pytest.mark.parametrize("mode", ["validation", "serialization"])
def test_json_schema(
    adapter: TypeAdapter[ObjectId],
    mode: Literal["validation", "serialization"],
):
    assert adapter.json_schema(mode=mode) == {
        "type": "string",
        "minLength": 24,
        "maxLength": 24,
        "pattern": "^[0-9a-fA-F]{24}$",
    }


def test_model():
    class Document(BaseModel):
        id: ObjectId
        optional: ObjectId | None = None
        generated: ObjectId = Field(default_factory=ObjectId)
        values: list[ObjectId] = Field(default_factory=list[ObjectId])

    document = Document.model_validate({"id": HEX, "values": [HEX]})
    assert isinstance(document.id, ObjectId)
    assert isinstance(document.generated, ObjectId)
    assert document.values == [document.id]
    assert document.model_dump()["id"] is document.id
    dumped = document.model_dump(mode="json")
    assert dumped["id"] == HEX.lower()
    assert dumped["values"] == [HEX.lower()]
    assert dumped["optional"] is None
    assert Document.model_validate_json(document.model_dump_json()) == document
    for mode in ("validation", "serialization"):
        schema = Document.model_json_schema(mode=mode)
        assert schema["properties"]["id"]["pattern"] == "^[0-9a-fA-F]{24}$"
    with pytest.raises(ValidationError):
        Document.model_validate({"id": None})
    with pytest.raises(ValidationError):
        Document.model_validate({})


def test_subclass():
    class CustomObjectId(ObjectId):
        pass

    adapter = TypeAdapter(CustomObjectId)
    result = adapter.validate_python(HEX)
    assert type(result) is CustomObjectId
    assert adapter.validate_python(result) is result
    assert type(adapter.validate_python(bytes.fromhex(HEX))) is CustomObjectId
    assert type(adapter.validate_json(json.dumps(HEX))) is CustomObjectId
    assert adapter.dump_json(result) == json.dumps(HEX.lower()).encode()
    assert adapter.json_schema()["type"] == "string"
