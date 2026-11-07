use pyo3::basic::CompareOp;
use pyo3::prelude::*;

macro_rules! key {
    ($name:ident, $module:literal, $hash:expr, $min:expr) => {
        #[pyclass(module = $module, frozen)]
        pub struct $name;
        #[pymethods]
        impl $name {
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
key!(MinKey, "bson.min_key", 255, true);
key!(MaxKey, "bson.max_key", 127, false);
