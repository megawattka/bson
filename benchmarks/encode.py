"""Repeatable encode/ObjectId benchmark against PyMongo's native BSON encoder.

Run from the repository root after building the extension:

    maturin develop --release
    python -m benchmarks.encode
The benchmark intentionally uses the same call shape for both implementations.
It is a throughput smoke test, not a statistically rigorous profiler.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import datetime as dt
import platform
import statistics
import sys
import timeit
from typing import TYPE_CHECKING, Any, cast

import _p_bson  # ruff: ignore[import-private-name]

import elune
from elune import _elune  # pyright: ignore[reportPrivateUsage] # ruff: ignore[import-private-name]

if TYPE_CHECKING:
    from collections.abc import Callable

Document = dict[str, Any]


def documents() -> dict[str, Document]:
    """Return representative documents to encode."""
    oid = elune.ObjectId(bytes(range(12)))
    return {
        "small": {"x": 42, "name": "example", "active": True, "id": oid},
        "nested": {
            "items": list(range(100)),
            "child": {"name": "hello", "payload": b"x" * 100},
            "ids": [oid, oid, oid],
        },
        "binary_64k": {"payload": b"x" * 65_536},
        "binary_4k": {"payload": b"x" * 4096},
        "binary_pair": {"a": b"x" * 65_536, "b": b"y" * 65_536},
        "binary_nested": {"child": {"payload": b"x" * 65_536}},
        "binary_sub1": {"payload": elune.Binary(b"x" * 65_536, 1)},
        "binary_old": {"payload": elune.Binary(b"x" * 65_536, 2)},
        "binary_user": {"payload": elune.Binary(b"x" * 65_536, 128)},
        "unicode": {"text": "привет 🦀\0" * 100, "empty": ""},
    }


def for_pymongo(value: object) -> object:
    """Convert BSON-specific values into PyMongo equivalents.

    Returns:
        The value represented using the corresponding PyMongo types.
    """
    if isinstance(value, elune.Binary):
        return _p_bson.Binary(value, value.subtype)
    if isinstance(value, elune.ObjectId):
        return _p_bson.ObjectId(value.binary)
    if isinstance(value, Mapping):
        return cast(
            "dict[str, Any]",
            {
                key: for_pymongo(item)  # pyright: ignore[reportUnknownArgumentType]
                for key, item in value.items()  # type: ignore  # ruff: ignore[blanket-type-ignore]
            },
        )
    if isinstance(value, list):
        return [for_pymongo(item) for item in value]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    if isinstance(value, tuple):
        return tuple(for_pymongo(item) for item in value)  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    return value


def measure[T](
    function: Callable[[T], object],
    document: T,
    repeat: int,
    number: int,
) -> list[float]:
    """Return one execution time per repeat, in microseconds per call."""
    timer = timeit.Timer(lambda: function(document))
    return [
        duration / number * 1_000_000
        for duration in timer.repeat(repeat=repeat, number=number)
    ]


def measure_pair[T, U](  # ruff: ignore[too-many-arguments, too-many-positional-arguments]
    function: Callable[[T], object],
    document: T,
    reference_function: Callable[[U], object],
    reference_document: U,
    repeat: int,
    number: int,
) -> tuple[list[float], list[float]]:
    """Warm both implementations, then alternate their measurement order.

    Returns:
        Native and reference samples in microseconds per call.
    """
    measure(function, document, repeat=1, number=min(number, 100))
    measure(
        reference_function,
        reference_document,
        repeat=1,
        number=min(number, 100),
    )
    elune_times: list[float] = []
    pymongo_times: list[float] = []
    for index in range(repeat):
        if index % 2 == 0:
            elune_times.extend(measure(function, document, 1, number))
            pymongo_times.extend(
                measure(reference_function, reference_document, 1, number),
            )
        else:
            pymongo_times.extend(
                measure(reference_function, reference_document, 1, number),
            )
            elune_times.extend(measure(function, document, 1, number))
    return elune_times, pymongo_times


def report(
    name: str,
    elune_times: list[float],
    pymongo_times: list[float],
) -> None:
    """Print median encode times and their ratio."""
    elune_time = statistics.median(elune_times)
    pymongo_time = statistics.median(pymongo_times)
    ratio = elune_time / pymongo_time
    print(
        f"{name:12} elune={elune_time:9.3f} us  "
        f"pymongo={pymongo_time:9.3f} us  ratio={ratio:6.3f}x",
    )


def positive_int(value: str) -> int:
    """Parse a strictly positive iteration count.

    Returns:
        The validated count.

    Raises:
        argparse.ArgumentTypeError: If the count is not positive.
    """
    result = int(value)
    if result <= 0:
        message = "must be a positive integer"
        raise argparse.ArgumentTypeError(message)
    return result


def main() -> None:
    """Run BSON encoder and ObjectId method microbenchmarks.

    Raises:
        AssertionError: If implementations produce different results.
        RuntimeError: If the PyMongo C extension is unavailable.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=positive_int, default=7)
    parser.add_argument("--number", type=positive_int, default=20_000)
    args = parser.parse_args()

    if not _p_bson.has_c():
        message = "PyMongo C extension is required for this comparison"
        raise RuntimeError(message)
    print(f"Python: {sys.version.split()[0]} ({platform.platform()})")
    print(f"elune: {elune.__file__}")
    print(f"native: {_elune.__file__}")
    print(f"pymongo: {_p_bson.__file__}")
    print(f"PyMongo BSON C extension: {_p_bson.has_c()}")
    print(f"repeat={args.repeat}, number={args.number}")
    print("Median us/call; ratio=elune/pymongo (<1: elune faster)")
    print("case         elune             pymongo             ratio")
    for name, document in documents().items():
        reference_document = cast("Document", for_pymongo(document))
        expected = _p_bson.encode(reference_document)
        actual = elune.encode(document)
        if actual != expected:
            raise AssertionError(name)
        report(
            name,
            *measure_pair(
                elune.encode,
                document,
                _p_bson.encode,
                reference_document,
                args.repeat,
                args.number,
            ),
        )

    value = dt.datetime(2024, 1, 1, 12, 30, 1, 123456, tzinfo=dt.UTC)
    if (
        elune.ObjectId.from_datetime(value).binary
        != _p_bson.ObjectId.from_datetime(value).binary
    ):
        message = "from_datetime"
        raise AssertionError(message)
    report(
        "from_datetime",
        *measure_pair(
            elune.ObjectId.from_datetime,
            value,
            _p_bson.ObjectId.from_datetime,
            value,
            args.repeat,
            args.number,
        ),
    )


if __name__ == "__main__":
    main()
