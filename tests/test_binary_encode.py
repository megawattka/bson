import struct

import pytest

import bson


def test_sizes_subtypes_and_keys():
    class CustomBytes(bytes):
        pass

    class CustomBinary(bson.Binary):
        pass

    for size in (0, 255, 4095, 4096, 4097, 65536, 1048576):
        payload = (bytes(range(256)) * ((size + 255) // 256))[:size]
        for key in (
            "",
            "payload",
            "привет мир! 🦀",
            "_id",
        ):
            for cls, subtype in (
                (bytes, 0),
                (CustomBytes, 0),
                (bson.Binary, 0),
                (bson.Binary, 2),
                (bson.Binary, 128),
                (CustomBinary, 255),
            ):
                value = (
                    cls(payload, subtype)
                    if issubclass(cls, bson.Binary)
                    else cls(payload)
                )
                inner = (
                    struct.pack("<i", size) + payload
                    if subtype == 2
                    else payload
                )
                body = (
                    b"\x05"
                    + key.encode()
                    + b"\0"
                    + struct.pack("<iB", len(inner), subtype)
                    + inner
                    + b"\0"
                )
                expected = struct.pack("<i", len(body) + 4) + body
                actual = bson.encode({key: value})
                assert actual == expected
                assert bson.decode(actual)[key] == (
                    value if subtype else payload
                )


def test_general_encoder_paths():
    payload = b"x" * 65536
    for document in (
        {"a": payload, "b": payload},
        {"a": {"payload": payload}},
        {"a": [payload, bson.Binary(payload, 2)]},
        {"payload": payload, "tail": 42, "_id": 1},
    ):
        assert bson.decode(bson.encode(document)) == document


def test_key_and_option_validation():
    payload = b"x" * 65536
    for key in (1, "bad\0key"):
        with pytest.raises(bson.InvalidDocument):
            bson.encode({key: payload})  # pyright: ignore[reportArgumentType]
    for key in (chr(36) + "bad", "bad.key"):
        with pytest.raises(bson.InvalidDocument):
            bson.encode({key: payload}, check_keys=True)
        assert bson.decode(bson.encode({key: payload})) == {key: payload}
    with pytest.raises(TypeError):
        bson.encode({"payload": payload}, codec_options=object())  # pyright: ignore[reportArgumentType]
