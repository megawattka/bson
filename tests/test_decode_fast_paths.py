import struct
from typing import Any

import pytest

import bson


def test_empty_documents_are_independent():
    result = bson.decode_all(bson.encode({}) * 1000)
    assert result == [{}] * 1000
    result[0]["changed"] = True
    assert result[1:] == [{}] * 999


def test_stack_reuse_with_alternating_depths_and_scope():
    deepest: dict[str, Any] = {}
    for _ in range(99):
        deepest = {"child": deepest}

    documents: list[Any] = [
        deepest,
        {},
        {"x": 1},
        {"a": [{}, {"b": [1, [], {}]}], "after": True},
        {"code": bson.Code("x", {"a": [{"b": 2}]}), "after": 3},
        {},
        deepest,
    ] * 10
    assert (
        bson.decode_all(b"".join(bson.encode(x) for x in documents))  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
        == documents
    )


def test_empty_fast_path_validates_boundaries():
    empty = bson.encode({})
    for invalid in (
        b"\x04\0\0\0\0",
        b"\x05\0\0\0\x01",
        b"\x06\0\0\0\0",
        empty + b"\x05\0",
    ):
        with pytest.raises(bson.InvalidBSON):
            bson.decode(invalid)
        with pytest.raises(bson.InvalidBSON):
            bson.decode_all(empty * 10 + invalid)


def test_strict_utf8_in_names_and_values():
    for invalid in (
        b"\xff",
        b"\xc0\x80",
        b"\xed\xa0\x80",
        b"\xf4\x90\x80\x80",
        b"\xe2\x82",
    ):
        for body in (
            b"\x0a" + invalid + b"\0",
            b"\x02x\0" + struct.pack("<i", len(invalid) + 1) + invalid + b"\0",
        ):
            data = struct.pack("<i", len(body) + 5) + body + b"\0"
            with pytest.raises(bson.InvalidBSON, match="UTF-8"):
                bson.decode(data)
            with pytest.raises(bson.InvalidBSON, match="UTF-8"):
                bson.decode_all(bson.encode({}) + data)


def test_unicode_and_embedded_nuls():
    document = {
        "": "",
        "ascii": "a\0b",
        "кириллица": "привет" * 1000,
        "emoji🦀": "🦀\0世界" * 1000,
    }
    data = bson.encode(document)
    assert bson.decode(data) == document
    assert bson.decode_all(data * 10) == [document] * 10


def test_batch_key_cache_collisions_and_independent_documents():
    # Same length, first and last byte: deliberately collide in the key cache.
    documents = [
        {
            "aba": index,
            "aca": {"aba": index + 1},
            "🦀": index,
            "long" * 100: index,
            "": index,
        }
        for index in range(150)
    ]
    data = b"".join(bson.encode(doc) for doc in documents)
    result = bson.decode_all(data)
    assert result == documents
    result[0]["aca"]["aba"] = -1
    assert result[1:] == documents[1:]


def test_batch_cached_names_do_not_hide_invalid_utf8():
    valid = bson.encode({"aXa": 1})
    body = b"\x10a\xffa\0" + struct.pack("<i", 2)
    invalid = struct.pack("<i", len(body) + 5) + body + b"\0"
    with pytest.raises(bson.InvalidBSON, match="UTF-8"):
        bson.decode_all(valid * 100 + invalid)


def test_batch_key_cache_preserves_duplicate_names_and_dbrefs():
    body = b"\x10same\0" + struct.pack("<i", 1)
    body += b"\x10same\0" + struct.pack("<i", 2)
    duplicate = struct.pack("<i", len(body) + 5) + body + b"\0"
    reference = {"child": bson.DBRef("items", 42, "db", extra=True)}
    data = (duplicate + bson.encode(reference)) * 100
    assert bson.decode_all(data) == [{"same": 2}, reference] * 100


def test_dbref_detection_preserves_plain_documents_and_scope():
    values = [
        {"$ref": 123, "$id": 1},
        {"$ref": "items"},
        {"$ref": "items", "$id": 1, "$db": 123},
        {"normal": {"$id": 1}},
        {"child": bson.DBRef("items", 1)},
        {"code": bson.Code("x", {"$ref": "items", "$id": 1})},
    ]
    for value in values:
        data = bson.encode(value)
        assert bson.decode(data) == value
        assert bson.decode_all(data * 3) == [value] * 3
