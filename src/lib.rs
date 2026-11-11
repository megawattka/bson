use pyo3::prelude::*;
use pyo3::types::PyTuple;

mod binary;
mod bridge;
mod builtins;
mod code;
mod codec_options;
mod datetime;
mod dbref;
mod decimal128;
mod decoder;
mod encoder;
mod errors;
mod int64;
mod keys;
mod objectid;
mod regex;
mod schema;
mod timestamp;

/// BSON codec implemented in Rust, with no Python implementation files.
#[pymodule(gil_used = false)]
fn _elune(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(encoder::encode, module)?)?;
    module.add_function(wrap_pyfunction!(decoder::decode, module)?)?;
    module.add_function(wrap_pyfunction!(decoder::decode_all, module)?)?;
    module.add_class::<codec_options::CodecOptions>()?;
    module.add_class::<codec_options::TypeEncoder>()?;
    module.add_class::<codec_options::TypeDecoder>()?;
    module.add_class::<codec_options::TypeCodec>()?;
    module.add_class::<codec_options::TypeRegistry>()?;
    module.add("BSONError", module.py().get_type::<errors::BSONError>())?;
    module.add("InvalidBSON", module.py().get_type::<errors::InvalidBSON>())?;
    module.add(
        "InvalidDocument",
        module.py().get_type::<errors::InvalidDocument>(),
    )?;
    module.add_class::<objectid::ObjectId>()?;
    module.add_class::<dbref::DBRef>()?;
    module.add("InvalidId", module.py().get_type::<errors::InvalidId>())?;
    builtins::register(module)?;
    code::register(module)?;
    module.add_class::<decimal128::Decimal128>()?;
    module.add_class::<keys::MinKey>()?;
    module.add_class::<keys::MaxKey>()?;
    module.add_class::<regex::Regex>()?;
    module.add_class::<timestamp::Timestamp>()?;
    module.add_class::<datetime::DatetimeMS>()?;
    codec_options::register(module)?;
    module.add_function(wrap_pyfunction!(
        decimal128::create_decimal128_context,
        module
    )?)?;
    module.add(
        "DEFAULT_CODEC_OPTIONS",
        Py::new(module.py(), codec_options::CodecOptions::default())?,
    )?;
    let modules = module.py().import("sys")?.getattr("modules")?;
    let importlib_machinery = module.py().import("importlib.machinery")?;
    let builtin_importer = importlib_machinery.getattr("BuiltinImporter")?;
    let spec_from_loader = module
        .py()
        .import("importlib.util")?
        .getattr("spec_from_loader")?;
    for (name, exports) in [
        ("code", &["Code"][..]),
        ("dbref", &["DBRef"][..]),
        (
            "decimal128",
            &["Decimal128", "create_decimal128_context"][..],
        ),
        ("min_key", &["MinKey"][..]),
        ("max_key", &["MaxKey"][..]),
        ("regex", &["Regex"][..]),
        ("timestamp", &["Timestamp"][..]),
        ("datetime_ms", &["DatetimeMS"][..]),
        (
            "binary",
            &[
                "Binary",
                "UuidRepresentation",
                "BINARY_SUBTYPE",
                "UUID_SUBTYPE",
            ][..],
        ),
        ("int64", &["Int64"][..]),
        ("objectid", &["ObjectId"][..]),
        (
            "codec_options",
            &[
                "CodecOptions",
                "DEFAULT_CODEC_OPTIONS",
                "DatetimeConversion",
                "TypeEncoder",
                "TypeDecoder",
                "TypeCodec",
                "TypeRegistry",
            ][..],
        ),
        (
            "errors",
            &["BSONError", "InvalidBSON", "InvalidDocument", "InvalidId"][..],
        ),
    ] {
        let fullname = format!("elune.{name}");
        let child = PyModule::new(module.py(), &fullname)?;
        child.setattr("__package__", "elune")?;
        child.setattr(
            "__spec__",
            spec_from_loader.call1((&fullname, &builtin_importer))?,
        )?;
        for export in exports {
            child.add(*export, module.getattr(*export)?)?;
        }
        child.add("__all__", exports.to_vec())?;
        modules.set_item(&fullname, &child)?;
        module.add(name, child)?;
    }
    module.add(
        "__all__",
        PyTuple::new(
            module.py(),
            [
                "BINARY_SUBTYPE",
                "DEFAULT_CODEC_OPTIONS",
                "UUID_SUBTYPE",
                "BSONError",
                "Binary",
                "Code",
                "CodecOptions",
                "DatetimeConversion",
                "DatetimeMS",
                "DBRef",
                "Decimal128",
                "Int64",
                "InvalidBSON",
                "InvalidDocument",
                "InvalidId",
                "MaxKey",
                "MinKey",
                "ObjectId",
                "Regex",
                "Timestamp",
                "UuidRepresentation",
                "create_decimal128_context",
                "decode",
                "decode_all",
                "encode",
            ],
        )?,
    )?;
    Ok(())
}
