//! JSON conversion of nested BSON values with cycle and depth checks.

use std::collections::HashSet;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple, PyType};

use super::Kind;
use super::conversion::{check_external, check_keys, external};
use crate::{bridge, datetime::DatetimeMS, dbref::DBRef, decimal128::Decimal128};
use crate::{
    keys::{MaxKey, MinKey},
    objectid::ObjectId,
    regex::Regex,
    timestamp::Timestamp,
};

pub(super) fn serialize<'py>(
    value: &Bound<'py, PyAny>,
    cls: &Bound<'py, PyType>,
    kind: Kind,
) -> PyResult<Bound<'py, PyAny>> {
    // Union serializers must be able to select the correct BSON type.
    if !value.is_instance(cls)? {
        return Err(PyValueError::new_err("unexpected BSON type for serializer"));
    }
    let doc = external(value, kind)?;
    check_external(&doc, kind)?;
    let mut active = HashSet::new();
    active.insert(value.as_ptr() as usize);
    json_value(doc.as_any(), &mut active)
}

/// Convert nested BSON values before Pydantic's Any serializer sees int/str/bytes
/// subclasses. Unknown leaves are left to Pydantic (datetime, UUID, errors, ...).
fn json_value<'py>(
    value: &Bound<'py, PyAny>,
    active: &mut HashSet<usize>,
) -> PyResult<Bound<'py, PyAny>> {
    if active.len() >= 100 {
        return Err(PyValueError::new_err("JSON nesting exceeds 100 containers"));
    }
    let py = value.py();
    let kind = if value.is_instance(bridge::binary(py)?.as_any())? {
        Some(Kind::Binary)
    } else if value.is_instance(bridge::code(py)?.as_any())? {
        Some(Kind::Code)
    } else if value.is_instance_of::<Timestamp>() {
        Some(Kind::Timestamp)
    } else if value.is_instance_of::<Regex>() {
        Some(Kind::Regex)
    } else if value.is_instance_of::<DBRef>() {
        Some(Kind::DBRef)
    } else if value.is_instance_of::<MinKey>() {
        Some(Kind::MinKey)
    } else if value.is_instance_of::<MaxKey>() {
        Some(Kind::MaxKey)
    } else {
        None
    };
    let container = kind.is_some()
        || value.is_instance_of::<PyDict>()
        || value.is_instance_of::<PyList>()
        || value.is_instance_of::<PyTuple>();
    let id = value.as_ptr() as usize;
    if container && !active.insert(id) {
        return Err(PyValueError::new_err("cyclic JSON value"));
    }
    let result = (|| {
        if let Some(kind) = kind {
            let doc = external(value, kind)?;
            check_external(&doc, kind)?;
            return json_value(doc.as_any(), active);
        }
        if value.is_instance_of::<ObjectId>() {
            return Ok(value.str()?.into_any());
        }
        if value.is_instance_of::<DatetimeMS>() || value.is_instance(bridge::int64(py)?.as_any())? {
            return py.get_type::<pyo3::types::PyInt>().call1((value,));
        }
        if value.is_instance_of::<Decimal128>() {
            return Ok(value.call_method0("to_decimal")?.str()?.into_any());
        }
        if let Ok(doc) = value.cast::<PyDict>() {
            check_keys(doc)?;
            let result = PyDict::new(py);
            for (key, item) in doc.iter() {
                result.set_item(key, json_value(&item, active)?)?;
            }
            return Ok(result.into_any());
        }
        if value.is_instance_of::<PyList>() || value.is_instance_of::<PyTuple>() {
            let result = PyList::empty(py);
            for item in value.try_iter()? {
                result.append(json_value(&item?, active)?)?;
            }
            return Ok(result.into_any());
        }
        Ok(value.clone())
    })();
    if container {
        active.remove(&id);
    }
    result
}
