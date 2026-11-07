//! Cached identities for native-created subclasses of immutable builtins.

use pyo3::prelude::*;
use pyo3::sync::GILOnceCell;
use pyo3::types::PyType;

static INT64: GILOnceCell<Py<PyType>> = GILOnceCell::new();
static BINARY: GILOnceCell<Py<PyType>> = GILOnceCell::new();
static UUID: GILOnceCell<Py<PyType>> = GILOnceCell::new();
static CODE: GILOnceCell<Py<PyType>> = GILOnceCell::new();

pub fn code(py: Python<'_>) -> PyResult<Bound<'_, PyType>> {
    registered(py, &CODE)
}

pub fn register_code(cls: &Bound<'_, PyType>) -> PyResult<()> {
    CODE.set(cls.py(), cls.clone().unbind())
        .map_err(|_| pyo3::exceptions::PyRuntimeError::new_err("Code already initialized"))
}

fn cached<'py>(
    py: Python<'py>,
    cell: &GILOnceCell<Py<PyType>>,
    module: &str,
    name: &str,
) -> PyResult<Bound<'py, PyType>> {
    let cls = cell.get_or_try_init(py, || -> PyResult<_> {
        Ok(py
            .import(module)?
            .getattr(name)?
            .downcast_into::<PyType>()?
            .unbind())
    })?;
    Ok(cls.bind(py).clone())
}

pub fn int64(py: Python<'_>) -> PyResult<Bound<'_, PyType>> {
    registered(py, &INT64)
}

pub fn binary(py: Python<'_>) -> PyResult<Bound<'_, PyType>> {
    registered(py, &BINARY)
}

fn registered<'py>(
    py: Python<'py>,
    cell: &GILOnceCell<Py<PyType>>,
) -> PyResult<Bound<'py, PyType>> {
    cell.get(py).map(|cls| cls.bind(py).clone()).ok_or_else(|| {
        pyo3::exceptions::PyRuntimeError::new_err("native BSON types are not initialized")
    })
}

pub fn register(int64: &Bound<'_, PyType>, binary: &Bound<'_, PyType>) -> PyResult<()> {
    let py = int64.py();
    INT64
        .set(py, int64.clone().unbind())
        .map_err(|_| pyo3::exceptions::PyRuntimeError::new_err("Int64 already initialized"))?;
    BINARY
        .set(py, binary.clone().unbind())
        .map_err(|_| pyo3::exceptions::PyRuntimeError::new_err("Binary already initialized"))
}

pub fn uuid(py: Python<'_>) -> PyResult<Bound<'_, PyType>> {
    cached(py, &UUID, "uuid", "UUID")
}
