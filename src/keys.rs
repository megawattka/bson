use pyo3::basic::CompareOp;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyType};

macro_rules! key {
    ($name:ident, $module:literal, $hash:expr, $min:expr) => {
        #[pyclass(module = $module, frozen)]
        pub struct $name;
        #[pymethods]
        impl $name {
            #[classmethod]
            fn __get_pydantic_core_schema__<'py>(
                cls: &Bound<'py, PyType>,
                _source_type: &Bound<'py, PyAny>,
                _handler: &Bound<'py, PyAny>,
            ) -> PyResult<Bound<'py, PyDict>> {
                crate::schema::value_schema(cls, crate::schema::Kind::$name)
            }

            #[new]
            fn new() -> Self {
                Self
            }
            fn __repr__(&self) -> &'static str {
                concat!(stringify!($name), "()")
            }
            fn __hash__(&self) -> isize {
                $hash
            }
            fn __richcmp__(&self, other: &Bound<'_, PyAny>, op: CompareOp) -> bool {
                let same = other.is_instance_of::<Self>();
                match op {
                    CompareOp::Eq => same,
                    CompareOp::Ne => !same,
                    CompareOp::Lt => $min && !same,
                    CompareOp::Le => $min || same,
                    CompareOp::Gt => !$min && !same,
                    CompareOp::Ge => !$min || same,
                }
            }
        }
    };
}
key!(MinKey, "elune.min_key", 255, true);
key!(MaxKey, "elune.max_key", 127, false);
