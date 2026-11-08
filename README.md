# 🦀 BSON — Rust performance and Python simplicity.

**A fast, native BSON codec for Python 3.12+, powered by Rust and PyO3, with a 1:1-compatible pymongo `bson` API.**

Encode documents, decode BSON streams, and work with rich BSON types through a 1:1-compatible pymongo `bson` API. The project focuses on two goals: **speed** and drop-in API compatibility with pymongo `bson`, while preserving strict BSON validation.

> **Compatibility warning:** using this package together with PyMongo's BSON implementation is **not recommended**. Both packages use the `bson` import namespace, so installing them in the same environment can cause import conflicts. Their `ObjectId`, `Binary`, `Code`, `Decimal128`, `Timestamp`, `CodecOptions`, and other values are distinct types and must not be mixed.

## ✨ Highlights

- **Strict typing:** designed for Pyright's `strict` mode, with explicitly typed Python API declarations for static analysis and IDE support. Strict type checking is a development target alongside runtime correctness and performance.

- **Native speed:** Rust-powered `encode`, `decode`, and `decode_all`.
- **Speed-focused implementation:** optimized traversal, bounded field-name reuse, and efficient batch decoding.
- **Rich documents:** nested mappings, arrays, Unicode, and binary payloads.
- **BSON types:** `ObjectId`, `Binary`, `Int64`, `DBRef`, `Decimal128`, and `Timestamp`.
- **Beyond scalars:** `Regex`, `Code`, `MinKey`, `MaxKey`, dates, and `DatetimeMS`.
- **Explicit UUID handling:** standard and legacy representations.
- **Custom type codecs:** implemented `TypeEncoder`, `TypeDecoder`, `TypeCodec`, and `TypeRegistry`, including fallback encoding.
- **Built for confidence:** Python type annotations and differential tests against an independent PyMongo BSON package.

## 🚀 Build from source

### Python ABI and free-threaded builds

The extension uses the version-specific CPython ABI, not `abi3`. Build and
install a separate wheel for each Python version, platform, and ABI. Standard
CPython and free-threaded CPython require different wheels (for example,
`cp313-cp313` versus `cp313-cp313t`). Existing `abi3` wheels are not converted.

Free-threaded CPython 3.13t is supported: importing `bson` does not enable the
GIL. Build using that interpreter, for example:

```sh
uv venv --python 3.13t .venv
uv sync --python 3.13t --group dev
uv run maturin develop --release
uv run python -c "import sys, bson; assert not sys._is_gil_enabled()"
```

Calls can run concurrently without a module-wide lock. Callers must not mutate
documents, buffers, or codec state while another thread is using them. Custom
codecs and timezone callbacks must themselves be thread-safe when shared.
This does not release the GIL on conventional CPython builds, and does not
add subinterpreter support (a separate PyO3 limitation). CI covers Python 3.12,
3.13, and 3.13t; wheel builds target each interpreter separately.

Requirements: **Python 3.12+**, Rust/Cargo, and a system C/C++ toolchain. On Windows, install Visual Studio Build Tools with C++ support.

From the repository root:

```sh
uv sync --group dev
uv run maturin develop --release
```

Build a distributable wheel:

```sh
uv run maturin build --release
```

## ⚡ Quick start

```python
from bson import ObjectId, decode, decode_all, encode

document = {
    "_id": ObjectId(),
    "name": "Hello, BSON! 🦀",
    "values": [42, True, None],
    "payload": b"\x00\x01\x02",
}

data = encode(document)
assert decode(data) == document
assert decode_all(data + data) == [document, document]
assert decode_all(b"") == []
```

### UUIDs

```python
from uuid import UUID
from bson import CodecOptions, UuidRepresentation, decode, encode

options = CodecOptions(uuid_representation=UuidRepresentation.STANDARD)
value = UUID("00112233-4455-6677-8899-aabbccddeeff")
data = encode({"id": value}, codec_options=options)
assert decode(data, codec_options=options)["id"] == value
```

The default representation is `UNSPECIFIED`: choose a representation before encoding `uuid.UUID`. Prefer `STANDARD` for new data; legacy modes require knowing the original application's byte order.

### Rich BSON types

```python
from datetime import datetime, timezone

from bson import Decimal128, Int64, Regex, Timestamp, decode, encode

document = {
    "price": Decimal128("19.95"),
    "counter": Int64(1),
    "created": datetime(2025, 1, 1, tzinfo=timezone.utc),
    "position": Timestamp(7, 9),
    "pattern": Regex("^hello", "im"),
}

data = encode(document)
restored = decode(data)
assert restored["price"] == document["price"]
```

## 📖 API

### Compatibility warning

The API is modeled after PyMongo's `bson`, but this is a standalone implementation, not a replacement BSON backend for the PyMongo driver. **Using the two implementations together is not recommended**, including installing them in the same environment or mixing their objects and type registries. Keep them in separate environments; exchange BSON bytes rather than package-specific Python objects.

| Function | Result |
| :--- | :--- |
| `encode(document, check_keys=False, codec_options=None)` | BSON as `bytes` |
| `decode(data, codec_options=None)` | One document as a `dict`; trailing bytes are rejected |
| `decode_all(data, codec_options=None)` | A list of documents from a concatenated BSON stream |

- Keys must be strings without NUL characters. `check_keys=True` also rejects keys starting with `$` or containing `.`.
- Python integers use int32 or int64 as appropriate. Values outside the signed 64-bit range raise `OverflowError`.
- BSON int64 decodes to `Int64`, arrays to `list`, and binary subtype 0 to `bytes`.
- Dates decode without `tzinfo` by default. Use `CodecOptions(tz_aware=True)` for UTC-aware dates.
- Set `CodecOptions(tz_aware=True, tzinfo=zone)` to decode dates in a specific timezone, including custom `datetime.tzinfo` subclasses and `zoneinfo.ZoneInfo`.
- `DatetimeConversion` modes and `DatetimeMS` handle dates beyond Python's `datetime` range.
- Invalid documents raise `InvalidDocument`; malformed BSON raises `InvalidBSON`.
- Nesting is limited to 100 containers. Size is constrained by the BSON format rather than MongoDB's server-side 16 MiB limit.

### Custom type codecs

Custom codecs and type registries are implemented. Import them from `bson.codec_options` (or directly from `bson`):

| Class | Implement in a subclass |
| :--- | :--- |
| `TypeEncoder` | `python_type` property and `transform_python(value)` method |
| `TypeDecoder` | `bson_type` property and `transform_bson(value)` method |
| `TypeCodec` | Both pairs above, for bidirectional conversion |
| `TypeRegistry` | No subclass needed; pass codec instances and an optional `fallback_encoder` |

`python_type` identifies the custom Python type to encode. `bson_type` is the **Python type produced by BSON decoding**, not a numeric BSON type code. Register codec **instances**, then pass the registry through `CodecOptions` to `encode`, `decode`, or `decode_all`.

For example, store `decimal.Decimal` as a BSON string and restore it on decoding:

```python
from decimal import Decimal
from typing import override

from bson import decode, decode_all, encode
from bson.codec_options import CodecOptions, TypeCodec, TypeRegistry


class DecimalCodec(TypeCodec):
    """Decimal codec."""

    @property
    def python_type(self) -> type[Decimal]:
        """Python type of value."""
        return Decimal

    @property
    def bson_type(self) -> type[str]:
        """Bson type of value."""
        return str

    @override
    def transform_python(self, value: Decimal) -> str:
        return str(value)

    @override
    def transform_bson(self, value: str) -> Decimal:
        return Decimal(value)


registry = TypeRegistry([DecimalCodec()])
options = CodecOptions(type_registry=registry)
document = {"price": Decimal("19.9500"), "values": [Decimal("0.125")]}
data = encode(document, codec_options=options)

assert decode(data) == {"price": "19.9500", "values": ["0.125"]}
assert decode(data, codec_options=options) == document
assert decode_all(data + data, codec_options=options) == [document, document]
```

**Decoder scope:** this example converts every decoded string value to `Decimal`, including values in nested documents and arrays. It is suitable only when all string values are decimal representations; other strings will raise a conversion error. Codec selection is type-based, not field-name-based. For mixed documents, choose a dedicated BSON representation such as `Decimal128` and use `bson_type = Decimal128` with `to_decimal()` in your decoder instead.

Registry behavior:

- Matching uses exact Python types, not subclasses. Nested document and array values also use the registry.
- Encoders cannot override `bool`, `bytes`, `dict`, `float`, `int`, `list`, `str`, or `tuple`, or subclasses of these built-in types.
- When multiple codecs target the same type, the last registered transformation for that direction wins.
- `registry.codecs` returns a new list of the registered codec instances; changing that list does not change the registry.
- Pass the options on every call that needs custom conversion. Without them, decoding returns the ordinary BSON Python types and unsupported custom values cannot be encoded.

### Fallback encoding

`TypeRegistry(fallback_encoder=callable)` handles otherwise unsupported Python values without requiring a separate encoder for each type. The callable must return a BSON-encodable replacement; it does not provide reverse conversion:

```python
from decimal import Decimal
from typing import Any

from bson import decode, encode
from bson.codec_options import CodecOptions, TypeRegistry


def fallback_encoder(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported value type: {type(value).__name__}")


options = CodecOptions(
    type_registry=TypeRegistry(fallback_encoder=fallback_encoder),
)
data = encode({"price": Decimal("19.95")}, codec_options=options)
assert decode(data) == {"price": "19.95"}
```

### Timezones and datetime conversion

```python
from datetime import UTC, datetime, timedelta, timezone
from bson import decode, decode_all, encode
from bson.codec_options import CodecOptions

zone = timezone(timedelta(hours=5, minutes=45))
options = CodecOptions(tz_aware=True, tzinfo=zone)
original = datetime(2024, 6, 1, 12, 30, tzinfo=UTC)
data = encode({"created": original})
restored = decode(data, codec_options=options)["created"]

assert restored == original
assert restored.hour == 18
assert restored.minute == 15
assert restored.tzinfo is zone
assert decode_all(data * 2, codec_options=options) == [
    {"created": restored}, {"created": restored},
]
```

- `tzinfo` must be a `datetime.tzinfo` instance and requires `tz_aware=True`; invalid types raise `TypeError`, and using it with naive decoding raises `ValueError`.
- Without a custom zone, `tz_aware=True` returns UTC-aware datetimes. The default `tz_aware=False` returns naive UTC datetimes.
- Conversion uses `datetime.astimezone()`, respecting custom `fromutc()` implementations, DST transitions, and `fold`. For example, use `ZoneInfo("America/New_York")` from `zoneinfo`; this requires an available IANA timezone database (system data or the optional `tzdata` package).
- BSON stores UTC milliseconds, not timezone names or offsets. The decoding zone does not change the encoded instant; aware input datetimes use their own UTC offset, and naive inputs are treated as UTC.
- `DATETIME` raises `InvalidBSON` when the UTC date or converted local date is out of range. `DATETIME_CLAMP` clamps to bounds safe for both UTC and the target zone; `DATETIME_AUTO` returns `DatetimeMS` outside those bounds. `DATETIME_MS` always returns raw milliseconds without timezone conversion.
- The same options apply to `DatetimeMS.as_datetime(options)`, nested values, and `decode_all`. `options.with_options(tzinfo=other_zone)` replaces the zone; `None` retains the current zone, as with the other optional replacements. Create fresh `CodecOptions` to reset the zone to its default.

## 📊 Benchmarks

Measured locally on **November 7, 2026**, using release build **0.1.0**.

| Setting | Value |
| :--- | :--- |
| CPU | AMD Ryzen 5 8645HS |
| OS | Windows 11, build 26200, x86-64 |
| Python | CPython 3.12.6 |
| Build | `maturin develop --release`, Rust/PyO3, LTO |
| Reference | PyMongo BSON as `_p_bson`, with its C extension enabled |
| Repeats | 7; all results are medians |

The installed `_p_bson` version could not be verified from distribution metadata. The reference setup script defaults to PyMongo 4.19.0.

### Known size trade-off

The compiled `_bson.pyd` is currently approximately **700 KiB**, while PyMongo's `_cbson.pyd` is approximately **70 KiB** in the comparison environment. This is a known limitation of the current standalone architecture: the extension contains the native codec, BSON types, validation, Python bindings, and error handling in one module. PyMongo ships its BSON implementation inside the larger PyMongo package, while this project packages the BSON layer independently. The larger extension file is a size trade-off, not an API or runtime limitation.

**Lower is better.** Ratio = `bson` time / PyMongo time; values below `1` favor this codec. Both implementations are warmed up, measurement order alternates, and correctness checks run outside the timed region. These microbenchmarks describe this environment, not a universal application-level speed guarantee.

### Encoding · µs/call

20,000 calls per repeat. `from_datetime` measures `ObjectId.from_datetime`, not document encoding.

| Case | bson | PyMongo | Ratio |
| :--- | ---: | ---: | ---: |
| small | 0.821 | 1.160 | 0.707 |
| nested | 5.760 | 5.331 | 1.080 |
| binary_64k | 3.419 | 5.760 | 0.594 |
| binary_4k | 0.337 | 1.059 | 0.318 |
| binary_pair | 11.932 | 15.327 | 0.778 |
| binary_nested | 5.384 | 5.674 | 0.949 |
| binary_old | 3.894 | 6.083 | 0.640 |
| unicode | 0.687 | 1.212 | 0.567 |
| from_datetime | 1.624 | 3.518 | 0.462 |

### Single-document decoding · µs/call

1,000 calls per repeat. These are the latest measurements after decode-path optimization.

| Case | bson | PyMongo | Ratio |
| :--- | ---: | ---: | ---: |
| empty | 0.133 | 0.479 | 0.277 |
| small | 0.511 | 1.071 | 0.477 |
| nested | 3.661 | 4.602 | 0.796 |
| binary_64k | 2.382 | 2.857 | 0.834 |
| binary_4k | 0.483 | 0.914 | 0.528 |
| binary_pair | 4.494 | 4.957 | 0.907 |
| binary_nested | 2.580 | 3.166 | 0.815 |
| binary_old | 6.000 | 8.890 | 0.675 |
| unicode | 2.942 | 3.443 | 0.855 |

### Batch decoding · µs/batch

`decode_all`: 100 documents per batch, 1,000 calls per repeat. Divide by 100 for time per document, except for `empty_stream`, which contains no documents. These are the latest measurements after batch-decoding optimization.

| Case | bson | PyMongo | Ratio |
| :--- | ---: | ---: | ---: |
| empty | 5.781 | 5.623 | 1.028 |
| small | 28.615 | 63.144 | 0.453 |
| nested | 363.672 | 471.053 | 0.772 |
| binary_64k | 4421.486 | 5001.686 | 0.884 |
| binary_4k | 30.623 | 34.004 | 0.901 |
| binary_pair | 7859.531 | 7976.296 | 0.985 |
| binary_nested | 3492.865 | 3562.497 | 0.980 |
| binary_old | 4911.916 | 5545.285 | 0.886 |
| unicode | 313.797 | 323.738 | 0.969 |
| mixed | 2156.967 | 2341.058 | 0.921 |
| empty_stream | 0.269 | 0.685 | 0.392 |

**Performance highlights:** the 1:1-compatible standalone BSON layer is faster than PyMongo in every latest single-document decoding case and in 10 of 11 `decode_all` cases. `decode_all(small)` completes in 28.615 µs versus 63.144 µs, while `decode_all(nested)` takes 363.672 µs versus 471.053 µs. The codec keeps strict boundary, UTF-8, type, depth, and malformed-input checks enabled while delivering this speed-first profile.

### Reproduce the results

From the repository root, with the virtual environment activated:

```sh
python -m maturin develop --release
python -m benchmarks.encode --repeat 7 --number 20000
python -m benchmarks.decode --repeat 7 --number 1000 --batch-size 100
```

`small` is a compact document with an ObjectId; `nested` includes an array of 100 integers and nested values; `binary_pair` contains two 64 KiB blocks; `binary_old` uses subtype 2; `unicode` repeats Unicode text with NUL characters. Exact inputs are defined in `benchmarks/encode.py`.

## 🧪 Testing

Prepare the independent reference package for differential tests and benchmarks:

```sh
python scripts/extract_pymongo_bson.py --version 4.19.0
python -m pytest tests -q
```

The setup script downloads PyMongo sources from PyPI, verifies SHA256, renames the BSON package to `_p_bson`, and builds its C extension. This isolated reference is only for tests and benchmarks; it does not install PyMongo alongside this package under the shared `bson` namespace. It requires network access and a system C/C++ toolchain. Without `_p_bson`, differential tests may be skipped; benchmarks require it.

## 📝 TODO

Implementation status:

- [ ] Custom document classes.
- [x] Type registries and custom type codecs.
- [x] Arbitrary `tzinfo` objects in `CodecOptions`.