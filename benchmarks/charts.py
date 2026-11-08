"""Measure native codecs and render grouped bars from saved JSON results.

Measure and render using separate interpreters if needed::

    python -m benchmarks.charts measure
    python -m benchmarks.charts render
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import sys
from typing import Any

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "benchmarks"
DARK_BLUE = "#153E75"
LIGHT_BLUE = "#64B5F6"


def positive_int(value: str) -> int:
    """Parse a positive benchmark iteration count.

    Returns:
        A positive count.

    Raises:
        argparse.ArgumentTypeError: If the count is not positive.
    """
    result = int(value)
    if result <= 0:
        message = "must be a positive integer"
        raise argparse.ArgumentTypeError(message)
    return result


def measure(args: argparse.Namespace) -> None:
    """Validate both codecs and save alternating, warmed-up timing samples.

    Raises:
        RuntimeError: If the reference C extension is unavailable.
    """
    # Keep native modules out of the rendering process (different ABI allowed).
    import _p_bson  # ruff: ignore[import-outside-top-level, import-private-name]

    from benchmarks.decode import inputs  # ruff: ignore[import-outside-top-level]
    from benchmarks.encode import measure_pair  # ruff: ignore[import-outside-top-level]
    import bson  # ruff: ignore[import-outside-top-level]
    from bson import _bson  # pyright: ignore[reportPrivateUsage] # ruff: ignore[import-outside-top-level, import-private-name]

    if not _p_bson.has_c():
        message = "PyMongo's C extension is required"
        raise RuntimeError(message)
    cases = inputs()
    results: dict[str, Any] = {"encode": [], "decode": [], "decode_all": []}

    def record(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]
        operation: str,
        name: str,
        value: object,
        reference: object,
        expected: object,
        reference_expected: object,
    ) -> None:
        function = getattr(bson, operation)
        reference_function = getattr(_p_bson, operation)
        if function(value) != expected:
            message = f"bson {operation}: {name}"
            raise AssertionError(message)
        if reference_function(reference) != reference_expected:
            message = f"PyMongo {operation}: {name}"
            raise AssertionError(message)
        number = (
            args.batch_number if operation == "decode_all" else args.number
        )
        native, pymongo = measure_pair(
            function,
            value,
            reference_function,
            reference,
            args.repeat,
            number,
        )
        results[operation].append(
            {
                "case": name,
                "bson_us": native,
                "pymongo_us": pymongo,
            },
        )
        print(
            f"{operation:10} {name:14} "
            f"bson={statistics.median(native):.3f} us "
            f"pymongo={statistics.median(pymongo):.3f} us",
            flush=True,
        )

    for name, (data, document, reference) in cases.items():
        record("encode", name, document, reference, data, data)
        record("decode", name, data, data, document, reference)
        batch = data * args.batch_size
        record(
            "decode_all",
            name,
            batch,
            batch,
            [document] * args.batch_size,
            [reference] * args.batch_size,
        )
    selected = [
        list(cases.values())[i % len(cases)] for i in range(args.batch_size)
    ]
    mixed = b"".join(item[0] for item in selected)
    record(
        "decode_all",
        "mixed",
        mixed,
        mixed,
        [item[1] for item in selected],
        [item[2] for item in selected],
    )
    record("decode_all", "empty_stream", b"", b"", [], [])
    metadata = {
        "timestamp_utc": dt.datetime.now(dt.UTC).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "gil_enabled": getattr(sys, "_is_gil_enabled", lambda: True)(),
        "native_module": _bson.__file__,
        "native_sha256": hashlib.sha256(
            Path(_bson.__file__).read_bytes(),  # pyright: ignore[reportArgumentType]
        ).hexdigest(),
        "reference_module": _p_bson.__file__,
        "reference_c_extension": True,
        "repeat": args.repeat,
        "number": args.number,
        "batch_number": args.batch_number,
        "batch_size": args.batch_size,
        "unit": "microseconds per call (decode_all: per batch)",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / "results.json"
    path.write_text(
        json.dumps({"metadata": metadata, "results": results}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(path)


def render(args: argparse.Namespace) -> None:
    """Render median timings with min/max ranges, without remeasurement."""
    import matplotlib as mpl  # pyright: ignore[reportMissingModuleSource] # ruff: ignore[import-outside-top-level]

    mpl.use("Agg")
    from matplotlib.patches import Patch  # pyright: ignore[reportMissingModuleSource] # ruff: ignore[import-outside-top-level]
    import matplotlib.pyplot as plt  # pyright: ignore[reportMissingModuleSource] # ruff: ignore[import-outside-top-level]

    payload = json.loads(
        (args.output / "results.json").read_text(encoding="utf-8"),
    )
    metadata = payload["metadata"]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})  # pyright: ignore[reportUnknownMemberType]
    for operation, cases in payload["results"].items():
        rows = math.ceil(len(cases) / 3)
        figure, axes = plt.subplots(rows, 3, figsize=(13, rows * 2.7 + 1.6))  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
        for axis, case in zip(axes.flat, cases, strict=False):  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType, reportUnknownVariableType]
            samples = [case["pymongo_us"], case["bson_us"]]
            medians = [statistics.median(values) for values in samples]
            errors = [
                [
                    median - min(values)
                    for median, values in zip(medians, samples, strict=True)
                ],
                [
                    max(values) - median
                    for median, values in zip(medians, samples, strict=True)
                ],
            ]
            bars = axis.bar(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                [0, 1],
                medians,
                width=0.64,
                color=[DARK_BLUE, LIGHT_BLUE],
                yerr=errors,
                capsize=4,
                error_kw={"elinewidth": 1, "ecolor": "#334155"},
            )
            axis.bar_label(bars, fmt="%.3f", padding=6, fontsize=10)  # pyright: ignore[reportUnknownMemberType]
            axis.set_xticks([0, 1], ["PyMongo BSON", "bson (Rust)"])  # pyright: ignore[reportUnknownMemberType]
            axis.set_title(case["case"], loc="left", fontweight="bold", pad=12)  # pyright: ignore[reportUnknownMemberType]
            axis.set_ylabel(  # pyright: ignore[reportUnknownMemberType]
                "\N{GREEK SMALL LETTER MU}s / batch"
                if operation == "decode_all"
                else "\N{GREEK SMALL LETTER MU}s / call",
            )
            axis.set_ylim(0, max(max(values) for values in samples) * 1.32)  # pyright: ignore[reportUnknownMemberType]
            axis.set_axisbelow(True)  # pyright: ignore[reportUnknownMemberType]
            axis.grid(axis="y", color="#E2E8F0", linewidth=0.7)  # pyright: ignore[reportUnknownMemberType]
            axis.spines[["top", "right"]].set_visible(False)  # pyright: ignore[reportUnknownMemberType]
            axis.spines[["left", "bottom"]].set_color("#CBD5E1")  # pyright: ignore[reportUnknownMemberType]
        for axis in list(axes.flat)[len(cases) :]:  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType, reportUnknownMemberType]
            axis.set_visible(False)  # pyright: ignore[reportUnknownMemberType]
        figure.suptitle(  # pyright: ignore[reportUnknownMemberType]
            f"BSON performance · {operation}",
            fontsize=23,
            fontweight="bold",
            x=0.06,
            ha="left",
            y=0.98,
            color=DARK_BLUE,
        )
        figure.legend(  # pyright: ignore[reportUnknownMemberType]
            handles=[
                Patch(color=DARK_BLUE, label="PyMongo BSON (C extension)"),
                Patch(color=LIGHT_BLUE, label="bson (Rust, release build)"),
            ],
            loc="upper left",
            bbox_to_anchor=(0.055, 0.945),
            ncol=2,
            frameon=False,
        )
        batch_note = (
            f" | {metadata['batch_size']} documents/batch; empty_stream: 0"
            if operation == "decode_all"
            else ""
        )
        footer = (
            f"Python {metadata['python'].split()[0]} | {metadata['platform']}"
            f" | GIL {'on' if metadata['gil_enabled'] else 'off'}\n"
            f"Median of {metadata['repeat']} repeats; whiskers: min-max. "
            f"Lower is better.{batch_note}\n"
            "Linear axes start at zero; each panel has its own scale. "
            "Local microbenchmarks, not an application-level guarantee."
        )
        figure.text(  # pyright: ignore[reportUnknownMemberType]
            0.06,
            0.015,
            footer,
            fontsize=9,
            color="#475569",
            linespacing=1.6,
        )
        figure.tight_layout(rect=(0.025, 0.105, 0.99, 0.90), h_pad=2.2)
        path = args.output / f"{operation}.png"
        figure.savefig(path, dpi=180, facecolor="white")  # pyright: ignore[reportUnknownMemberType]
        print(path)
        plt.close(figure)  # pyright: ignore[reportUnknownMemberType]


def main() -> None:
    """Select independent measurement or rendering stages."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("measure", "render"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--repeat", type=positive_int, default=7)
    parser.add_argument("--number", type=positive_int, default=20_000)
    parser.add_argument("--batch-number", type=positive_int, default=1000)
    parser.add_argument("--batch-size", type=positive_int, default=100)
    args = parser.parse_args()
    (measure if args.command == "measure" else render)(args)


if __name__ == "__main__":
    main()
