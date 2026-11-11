"""Tools for representing MongoDB regular expressions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._elune import Regex

if TYPE_CHECKING:
    import re

    class Regex:
        """BSON regular expression pattern and its options.

        The pattern may be text or bytes. String flags use the BSON option
        letters ``i``, ``l``, ``m``, ``s``, ``u``, and ``x``; integer flags are
        stored directly as a bit mask.
        """

        pattern: str | bytes
        """Regular expression pattern as text or bytes."""

        flags: int
        """Regular expression options stored as an integer bit mask."""

        def __init__(self, pattern: str | bytes, flags: str | int = 0) -> None:
            """Create a BSON regular expression.

            Args:
                pattern: Pattern text or bytes.
                flags: BSON option letters or their integer bit mask.
                    Defaults to ``0``.

            Raises:
                TypeError: ``pattern`` is not ``str`` or ``bytes``, or
                    ``flags`` is neither ``str`` nor ``int``.
            """
            ...

        @staticmethod
        def from_native(regex: re.Pattern[str] | re.Pattern[bytes]) -> Regex:
            """Create a BSON regex from a compiled Python regular expression.

            Args:
                regex: Compiled text or bytes regular expression.

            Returns:
                A BSON ``Regex`` with the same pattern and options.

            Raises:
                TypeError: ``regex`` is not a compiled regular expression.
            """
            ...

        def try_compile(self) -> re.Pattern[str] | re.Pattern[bytes]:
            """Compile this pattern with Python's :mod:`re` module.

            Returns:
                A compiled text or bytes regular expression.

            Raises:
                re.error: The pattern or flags are invalid for Python's regex
                    engine.
            """
            ...

        def __eq__(self, other: object) -> bool: ...

__all__ = (
    "Regex",
)
