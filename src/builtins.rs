//! Builtin subclasses with standard CPython method descriptors.
//! PyO3 cannot directly extend the variable-sized int/bytes layouts.
use pyo3::exceptions::{PyRuntimeError, PyTypeError, PyValueError};
use pyo3::ffi;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyInt, PyTuple, PyType};
use std::ffi::CStr;
use std::panic::{AssertUnwindSafe, catch_unwind};

struct Definition(ffi::PyMethodDef);
// SAFETY: immutable definitions contain only static strings/function pointers.
unsafe impl Sync for Definition {}

macro_rules! definition {
    ($name:ident, $python_name:literal, $handler:path, $flags:expr) => {
        mod $name {
            use super::*;
            unsafe extern "C" fn call(
                obj: *mut ffi::PyObject,
                args: *mut ffi::PyObject,
                kwargs: *mut ffi::PyObject,
            ) -> *mut ffi::PyObject {
                // SAFETY: CPython has attached this thread to the interpreter;
                // a GIL is not required on free-threaded builds.
                // Arguments match METH_VARARGS |
                // METH_KEYWORDS. The descriptor validates the receiver's type.
                let py = unsafe { Python::assume_gil_acquired() };
                let result = catch_unwind(AssertUnwindSafe(|| unsafe {
                    let obj = Bound::from_borrowed_ptr(py, obj);
                    let args = Bound::from_borrowed_ptr(py, args).downcast_into::<PyTuple>()?;
                    let kwargs = Bound::from_borrowed_ptr_or_opt(py, kwargs)
                        .map(|value| value.downcast_into::<PyDict>())
                        .transpose()?;
                    $handler(&obj, &args, kwargs.as_ref())
                }));
                match result {
                    Ok(Ok(value)) => value.into_ptr(),
                    Ok(Err(error)) => {
                        error.restore(py);
                        std::ptr::null_mut()
                    }
                    Err(_) => {
                        PyRuntimeError::new_err("panic in native BSON method").restore(py);
                        std::ptr::null_mut()
                    }
                }
            }
            pub(super) static DEF: Definition = Definition(ffi::PyMethodDef {
                ml_name: $python_name.as_ptr(),
                ml_meth: ffi::PyMethodDefPointer {
                    PyCFunctionWithKeywords: call,
                },
                ml_flags: ffi::METH_VARARGS | ffi::METH_KEYWORDS | $flags,
                ml_doc: std::ptr::null(),
            });
        }
    };
}

fn arguments<'py, const N: usize>(
    args: &Bound<'py, PyTuple>,
    kwargs: Option<&Bound<'py, PyDict>>,
    names: &[&str; N],
    required: usize,
) -> PyResult<[Option<Bound<'py, PyAny>>; N]> {
    if args.len() > names.len() {
        return Err(PyTypeError::new_err("too many positional arguments"));
    }
    let mut values = std::array::from_fn(|_| None);
    for (index, value) in args.iter().enumerate() {
        values[index] = Some(value);
    }
    if let Some(kwargs) = kwargs {
        for (key, value) in kwargs.iter() {
            let key = key.extract::<&str>()?;
            let index = names.iter().position(|name| *name == key).ok_or_else(|| {
                PyTypeError::new_err(format!("unexpected keyword argument: {key}"))
            })?;
            if values[index].is_some() {
                return Err(PyTypeError::new_err(format!("multiple values for {key}")));
            }
            values[index] = Some(value);
        }
    }
    for index in 0..required {
        if values[index].is_none() {
            return Err(PyTypeError::new_err(format!(
                "missing required argument: {}",
                names[index]
            )));
        }
    }
    Ok(values)
}

#[pyfunction]
#[pyo3(signature = (cls, *args, **kwargs))]
fn binary_constructor<'py>(
    cls: &Bound<'py, PyType>,
    args: &Bound<'py, PyTuple>,
    kwargs: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let values = arguments(args, kwargs, &["data", "subtype"], 1)?;
    let data = values[0].as_ref().unwrap();
    let subtype = match values[1].as_ref() {
        Some(value) if value.is_instance_of::<PyInt>() => value
            .extract::<u8>()
            .map_err(|_| PyValueError::new_err("subtype must be contained in [0, 256)"))?,
        Some(_) => return Err(PyTypeError::new_err("subtype must be an instance of int")),
        None => 0,
    };
    let py = cls.py();
    let payload = if data.is_instance_of::<PyBytes>() {
        data.clone()
    } else {
        py.import("builtins")?
            .getattr("memoryview")?
            .call1((data,))?
            .call_method0("tobytes")?
    };
    build_binary(cls, &payload, subtype)
}

/// Construct from a validated payload without parsing public constructor arguments.
pub fn build_binary<'py>(
    cls: &Bound<'py, PyType>,
    payload: &Bound<'py, PyAny>,
    subtype: u8,
) -> PyResult<Bound<'py, PyAny>> {
    let value = cls
        .py()
        .get_type::<PyBytes>()
        .getattr("__new__")?
        .call1((cls, payload))?;
    value.setattr("_subtype", subtype)?;
    Ok(value)
}

#[pyfunction]
fn subtype(obj: &Bound<'_, PyAny>) -> PyResult<u8> {
    obj.getattr("_subtype")?.extract()
}

fn from_uuid<'py>(
    cls: &Bound<'py, PyAny>,
    args: &Bound<'py, PyTuple>,
    kwargs: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let values = arguments(args, kwargs, &["uuid", "uuid_representation"], 1)?;
    let rep = values[1]
        .as_ref()
        .map(|value| value.extract())
        .transpose()?
        .unwrap_or(4);
    let (data, subtype) = crate::binary::_uuid_to_binary(values[0].as_ref().unwrap(), rep)?;
    cls.call1((data, subtype))
}

fn as_uuid<'py>(
    obj: &Bound<'py, PyAny>,
    args: &Bound<'py, PyTuple>,
    kwargs: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let values = arguments(args, kwargs, &["uuid_representation"], 0)?;
    let rep = values[0]
        .as_ref()
        .map(|value| value.extract())
        .transpose()?
        .unwrap_or(4);
    crate::binary::_binary_as_uuid(obj.downcast::<PyBytes>()?, subtype(obj)?, rep)
}

fn equals(obj: &Bound<'_, PyAny>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
    Ok(
        other.is_instance(crate::bridge::binary(obj.py())?.as_any())?
            && subtype(obj)? == subtype(other)?
            && obj.downcast::<PyBytes>()?.as_bytes() == other.downcast::<PyBytes>()?.as_bytes(),
    )
}

fn equal<'py>(
    obj: &Bound<'py, PyAny>,
    args: &Bound<'py, PyTuple>,
    kwargs: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let values = arguments(args, kwargs, &["other"], 1)?;
    Ok(equals(obj, values[0].as_ref().unwrap())?
        .into_pyobject(obj.py())?
        .to_owned()
        .into_any())
}

fn not_equal<'py>(
    obj: &Bound<'py, PyAny>,
    args: &Bound<'py, PyTuple>,
    kwargs: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let values = arguments(args, kwargs, &["other"], 1)?;
    Ok((!equals(obj, values[0].as_ref().unwrap())?)
        .into_pyobject(obj.py())?
        .to_owned()
        .into_any())
}

fn hash<'py>(
    obj: &Bound<'py, PyAny>,
    args: &Bound<'py, PyTuple>,
    kwargs: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    arguments(args, kwargs, &[], 0)?;
    let value = obj
        .py()
        .get_type::<PyBytes>()
        .getattr("__hash__")?
        .call1((obj,))?
        .extract::<isize>()?
        ^ isize::from(subtype(obj)?);
    Ok(value.into_pyobject(obj.py())?.into_any())
}

fn repr<'py>(
    obj: &Bound<'py, PyAny>,
    args: &Bound<'py, PyTuple>,
    kwargs: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    arguments(args, kwargs, &[], 0)?;
    let subtype = subtype(obj)?;
    let text = if subtype == 8 {
        "<Binary(REDACTED, 8)>".to_owned()
    } else {
        format!(
            "Binary({}, {subtype})",
            obj.py()
                .get_type::<PyBytes>()
                .getattr("__repr__")?
                .call1((obj,))?
        )
    };
    Ok(text.into_pyobject(obj.py())?.into_any())
}

definition!(uuid_constructor, c"from_uuid", from_uuid, ffi::METH_CLASS);
definition!(uuid_conversion, c"as_uuid", as_uuid, 0);
definition!(equality, c"__eq__", equal, 0);
definition!(inequality, c"__ne__", not_equal, 0);
definition!(hashing, c"__hash__", hash, 0);
definition!(representation, c"__repr__", repr, 0);

fn install(cls: &Bound<'_, PyType>, definition: &'static Definition) -> PyResult<()> {
    // SAFETY: CPython retains the static definition and does not modify it.
    // cls is a live heap type. Returned descriptor is a new owned reference.
    let descriptor = unsafe {
        let def = std::ptr::from_ref(&definition.0).cast_mut();
        let ptr = if definition.0.ml_flags & ffi::METH_CLASS != 0 {
            ffi::PyDescr_NewClassMethod(cls.as_type_ptr(), def)
        } else {
            ffi::PyDescr_NewMethod(cls.as_type_ptr(), def)
        };
        Bound::from_owned_ptr_or_err(cls.py(), ptr)?
    };
    // SAFETY: method names are static NUL-terminated ASCII strings.
    let name = unsafe { CStr::from_ptr(definition.0.ml_name) }
        .to_str()
        .expect("ASCII method name");
    cls.setattr(name, descriptor)
}

definition!(code_equality, c"__eq__", crate::code::equal, 0);
definition!(code_inequality, c"__ne__", crate::code::not_equal, 0);
definition!(code_representation, c"__repr__", crate::code::repr, 0);

pub fn install_code(cls: &Bound<'_, PyType>) -> PyResult<()> {
    for definition in [
        &code_equality::DEF,
        &code_inequality::DEF,
        &code_representation::DEF,
    ] {
        install(cls, definition)?;
    }
    Ok(())
}

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let builtins = py.import("builtins")?;
    let attrs = PyDict::new(py);
    attrs.set_item("__module__", "bson.int64")?;
    attrs.set_item("__slots__", PyTuple::empty(py))?;
    let int64 = py
        .get_type::<PyType>()
        .call1(("Int64", (py.get_type::<PyInt>(),), attrs))?
        .downcast_into::<PyType>()?;
    module.add("Int64", &int64)?;

    let attrs = PyDict::new(py);
    attrs.set_item("__module__", "bson.binary")?;
    attrs.set_item(
        "__new__",
        builtins
            .getattr("staticmethod")?
        .call1((wrap_pyfunction!(binary_constructor, py)?,))?,
    )?;
    attrs.set_item(
        "subtype",
        builtins
            .getattr("property")?
            .call1((wrap_pyfunction!(subtype, py)?,))?,
    )?;
    let binary = py
        .get_type::<PyType>()
        .call1(("Binary", (py.get_type::<PyBytes>(),), attrs))?
        .downcast_into::<PyType>()?;
    for definition in [
        &uuid_constructor::DEF,
        &uuid_conversion::DEF,
        &equality::DEF,
        &inequality::DEF,
        &hashing::DEF,
        &representation::DEF,
    ] {
        install(&binary, definition)?;
    }
    crate::bridge::register(&int64, &binary)?;
    module.add("Binary", binary)?;
    module.add("BINARY_SUBTYPE", 0)?;
    module.add("UUID_SUBTYPE", 4)?;
    let int_enum = py.import("enum")?.getattr("IntEnum")?;
    let values = PyDict::new(py);
    values.set_item("UNSPECIFIED", 0)?;
    values.set_item("STANDARD", 4)?;
    values.set_item("PYTHON_LEGACY", 3)?;
    values.set_item("JAVA_LEGACY", 5)?;
    values.set_item("CSHARP_LEGACY", 6)?;
    let uuid_representation = int_enum.call1(("UuidRepresentation", values))?;
    uuid_representation.setattr("__module__", "bson.binary")?;
    module.add(
        "UuidRepresentation",
        uuid_representation,
    )?;
    Ok(())
}
