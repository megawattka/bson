"""Tools for representing MongoDB internal Timestamps."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._elune import Timestamp

if TYPE_CHECKING:
    from datetime import datetime

    class Timestamp:
        """BSON timestamp containing seconds and an incrementing ordinal.

        Timestamps are ordered first by ``time`` and then by ``inc``. Both
        components are unsigned 32-bit integers in the BSON representation.
        """

        def __init__(self, time: int | datetime, inc: int) -> None:
            """Create a timestamp from seconds or a datetime and an increment.

            Args:
                time: Unsigned 32-bit seconds since the Unix epoch, or a
                    ``datetime`` whose Unix timestamp supplies the seconds.
                inc: Unsigned 32-bit increment value.

            Raises:
                TypeError: ``time`` is neither an integer nor a datetime, or
                    ``inc`` is not an integer.
                ValueError: Either integer is outside the range 0 through
                    ``2**32 - 1``, or the datetime is outside that range.
            """
            ...

        @property
        def time(self) -> int:
            """Seconds since the Unix epoch, as an unsigned 32-bit integer."""
            ...

        @property
        def inc(self) -> int:
            """Unsigned 32-bit increment component of this timestamp."""
            ...

        def as_datetime(self) -> datetime:
            """Convert the timestamp's seconds component to a UTC datetime."""
            ...

        def __eq__(self, other: object) -> bool: ...
        def __lt__(self, other: Timestamp) -> bool: ...
        def __le__(self, other: Timestamp) -> bool: ...
        def __gt__(self, other: Timestamp) -> bool: ...
        def __ge__(self, other: Timestamp) -> bool: ...
        def __hash__(self) -> int: ...

__all__ = (
    "Timestamp",
)
