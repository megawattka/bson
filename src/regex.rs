use pyo3::basic::CompareOp;
use pyo3::exceptions::PyTypeError;
use pyo3::gc::{PyTraverseError, PyVisit};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyInt, PyString, PyType};

pub const FLAGS: [(char, i64); 6] = [
    ('i', 2),
    ('l', 4),
    ('m', 8),
    ('s', 16),
    ('u', 32),
    ('x', 64),
];

#[derive(FromPyObject)]
enum RegexFlags {
    Integer(i64),
    Text(String),
}

#[pyclass(module = "elune.regex")]
pub struct Regex {
    #[pyo3(get, set)]
    pub pattern: Py<PyAny>,
    #[pyo3(get, set)]
    pub flags: i64,
}

#[pymethods]
impl Regex {
    #[classmethod]
    fn __get_pydantic_core_schema__<'py>(
        cls: &Bound<'py, PyType>,
        _source_type: &Bound<'py, PyAny>,
        _handler: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyDict>> {
        crate::schema::value_schema(cls, crate::schema::Kind::Regex)
    }

    fn __traverse__(&self, visit: PyVisit<'_>) -> Result<(), PyTraverseError> {
        visit.call(&self.pattern)
    }
    fn __clear__(&mut self, py: Python<'_>) {
        self.pattern = py.None();
    }
    #[new]
    #[pyo3(signature = (pattern, flags=RegexFlags::Integer(0)))]
    fn new(pattern: &Bound<'_, PyAny>, flags: RegexFlags) -> PyResult<Self> {
        let flags = match flags {
            RegexFlags::Integer(value) => value.into_pyobject(pattern.py())?.into_any(),
            RegexFlags::Text(value) => value.into_pyobject(pattern.py())?.into_any(),
        };
        Self::from_parts(pattern, Some(&flags))
    }
    #[staticmethod]
    fn from_native(regex: &Bound<'_, PyAny>) -> PyResult<Self> {
        if !is_native(regex)? {
            return Err(PyTypeError::new_err(
                "regex must be a compiled regular expression",
            ));
        }
        Self::from_parts(&regex.getattr("pattern")?, Some(&regex.getattr("flags")?))
    }
    fn try_compile<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        py.import("re")?
            .call_method1("compile", (self.pattern.bind(py), self.flags))
    }
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "Regex({}, {})",
            self.pattern.bind(py).repr()?,
            self.flags
        ))
    }
    fn __richcmp__(&self, other: &Bound<'_, PyAny>, op: CompareOp) -> PyResult<Py<PyAny>> {
        let py = other.py();
        let Ok(other) = other.extract::<PyRef<'_, Self>>() else {
            return Ok(py.NotImplemented());
        };
        let equal =
            self.flags == other.flags && self.pattern.bind(py).eq(other.pattern.bind(py))?;
        match op {
            CompareOp::Eq | CompareOp::Ne => Ok((if matches!(op, CompareOp::Eq) {
                equal
            } else {
                !equal
            })
            .into_pyobject(py)?
            .to_owned()
            .into_any()
            .unbind()),
            _ => Ok(py.NotImplemented()),
        }
    }
}

impl Regex {
    pub fn from_parts(
        pattern: &Bound<'_, PyAny>,
        flags: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        if !pattern.is_instance_of::<PyString>() && !pattern.is_instance_of::<PyBytes>() {
            return Err(PyTypeError::new_err("pattern must be a string or bytes"));
        }
        let flags = match flags {
            None => 0,
            Some(value) if value.is_instance_of::<PyInt>() => value.extract()?,
            Some(value) if value.is_instance_of::<PyString>() => {
                let text = value.extract::<&str>()?;
                FLAGS
                    .iter()
                    .filter(|(ch, _)| text.contains(*ch))
                    .map(|(_, bit)| bit)
                    .sum()
            }
            Some(_) => return Err(PyTypeError::new_err("flags must be a string or int")),
        };
        Ok(Self {
            pattern: pattern.clone().unbind(),
            flags,
        })
    }
}

pub fn is_native(value: &Bound<'_, PyAny>) -> PyResult<bool> {
    value.is_instance(&value.py().import("re")?.getattr("Pattern")?)
}
