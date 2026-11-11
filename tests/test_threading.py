from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import sysconfig
from threading import Barrier

import pytest

from elune import Binary, Code, ObjectId, decode, decode_all, encode
from elune.codec_options import CodecOptions, TypeCodec, TypeRegistry


class DecimalCodec(TypeCodec):
    """Convert decimals to strings and back for concurrent codec tests."""

    @property
    def python_type(self) -> type[Decimal]:
        """Custom input type."""
        return Decimal

    @property
    def bson_type(self) -> type[str]:
        """Decoded input type."""
        return str

    def transform_python(self, value: Decimal) -> str:  # ruff: ignore[no-self-use]
        """Return the decimal representation.

        Returns:
            The encoded decimal string.
        """
        return str(value)

    def transform_bson(self, value: str) -> Decimal:  # ruff: ignore[no-self-use]
        """Restore a decimal.

        Returns:
            The decoded decimal value.
        """
        return Decimal(value)


@pytest.mark.skipif(
    not sysconfig.get_config_var("Py_GIL_DISABLED"),
    reason="requires free-threaded CPython",
)
def test_import_does_not_enable_gil():
    result = subprocess.run(
        [
            sys.executable,
            "-W",
            "error",
            "-c",
            (
                "import sys; assert not sys._is_gil_enabled(); "
                "import elune; assert not sys._is_gil_enabled()"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_concurrent_codecs_and_objectids():
    workers = 8
    barrier = Barrier(workers)
    zone = timezone(timedelta(hours=5, minutes=45))
    options = CodecOptions(
        tz_aware=True,
        tzinfo=zone,
        type_registry=TypeRegistry([DecimalCodec()]),
    )
    date = datetime(2024, 6, 1, tzinfo=UTC)

    def work(worker: int) -> list[ObjectId]:
        barrier.wait(timeout=30)
        identifiers: list[ObjectId] = []
        for index in range(100):
            oid = ObjectId()
            identifiers.append(oid)
            document = {
                "_id": oid,
                "value": Decimal(f"{worker}.{index:03d}"),
                "date": date,
                "nested": {"payload": Binary(b"abc", 7)},
                "code": Code("return 1", {"n": index}),
            }
            data = encode(document, codec_options=options)
            restored = decode(data, codec_options=options)
            assert restored == document
            assert restored["date"].tzinfo is zone
            assert decode_all(data * 2, codec_options=options) == [
                document,
                document,
            ]
        return identifiers

    with ThreadPoolExecutor(max_workers=workers) as executor:
        batches = list(executor.map(work, range(workers)))
    identifiers = [oid for batch in batches for oid in batch]
    assert len(set(identifiers)) == workers * 100
