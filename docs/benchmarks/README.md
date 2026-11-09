# BSON benchmark charts

Dark blue: PyMongo BSON with its native C extension, independently installed
as `_p_bson`. Light blue: this project's Rust BSON codec, release build.

![Encoding](encode.png)
![Decoding](decode.png)
![Batch decoding](decode_all.png)

Each pair shows median microseconds per call; lower is better. Whiskers show
the minimum and maximum of seven repeats. Each panel uses its own linear
axis starting at zero. `decode_all` measures batches of 100 documents, except
`empty_stream`, which contains no documents. All cases are shown, including
those where PyMongo is faster. These are local, single-threaded microbenchmarks,
not universal application-level performance claims.

Raw samples and runtime metadata are in `results.json`. SVG versions are also
included. Inputs and correctness checks reuse the existing benchmark helpers;
both implementations are warmed up and timing order alternates.

From the repository root, after preparing `_p_bson` using the existing setup
script and building this extension with `maturin develop --release`:

```sh
python -m benchmarks.charts measure
python -m pip install matplotlib
python -m benchmarks.charts render
```

Measurement does not require matplotlib. Rendering only reads JSON and can run
under a different interpreter. The committed measurements used Windows x64,
Python 3.13.7 free-threaded with the GIL disabled; rendering used Python 3.12.
