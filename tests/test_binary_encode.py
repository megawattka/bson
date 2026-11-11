import statistics
import struct
import timeit

import pytest

import elune


def test_sizes_subtypes_and_keys():
    class CustomBytes(bytes):
        pass

    class CustomBinary(elune.Binary):
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
                (elune.Binary, 0),
                (elune.Binary, 2),
                (elune.Binary, 128),
                (CustomBinary, 255),
            ):
                value = (
                    cls(payload, subtype)
                    if issubclass(cls, elune.Binary)
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
                actual = elune.encode({key: value})
                assert actual == expected
                assert elune.decode(actual)[key] == (
                    value if subtype else payload
                )


def test_general_encoder_paths():
    payload = b"x" * 65536
    for document in (
        {"a": payload, "b": payload},
        {"a": {"payload": payload}},
        {"a": [payload, elune.Binary(payload, 2)]},
        {"payload": payload, "tail": 42, "_id": 1},
    ):
        assert elune.decode(elune.encode(document)) == document


@pytest.mark.parametrize("subtype", [0, 1, 2, 128])
def test_large_binary_matches_reference_in_all_envelopes(subtype: int):
    reference = pytest.importorskip("_p_bson")
    payload = bytes(range(256)) * 256
    value = elune.Binary(payload, subtype)
    reference_value = reference.Binary(payload, subtype)
    for wrap in (  # pyright: ignore[reportUnknownVariableType]
        lambda item: {"payload": item},  # pyright: ignore[reportUnknownLambdaType]
        lambda item: {"child": {"payload": item}},  # pyright: ignore[reportUnknownLambdaType]
        lambda item: {"payload": item, "tail": 42},  # pyright: ignore[reportUnknownLambdaType]
        lambda item: {"items": [item, item]},  # pyright: ignore[reportUnknownLambdaType]
    ):
        actual = elune.encode(wrap(value))  # pyright: ignore[reportUnknownArgumentType]
        assert actual == reference.encode(wrap(reference_value))
        assert elune.decode(actual) == wrap(value if subtype else payload)


def test_large_binary_has_no_several_fold_copy_penalty():
    payload = b"x" * 65_536
    plain_document = {"payload": payload}
    plain_timer = timeit.Timer(lambda: elune.encode(plain_document))
    for subtype in (0, 1, 2, 128):
        document = {"payload": elune.Binary(payload, subtype)}
        binary_timer = timeit.Timer(
            lambda document=document: elune.encode(document),
        )
        plain_timer.timeit(number=1000)
        binary_timer.timeit(number=1000)
        plain_samples = []
        binary_samples = []
        for index in range(7):
            order = (  # pyright: ignore[reportUnknownVariableType]
                [(plain_timer, plain_samples), (binary_timer, binary_samples)]
                if index % 2 == 0
                else [
                    (binary_timer, binary_samples),
                    (plain_timer, plain_samples),
                ]
            )
            for timer, samples in order:
                samples.append(timer.timeit(number=2000))  # pyright: ignore[reportUnknownMemberType]
        # A broad guard against the original ~7x slowdown, not a speed claim.
        assert statistics.median(binary_samples) < (  # pyright: ignore[reportUnknownArgumentType]
            3 * statistics.median(plain_samples)  # pyright: ignore[reportUnknownArgumentType]
        ), subtype


def test_key_and_option_validation():
    payload = b"x" * 65536
    for key in (1, "bad\0key"):
        with pytest.raises(elune.InvalidDocument):
            elune.encode({key: payload})  # pyright: ignore[reportArgumentType]
    for key in (chr(36) + "bad", "bad.key"):
        with pytest.raises(elune.InvalidDocument):
            elune.encode({key: payload}, check_keys=True)
        assert elune.decode(elune.encode({key: payload})) == {key: payload}
    with pytest.raises(TypeError):
        elune.encode({"payload": payload}, codec_options=object())  # pyright: ignore[reportArgumentType]
