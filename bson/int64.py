"""Tools for representing BSON signed 64-bit integers."""

from typing import TYPE_CHECKING

from ._bson import Int64

if TYPE_CHECKING:
    class Int64(int):
        """Integer encoded using BSON's signed 64-bit integer type.

        ``Int64`` behaves like a Python ``int`` while preserving the BSON
        int64 representation when encoded.
        """

__all__ = (
    "Int64",
)
