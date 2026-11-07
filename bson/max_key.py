"""BSON maximum-key marker type."""

from typing import TYPE_CHECKING

from ._bson import MaxKey

if TYPE_CHECKING:
    class MaxKey:
        """BSON value that sorts after every other BSON value."""

        def __eq__(self, other: object) -> bool: ...
        def __lt__(self, other: object) -> bool: ...
        def __le__(self, other: object) -> bool: ...
        def __gt__(self, other: object) -> bool: ...
        def __ge__(self, other: object) -> bool: ...
        def __hash__(self) -> int: ...

__all__ = (
    "MaxKey",
)
