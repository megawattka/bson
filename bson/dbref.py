"""MongoDB document references represented as BSON embedded documents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._bson import DBRef

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Self

    class DBRef:
        """Reference a document in a MongoDB collection.

        A DBRef stores a collection name, identifier, optional database name,
        and optional extra fields. BSON encodes it as an embedded document with
        ``$ref``, ``$id``, and (when provided) ``$db`` fields. Extra fields follow
        these standard fields in insertion order.

        DBRef objects are immutable with respect to their core attributes, but
        the referenced identifier and extra values are not deep-copied on
        construction. The object is hashable only when all values used in its
        hash are themselves hashable.

        Args:
            collection: Name of the referenced collection. Must be a string.
            id: Identifier of the referenced document. May be any value
                supported by the BSON encoder.
            database: Optional database name. Must be a string or ``None``.
            _extra: Optional mapping of additional reference fields. Entries
                are merged first; keyword fields with the same name override
                them.
            **kwargs: Additional reference fields, merged after ``_extra``.

        Raises:
            TypeError: ``collection`` or ``database`` has an invalid type.

        Notes:
            :meth:`as_doc` returns an insertion-ordered ``dict``. Unlike
            PyMongo, this implementation does not return ``SON``.
        """

        def __init__(
            self,
            collection: str,
            id: object,
            database: str | None = None,
            _extra: Mapping[str, Any] | None = None,
            **kwargs: object,
        ) -> None:
            """Initialize the reference fields and optional extra values."""
            ...

        @property
        def collection(self) -> str:
            """Name of the referenced collection."""
            ...

        @property
        def id(self) -> object:
            """Identifier of the referenced document."""
            ...

        @property
        def database(self) -> str | None:
            """Name of the referenced database, or ``None`` if unspecified."""
            ...

        def as_doc(self) -> dict[str, Any]:
            """Return the reference as an insertion-ordered BSON document.

            Returns:
                A dictionary containing ``$ref``, ``$id``, the optional ``$db``,
                and any extra fields.
            """
            ...

        def __getattr__(self, name: str) -> object: ...
        def __repr__(self) -> str: ...
        def __eq__(self, other: object) -> bool: ...
        def __ne__(self, other: object) -> bool: ...
        def __hash__(self) -> int: ...
        def __deepcopy__(self, memo: dict[int, Any]) -> Self: ...


__all__ = (
    "DBRef",
)
