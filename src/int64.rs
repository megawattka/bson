//! Pydantic integration for the native-created int subclass.

use pyo3::prelude::*;
use pyo3::types::{PyCFunction, PyDict, PyInt, PyTuple, PyType};

use crate::schema;

#[pyfunction]
pub(crate) fn __get_pydantic_core_schema__<'py>(
    cls: &Bound<'py, PyType>,
    _source_type: &Bound<'py, PyAny>,
    _handler: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py = cls.py();
    let integer = schema::int64(py)?;
    let class = cls.clone().unbind();
    let validate = PyCFunction::new_closure(
        py,
        Some(c"validate_int64"),
        None,
        move |args: &Bound<'_, PyTuple>, _kwargs: Option<&Bound<'_, PyDict>>| {
            let (value, handler) = args.extract::<(Bound<'_, PyAny>, Bound<'_, PyAny>)>()?;
            // Validate first: even existing Int64 instances can exceed int64.
            let integer = handler.call1((&value,))?;
            let cls = class.bind(args.py());
            if value.is_instance(cls)? {
                Ok(value.unbind())
            } else {
                cls.call1((integer,)).map(Bound::unbind)
            }
        },
    )?;
    let schema = schema::wrap_validator(validate.as_any(), &integer)?;
    schema.set_item(
        "serialization",
        schema::json_serializer(py.get_type::<PyInt>().as_any(), &integer)?,
    )?;
    Ok(schema)
}
