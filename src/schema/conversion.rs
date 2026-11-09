//! Validation and conversion between BSON instances and external dictionaries.

use pyo3::exceptions::{PyAttributeError, PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyString, PyType};

use super::compound::key_name;
use super::{Kind, py_dict};
use crate::{bridge, dbref::DBRef};

fn encode_base64<'py>(value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    value
        .py()
        .import("base64")?
        .call_method1("b64encode", (value,))?
        .call_method1("decode", ("ascii",))
}

fn decode_base64<'py>(value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let kwargs = py_dict!(value.py(), { "validate" => true })?;
    // binascii.Error is a ValueError, so Pydantic reports a ValidationError.
    value
        .py()
        .import("base64")?
        .call_method("b64decode", (value,), Some(&kwargs))
}

fn check_pattern(value: &Bound<'_, PyAny>) -> PyResult<()> {
    let text = if let Ok(bytes) = value.cast::<PyBytes>() {
        std::str::from_utf8(bytes.as_bytes())
            .map_err(|_| PyValueError::new_err("regex pattern must be valid UTF-8"))?
    } else if let Ok(text) = value.cast::<PyString>() {
        text.to_str()?
    } else {
        return Err(PyValueError::new_err("regex pattern must be str or bytes"));
    };
    if text.contains('\0') {
        return Err(PyValueError::new_err("regex pattern must not contain NUL"));
    }
    Ok(())
}

pub(super) fn check_keys(doc: &Bound<'_, PyDict>) -> PyResult<()> {
    for key in doc.keys().iter() {
        let key = key
            .cast::<PyString>()
            .map_err(|_| PyValueError::new_err("document keys must be strings"))?;
        if key.to_str()?.contains('\0') {
            return Err(PyValueError::new_err("document keys must not contain NUL"));
        }
    }
    Ok(())
}

fn required<'py>(doc: &Bound<'py, PyDict>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    doc.get_item(key)?
        .ok_or_else(|| PyValueError::new_err(format!("missing {key}")))
}

/// Convert a ready instance to its external representation, retaining nested values.
pub(super) fn external<'py>(value: &Bound<'py, PyAny>, kind: Kind) -> PyResult<Bound<'py, PyDict>> {
    let py = value.py();
    match kind {
        Kind::Binary => {
            let subtype = value.getattr("_subtype").map_err(|error| {
                if error.is_instance_of::<PyAttributeError>(py) {
                    PyValueError::new_err("Binary has no subtype")
                } else {
                    error
                }
            })?;
            py_dict!(py, { "data" => encode_base64(value)?, "subtype" => subtype })
        }
        Kind::Timestamp => {
            py_dict!(py, { "time" => value.getattr("time")?, "inc" => value.getattr("inc")? })
        }
        Kind::Regex => {
            let pattern = value.getattr("pattern")?;
            check_pattern(&pattern)?;
            let pattern = if pattern.is_instance_of::<PyBytes>() {
                py_dict!(py, { "base64" => encode_base64(&pattern)? })?.into_any()
            } else {
                pattern
            };
            py_dict!(py, { "pattern" => pattern, "flags" => value.getattr("flags")? })
        }
        Kind::Code => py_dict!(py, {
            "code" => py.get_type::<PyString>().call1((value,))?,
            "scope" => value.getattr("scope")?,
        }),
        Kind::DBRef => value.extract::<PyRef<'_, DBRef>>()?.schema_document(py),
        Kind::MinKey | Kind::MaxKey => py_dict!(py, { key_name(kind) => 1 }),
    }
}

pub(super) fn construct<'py>(
    cls: &Bound<'py, PyType>,
    value: &Bound<'py, PyDict>,
    kind: Kind,
) -> PyResult<Bound<'py, PyAny>> {
    match kind {
        Kind::Binary => cls.call1((
            decode_base64(&required(value, "data")?)?,
            required(value, "subtype")?,
        )),
        Kind::Timestamp => cls.call1((required(value, "time")?, required(value, "inc")?)),
        Kind::Regex => {
            let pattern = required(value, "pattern")?;
            let pattern = if let Ok(bytes) = pattern.cast::<PyDict>() {
                decode_base64(&required(bytes, "base64")?)?
            } else {
                pattern
            };
            check_pattern(&pattern)?;
            cls.call1((pattern, required(value, "flags")?))
        }
        Kind::Code => cls.call1((required(value, "code")?, required(value, "scope")?)),
        Kind::DBRef => {
            check_keys(value)?;
            let extra = value.copy()?;
            let collection = required(value, "$ref")?;
            let id = required(value, "$id")?;
            let db = value
                .get_item("$db")?
                .unwrap_or_else(|| value.py().None().into_bound(value.py()));
            extra.del_item("$ref")?;
            extra.del_item("$id")?;
            if extra.contains("$db")? {
                extra.del_item("$db")?;
            }
            let kwargs = py_dict!(value.py(), { "_extra" => extra })?;
            cls.call((collection, id, db), Some(&kwargs))
        }
        Kind::MinKey | Kind::MaxKey => cls.call0(),
    }
}

/// Extra Python inputs are deliberately absent from the JSON branch.
pub(super) fn python_input<'py>(
    value: &Bound<'py, PyAny>,
    cls: &Bound<'py, PyType>,
    kind: Kind,
) -> PyResult<Bound<'py, PyAny>> {
    if value.is_instance(cls)? {
        return Ok(external(value, kind)?.into_any());
    }
    match kind {
        Kind::Code if value.is_instance_of::<PyString>() => {
            // A base Code passed to a subclass must retain its scope too.
            if crate::code::state(value)?.is_some() {
                Ok(external(value, kind)?.into_any())
            } else {
                Ok(
                    py_dict!(value.py(), { "code" => value, "scope" => value.py().None() })?
                        .into_any(),
                )
            }
        }
        Kind::Binary if !value.is_instance_of::<PyDict>() => {
            if value.is_instance(bridge::binary(value.py())?.as_any())? {
                return Ok(external(value, kind)?.into_any());
            }
            match value
                .py()
                .import("builtins")?
                .getattr("memoryview")?
                .call1((value,))
            {
                Ok(buffer) => Ok(py_dict!(value.py(), {
                    "data" => encode_base64(&buffer.call_method0("tobytes")?)?, "subtype" => 0,
                })?
                .into_any()),
                Err(error) if error.is_instance_of::<PyTypeError>(value.py()) => Ok(value.clone()),
                Err(error) => Err(error),
            }
        }
        Kind::Regex if crate::regex::is_native(value)? => Ok(external(value, kind)?.into_any()),
        _ => Ok(value.clone()),
    }
}

pub(super) fn check_external(doc: &Bound<'_, PyDict>, kind: Kind) -> PyResult<()> {
    match kind {
        Kind::Code => {
            let scope = required(doc, "scope")?;
            if !scope.is_none() {
                check_keys(scope.cast::<PyDict>()?)?;
            }
        }
        Kind::DBRef => check_keys(doc)?,
        Kind::Binary => {
            let subtype = required(doc, "subtype")?;
            if subtype.is_instance_of::<pyo3::types::PyBool>()
                || !subtype.is_instance_of::<pyo3::types::PyInt>()
            {
                return Err(PyValueError::new_err("subtype must be an integer"));
            }
            subtype
                .extract::<u8>()
                .map_err(|_| PyValueError::new_err("subtype must be in [0, 255]"))?;
        }
        _ => {}
    }
    Ok(())
}
