from decimal import Decimal, Inexact
import json
from typing import Literal

from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic_core import PydanticSerializationError
import pytest

from bson import Decimal128, decode, encode


@pytest.fixture
def adapter() -> TypeAdapter[Decimal128]:
    return TypeAdapter(Decimal128)


@pytest.mark.parametrize(
    "text",
    [
        "0",
        "-0",
        "123.4500",
        "1E-6176",
        "9.999999999999999999999999999999999E6144",
        "Infinity",
        "-Infinity",
        "NaN",
        "-NaN",
        "sNaN",
        "-sNaN",
    ],
)
def test_validation_and_serialization(
    adapter: TypeAdapter[Decimal128],
    text: str,
):
    expected = Decimal128(text)
    for result in (
        adapter.validate_python(text),
        adapter.validate_python(Decimal(text)),
        adapter.validate_json(json.dumps(text)),
    ):
        assert type(result) is Decimal128
        assert result.bid == expected.bid
        assert adapter.validate_python(result) is result
        assert adapter.dump_python(result) is result
        serialized = str(expected.to_decimal())
        assert adapter.dump_python(result, mode="json") == serialized
        assert adapter.dump_json(result) == json.dumps(serialized).encode()
        assert (
            adapter.validate_json(adapter.dump_json(result)).bid == result.bid
        )
        assert decode(encode({"value": result}))["value"] == result


@pytest.mark.parametrize(
    "text",
    [
        "",
        "abc",
        "1E6145",
        "1E-6177",
        "12345678901234567890123456789012345",
        "NaN123",
        "sNaN123",
    ],
)
def test_invalid_decimal_text(adapter: TypeAdapter[Decimal128], text: str):
    with pytest.raises(ValidationError):
        adapter.validate_python(text)
    with pytest.raises(ValidationError):
        adapter.validate_json(json.dumps(text))


@pytest.mark.parametrize(
    "text",
    ["1E6145", "1E-6177", "NaN123", "12345678901234567890123456789012345"],
)
def test_invalid_decimal_instance(adapter: TypeAdapter[Decimal128], text: str):
    with pytest.raises(ValidationError):
        adapter.validate_python(Decimal(text))


@pytest.mark.parametrize("value", [None, True, False, 1, 1.5, [], {}, [0, 0]])
def test_invalid_values(adapter: TypeAdapter[Decimal128], value: object):
    with pytest.raises(ValidationError):
        adapter.validate_python(value)
    with pytest.raises(ValidationError):
        adapter.validate_json(json.dumps(value))


@pytest.mark.parametrize("value", [b"1.25", bytes(16), (0, 0)])
def test_no_raw_bid_input(adapter: TypeAdapter[Decimal128], value: object):
    with pytest.raises(ValidationError):
        adapter.validate_python(value)


def test_existing_bid_instance(adapter: TypeAdapter[Decimal128]):
    value = Decimal128.from_bid(Decimal128("123.4500").bid)
    assert adapter.validate_python(value) is value
    assert adapter.dump_json(value) == b'"123.4500"'


def test_noncanonical_bid_serialization(adapter: TypeAdapter[Decimal128]):
    value = Decimal128((0x3041FFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF))
    assert adapter.validate_python(value) is value
    assert adapter.dump_python(value) is value
    with pytest.raises(Inexact):
        value.to_decimal()
    with pytest.raises(PydanticSerializationError):
        adapter.dump_json(value)


@pytest.mark.parametrize("mode", ["validation", "serialization"])
def test_json_schema(
    adapter: TypeAdapter[Decimal128],
    mode: Literal["validation", "serialization"],
):
    assert adapter.json_schema(mode=mode) == {"type": "string"}


def test_model():
    class Document(BaseModel):
        value: Decimal128
        values: list[Decimal128]
        optional: Decimal128 | None = None

    document = Document.model_validate(
        {"value": Decimal("123.4500"), "values": ["-NaN", "sNaN"]},
    )
    assert type(document.value) is Decimal128
    assert all(type(value) is Decimal128 for value in document.values)
    assert document.model_dump()["value"] is document.value
    assert document.model_dump(mode="json") == {
        "value": "123.4500",
        "values": ["-NaN", "sNaN"],
        "optional": None,
    }
    assert Document.model_validate_json(document.model_dump_json()) == document
    for mode in ("validation", "serialization"):
        schema = Document.model_json_schema(mode=mode)
        assert schema["properties"]["value"]["type"] == "string"
    with pytest.raises(ValidationError):
        Document.model_validate({"value": None, "values": []})
