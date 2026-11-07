"""Tools for working with MongoDB ObjectIds."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from ._bson import ObjectId

if TYPE_CHECKING:
    from datetime import datetime

    class ObjectId:
        """A 12-byte BSON identifier with a timestamp and unique counter.

        ObjectIds can be constructed from their 12-byte binary representation,
        a 24-character hexadecimal string, another ``ObjectId``, or generated
        automatically. They sort by their binary value, beginning with the
        timestamp component.
        """

        def __init__(self, oid: str | ObjectId | bytes | None = None) -> None:
            """Create an ObjectId or generate a new one when omitted.

            Args:
                oid: Another ObjectId, exactly 12 bytes, or a 24-character
                    hexadecimal string. ``None`` generates a new identifier.

            Raises:
                TypeError: ``oid`` is not ``None``, ``str``, ``bytes``, or an
                    ObjectId.
                InvalidId: A string is not 24 hexadecimal characters or bytes
                    do not contain exactly 12 bytes.
            """
            ...

        @classmethod
        def from_datetime(cls, generation_time: datetime) -> Self:
            """Create an ObjectId containing the given timestamp.

            The remaining identifier bytes are zeroed, so the result is not
            guaranteed to be unique. Naive datetimes are treated as UTC, and
            timezone-aware datetimes are converted to UTC. Timestamp precision
            is one second.

            Args:
                generation_time: Datetime to encode in the timestamp portion.

            Returns:
                An ObjectId whose timestamp corresponds to ``generation_time``.

            Raises:
                TypeError: ``generation_time`` is not a ``datetime``.
                OverflowError: The UTC timestamp is outside the supported
                    unsigned 32-bit seconds range.
            """
            ...

        @classmethod
        def is_valid(cls, oid: object) -> bool:
            """Return whether a value can be used to construct an ObjectId.

            Args:
                oid: Value to validate.

            Returns:
                ``True`` for a valid ObjectId, 12-byte ``bytes``, or
                24-character hexadecimal string; otherwise ``False``.
            """
            ...

        @property
        def binary(self) -> bytes:
            """The 12-byte binary representation of this ObjectId."""
            ...

        @property
        def generation_time(self) -> datetime:
            """The timestamp component as a UTC-aware datetime.

            The returned datetime has zero microseconds because ObjectId
            timestamps have one-second precision.
            """
            ...

        def __eq__(self, other: object) -> bool: ...
        def __ne__(self, other: object) -> bool: ...
        def __lt__(self, other: ObjectId) -> bool: ...
        def __le__(self, other: ObjectId) -> bool: ...
        def __gt__(self, other: ObjectId) -> bool: ...
        def __ge__(self, other: ObjectId) -> bool: ...
        def __hash__(self) -> int: ...

__all__ = (
    "ObjectId",
)
