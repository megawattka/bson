//! Fixed external contracts for compound BSON values.

use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::{int64, py_dict, union};

#[derive(Clone, Copy)]
pub(crate) enum Kind {
    Binary,
    Timestamp,
    Regex,
    Code,
    DBRef,
    MinKey,
    MaxKey,
}

fn string(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    py_dict!(py, { "type" => "str", "strict" => true })
}

fn cstring(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    let schema = string(py)?;
    schema.set_item("pattern", r"^[^\x00]*$")?;
    Ok(schema)
}

fn base64(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    let schema = string(py)?;
    schema.set_item(
        "pattern",
        r"^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$",
    )?;
    Ok(schema)
}

fn bounded_int(py: Python<'_>, min: i64, max: i64) -> PyResult<Bound<'_, PyDict>> {
    py_dict!(py, { "type" => "int", "strict" => true, "ge" => min, "le" => max })
}

fn nullable<'py>(schema: &Bound<'py, PyDict>) -> PyResult<Bound<'py, PyDict>> {
    py_dict!(schema.py(), { "type" => "nullable", "schema" => schema })
}

fn field<'py>(schema: &Bound<'py, PyDict>, required: bool) -> PyResult<Bound<'py, PyDict>> {
    py_dict!(schema.py(), {
        "type" => "typed-dict-field", "schema" => schema, "required" => required,
    })
}

fn default<'py>(
    schema: &Bound<'py, PyDict>,
    value: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    py_dict!(schema.py(), { "type" => "default", "schema" => schema, "default" => value })
}

fn document(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    py_dict!(py, {
        "type" => "dict", "strict" => true,
        "keys_schema" => cstring(py)?,
        "values_schema" => py_dict!(py, { "type" => "any" })?,
    })
}

fn object<'py>(fields: &Bound<'py, PyDict>, allow_extra: bool) -> PyResult<Bound<'py, PyDict>> {
    let schema = py_dict!(fields.py(), {
        "type" => "typed-dict", "fields" => fields,
        "extra_behavior" => if allow_extra { "allow" } else { "forbid" },
    })?;
    if allow_extra {
        schema.set_item("extras_schema", py_dict!(fields.py(), { "type" => "any" })?)?;
    }
    Ok(schema)
}

pub(super) fn external_schema(py: Python<'_>, kind: Kind) -> PyResult<Bound<'_, PyDict>> {
    let fields = PyDict::new(py);
    match kind {
        Kind::Binary => {
            fields.set_item("data", field(&base64(py)?, true)?)?;
            let subtype = default(
                &bounded_int(py, 0, 255)?,
                0_i64.into_pyobject(py)?.into_any(),
            )?;
            fields.set_item("subtype", field(&subtype, false)?)?;
        }
        Kind::Timestamp => {
            let integer = bounded_int(py, 0, u32::MAX.into())?;
            fields.set_item("time", field(&integer, true)?)?;
            fields.set_item("inc", field(&integer, true)?)?;
        }
        Kind::Regex => {
            let bytes = object(
                &py_dict!(py, { "base64" => field(&base64(py)?, true)? })?,
                false,
            )?;
            fields.set_item("pattern", field(&union(py, &[cstring(py)?, bytes])?, true)?)?;
            let flags = default(&int64(py)?, 0_i64.into_pyobject(py)?.into_any())?;
            fields.set_item("flags", field(&flags, false)?)?;
        }
        Kind::Code => {
            fields.set_item("code", field(&string(py)?, true)?)?;
            let scope = default(&nullable(&document(py)?)?, py.None().into_bound(py))?;
            fields.set_item("scope", field(&scope, false)?)?;
        }
        Kind::DBRef => {
            fields.set_item("$ref", field(&string(py)?, true)?)?;
            fields.set_item("$id", field(&py_dict!(py, { "type" => "any" })?, true)?)?;
            fields.set_item("$db", field(&nullable(&string(py)?)?, false)?)?;
        }
        Kind::MinKey | Kind::MaxKey => {
            fields.set_item(key_name(kind), field(&bounded_int(py, 1, 1)?, true)?)?;
        }
    }
    object(&fields, matches!(kind, Kind::DBRef))
}

pub(super) fn key_name(kind: Kind) -> &'static str {
    match kind {
        Kind::MinKey => "$minKey",
        Kind::MaxKey => "$maxKey",
        _ => unreachable!("not a sentinel"),
    }
}
