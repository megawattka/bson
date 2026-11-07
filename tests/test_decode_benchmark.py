from contextlib import redirect_stdout
import io
from unittest.mock import patch

import pytest

from benchmarks import decode as benchmark  # pyright: ignore[reportMissingTypeStubs]


def run_benchmark():
    with (
        patch(
            "sys.argv",
            [
                "benchmark",
                "--repeat",
                "1",
                "--number",
                "2",
                "--batch-size",
                "12",
            ],
        ),
        redirect_stdout(io.StringIO()) as output,
    ):
        benchmark.main()
    return output.getvalue()


def test_dispatch_shared_inputs_and_batch_sizes():
    with patch.object(
        benchmark, "measure_pair", wraps=benchmark.measure_pair,
    ) as timed:
        output = run_benchmark()
    cases = benchmark.inputs()
    assert timed.call_count == 2 * len(cases) + 2
    for index, call in enumerate(timed.call_args_list):
        single = index < len(cases)
        assert call.args[0] == (
            benchmark.bson.decode if single else benchmark.bson.decode_all
        )
        assert call.args[2] == (
            benchmark._p_bson.decode  # pyright: ignore[reportUnknownMemberType]
            if single
            else benchmark._p_bson.decode_all  # pyright: ignore[reportUnknownMemberType]
        )
        assert call.args[1] == call.args[3]
        if not single:
            assert len(benchmark.bson.decode_all(call.args[1])) == (
                12 if call.args[1] else 0
            )
    assert "us/batch" in output
    assert "ratio=bson/pymongo" in output
    mixed_data = timed.call_args_list[-2].args[1]
    assert (
        benchmark.bson.decode_all(mixed_data)[0]
        != benchmark.bson.decode_all(mixed_data)[1]
    )


def test_wrong_single_result_stops_before_timing():
    with (
        patch.object(benchmark.bson, "decode", return_value={"wrong": 1}),
        patch.object(benchmark, "measure_pair") as timed,
        pytest.raises(AssertionError, match="empty"),
    ):
        run_benchmark()
    timed.assert_not_called()


def test_wrong_batch_result_is_rejected():
    with (
        patch.object(benchmark.bson, "decode_all", return_value=[]),
        patch.object(
            benchmark, "measure_pair", return_value=([1], [1]),
        ) as timed,
        pytest.raises(AssertionError, match="empty"),
    ):
        run_benchmark()
    assert timed.call_count == len(benchmark.inputs())


def test_requires_reference_c_extension():
    with (
        patch.object(benchmark._p_bson, "has_c", return_value=False),
        pytest.raises(RuntimeError, match="C extension"),
    ):
        run_benchmark()


def test_invalid_batch_size():
    with (
        patch("sys.argv", ["benchmark", "--batch-size", "0"]),
        redirect_stdout(io.StringIO()),
        patch("sys.stderr", new_callable=io.StringIO),
        pytest.raises(SystemExit) as error,
    ):
        benchmark.main()
    assert error.value.code == 2
