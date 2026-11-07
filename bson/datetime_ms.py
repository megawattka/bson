"""Tools for representing the BSON datetime type."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._bson import DatetimeMS

if TYPE_CHECKING:
    from datetime import datetime

    from .codec_options import CodecOptions

    class DatetimeMS:
        """Represent a BSON date as milliseconds since the Unix epoch.

        Unlike :class:`datetime.datetime`, ``DatetimeMS`` can represent the
        full signed 64-bit range of BSON datetime values. Values can be
        converted to ``datetime`` with :meth:`as_datetime`, subject to the
        selected conversion policy and Python's supported date range.
        """

        def __int__(self) -> int: ...
        def __hash__(self) -> int: ...
        def __eq__(self, other: object) -> bool: ...
        def __lt__(self, other: DatetimeMS | int) -> bool: ...
        def __le__(self, other: DatetimeMS | int) -> bool: ...
        def __gt__(self, other: DatetimeMS | int) -> bool: ...
        def __ge__(self, other: DatetimeMS | int) -> bool: ...

        def as_datetime(
            self,
            codec_options: CodecOptions | None = None,
        ) -> datetime | DatetimeMS:
            """Convert this value to ``datetime`` according to codec options.

            The default policy raises :class:`OverflowError` if the stored
            milliseconds are outside Python's ``datetime`` range. The
            ``DATETIME_CLAMP`` policy clamps to the nearest representable
            boundary, ``DATETIME_MS`` returns this value unchanged, and
            ``DATETIME_AUTO`` returns ``DatetimeMS`` only when out of range.
            The ``tz_aware`` option controls whether a returned datetime is
            timezone-aware.

            Args:
                codec_options: Options controlling date conversion and
                    timezone-awareness. Defaults to the default codec options.

            Returns:
                A ``datetime`` or, for policies that preserve millisecond
                values, a ``DatetimeMS``.

            Raises:
                TypeError: ``codec_options`` is not ``None`` or a
                    :class:`CodecOptions` instance.
                OverflowError: The default conversion policy cannot represent
                    this value as a ``datetime``.
            """
            ...

__all__ = (
    "DatetimeMS",
)
