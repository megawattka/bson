"""BSON minimum-key marker type."""

from typing import TYPE_CHECKING

from ._bson import MinKey

if TYPE_CHECKING:
    class MinKey:
        """BSON value that sorts before every other BSON value."""

        def __eq__(self, other: object) -> bool: ...
        def __lt__(self, other: object) -> bool: ...
        def __le__(self, other: object) -> bool: ...
        def __gt__(self, other: object) -> bool: ...
        def __ge__(self, other: object) -> bool: ...
        def __hash__(self) -> int: ...

__all__ = (
    "MinKey",
)
