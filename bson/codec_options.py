"""Tools for specifying BSON codec options."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._bson import (
    DEFAULT_CODEC_OPTIONS,
    CodecOptions,
    TypeCodec,
    TypeDecoder,
    TypeEncoder,
    TypeRegistry,
    DatetimeConversion,
    UuidRepresentation,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from abc import ABC, abstractmethod
    from enum import IntEnum
    from typing import Any

    class TypeEncoder(ABC):
        """Base class for converting a custom Python type to a BSON value.

        Subclasses must override ``python_type`` and ``transform_python``.
        Registered encoders match exact types, not subclasses, and cannot
        replace encoding for supported built-in types or their subclasses.
        """

        @property
        @abstractmethod
        def python_type(self) -> type[Any]:
            """Python type handled by this encoder; must be overridden.

            Raises:
                TypeError: The base implementation is accessed.
            """
            ...

        @abstractmethod
        def transform_python(self, _value: object) -> object:
            """Convert a custom value to a BSON-encodable value.

            Args:
                _value: Value whose exact type matches ``python_type``.

            Returns:
                A replacement value supported by the BSON encoder.

            Raises:
                TypeError: The base implementation is called.
            """
            ...

    class TypeDecoder(ABC):
        """Base class for converting a decoded BSON value to a custom type.

        Subclasses must override ``bson_type`` and ``transform_bson``.
        Registered decoders match the exact Python type produced by BSON
        decoding, not its subclasses.
        """

        @property
        @abstractmethod
        def bson_type(self) -> type[object]:
            """Decoded Python type handled by this decoder; must be overridden.

            Raises:
                TypeError: The base implementation is accessed.
            """
            ...

        @abstractmethod
        def transform_bson(self, _value: object) -> object:
            """Convert a decoded BSON value to a custom Python value.

            Args:
                _value: Value whose exact type matches ``bson_type``.

            Returns:
                The custom value to include in the decoded document.

            Raises:
                TypeError: The base implementation is called.
            """
            ...

    class TypeCodec(TypeEncoder, TypeDecoder):
        """Base class for a bidirectional custom type codec.

        Subclasses must define ``python_type``, ``transform_python``,
        ``bson_type``, and ``transform_bson`` as described by
        :class:`TypeEncoder` and :class:`TypeDecoder`.

        This implementation does not inherit from those classes and does not
        supply their properties or transformation methods.
        """

    class TypeRegistry:
        """Immutable registry of custom codecs and an optional fallback encoder.

        Codecs are selected by exact type. When multiple codecs handle the
        same type, the last registered transformation for that direction wins.

        Args:
            type_codecs: Iterable of encoder, decoder, or bidirectional codec
                instances. Defaults to an empty registry.
            fallback_encoder: Callable converting otherwise unsupported Python
                values to BSON-encodable values, or ``None`` to disable it.

        Raises:
            TypeError: A codec lacks the required interface, a declared type
                is not a type, an encoder targets a supported built-in type or
                its subclass, or the fallback encoder is not callable.
        """

        def __init__(
            self,
            type_codecs: Iterable[TypeEncoder | TypeDecoder | TypeCodec] | None = None,
            fallback_encoder: Callable[[Any], Any] | None = None,
        ) -> None:
            """Collect codecs and validate their declared types and fallback."""
            ...

        @property
        def codecs(self) -> list[TypeEncoder | TypeDecoder | TypeCodec]:
            """A new list of codec instances in registration order."""
            ...

        @property
        def fallback_encoder(self) -> Callable[[Any], Any] | None:
            """Fallback encoder for unsupported values, or ``None``."""
            ...

        def __repr__(self) -> str: ...

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
            type_registry: Custom codecs and fallback encoder, or ``None``.

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
            type_registry: TypeRegistry | None = None,
        ) -> None:
            """Initialize immutable BSON codec settings.

            Args:
                uuid_representation: UUID representation value. Defaults to
                    ``0`` (:attr:`UuidRepresentation.UNSPECIFIED`).
                tz_aware: Whether decoded datetimes include timezone
                    information. Defaults to ``False``.
                datetime_conversion: Datetime conversion policy. Defaults to
                    ``1`` (:attr:`DatetimeConversion.DATETIME`).
                type_registry: Custom codecs and fallback encoder, or ``None``.

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
            type_registry: TypeRegistry | None = None,
        ) -> CodecOptions:
            """Return a new instance with selected options replaced.

            Options passed as ``None`` retain their current values.

            Args:
                uuid_representation: Replacement UUID representation, if given.
                tz_aware: Replacement timezone-awareness setting, if given.
                datetime_conversion: Replacement datetime conversion policy,
                    if given.
                type_registry: Replacement registry, if given. ``None`` keeps
                    the current registry.

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
    "TypeCodec",
    "TypeDecoder",
    "TypeEncoder",
    "TypeRegistry",
    "UuidRepresentation",
)
