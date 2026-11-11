"""Tools for working with the BSON decimal128 type."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._elune import Decimal128, create_decimal128_context

if TYPE_CHECKING:
    from decimal import Context, Decimal

    class Decimal128:
        """Represent a decimal number in BSON's IEEE 754 Decimal128 format.

        Values have 34 digits of precision and the exponent range supported by
        Decimal128. Instances preserve the encoded 16-byte BID representation;
        use :meth:`to_decimal` to obtain a :class:`decimal.Decimal` value.

        Args:
            value: Decimal text, a :class:`decimal.Decimal`, or a pair of
                64-bit integers ``(high, low)`` containing the BID encoding.

        Raises:
            TypeError: ``value`` has an unsupported type.
            ValueError: The decimal cannot be represented as Decimal128 or a
                BID pair does not contain exactly two valid integers.
        """

        def __init__(
            self,
            value: str | Decimal | tuple[int, int] | list[int],
        ) -> None:
            """Create a Decimal128 value from decimal data or BID words.

            Args:
                value: Decimal text, a :class:`decimal.Decimal`, or a
                    two-element ``(high, low)`` tuple or list of BID words.

            Raises:
                TypeError: ``value`` is not a string, Decimal, tuple, or list,
                    or a BID word is not an integer.
                ValueError: Decimal precision or exponent is outside the
                    Decimal128 range, the BID pair has the wrong length, or a
                    NaN contains an unsupported debug payload.
            """
            ...

        @staticmethod
        def from_bid(value: bytes) -> Decimal128:
            """Create a Decimal128 value from its 16-byte BID encoding.

            Args:
                value: Exactly 16 bytes containing the encoded Decimal128.

            Returns:
                The decoded Decimal128 value.

            Raises:
                TypeError: ``value`` is not ``bytes``.
                ValueError: ``value`` does not contain exactly 16 bytes.
            """
            ...

        @property
        def bid(self) -> bytes:
            """The 16-byte BID encoding of this value."""
            ...

        def to_decimal(self) -> Decimal:
            """Convert this value to :class:`decimal.Decimal`."""
            ...

        def __eq__(self, other: object) -> bool: ...
        def __ne__(self, other: object) -> bool: ...

    def create_decimal128_context() -> Context:
        """Create a decimal context configured for Decimal128 arithmetic.

        The context uses 34-digit precision, Decimal128's exponent limits,
        round-half-even rounding, and clamping. Invalid operations, overflow,
        and inexact results are not trapped by this context.

        Returns:
            A new :class:`decimal.Context` configured for Decimal128 values.
        """
        ...

__all__ = (
    "Decimal128",
    "create_decimal128_context",
)
