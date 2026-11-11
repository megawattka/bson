import array
from datetime import UTC, datetime
import gc
import struct
from typing import TYPE_CHECKING
import weakref

import pytest

import elune
from elune.codec_options import TypeDecoder, TypeRegistry

if TYPE_CHECKING:
    from collections.abc import Buffer, Iterator


def document(body: bytes) -> bytes:
    return struct.pack("<i", len(body) + 5) + body + b"\0"


def element(tag: int, payload: bytes = b"", name: bytes = b"x") -> bytes:
    return bytes([tag]) + name + b"\0" + payload


def test_empty_and_independent_documents():
    assert list(elune.decode_iter(b"")) == []
    documents = [{}, {"x": [1, {"y": "hello"}]}, {}] * 30
    data = b"".join(elune.encode(doc) for doc in documents)
    iterator = elune.decode_iter(data)
    assert iter(iterator) is iterator
    result = list(iterator)
    assert result == documents
    result[1]["x"][1]["y"] = "changed"
    assert result[4]["x"][1]["y"] == "hello"
    for _ in range(2):
        with pytest.raises(StopIteration):
            next(iterator)


@pytest.mark.parametrize(
    "suffix",
    [
        b"x",
        b"\0",
        b"\x05\0",
        struct.pack("<i", -1) + b"\0",
        struct.pack("<i", 0) + b"\0",
        struct.pack("<i", 2**31 - 1) + b"\0",
        b"\x05\0\0\0\1",
        document(element(10, name=b"\xff")),
        document(element(2, struct.pack("<i", 2) + b"\xff\0")),
        document(element(3, struct.pack("<i", 100) + b"\0")),
    ],
)
def test_malformed_suffix_is_lazy_and_closes_iterator(suffix: bytes):
    iterator = elune.decode_iter(elune.encode({"x": 1}) + suffix)
    assert next(iterator) == {"x": 1}
    with pytest.raises(elune.InvalidBSON):
        next(iterator)
    with pytest.raises(StopIteration):
        next(iterator)


def test_truncated_documents():
    data = elune.encode({"x": ["text", bytes(20), {"y": True}]})
    for end in range(1, len(data)):
        with pytest.raises(elune.InvalidBSON):
            list(elune.decode_iter(data[:end]))


def test_buffer_inputs_and_snapshot():
    data = elune.encode({"x": [1, "привет"]}) * 2
    interleaved = b"".join(bytes([byte, 255]) for byte in data)
    inputs: tuple[Buffer, ...] = (
        data,
        bytearray(data),
        memoryview(data),
        array.array("B", data),
        memoryview(interleaved)[::2],
        memoryview(data[::-1])[::-1],
    )
    for value in inputs:
        assert list(elune.decode_iter(value)) == elune.decode_all(data)

    mutable = bytearray(data)
    view = memoryview(mutable)
    iterator = elune.decode_iter(view)
    assert next(iterator) == {"x": [1, "привет"]}
    view.release()
    mutable.clear()
    assert list(iterator) == [{"x": [1, "привет"]}]


def test_invalid_arguments_are_checked_during_iteration():
    for invalid in (None, [], "bytes", 123, object()):  # pyright: ignore[reportUnknownVariableType]
        iterator = elune.decode_iter(invalid)  # pyright: ignore[reportArgumentType]
        with pytest.raises((TypeError, BufferError)):
            next(iterator)
        assert list(iterator) == []
    iterator = elune.decode_iter(b"", codec_options=object())  # pyright: ignore[reportArgumentType]
    with pytest.raises(TypeError, match="CodecOptions"):
        next(iterator)


def test_codec_options():
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    data = elune.encode({"date": instant}) * 2
    options = elune.CodecOptions(tz_aware=True)
    assert list(elune.decode_iter(data, codec_options=options)) == [
        {"date": instant},
        {"date": instant},
    ]


class RecordingDecoder(TypeDecoder):
    """Record exactly when values are decoded."""

    def __init__(self) -> None:
        """Initialize callback records."""
        self.values: list[str] = []
        self.iterator: Iterator[dict[str, object]] | None = None

    @property
    def bson_type(self) -> type[str]:
        """Python type produced by the wire decoder."""
        return str

    def transform_bson(self, value: str) -> str:
        """Record and transform a string.

        Returns:
            The uppercase string.

        Raises:
            ValueError: If the value requests a callback failure.
        """
        self.values.append(value)
        if value == "fail":
            msg = "callback failed"
            raise ValueError(msg)
        return value.upper()


def test_custom_decoders_are_lazy_and_errors_propagate():
    decoder = RecordingDecoder()
    options = elune.CodecOptions(type_registry=TypeRegistry([decoder]))
    data = b"".join(elune.encode({"x": value}) for value in ("one", "fail"))
    iterator = elune.decode_iter(data, codec_options=options)
    assert decoder.values == []
    assert next(iterator) == {"x": "ONE"}
    assert decoder.values == ["one"]
    with pytest.raises(ValueError, match="callback failed"):
        next(iterator)
    assert decoder.values == ["one", "fail"]
    assert list(iterator) == []


@pytest.mark.parametrize("started", [False, True])
def test_iterator_reference_cycles_are_collectable(*, started: bool):
    decoder = RecordingDecoder()
    options = elune.CodecOptions(type_registry=TypeRegistry([decoder]))
    decoder.iterator = elune.decode_iter(
        elune.encode({}) * 2,
        codec_options=options,
    )
    if started:
        assert next(decoder.iterator) == {}
    reference = weakref.ref(decoder)
    del options, decoder
    gc.collect()
    assert reference() is None


def test_exhaustion_releases_codec_options():
    decoder = RecordingDecoder()
    options = elune.CodecOptions(type_registry=TypeRegistry([decoder]))
    iterator = elune.decode_iter(elune.encode({}), codec_options=options)
    reference = weakref.ref(decoder)
    del options, decoder
    assert list(iterator) == [{}]
    gc.collect()
    assert reference() is None


def test_reference_compatibility():
    reference = pytest.importorskip("_p_bson")
    documents = [{}, {"x": [1, "hello", {"y": True}]}, {"data": b"abc"}]
    data = b"".join(elune.encode(doc) for doc in documents)
    assert list(elune.decode_iter(data)) == list(reference.decode_iter(data))
