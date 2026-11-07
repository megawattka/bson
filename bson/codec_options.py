"""Tools for specifying BSON codec options."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from ._bson import (
    DEFAULT_CODEC_OPTIONS,
    CodecOptions,
    DatetimeConversion,
    UuidRepresentation,
)

if TYPE_CHECKING:
    from enum import IntEnum

    class DatetimeConversion(IntEnum):
        """Policy for converting BSON dates to Python values.

        ``DATETIME`` raises when a date is outside Python's ``datetime`` range;
        ``DATETIME_CLAMP`` clamps it to the nearest representable boundary;
        ``DATETIME_MS`` returns a :class:`DatetimeMS` value; and
        ``DATETIME_AUTO`` returns a ``datetime`` when representable and a
        ``DatetimeMS`` otherwise.
        """

        DATETIME = 1
        """Return ``datetime`` values, raising if a date is out of range."""

        DATETIME_CLAMP = 2
        """Clamp out-of-range dates to Python's ``datetime`` limits."""

        DATETIME_MS = 3
        """Return dates as millisecond values using :class:`DatetimeMS`."""

        DATETIME_AUTO = 4
        """Return ``datetime`` when possible, otherwise :class:`DatetimeMS`."""

    class UuidRepresentation(IntEnum):
        """UUID byte-order and BSON binary-subtype conventions.

        Members select the representation used when encoding native
        :class:`uuid.UUID` objects and interpreting UUID-compatible BSON
        binary values.
        """

        UNSPECIFIED = 0
        """Do not encode or decode native UUID values implicitly."""

        STANDARD = 4
        """Use standard UUID byte order and BSON binary subtype 4."""

        PYTHON_LEGACY = 3
        """Use Python legacy UUID byte order and BSON binary subtype 3."""

        JAVA_LEGACY = 5
        """Use Java legacy UUID byte order and BSON binary subtype 3."""

        CSHARP_LEGACY = 6
        """Use C# legacy UUID byte order and BSON binary subtype 3."""

    class CodecOptions:
        """Immutable settings controlling BSON encoding and decoding.

        Args:
            uuid_representation: UUID byte-order convention, represented by a
                member of :class:`UuidRepresentation`. Defaults to
                :attr:`UuidRepresentation.UNSPECIFIED`.
            tz_aware: Whether decoded datetimes should be timezone-aware.
                Defaults to ``False``.
            datetime_conversion: Policy for BSON datetimes that are outside
                Python's ``datetime`` range. Defaults to
                :attr:`DatetimeConversion.DATETIME`.

        Raises:
            TypeError: An option has an invalid type.
            ValueError: An option is not one of the supported values.
        """

        def __init__(
            self,
            uuid_representation: int = UuidRepresentation.UNSPECIFIED,
            *,
            tz_aware: bool = False,
            datetime_conversion: int = DatetimeConversion.DATETIME,
        ) -> None:
            """Initialize immutable BSON codec settings.

            Args:
                uuid_representation: UUID representation value. Defaults to
                    ``0`` (:attr:`UuidRepresentation.UNSPECIFIED`).
                tz_aware: Whether decoded datetimes include timezone
                    information. Defaults to ``False``.
                datetime_conversion: Datetime conversion policy. Defaults to
                    ``1`` (:attr:`DatetimeConversion.DATETIME`).

            Raises:
                TypeError: An option has an invalid type.
                ValueError: A representation or conversion policy is unsupported.
            """
            ...

        @property
        def uuid_representation(self) -> int:
            """UUID representation used for encoding and decoding."""
            ...

        @property
        def tz_aware(self) -> bool:
            """Whether decoded datetimes are timezone-aware."""
            ...

        @property
        def datetime_conversion(self) -> int:
            """Datetime conversion policy used when decoding BSON dates."""
            ...

        def with_options(
            self,
            *,
            uuid_representation: int | None = None,
            tz_aware: bool | None = None,
            datetime_conversion: int | None = None,
        ) -> Self:
            """Return a new instance with selected options replaced.

            Options passed as ``None`` retain their current values.

            Args:
                uuid_representation: Replacement UUID representation, if given.
                tz_aware: Replacement timezone-awareness setting, if given.
                datetime_conversion: Replacement datetime conversion policy,
                    if given.

            Returns:
                A new :class:`CodecOptions` with the selected settings.

            Raises:
                TypeError: An option has an invalid type.
                ValueError: A representation or conversion policy is unsupported.
            """
            ...

    DEFAULT_CODEC_OPTIONS: CodecOptions

__all__ = (
    "DEFAULT_CODEC_OPTIONS",
    "CodecOptions",
    "DatetimeConversion",
    "UuidRepresentation",
)
