"""Public exports of the native bson codec."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._bson import *
from ._bson import __all__ as __all__
from ._bson import binary as binary
from ._bson import code as code
from ._bson import codec_options as codec_options
from ._bson import datetime_ms as datetime_ms
from ._bson import dbref as dbref
from ._bson import decimal128 as decimal128
from ._bson import errors as errors
from ._bson import int64 as int64
from ._bson import max_key as max_key
from ._bson import min_key as min_key
from ._bson import objectid as objectid
from ._bson import regex as regex
from ._bson import timestamp as timestamp
from .codec_options import (
    TypeCodec as TypeCodec,
    TypeDecoder as TypeDecoder,
    TypeEncoder as TypeEncoder,
    TypeRegistry as TypeRegistry,
)

if TYPE_CHECKING:
    from collections.abc import Buffer

    from .binary import (
        BINARY_SUBTYPE as BINARY_SUBTYPE,
        UUID_SUBTYPE as UUID_SUBTYPE,
        Binary as Binary,
    )
    from .code import Code as Code
    from .codec_options import (
        DEFAULT_CODEC_OPTIONS as DEFAULT_CODEC_OPTIONS,
        CodecOptions as CodecOptions,
        DatetimeConversion as DatetimeConversion,
        UuidRepresentation as UuidRepresentation,
    )
    from .datetime_ms import DatetimeMS as DatetimeMS
    from .dbref import DBRef as DBRef
    from .decimal128 import (
        Decimal128 as Decimal128,
        create_decimal128_context as create_decimal128_context,
    )
    from .errors import (
        BSONError as BSONError,
        InvalidBSON as InvalidBSON,
        InvalidDocument as InvalidDocument,
        InvalidId as InvalidId,
    )
    from .int64 import Int64 as Int64
    from .max_key import MaxKey as MaxKey
    from .min_key import MinKey as MinKey
    from .objectid import ObjectId as ObjectId
    from .regex import Regex as Regex
    from .timestamp import Timestamp as Timestamp

    def encode(
        document: dict[str, Any],
        /,
        *,
        check_keys: bool = False,
        codec_options: CodecOptions | None = None,
    ) -> bytes:
        """Encode a document as BSON.

        Args:
            document: Dictionary to encode. All keys must be strings.
            check_keys: Reject keys starting with "$" or containing ".".
                Null characters in keys are always rejected.
            codec_options: Codec settings. Uses DEFAULT_CODEC_OPTIONS if None.

        Returns:
            BSON-encoded document as bytes.

        Raises:
            InvalidDocument: The document contains invalid keys or unsupported
                values, or exceeds the BSON size limit.
            TypeError: An argument has an invalid type.
            RecursionError: The document is cyclic or exceeds the nesting limit.
        """
        ...

    def decode(
        data: Buffer,
        /,
        *,
        codec_options: CodecOptions | None = None,
    ) -> dict[str, Any]:
        """Decode exactly one BSON document.

        Args:
            data: Buffer containing a single BSON document. Its element format
                must be compatible with unsigned bytes.
            codec_options: Codec settings. Uses DEFAULT_CODEC_OPTIONS if None.

        Returns:
            The decoded document as a dictionary.

        Raises:
            InvalidBSON: The input is malformed, truncated, or contains trailing
                data after the document.
            TypeError: An argument has an invalid type or an incompatible buffer
                format.
        """
        ...

    def decode_all(
        data: Buffer,
        /,
        *,
        codec_options: CodecOptions | None = None,
    ) -> list[dict[str, Any]]:
        """Decode concatenated BSON documents from a single buffer.

        Args:
            data: Buffer containing consecutive BSON documents, not a sequence
                of separate buffers. Its element format must be compatible with
                unsigned bytes.
            codec_options: Codec settings. Uses DEFAULT_CODEC_OPTIONS if None.

        Returns:
            Decoded documents in input order. Returns an empty list for an
            empty buffer.

        Raises:
            InvalidBSON: Any document in the input is malformed or truncated.
            TypeError: An argument has an invalid type or an incompatible buffer
                format.
        """
        ...
