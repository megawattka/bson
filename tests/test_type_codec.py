from decimal import Decimal
from typing import override

import pytest

from bson import (
    CodecOptions,
    TypeCodec,
    TypeRegistry,
    decode,
    decode_all,
    encode,
)
from bson.codec_options import TypeCodec as ModuleTypeCodec
from bson.errors import InvalidDocument


class DecimalCodec(TypeCodec):
    """Store decimals as strings and restore them when decoding."""

    @property
    def python_type(self) -> type[Decimal]:
        """Custom Python type handled by this codec."""
        return Decimal

    @property
    def bson_type(self) -> type[str]:
        """Python type produced by decoding the stored BSON value."""
        return str

    @override
    def transform_python(self, _value: object) -> str:
        """Convert a decimal to its lossless string representation.

        Returns:
            The decimal's string representation, preserving trailing zeros.
        """
        assert isinstance(_value, Decimal)
        return str(_value)

    @override
    def transform_bson(self, _value: object) -> Decimal:
        """Restore a decimal from a decoded string.

        Returns:
            The decimal represented by the stored string.
        """
        assert isinstance(_value, str)
        return Decimal(_value)


@pytest.mark.parametrize("value", ["0", "-12.3400", "1E+100"])
def test_type_codec_roundtrip(value: str):
    assert TypeCodec is ModuleTypeCodec
    codec = DecimalCodec()
    registry = TypeRegistry([codec])
    options = CodecOptions(type_registry=registry)
    decimal = Decimal(value)

    data = encode({"value": decimal}, codec_options=options)

    assert registry.codecs == [codec]
    assert data == encode({"value": value})
    assert decode(data) == {"value": value}
    restored = decode(data, codec_options=options)["value"]
    assert type(restored) is Decimal
    assert restored.as_tuple() == decimal.as_tuple()


def test_type_codec_nested_values_and_multiple_documents():
    options = CodecOptions(type_registry=TypeRegistry([DecimalCodec()]))
    document = {
        "nested": {"value": Decimal("12.3400")},
        "values": [Decimal("-5.6"), Decimal(0)],
        "unchanged": 42,
    }

    data = encode(document, codec_options=options)

    assert decode(data) == {
        "nested": {"value": "12.3400"},
        "values": ["-5.6", "0"],
        "unchanged": 42,
    }
    assert decode(data, codec_options=options) == document
    assert decode_all(data * 2, codec_options=options) == [document, document]


def test_type_codec_requires_registry():
    document = {"value": Decimal("1.25")}
    options = CodecOptions(type_registry=TypeRegistry([DecimalCodec()]))

    assert decode(encode(document, codec_options=options)) == {"value": "1.25"}
    with pytest.raises(InvalidDocument):
        encode(document)


def test_type_codec_registration_rejects_missing_transformations():
    with pytest.raises(TypeError, match="Expected an instance"):
        TypeRegistry([TypeCodec()])  # pyright: ignore[reportAbstractUsage]
