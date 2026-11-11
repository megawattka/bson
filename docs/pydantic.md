# Pydantic integration

Elune's BSON types integrate directly with **Pydantic v2**: use them as field
annotations in `BaseModel` or with `TypeAdapter`. No custom validators,
`arbitrary_types_allowed`, or `json_encoders` configuration is needed.
Pydantic v1 is not supported by this integration.

This guide describes the integration in the 0.4.0 source tree. Pydantic is
optional: importing and using Elune alone does not require it. The integration
is tested with Pydantic 2.14.3; earlier v2 releases are not verified here.

## Installation

Install Elune as described in the
[README](../README.md#installation), then install Pydantic separately:

```sh
python -m pip install "pydantic>=2.14.3,<3"
```

Elune and PyMongo use separate import namespaces and can coexist in the same
environment. For a source checkout, follow the README's
[build instructions](../README.md#building-and-testing).

## Model validation and BSON round trips

```python
from pydantic import BaseModel, Field

from elune import Decimal128, Int64, ObjectId, decode, encode


class Product(BaseModel):
    id: ObjectId = Field(alias="_id", default_factory=ObjectId)
    name: str
    price: Decimal128
    stock: Int64
    related: list[ObjectId] = Field(default_factory=list)
    parent: ObjectId | None = None


product = Product.model_validate(
    {
        "_id": "507F1F77BCF86CD799439011",
        "name": "Notebook",
        "price": "19.95",
        "stock": 42,
        "related": ["507f191e810c19729de860ea"],
    }
)
assert isinstance(product.id, ObjectId)
assert isinstance(product.price, Decimal128)
assert isinstance(product.stock, Int64)

# Python mode retains BSON instances for the BSON encoder.
document = product.model_dump(by_alias=True)
assert document["_id"] is product.id
data = encode(document)
assert Product.model_validate(decode(data)) == product

# JSON mode produces JSON-compatible values instead.
json_document = product.model_dump(mode="json", by_alias=True)
assert json_document["_id"] == "507f1f77bcf86cd799439011"
assert json_document["price"] == "19.95"
assert json_document["stock"] == 42
json_text = product.model_dump_json(by_alias=True)
assert Product.model_validate_json(json_text) == product
```

Use a public field such as `id` with `Field(alias="_id")`: Pydantic treats
leading-underscore attributes as private, not model fields. Pass
`by_alias=True` when exporting MongoDB-style document keys. A default factory
generates an ID when the input omits `_id`. Nullable fields still need a
default such as `= None` if omission should be allowed.

Pass `model_dump()` (Python mode), **not** `model_dump(mode="json")` or
`model_dump_json()`, to `encode`. JSON mode turns BSON values into strings,
numbers, and objects, losing BSON type information. `encode` accepts a
dictionary, not a Pydantic model or JSON text.

## Accepted values and JSON formats

All types below accept valid existing instances in Python mode and retain
them in Python-mode dumps. The JSON representation is also accepted as
Python input. Additional Python-only inputs are listed separately.

| Annotation | JSON input/output | Additional Python input |
| --- | --- | --- |
| `ObjectId` | 24 hexadecimal characters, e.g. `"507f1f77bcf86cd799439011"`; output is lowercase | Exactly 12 raw `bytes` |
| `Int64` | Integer from `-2**63` through `2**63 - 1` | No additional form |
| `DatetimeMS` | Integer milliseconds since the Unix epoch, in the signed 64-bit range | `datetime.datetime`; naive values are interpreted as UTC, sub-millisecond precision is discarded |
| `Decimal128` | Decimal string, e.g. `"123.4500"` | `decimal.Decimal` |
| `Binary` | `{"data": "YWJj", "subtype": 128}` | `bytes`, `bytearray`, or another buffer; subtype defaults to `0` |
| `Timestamp` | `{"time": 1, "inc": 2}` | No additional form |
| `Regex` | `{"pattern": "^abc", "flags": 10}`; a byte pattern uses `{"pattern": {"base64": "YWJj"}, "flags": 0}` | Compiled `re.Pattern` |
| `Code` | `{"code": "return x", "scope": {"x": 1}}` | Plain `str`, with no scope |
| `DBRef` | `{"$ref": "products", "$id": "item-1", "$db": "shop"}` | No additional form |
| `MinKey` | `{"$minKey": 1}` | No additional form |
| `MaxKey` | `{"$maxKey": 1}` | No additional form |

These are this project's Pydantic JSON contracts, **not MongoDB Extended
JSON**. For example, `ObjectId` uses a string, not `{"$oid": "..."}`, and
`Decimal128` uses a string, not `{"$numberDecimal": "..."}`.

Validation rules:

- Integer fields reject booleans, floats, and numeric strings rather than
  coercing them. Large `Int64` and `DatetimeMS` JSON numbers may lose precision
  in JavaScript clients outside the safe integer range.
- `Decimal128` accepts only values exactly representable as Decimal128.
  Overflow, inexact conversion, and invalid decimal strings produce
  `ValidationError`. Special strings such as `"Infinity"`, `"NaN"`, and
  `"sNaN"` are supported. Raw BID bytes or word pairs are not Pydantic inputs;
  construct a `Decimal128` instance explicitly if needed.
- `Binary.data` is strict standard Base64 with padding where required and no
  whitespace. `subtype` is optional on input (default `0`), is always included
  in output, and must be an integer from `0` to `255`.
- `Timestamp.time` and `Timestamp.inc` are both required unsigned 32-bit
  integers (`0` through `2**32 - 1`).
- `Regex.flags` is a signed 64-bit integer, defaults to `0`, and is always
  emitted. Patterns must be NUL-free; byte patterns must also be valid UTF-8.
  Patterns are stored, not compiled or checked against Python's regex syntax.
- `Code.scope` defaults to `None` and is always emitted. `None` and `{}` remain
  distinct. Scope dictionary keys must be strings without NUL characters.
- `DBRef` requires `$ref` and `$id`; `$id` may be `None`. `$db` is optional and
  is omitted from output when `None`. Extra fields are preserved; dictionary
  keys must be strings without NUL characters.
- Other compound representations reject extra fields. `MinKey` and `MaxKey`
  require their respective marker with the integer value `1`.
- JSON input for `DatetimeMS` must be an integer, not an ISO datetime string.

These rules describe Pydantic validation, not every input accepted by the
types' direct constructors. Invalid input raises `pydantic.ValidationError`.

## TypeAdapter and JSON Schema

Use `TypeAdapter` when validation is needed without a model:

```python
from pydantic import TypeAdapter, ValidationError

from elune import Binary, ObjectId

ids = TypeAdapter(list[ObjectId])
values = ids.validate_json('["507f1f77bcf86cd799439011"]')
assert isinstance(values[0], ObjectId)
assert ids.dump_json(values) == b'["507f1f77bcf86cd799439011"]'

binary = TypeAdapter(Binary)
payload = binary.validate_python(b"abc")
assert binary.dump_python(payload) is payload
assert binary.dump_python(payload, mode="json") == {
    "data": "YWJj",
    "subtype": 0,
}

try:
    TypeAdapter(ObjectId).validate_python("not-an-object-id")
except ValidationError as error:
    assert error.error_count() > 0
else:
    raise AssertionError("Invalid ObjectId was accepted")

schema = TypeAdapter(ObjectId).json_schema()
assert schema["type"] == "string"
assert schema["pattern"] == "^[0-9a-fA-F]{24}$"
assert binary.json_schema()["properties"]["subtype"]["maximum"] == 255
```

Both `Model.model_json_schema(mode="validation")` and
`Model.model_json_schema(mode="serialization")` are supported, as are the
corresponding `TypeAdapter.json_schema()` modes. Schemas describe JSON
representations, not Python-only inputs such as buffers or `Decimal`.
Runtime validation additionally enforces semantic constraints such as decimal
representability and decoded regex byte validity.

## Datetime decoding and nested values

To retain `DatetimeMS` when decoding BSON, select `DATETIME_MS` explicitly;
the default decoder returns Python `datetime` values for in-range dates:

```python
from pydantic import BaseModel

from elune import CodecOptions, DatetimeConversion, DatetimeMS, decode, encode


class Event(BaseModel):
    occurred_at: DatetimeMS


event = Event(occurred_at=2**63 - 1)
options = CodecOptions(datetime_conversion=DatetimeConversion.DATETIME_MS)
data = encode(event.model_dump())
document = decode(data, codec_options=options)
assert isinstance(document["occurred_at"], DatetimeMS)
assert Event.model_validate(document) == event
```

In JSON mode, BSON values nested inside `Code.scope`, `DBRef.id`, and DBRef
extra fields are recursively converted to the formats above. Those nested
values are untyped: JSON validation does **not** automatically turn their
strings and dictionaries back into BSON instances. For example, an `ObjectId`
in `DBRef.id` becomes a plain string after a JSON round trip. Use explicitly
typed model fields or application validation when reconstruction is required.

Cyclic values, excessive nesting, and unsupported nested objects can fail
JSON serialization with `pydantic_core.PydanticSerializationError`. Pydantic
validation of a model is not a guarantee that every value in an untyped
container is BSON-encodable; `encode` still performs its own validation.