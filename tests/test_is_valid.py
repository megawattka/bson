import random
import struct

import pytest

import elune


def document(body: bytes) -> bytes:
    return struct.pack("<i", len(body) + 5) + body + b"\0"


def element(tag: int, payload: bytes = b"", name: bytes = b"x") -> bytes:
    return bytes([tag]) + name + b"\0" + payload


@pytest.mark.parametrize(
    "data",
    [
        elune.encode({}),
        elune.encode({"x": [1, "привет", {"y": b"abc"}]}),
        elune.encode({"oid": elune.ObjectId(), "int": elune.Int64(42)}),
        b"",
        b"x",
        b"\x05\0\0\0\1",
        elune.encode({}) * 2,
        elune.encode({}) + b"\0",
        document(element(8, b"\2")),
        document(element(10, name=b"\xff")),
        document(element(2, struct.pack("<i", 2) + b"\xff\0")),
        document(element(3, struct.pack("<i", 100) + b"\0")),
        document(element(9, struct.pack("<q", 2**63 - 1))),
    ],
)
def test_matches_default_decode_and_reference(data: bytes):
    try:
        elune.decode(data)
    except elune.InvalidBSON:
        expected = False
    else:
        expected = True
    assert elune.is_valid(data) is expected
    reference = pytest.importorskip("_p_bson")
    assert elune.is_valid(data) is reference.is_valid(data)


def test_accepts_bytes_subclasses():
    class Data(bytes):
        pass

    assert elune.is_valid(Data(elune.encode({}))) is True
    assert elune.is_valid(Data(b"")) is False


@pytest.mark.parametrize(
    "data",
    [None, "", 1, [], {}, bytearray(), memoryview(b"\x05\0\0\0\0")],
)
def test_requires_bytes(data: object):
    with pytest.raises(TypeError):
        elune.is_valid(data)  # pyright: ignore[reportArgumentType]


def test_all_truncation_points():
    data = elune.encode({"nested": [{"text": "hello"}], "bytes": bytes(20)})
    assert elune.is_valid(data)
    for end in range(len(data)):
        assert elune.is_valid(data[:end]) is False


def test_random_malformed_input():
    rng = random.Random(924)  # ruff: ignore[suspicious-non-cryptographic-random-usage]
    for _ in range(300):
        data = bytearray(rng.randbytes(rng.randrange(5, 80)))
        struct.pack_into("<i", data, 0, len(data))
        data[-1] = 0
        raw = bytes(data)
        try:
            elune.decode(raw)
        except elune.InvalidBSON:
            assert elune.is_valid(raw) is False
        else:
            assert elune.is_valid(raw) is True
