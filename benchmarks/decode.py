"""Compare decode/decode_all with PyMongo's native BSON decoder.

Run after building the extension with ``maturin develop --release``::

    python -m benchmarks.decode --repeat 7 --number 1000 --batch-size 100

Inputs and correctness checks are prepared outside the timed region.
decode_all times are per batch, not per document. Like benchmarks.encode,
this is a throughput smoke test, not a statistically rigorous profiler.
"""

from __future__ import annotations

import argparse
import platform
import sys
from typing import TYPE_CHECKING, cast

import _p_bson  # ruff: ignore[import-private-name]

from benchmarks.encode import (
    documents,
    for_pymongo,
    measure_pair,
    positive_int,
    report,
)
import bson
from bson import _bson  # pyright: ignore[reportPrivateUsage] # ruff: ignore[import-private-name]

if TYPE_CHECKING:
    from benchmarks.encode import Document


def inputs() -> dict[str, tuple[bytes, Document, Document]]:
    """Prepare shared wire inputs and implementation-specific expected values.

    Returns:
        Case names mapped to wire bytes, native and reference documents.

    Raises:
        AssertionError: If the encoders disagree on the wire representation.
    """
    cases = {"empty": {}, **documents()}
    result: dict[str, tuple[bytes, Document, Document]] = {}
    for name, document in cases.items():
        reference = cast("Document", for_pymongo(document))
        data = _p_bson.encode(reference)
        if bson.encode(document) != data:
            raise AssertionError(name)
        result[name] = (data, document, reference)
    return result


def main() -> None:
    """Validate and benchmark single-document and concatenated BSON decoding.

    Raises:
        AssertionError: If a decoder returns incorrect values or batch lengths.
        RuntimeError: If the PyMongo C extension is unavailable.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=positive_int, default=7)
    parser.add_argument("--number", type=positive_int, default=1000)
    parser.add_argument("--batch-size", type=positive_int, default=100)
    args = parser.parse_args()

    if not _p_bson.has_c():
        message = "PyMongo C extension is required for this comparison"
        raise RuntimeError(message)
    print(f"Python: {sys.version.split()[0]} ({platform.platform()})")
    print(f"bson: {bson.__file__}")
    print(f"native: {_bson.__file__}")
    print(f"pymongo: {_p_bson.__file__}")
    print(f"PyMongo BSON C extension: {_p_bson.has_c()}")
    print(
        f"repeat={args.repeat}, number={args.number}, "
        f"batch_size={args.batch_size}",
    )
    print("Median us/call; ratio=bson/pymongo (<1: bson faster)")
    print("\ndecode (one document per call)")
    cases = inputs()
    for name, (data, document, reference) in cases.items():
        if bson.decode(data) != document or _p_bson.decode(data) != reference:  # pyright: ignore[reportUnknownMemberType]
            raise AssertionError(name)
        report(
            name,
            *measure_pair(
                bson.decode,
                data,
                _p_bson.decode,  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                data,
                args.repeat,
                args.number,
            ),
        )

    batches = {
        name: (
            data * args.batch_size,
            [document] * args.batch_size,
            [reference] * args.batch_size,
        )
        for name, (data, document, reference) in cases.items()
    }
    # Include heterogeneous documents to exercise stream boundaries and order.
    mixed = [*cases.values()]
    selected = [mixed[index % len(mixed)] for index in range(args.batch_size)]
    batches["mixed"] = (
        b"".join(item[0] for item in selected),
        [item[1] for item in selected],
        [item[2] for item in selected],
    )
    batches["empty_stream"] = (b"", [], [])
    print("\ndecode_all (us/batch; divide by batch_size for us/document)")
    print("empty_stream contains 0 documents; other batches use batch_size")
    for name, (data, expected, reference_expected) in batches.items():
        actual = bson.decode_all(data)
        reference_actual = _p_bson.decode_all(data)  # pyright: ignore[reportUnknownMemberType]
        if (
            actual != expected
            or reference_actual != reference_expected
        ):
            raise AssertionError(name)
        report(
            name,
            *measure_pair(
                bson.decode_all,
                data,
                _p_bson.decode_all,  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                data,
                args.repeat,
                args.number,
            ),
        )


if __name__ == "__main__":
    main()
