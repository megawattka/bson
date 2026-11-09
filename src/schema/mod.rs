//! Pydantic Core Schema integration without a runtime dependency on Pydantic.
//!
//! Builders describe schema, compound defines external contracts, conversion
//! validates and constructs values, and serialization handles nested BSON data.

mod builders;
mod compound;
mod conversion;
mod serialization;

use pyo3::prelude::*;
use pyo3::types::{PyCFunction, PyDict, PyTuple, PyType};

pub(crate) use builders::{
    after_validator, int64, is_instance, json_or_python, json_serializer, py_dict, union,
    wrap_validator,
};
pub(crate) use compound::Kind;

use compound::external_schema;
use conversion::{check_external, construct, python_input};
use serialization::serialize;

/// Assemble validation and serialization for a compound BSON type.
pub(crate) fn value_schema<'py>(
    cls: &Bound<'py, PyType>,
    kind: Kind,
) -> PyResult<Bound<'py, PyDict>> {
    let py = cls.py();
    let wire = external_schema(py, kind)?;
    let class = cls.clone().unbind();
    let create = PyCFunction::new_closure(
        py,
        Some(c"create_bson_value"),
        None,
        move |args: &Bound<'_, PyTuple>, _: Option<&Bound<'_, PyDict>>| {
            let value = args.get_item(0)?.cast_into::<PyDict>()?;
            construct(class.bind(args.py()), &value, kind).map(Bound::unbind)
        },
    )?;
    let json = after_validator(create.as_any(), &wire)?;
    let class = cls.clone().unbind();
    let validate = PyCFunction::new_closure(
        py,
        Some(c"validate_bson_value"),
        None,
        move |args: &Bound<'_, PyTuple>, _: Option<&Bound<'_, PyDict>>| {
            let (value, handler) = args.extract::<(Bound<'_, PyAny>, Bound<'_, PyAny>)>()?;
            let cls = class.bind(args.py());
            let input = python_input(&value, cls, kind)?;
            let validated = handler.call1((input,))?.cast_into::<PyDict>()?;
            if value.is_instance(cls)? {
                // Check semantic constraints too (Base64, document keys, etc.).
                check_external(&validated, kind)?;
                Ok(value.unbind())
            } else {
                construct(cls, &validated, kind).map(Bound::unbind)
            }
        },
    )?;
    let python = wrap_validator(validate.as_any(), &wire)?;
    // The validation input is a dict, but its result is a BSON instance.
    // Do not let the dict serializer inspect it in Python mode.
    python.set_item("serialization", py_dict!(py, { "type" => "any" })?)?;
    let class = cls.clone().unbind();
    let serializer = PyCFunction::new_closure(
        py,
        Some(c"serialize_bson_value"),
        None,
        move |args: &Bound<'_, PyTuple>, _: Option<&Bound<'_, PyDict>>| {
            serialize(&args.get_item(0)?, class.bind(args.py()), kind).map(Bound::unbind)
        },
    )?;
    let serialization = json_serializer(serializer.as_any(), &wire)?;
    json_or_python(&json, &python, &serialization)
}
