# 🦀 BSON — Rust performance and Python simplicity.

A standalone BSON codec for Python, implemented in Rust with PyO3. Encode
Python dictionaries, decode BSON documents and streams, and work with BSON
types through a Python API modeled after PyMongo's `bson`.

The project targets CPython 3.12, 3.13, 3.14, and 3.15. Release builds cover
Linux x86_64 and aarch64, Windows x64, and macOS Intel and Apple Silicon.
There are no runtime Python dependencies.

## Installation

Packages are published at **https://python.wattka.dev/**. To install this
implementation, explicitly select its package index: use `--index` with uv
or `--index-url` with pip. The index URL includes `/simple/`; installing
`bson` from the default PyPI index may select a different project.

With uv, add it to a project:

```sh
uv add bson --index https://python.wattka.dev/simple/
```

With pip:

```sh
python -m pip install bson --index-url https://python.wattka.dev/simple/
```

Matching wheels do not require Rust. Installation from a source distribution
requires Rust/Cargo and a platform build toolchain.

> **Do not install this package alongside PyMongo.** Both provide the `bson`
> import namespace. This is an independent codec, not a replacement backend
> for the PyMongo driver, and it does not implement the entire PyMongo BSON
> API. Keep the implementations in separate environments and exchange BSON
> bytes rather than mixing their Python objects.

## Quick start

```python
from bson import ObjectId, decode, decode_all, encode

document = {
    "_id": ObjectId(),
    "name": "Hello, BSON!",
    "values": [42, True, None],
    "payload": b"\x00\x01\x02",
}

data = encode(document)
assert decode(data) == document
assert decode_all(data + data) == [document, document]
assert decode_all(b"") == []
```

| Function | Behavior |
| --- | --- |
| `encode(document, check_keys=False, codec_options=None)` | Encode a dictionary as `bytes`. |
| `decode(data, codec_options=None)` | Decode exactly one document; reject trailing bytes. |
| `decode_all(data, codec_options=None)` | Decode concatenated documents into a list. |

Decoding accepts `bytes` and compatible byte buffers, including `bytearray`
and `memoryview`. `decode_all` takes one concatenated buffer, not a list of
buffers.

## Types and validation

Supported values include nested dictionaries and arrays, strings, booleans,
`None`, floats, signed 64-bit integers, binary data, datetimes, and UUIDs.
BSON-specific types include:

- `ObjectId`, `Binary`, and `Int64`;
- `Decimal128`, `DBRef`, and `Timestamp`;
- `Regex`, `Code`, `MinKey`, and `MaxKey`;
- `DatetimeMS` for dates represented as integer milliseconds.

Python integers are encoded as int32 or int64 according to their value;
`Int64` explicitly selects int64. BSON int64 decodes to `Int64`, arrays to
`list`, and binary subtype 0 to `bytes`.

Dictionary keys must be strings without NUL characters. `check_keys=True`
also rejects keys starting with `$` or containing `.`. Unsupported values
and invalid keys raise `InvalidDocument`; malformed BSON raises
`InvalidBSON`. Integers outside the signed 64-bit range raise `OverflowError`.
Cycles and excessive nesting raise `RecursionError`; nesting is limited to
100 containers, including the root document.

### UUIDs

Choose a UUID representation explicitly. The default, `UNSPECIFIED`, does
not encode native `uuid.UUID` objects. Prefer `STANDARD` for new data:

```python
from uuid import UUID

from bson import decode, encode
from bson.binary import UuidRepresentation
from bson.codec_options import CodecOptions

options = CodecOptions(uuid_representation=UuidRepresentation.STANDARD)
value = UUID("00112233-4455-6677-8899-aabbccddeeff")

data = encode({"id": value}, codec_options=options)
assert decode(data, codec_options=options) == {"id": value}
```

Python, Java, and C# legacy UUID representations are also available. Choose
one only when it matches the byte order of existing data.

### Dates and timezones

BSON stores UTC milliseconds, not timezone names. Encoding treats naive
datetimes as UTC and converts aware datetimes using their UTC offset;
sub-millisecond precision is not preserved. Decoding returns naive UTC
datetimes by default.

```python
from datetime import UTC, datetime, timedelta, timezone

from bson import decode, encode
from bson.codec_options import CodecOptions

zone = timezone(timedelta(hours=3))
options = CodecOptions(tz_aware=True, tzinfo=zone)
instant = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

data = encode({"created": instant})
restored = decode(data, codec_options=options)["created"]
assert restored == instant
assert restored.hour == 15
assert restored.tzinfo is zone
```

Use `tz_aware=True` without `tzinfo` for UTC-aware results. Custom `tzinfo`
objects and `zoneinfo.ZoneInfo` are supported; named zones require an IANA
timezone database from the system or the optional `tzdata` package.

`DatetimeConversion` selects the policy for dates outside Python's
`datetime` range: `DATETIME` raises an error, `DATETIME_CLAMP` clamps the
value, `DATETIME_AUTO` returns `DatetimeMS` when needed, and `DATETIME_MS`
always returns `DatetimeMS`.

### Custom codecs

Use `TypeEncoder`, `TypeDecoder`, or `TypeCodec` with a `TypeRegistry` to
convert application types. For example, store `Decimal` as BSON Decimal128:

```python
from decimal import Decimal
from typing import override

from bson import Decimal128, decode, encode
from bson.codec_options import CodecOptions, TypeCodec, TypeRegistry


class DecimalCodec(TypeCodec):
    """Decimal codec."""

    @property
    def python_type(self) -> type[Decimal]:
        """Python type of value."""
        return Decimal

    @property
    def bson_type(self) -> type[Decimal128]:
        """Bson type of value."""
        return Decimal128

    @override
    def transform_python(self, value: Decimal) -> Decimal128:
        return Decimal128(value)

    @override
    def transform_bson(self, value: Decimal128) -> Decimal:
        return value.to_decimal()


options = CodecOptions(type_registry=TypeRegistry([DecimalCodec()]))
document = {"price": Decimal("19.95")}
data = encode(document, codec_options=options)
assert decode(data, codec_options=options) == document

```

Codecs match exact Python types, including values in nested documents.
Encoders cannot override supported built-in types or their subclasses.
`TypeRegistry(fallback_encoder=callable)` can provide a BSON-encodable
replacement for otherwise unsupported values. Pass the codec options to
every operation that needs the conversion.

## Pydantic integration

BSON types can be used directly in Pydantic v2 models and `TypeAdapter`,
without custom validators or `arbitrary_types_allowed`. Pydantic remains an
optional dependency. See the [Pydantic integration guide](docs/pydantic.md)
for installation, accepted values, JSON Schema, and BSON/JSON round trips.

## Building and testing

Development requires CPython 3.12+, Rust/Cargo, and a system build toolchain.
On Windows, install Visual Studio Build Tools with C++ support.
From the repository root:

```sh
uv sync --group dev
uv run maturin develop --release
uv run pytest tests -q
```

Build a distributable wheel with:

```sh
uv run maturin build --release
```

The extension uses a version-specific CPython ABI, not `abi3`: wheels are
specific to the Python version, platform, and ABI. Free-threaded Python
requires a separate build; the release matrix above targets ordinary
CPython, not `t`-suffixed interpreters. A free-threaded build does not make
shared mutable documents or custom callbacks automatically thread-safe.

For differential tests and benchmarks, prepare an isolated PyMongo BSON
reference:

```sh
uv run python scripts/extract_pymongo_bson.py --version 4.19.0
uv run pytest tests -q
```

The script downloads PyMongo sources, verifies the archive's SHA256, renames
its BSON package to `_p_bson`, and builds its C extension. It requires network
access and a C toolchain. This reference does not install a second package
under the `bson` namespace. Without it, reference-dependent tests may skip.

## Benchmarks

After building in release mode and preparing `_p_bson`:

```sh
uv run python -m benchmarks.encode --repeat 7 --number 20000
uv run python -m benchmarks.decode --repeat 7 --number 1000 --batch-size 100
```

These are local microbenchmarks, not a universal speed guarantee. Results
depend on document structure, Python version, allocator state, and platform.
In particular, a single large `bytes` field uses a specialized encoding path;
its speedup should not be generalized to arbitrary documents. Repeat runs
and compare representative application data before drawing conclusions.

## License

[MIT](LICENSE).