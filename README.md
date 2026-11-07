# 🦀 BSON — Rust performance and Python simplicity.

**A fast, native BSON codec for Python 3.12+, powered by Rust and PyO3, with a 1:1-compatible `pymongo.bson` API.**

Encode documents, decode BSON streams, and work with rich BSON types through a 1:1-compatible `pymongo.bson` API. The project focuses on two goals: **speed** and drop-in API compatibility with `pymongo.bson`, while preserving strict BSON validation.

> **Compatibility warning:** this package mimics the pymongo `bson` API, but it is not object-compatible with PyMongo. Its `ObjectId`, `Binary`, `Code`, `Decimal128`, `Timestamp`, `CodecOptions`, and other values are distinct types. Do not mix objects from both packages together.

## ✨ Highlights

- **Strict typing:** designed for Pyright's `strict` mode, with explicitly typed Python API declarations for static analysis and IDE support. Strict type checking is a development target alongside runtime correctness and performance.

- **Native speed:** Rust-powered `encode`, `decode`, and `decode_all`.
- **Speed-focused implementation:** optimized traversal, bounded field-name reuse, and efficient batch decoding.
- **Rich documents:** nested mappings, arrays, Unicode, and binary payloads.
- **BSON types:** `ObjectId`, `Binary`, `Int64`, `DBRef`, `Decimal128`, and `Timestamp`.
- **Beyond scalars:** `Regex`, `Code`, `MinKey`, `MaxKey`, dates, and `DatetimeMS`.
- **Explicit UUID handling:** standard and legacy representations.
- **Built for confidence:** Python type annotations and differential tests against an independent PyMongo BSON package.

## 🚀 Build from source

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

The API is intentionally modeled 1:1 after `pymongo.bson`, but the implementations cannot be used together without a bridge. Direct `isinstance`, equality, subclassing, and type-registration behavior across the two packages is not guaranteed. Convert values explicitly whenever both packages are present in one application.

| Function | Result |
| :--- | :--- |
| `encode(document, check_keys=False, codec_options=None)` | BSON as `bytes` |
| `decode(data, codec_options=None)` | One document as a `dict`; trailing bytes are rejected |
| `decode_all(data, codec_options=None)` | A list of documents from a concatenated BSON stream |

- Keys must be strings without NUL characters. `check_keys=True` also rejects keys starting with `$` or containing `.`.
- Python integers use int32 or int64 as appropriate. Values outside the signed 64-bit range raise `OverflowError`.
- BSON int64 decodes to `Int64`, arrays to `list`, and binary subtype 0 to `bytes`.
- Dates decode without `tzinfo` by default. Use `CodecOptions(tz_aware=True)` for UTC-aware dates.
- `DatetimeConversion` modes and `DatetimeMS` handle dates beyond Python's `datetime` range.
- Invalid documents raise `InvalidDocument`; malformed BSON raises `InvalidBSON`.
- Nesting is limited to 100 containers. Size is constrained by the BSON format rather than MongoDB's server-side 16 MiB limit.

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

The setup script downloads PyMongo sources from PyPI, verifies SHA256, renames the BSON package, and builds its C extension. It requires network access and a system C/C++ toolchain. Without `_p_bson`, differential tests may be skipped; benchmarks require it.

## 📝 TODO

The following PyMongo API extensions are not implemented yet:

- [ ] Custom document classes.
- [ ] Type registries and custom type codecs.
- [ ] Arbitrary `tzinfo` objects in `CodecOptions`.