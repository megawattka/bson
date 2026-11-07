import argparse
from contextlib import redirect_stdout
import gc
import io
from unittest.mock import patch

import pytest

from benchmarks import encode as benchmark  # pyright: ignore[reportMissingTypeStubs]


def test_main_measures_both_implementations():
    measure_pair = benchmark.measure_pair
    with (
        patch("sys.argv", ["benchmark", "--repeat", "1", "--number", "2"]),
        patch.object(benchmark, "measure_pair", wraps=measure_pair) as timed,
        redirect_stdout(io.StringIO()) as output,
    ):
        benchmark.main()
    cases = benchmark.documents()
    assert timed.call_count == len(cases) + 1
    for call, doc in zip(timed.call_args_list, cases.values(), strict=False):
        assert call.args[0] == benchmark.bson.encode
        assert call.args[1] == doc
        assert call.args[2] == benchmark._p_bson.encode
        assert benchmark.bson.encode(call.args[1]) == benchmark._p_bson.encode(
            call.args[3],
        )
    assert (
        timed.call_args_list[-1].args[0]
        == benchmark.bson.ObjectId.from_datetime
    )
    assert "ratio=bson/pymongo" in output.getvalue()


def test_pair_alternates_order_and_keeps_samples():
    with patch.object(
        benchmark,
        "measure",
        side_effect=[[0], [0], [1], [2], [3], [4], [5], [6]],
    ) as measure:
        result = benchmark.measure_pair(
            str, "native", str, "reference", 3, 200,
        )
    assert result == ([1, 4, 5], [2, 3, 6])
    assert [call.args[1] for call in measure.call_args_list] == [
        "native",
        "reference",
        "native",
        "reference",
        "reference",
        "native",
        "native",
        "reference",
    ]


def test_measure_units_and_gc_state():
    for enabled in (True, False):
        previous = gc.isenabled()
        try:
            gc.enable() if enabled else gc.disable()
            with patch.object(
                benchmark.timeit.Timer, "repeat", return_value=[1, 2],
            ):
                assert benchmark.measure(str, "x", 2, 1000) == [1000, 2000]
            benchmark.measure(str, "x", 1, 2)
            assert gc.isenabled() == enabled
        finally:
            gc.enable() if previous else gc.disable()


def test_mismatched_bytes_stop_before_timing():
    with (
        patch("sys.argv", ["benchmark"]),
        patch.object(benchmark.bson, "encode", return_value=b"wrong"),
        patch.object(benchmark, "measure_pair") as timed,
        redirect_stdout(io.StringIO()),
        pytest.raises(AssertionError, match="small"),
    ):
        benchmark.main()
    timed.assert_not_called()


def test_requires_c_extension():
    with (
        patch("sys.argv", ["benchmark"]),
        patch.object(benchmark._p_bson, "has_c", return_value=False),
        pytest.raises(RuntimeError, match="C extension"),
    ):
        benchmark.main()


def test_iteration_counts_must_be_positive():
    for value in ("0", "-1"):
        with pytest.raises(argparse.ArgumentTypeError):
            benchmark.positive_int(value)
    assert benchmark.positive_int("7") == 7


def test_report_uses_medians_and_native_over_reference_ratio():
    with redirect_stdout(io.StringIO()) as output:
        benchmark.report("case", [1, 2, 99], [2, 4, 200])
    assert "bson=    2.000 us" in output.getvalue()
    assert "pymongo=    4.000 us" in output.getvalue()
    assert "ratio= 0.500x" in output.getvalue()
