"""Tools for representing JavaScript code in BSON."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._elune import Code

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Self

    class Code(str):
        """JavaScript code with an optional BSON scope document.

        ``Code`` behaves as a string containing JavaScript source. Its optional
        scope is encoded as part of BSON's JavaScript-with-scope value. Instances
        are unhashable and compare with other ``Code`` instances by source text.
        """

        __slots__ = ("_state",)

        def __new__(
            cls,
            code: str | Code,
            scope: Mapping[str, Any] | None = None,
            **kwargs: object,
        ) -> Self:
            """Create JavaScript code with an optional scope mapping.

            When ``code`` is another ``Code`` instance, its source and existing
            scope are copied. A supplied ``scope`` and keyword arguments update
            that scope; keyword arguments are merged last. Non-dict mappings are
            copied into a dictionary, while an existing dict remains shared.

            Args:
                code: JavaScript source text or an existing ``Code`` instance.
                scope: Optional mapping of scope variables. Defaults to ``None``.
                **kwargs: Additional scope variables.

            Returns:
                A new ``Code`` instance of ``cls``.

            Raises:
                TypeError: ``code`` is not a string or ``Code`` instance, or
                    ``scope`` is not a mapping.
            """
            ...

        @property
        def scope(self) -> dict[str, Any] | None:
            """Scope variables, or ``None`` when no scope was provided."""
            ...

        def __str__(self) -> str: ...
        def __repr__(self) -> str: ...
        def __eq__(self, other: object) -> bool: ...
        def __ne__(self, other: object) -> bool: ...
        def __hash__(self) -> int: ...

__all__ = (
    "Code",
)
