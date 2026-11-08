from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import override
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from bson import DatetimeMS, decode, decode_all, encode
from bson.codec_options import DEFAULT_CODEC_OPTIONS, CodecOptions
from bson.errors import InvalidBSON

MIN_MS = -62135596800000
MAX_MS = 253402300799999


class CustomTimezone(tzinfo):
    """User-defined timezone with a fixed non-hour offset."""

    @override
    def utcoffset(self, dt: datetime | None) -> timedelta:
        return timedelta(hours=5, minutes=45)

    @override
    def dst(self, dt: datetime | None) -> timedelta:
        return timedelta(0)

    @override
    def tzname(self, dt: datetime | None) -> str:
        return "Custom+05:45"


class FailingTimezone(CustomTimezone):
    """Timezone whose conversion fails, to check exception propagation."""

    @override
    def fromutc(self, dt: datetime) -> datetime:
        message = "custom fromutc failure"
        raise RuntimeError(message)


def test_timezone_fromutc_and_raw_milliseconds():
    zone = FailingTimezone()
    data = encode({"date": DatetimeMS(0)})
    options = CodecOptions(tz_aware=True, tzinfo=zone)
    with pytest.raises(RuntimeError, match="custom fromutc failure"):
        decode(data, codec_options=options)
    raw = options.with_options(datetime_conversion=3)
    assert int(decode(data, codec_options=raw)["date"]) == 0


def test_timezone_options():
    zone = CustomTimezone()
    options = CodecOptions(tz_aware=True, tzinfo=zone)
    assert DEFAULT_CODEC_OPTIONS.tzinfo is None
    assert options.tzinfo is zone
    assert options.with_options().tzinfo is zone
    replacement = options.with_options(tzinfo=UTC)
    assert replacement.tzinfo is UTC
    assert options.tzinfo is zone
    assert "tzinfo=" in repr(options)
    with pytest.raises(AttributeError):
        options.tzinfo = UTC  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(ValueError, match="tz_aware"):
        CodecOptions(tzinfo=zone)
    with pytest.raises(ValueError, match="tz_aware"):
        options.with_options(tz_aware=False)
    with pytest.raises(TypeError, match="tzinfo"):
        CodecOptions(tz_aware=True, tzinfo="UTC")  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize(
    "zone",
    [UTC, timezone(timedelta(hours=-7)), CustomTimezone()],
)
def test_timezone_roundtrip(zone: tzinfo):
    options = CodecOptions(tz_aware=True, tzinfo=zone)
    original = datetime(2024, 6, 1, 12, 30, 1, 123000, tzinfo=UTC)
    document = {"date": original, "nested": {"dates": [original]}}
    data = encode(document)
    expected = original.astimezone(zone)
    restored = decode(data, codec_options=options)
    assert restored["date"] == expected
    assert restored["date"].tzinfo is zone
    assert restored["date"].hour == expected.hour
    assert restored["nested"]["dates"][0].tzinfo is zone
    assert encode(restored, codec_options=options) == data
    assert decode_all(data * 2, codec_options=options) == [restored, restored]
    assert DatetimeMS(original).as_datetime(options) == expected
    assert decode(data)["date"].tzinfo is None


def test_timezone_dst_and_fold():
    try:
        zone = ZoneInfo("America/New_York")
    except ZoneInfoNotFoundError:
        pytest.skip("IANA timezone database is not installed")
    options = CodecOptions(tz_aware=True, tzinfo=zone)
    for hour, fold in [(5, 0), (6, 1)]:
        original = datetime(2024, 11, 3, hour, 30, tzinfo=UTC)
        restored = decode(encode({"date": original}), codec_options=options)[
            "date"
        ]
        assert restored.hour == 1
        assert restored.fold == fold
        assert restored.tzinfo is zone
        assert encode({"date": restored}) == encode({"date": original})
    for month, offset in [(1, -5), (7, -4)]:
        original = datetime(2024, month, 1, 12, tzinfo=UTC)
        restored = decode(encode({"date": original}), codec_options=options)[
            "date"
        ]
        assert restored.utcoffset() == timedelta(hours=offset)


@pytest.mark.parametrize("hours", [-7, 5])
def test_timezone_conversion_bounds(hours: int):
    zone = timezone(timedelta(hours=hours))
    offset = hours * 3600000
    lower = max(MIN_MS, MIN_MS - offset)
    upper = min(MAX_MS, MAX_MS - offset)
    for value in [-(2**63), lower - 1, lower, 0, upper, upper + 1, 2**63 - 1]:
        data = encode({"date": DatetimeMS(value)})
        for mode in range(1, 5):
            options = CodecOptions(
                tz_aware=True,
                tzinfo=zone,
                datetime_conversion=mode,
            )
            if mode == 1 and not lower <= value <= upper:
                with pytest.raises(InvalidBSON):
                    decode(data, codec_options=options)
                continue
            restored = decode(data, codec_options=options)["date"]
            if mode == 3 or (mode == 4 and not lower <= value <= upper):
                assert isinstance(restored, DatetimeMS)
                assert int(restored) == value
            else:
                assert isinstance(restored, datetime)
                assert restored.tzinfo is zone
                expected_ms = (
                    min(upper, max(lower, value)) if mode == 2 else value
                )
                assert int(DatetimeMS(restored)) == expected_ms


def test_timezone_bounds_match_pymongo():
    reference = pytest.importorskip("_p_bson")
    for zone in [timezone(timedelta(hours=-7)), CustomTimezone()]:
        for mode in range(1, 5):
            options = CodecOptions(
                tz_aware=True,
                tzinfo=zone,
                datetime_conversion=mode,
            )
            ref_options = reference.codec_options.CodecOptions(
                tz_aware=True,
                tzinfo=zone,
                datetime_conversion=mode,
            )
            for value in [MIN_MS - 1, MIN_MS, 0, MAX_MS, MAX_MS + 1]:
                data = encode({"date": DatetimeMS(value)})
                try:
                    expected = reference.decode(
                        data,
                        codec_options=ref_options,
                    )["date"]
                except reference.errors.InvalidBSON:
                    with pytest.raises(InvalidBSON):
                        decode(data, codec_options=options)
                else:
                    actual = decode(data, codec_options=options)["date"]
                    if isinstance(actual, DatetimeMS):
                        assert int(actual) == int(expected)
                    else:
                        assert actual == expected
