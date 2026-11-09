//! Small Core Schema builders and the shared Python dictionary macro.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyType};

macro_rules! py_dict {
    ($py:expr, { $($key:expr => $value:expr),* $(,)? }) => {{
        (|| {
            use pyo3::types::PyDictMethods as _;

            let dict = pyo3::types::PyDict::new($py);
            $(dict.set_item($key, $value)?;)*
            Ok::<_, pyo3::PyErr>(dict)
        })()
    }};
}

pub(crate) use py_dict;

pub(crate) fn int64(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    py_dict!(py, {
        "type" => "int",
        "strict" => true,
        "ge" => i64::MIN,
        "le" => i64::MAX,
    })
}

/// Call a validator after the nested schema, without ValidationInfo.
pub(crate) fn after_validator<'py>(
    function: &Bound<'py, PyAny>,
    schema: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    let py = schema.py();
    py_dict!(py, {
        "type" => "function-after",
        "function" => py_dict!(py, {
            "type" => "no-info",
            "function" => function,
        })?,
        "schema" => schema,
    })
}

pub(crate) fn is_instance<'py>(cls: &Bound<'py, PyType>) -> PyResult<Bound<'py, PyDict>> {
    py_dict!(cls.py(), {
        "type" => "is-instance",
        "cls" => cls,
    })
}

/// Call a validator around the nested schema, without ValidationInfo.
pub(crate) fn wrap_validator<'py>(
    function: &Bound<'py, PyAny>,
    schema: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    py_dict!(schema.py(), {
        "type" => "function-wrap",
        "function" => py_dict!(schema.py(), {
            "type" => "no-info",
            "function" => function,
        })?,
        "schema" => schema,
    })
}

pub(crate) fn union<'py>(
    py: Python<'py>,
    choices: &[Bound<'py, PyDict>],
) -> PyResult<Bound<'py, PyDict>> {
    py_dict!(py, {
        "type" => "union",
        "choices" => choices,
    })
}

/// Preserve Python values and serialize only in JSON mode.
pub(crate) fn json_serializer<'py>(
    function: &Bound<'py, PyAny>,
    return_schema: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    py_dict!(return_schema.py(), {
        "type" => "function-plain",
        "function" => function,
        "when_used" => "json",
        "return_schema" => return_schema,
    })
}

pub(crate) fn json_or_python<'py>(
    json_schema: &Bound<'py, PyDict>,
    python_schema: &Bound<'py, PyDict>,
    serialization: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    py_dict!(json_schema.py(), {
        "type" => "json-or-python",
        "json_schema" => json_schema,
        "python_schema" => python_schema,
        "serialization" => serialization,
    })
}
