"""Tools for representing BSON binary data."""

from typing import TYPE_CHECKING

from ._bson import (
    BINARY_SUBTYPE,
    UUID_SUBTYPE,
    Binary,
)

if TYPE_CHECKING:
    from collections.abc import Buffer
    from typing import Self
    from uuid import UUID

    from .codec_options import UuidRepresentation

    class Binary(bytes):
        """BSON binary data represented as a ``bytes`` subclass.

        The BSON subtype is preserved alongside the byte payload and
        participates in equality and hashing. Constructing ``Binary`` from
        a buffer copies its contents.

        Args:
            data: Object exporting a compatible byte buffer, such as
                ``bytes``, ``bytearray``, or ``memoryview``.
            subtype: BSON binary subtype in the range 0 through 255.
                Defaults to :data:`BINARY_SUBTYPE`.

        Raises:
            TypeError: ``data`` does not export a byte buffer or ``subtype``
                is not an integer.
            ValueError: ``subtype`` is outside the range 0 through 255.
        """

        @property
        def subtype(self) -> int:
            """BSON binary subtype associated with this payload."""
            ...

        @classmethod
        def from_uuid(
            cls,
            uuid: UUID,
            uuid_representation: int = UuidRepresentation.STANDARD,
        ) -> Self:
            """Create BSON binary data from a UUID.

            Args:
                uuid: UUID value to convert.
                uuid_representation: UUID byte-order convention. Defaults
                    to :attr:`UuidRepresentation.STANDARD`.

            Returns:
                Binary payload with the selected subtype and byte order.

            Raises:
                TypeError: ``uuid`` or ``uuid_representation`` has an
                    invalid type.
                ValueError: The representation is invalid or is
                    :attr:`UuidRepresentation.UNSPECIFIED`.
            """
            ...

        def as_uuid(self, uuid_representation: int = 4) -> UUID:
            """Interpret this payload as a UUID.

            Args:
                uuid_representation: UUID byte-order convention. Defaults
                    to :attr:`UuidRepresentation.STANDARD`.

            Returns:
                UUID decoded from this binary payload.

            Raises:
                TypeError: ``uuid_representation`` has an invalid type.
                ValueError: The representation is invalid or incompatible
                    with this payload's subtype.
            """
            ...

        def __eq__(self, other: object) -> bool: ...
        def __ne__(self, other: object) -> bool: ...
        def __hash__(self) -> int: ...

        def __new__(cls, data: Buffer, subtype: int = 0) -> Self:
            """Create binary data from a buffer and BSON subtype.

            Args:
                data: Object exporting a compatible byte buffer. Its contents
                    are copied into the new value.
                subtype: BSON binary subtype in the range 0 through 255.
                    Defaults to :data:`BINARY_SUBTYPE`.

            Raises:
                TypeError: ``data`` does not export a compatible byte buffer
                    or ``subtype`` is not an integer.
                ValueError: ``subtype`` is outside the range 0 through 255.
            """
            ...

    BINARY_SUBTYPE: int
    UUID_SUBTYPE: int


__all__ = (
    "BINARY_SUBTYPE",
    "UUID_SUBTYPE",
    "Binary",
)
