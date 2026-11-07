"""Public exception types raised by BSON encoding and decoding."""

from typing import TYPE_CHECKING

from ._bson import BSONError, InvalidBSON, InvalidDocument, InvalidId

if TYPE_CHECKING:
    class BSONError(Exception):
        """Base class for errors raised by BSON operations."""

    class InvalidBSON(BSONError):
        """Raised when BSON input is malformed or invalid during decoding."""

    class InvalidDocument(BSONError):
        """Raised when a document cannot be represented as valid BSON."""

    class InvalidId(BSONError):
        """Raised when an object identifier has an invalid value."""

__all__ = (
    "BSONError",
    "InvalidBSON",
    "InvalidDocument",
    "InvalidId",
)
