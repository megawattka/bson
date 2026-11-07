from uuid import UUID

import pytest

from bson import (
    DEFAULT_CODEC_OPTIONS,
    Binary,
    CodecOptions,
    decode,
    decode_all,
    encode,
)
from bson import UuidRepresentation as U
from bson.codec_options import CodecOptions as ModuleCodecOptions
from bson.errors import InvalidBSON

REPS = (
    U.UNSPECIFIED,
    U.STANDARD,
    U.PYTHON_LEGACY,
    U.JAVA_LEGACY,
    U.CSHARP_LEGACY,
)
UUID_VALUE = UUID("00112233-4455-6677-8899-aabbccddeeff")
PAYLOADS = {
    U.STANDARD: (4, "00112233445566778899aabbccddeeff"),
    U.PYTHON_LEGACY: (3, "00112233445566778899aabbccddeeff"),
    U.JAVA_LEGACY: (3, "7766554433221100ffeeddccbbaa9988"),
    U.CSHARP_LEGACY: (3, "33221100554477668899aabbccddeeff"),
}


def test_options_and_unspecified():
    assert CodecOptions is ModuleCodecOptions
    assert DEFAULT_CODEC_OPTIONS.uuid_representation == U.UNSPECIFIED
    for rep in REPS:
        assert CodecOptions(uuid_representation=rep).uuid_representation == rep
    opts = CodecOptions(U.STANDARD)
    assert opts.with_options().uuid_representation == U.STANDARD
    assert (
        opts.with_options(
            uuid_representation=U.JAVA_LEGACY,
        ).uuid_representation
        == U.JAVA_LEGACY
    )
    with pytest.raises(AttributeError):
        opts.uuid_representation = U.PYTHON_LEGACY  # pyright: ignore[reportAttributeAccessIssue]
    for rep in (-1, 1, 2, 7, 256):
        with pytest.raises(ValueError):  # ruff: ignore[pytest-raises-too-broad]
            CodecOptions(rep)
    for rep in ("standard", 4.0, None):
        with pytest.raises(TypeError):
            CodecOptions(rep)  # pyright: ignore[reportArgumentType]
    for fn, data in ((encode, {}), (decode, encode({})), (decode_all, b"")):  # pyright: ignore[reportUnknownVariableType]
        with pytest.raises(TypeError):
            fn(data, codec_options=object())  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValueError, match="UNSPECIFIED"):
        encode({"x": UUID_VALUE})
    with pytest.raises(ValueError):  # ruff: ignore[pytest-raises-too-broad]
        Binary.from_uuid(UUID_VALUE, U.UNSPECIFIED)


def test_golden_wire_bytes_and_roundtrip():
    for rep, (subtype, expected) in PAYLOADS.items():
        binary = Binary.from_uuid(UUID_VALUE, rep)
        assert binary.subtype == subtype
        assert bytes(binary).hex() == expected
        assert binary.as_uuid(rep) == UUID_VALUE
        opts = CodecOptions(rep)
        data = encode({"u": UUID_VALUE}, codec_options=opts)
        assert (
            data.hex()
            == "1d00000005750010000000" + f"{subtype:02x}" + expected + "00"
        )
        assert data == encode({"u": binary})
        assert decode(data, opts) == {"u": UUID_VALUE}  # pyright: ignore[reportCallIssue]
        assert decode_all(data * 2, opts) == [{"u": UUID_VALUE}] * 2  # pyright: ignore[reportCallIssue]


def test_invalid_uuid_and_binary_lengths():
    for value in (None, str(UUID_VALUE), UUID_VALUE.bytes, 123):
        with pytest.raises(TypeError):
            Binary.from_uuid(value)  # pyright: ignore[reportArgumentType]
    for rep in (-1, 1, 2, 7):
        with pytest.raises(ValueError):  # ruff: ignore[pytest-raises-too-broad]
            Binary.from_uuid(UUID_VALUE, rep)
    for subtype in (3, 4):
        for length in (0, 1, 15, 17, 32):
            binary = Binary(bytes(length), subtype)
            data = encode({"x": binary})
            assert decode(data)["x"] == binary
            for rep in REPS:
                opts = CodecOptions(rep)
                matching = (subtype == 4 and rep == 4) or (
                    subtype == 3 and rep in (3, 5, 6)  # ruff: ignore[literal-membership]
                )
                if matching:
                    with pytest.raises(InvalidBSON):
                        decode(data, opts)  # pyright: ignore[reportCallIssue]
                else:
                    assert decode(data, opts)["x"] == binary  # pyright: ignore[reportCallIssue]


def test_binary_equality_repr_and_subtypes():
    a, b, c = Binary(b"a", 3), Binary(b"a", 3), Binary(b"a", 4)
    assert isinstance(a, bytes)
    assert bytes(a) == b"a"
    assert a == b
    assert (a, c) != (a, b"a")
    assert hash(a) == hash(b"a") ^ hash(3)
    assert {a: 1}[b] == 1
    assert repr(a) == "Binary(b'a', 3)"
    assert repr(Binary(b"secret", 8)) == "<Binary(REDACTED, 8)>"
    with pytest.raises(AttributeError):
        a.subtype = 4  # pyright: ignore[reportAttributeAccessIssue]
    for subtype in range(256):
        val = Binary(b"payload", subtype)
        decoded = decode(encode({"x": val}))["x"]
        assert decoded == (b"payload" if subtype == 0 else val)
