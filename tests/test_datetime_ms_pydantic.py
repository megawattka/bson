import datetime as dt
import json
from typing import Literal

from pydantic import BaseModel, TypeAdapter, ValidationError
import pytest

from bson import CodecOptions, DatetimeConversion, DatetimeMS, decode, encode


@pytest.fixture
def adapter() -> TypeAdapter[DatetimeMS]:
    return TypeAdapter(DatetimeMS)


@pytest.mark.parametrize(
    "value",
    [-(2**63), -1, 0, 1, 1704067200000, 2**63 - 1],
)
def test_validation_and_serialization(
    adapter: TypeAdapter[DatetimeMS],
    value: int,
):
    result = adapter.validate_python(value)
    assert type(result) is DatetimeMS
    assert int(result) == value
    assert adapter.validate_python(result) is result
    assert adapter.dump_python(result) is result
    assert adapter.dump_python(result, mode="json") == value
    assert adapter.dump_json(result) == str(value).encode()
    assert adapter.validate_json(str(value)) == result
    assert adapter.validate_json(adapter.dump_json(result)) == result
    options = CodecOptions(datetime_conversion=DatetimeConversion.DATETIME_MS)
    assert decode(encode({"value": result}), codec_options=options) == {
        "value": result,
    }


@pytest.mark.parametrize(
    "value",
    [
        dt.datetime(1970, 1, 1),  # ruff: ignore[call-datetime-without-tzinfo] - naive UTC input
        dt.datetime(1969, 12, 31, 23, 59, 59, 999999, tzinfo=dt.UTC),
        dt.datetime(2024, 1, 1, microsecond=123456, tzinfo=dt.UTC),
        dt.datetime(
            2024,
            1,
            1,
            tzinfo=dt.timezone(dt.timedelta(hours=3)),
        ),
        dt.datetime.min,  # ruff: ignore[datetime-min-max] - boundary fixture
        dt.datetime.max,  # ruff: ignore[datetime-min-max] - boundary fixture
    ],
)
def test_datetime_input(adapter: TypeAdapter[DatetimeMS], value: dt.datetime):
    result = adapter.validate_python(value)
    assert type(result) is DatetimeMS
    assert result == DatetimeMS(value)
    assert adapter.dump_python(result, mode="json") == int(DatetimeMS(value))
    with pytest.raises(ValidationError):
        adapter.validate_json(json.dumps(value.isoformat()))


def test_datetime_overflow(adapter: TypeAdapter[DatetimeMS]):
    value = dt.datetime(
        1,
        1,
        1,
        tzinfo=dt.timezone(dt.timedelta(hours=1)),
    )
    with pytest.raises(ValidationError):
        adapter.validate_python(value)


@pytest.mark.parametrize(
    "value",
    [None, True, False, 1.0, 1.5, "1", "", [], {}, -(2**63) - 1, 2**63],
)
def test_invalid_values(adapter: TypeAdapter[DatetimeMS], value: object):
    with pytest.raises(ValidationError):
        adapter.validate_python(value)
    with pytest.raises(ValidationError):
        adapter.validate_json(json.dumps(value))


@pytest.mark.parametrize("value", [b"1", dt.date(2024, 1, 1)])
def test_invalid_python_values(
    adapter: TypeAdapter[DatetimeMS],
    value: object,
):
    with pytest.raises(ValidationError):
        adapter.validate_python(value)


@pytest.mark.parametrize("mode", ["validation", "serialization"])
def test_json_schema(
    adapter: TypeAdapter[DatetimeMS],
    mode: Literal["validation", "serialization"],
):
    assert adapter.json_schema(mode=mode) == {
        "type": "integer",
        "minimum": -(2**63),
        "maximum": 2**63 - 1,
    }


def test_model():
    class Document(BaseModel):
        value: DatetimeMS
        values: list[DatetimeMS]
        optional: DatetimeMS | None = None

    document = Document.model_validate({"value": 2**63 - 1, "values": [0, -1]})
    assert type(document.value) is DatetimeMS
    assert all(type(value) is DatetimeMS for value in document.values)
    assert document.model_dump()["value"] is document.value
    assert document.model_dump(mode="json") == {
        "value": 2**63 - 1,
        "values": [0, -1],
        "optional": None,
    }
    assert Document.model_validate_json(document.model_dump_json()) == document
    for mode in ("validation", "serialization"):
        schema = Document.model_json_schema(mode=mode)
        assert schema["properties"]["value"]["type"] == "integer"
    with pytest.raises(ValidationError):
        Document.model_validate({"value": None, "values": []})
