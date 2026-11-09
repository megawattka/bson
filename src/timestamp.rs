use pyo3::basic::CompareOp;
use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyInt, PyType};

#[pyclass(module = "bson.timestamp", frozen)]
#[derive(Clone, Copy)]
pub struct Timestamp {
    #[pyo3(get)]
    pub time: u32,
    #[pyo3(get)]
    pub inc: u32,
}

fn uint32(value: &Bound<'_, PyAny>, name: &str) -> PyResult<u32> {
    if !value.is_instance_of::<PyInt>() {
        return Err(PyTypeError::new_err(format!(
            "{name} must be an instance of int"
        )));
    }
    value
        .extract()
        .map_err(|_| PyValueError::new_err(format!("{name} must be contained in [0, 2**32)")))
}

#[pymethods]
impl Timestamp {
    #[classmethod]
    fn __get_pydantic_core_schema__<'py>(
        cls: &Bound<'py, PyType>,
        _source_type: &Bound<'py, PyAny>,
        _handler: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyDict>> {
        crate::schema::value_schema(cls, crate::schema::Kind::Timestamp)
    }

    #[new]
    fn new(time: &Bound<'_, PyAny>, inc: &Bound<'_, PyAny>) -> PyResult<Self> {
        let time = if crate::datetime::is_datetime(time)? {
            let seconds = crate::datetime::to_millis(time)?.div_euclid(1000);
            u32::try_from(seconds)
                .map_err(|_| PyValueError::new_err("time must be contained in [0, 2**32)"))?
        } else {
            uint32(time, "time")?
        };
        Ok(Self {
            time,
            inc: uint32(inc, "inc")?,
        })
    }
    fn as_datetime<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        crate::datetime::from_timestamp(py, self.time)
    }
    fn __repr__(&self) -> String {
        format!("Timestamp({}, {})", self.time, self.inc)
    }
    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        Ok(self.time.into_pyobject(py)?.hash()? ^ self.inc.into_pyobject(py)?.hash()?)
    }
    fn __richcmp__(&self, other: &Bound<'_, PyAny>, op: CompareOp) -> PyResult<Py<PyAny>> {
        let py = other.py();
        let Ok(other) = other.extract::<PyRef<'_, Self>>() else {
            return Ok(py.NotImplemented());
        };
        Ok(op
            .matches((self.time, self.inc).cmp(&(other.time, other.inc)))
            .into_pyobject(py)?
            .to_owned()
            .into_any()
            .unbind())
    }
}
