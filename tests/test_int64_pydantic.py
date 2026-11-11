import json
from typing import Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError
import pytest

from elune import Int64, decode, encode


@pytest.fixture
def adapter() -> TypeAdapter[Int64]:
    return TypeAdapter(Int64)


@pytest.mark.parametrize("value", [-(2**63), -1, 0, 1, 2**53 + 1, 2**63 - 1])
def test_validation_and_serialization(adapter: TypeAdapter[Int64], value: int):
    result = adapter.validate_python(value)
    assert type(result) is Int64
    assert result == value
    assert adapter.validate_python(result) is result
    assert adapter.dump_python(result) is result
    dumped = adapter.dump_python(result, mode="json")
    assert type(dumped) is int
    assert dumped == value
    assert adapter.dump_json(result) == str(value).encode()
    from_json = adapter.validate_json(str(value))
    assert type(from_json) is Int64
    assert from_json == value
    assert adapter.validate_json(adapter.dump_json(result)) == result
    assert type(decode(encode({"value": result}))["value"]) is Int64


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        1.0,
        1.5,
        "1",
        "",
        [],
        {},
        -(2**63) - 1,
        2**63,
        2**100,
    ],
)
def test_invalid_values(adapter: TypeAdapter[Int64], value: object):
    with pytest.raises(ValidationError):
        adapter.validate_python(value)
    with pytest.raises(ValidationError):
        adapter.validate_json(json.dumps(value))


@pytest.mark.parametrize("value", [-(2**63) - 1, 2**63, 2**100])
def test_invalid_existing_instance(adapter: TypeAdapter[Int64], value: int):
    with pytest.raises(ValidationError):
        adapter.validate_python(Int64(value))


@pytest.mark.parametrize("value", [b"1", bytearray(b"1"), memoryview(b"1")])
def test_invalid_binary(adapter: TypeAdapter[Int64], value: object):
    with pytest.raises(ValidationError):
        adapter.validate_python(value)


@pytest.mark.parametrize("mode", ["validation", "serialization"])
def test_json_schema(
    adapter: TypeAdapter[Int64],
    mode: Literal["validation", "serialization"],
):
    assert adapter.json_schema(mode=mode) == {
        "type": "integer",
        "minimum": -(2**63),
        "maximum": 2**63 - 1,
    }


def test_model():
    class Document(BaseModel):
        value: Int64
        optional: Int64 | None = None
        values: list[Int64] = Field(default_factory=list[Int64])

    document = Document.model_validate(
        {"value": 2**63 - 1, "values": [-(2**63), 0]},
    )
    assert type(document.value) is Int64
    assert all(type(value) is Int64 for value in document.values)
    assert document.model_dump()["value"] is document.value
    assert document.model_dump(mode="json") == {
        "value": 2**63 - 1,
        "optional": None,
        "values": [-(2**63), 0],
    }
    assert Document.model_validate_json(document.model_dump_json()) == document
    for mode in ("validation", "serialization"):
        schema = Document.model_json_schema(mode=mode)
        assert schema["properties"]["value"]["type"] == "integer"
        assert schema["properties"]["value"]["maximum"] == 2**63 - 1
    with pytest.raises(ValidationError):
        Document.model_validate({"value": None})
    with pytest.raises(ValidationError):
        Document.model_validate({})


def test_subclass():
    class CustomInt64(Int64):
        pass

    adapter = TypeAdapter(CustomInt64)
    value = adapter.validate_python(42)
    assert type(value) is CustomInt64
    assert adapter.validate_python(value) is value
    assert type(adapter.validate_python(Int64(42))) is CustomInt64
    assert type(adapter.validate_json("42")) is CustomInt64
    assert adapter.dump_json(value) == b"42"
    with pytest.raises(ValidationError):
        adapter.validate_python(CustomInt64(2**63))
