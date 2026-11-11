use pyo3::basic::CompareOp;
use pyo3::exceptions::PyTypeError;
use pyo3::gc::{PyTraverseError, PyVisit};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyString, PyTuple, PyType};

#[pyfunction]
fn __get_pydantic_core_schema__<'py>(
    cls: &Bound<'py, PyType>,
    _source_type: &Bound<'py, PyAny>,
    _handler: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    crate::schema::value_schema(cls, crate::schema::Kind::Code)
}

/// Internal state for the native-created str subclass.
#[pyclass(module = "elune.code")]
pub struct Code {
    pub text: Py<PyString>,
    pub scope: Option<Py<PyDict>>,
}

#[pymethods]
impl Code {
    fn __traverse__(&self, visit: PyVisit<'_>) -> Result<(), PyTraverseError> {
        visit.call(&self.text)?;
        visit.call(&self.scope)
    }
    fn __clear__(&mut self) {
        self.scope = None;
    }
    #[new]
    #[pyo3(signature = (code, scope=None, **kwargs))]
    fn new(
        code: &Bound<'_, PyAny>,
        scope: Option<&Bound<'_, PyAny>>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Self> {
        let py = code.py();
        let state = state(code)?;
        let (text, mut result) = if let Some(state) = state {
            let other = state.borrow();
            (
                other.text.clone_ref(py),
                other.scope.as_ref().map(|scope| scope.clone_ref(py)),
            )
        } else {
            (
                code.cast::<PyString>()
                    .map_err(|_| PyTypeError::new_err("code must be an instance of str or Code"))?
                    .clone()
                    .unbind(),
                None,
            )
        };
        if let Some(scope) = scope.filter(|value| !value.is_none()) {
            if !scope.is_instance(&py.import("collections.abc")?.getattr("Mapping")?)? {
                return Err(PyTypeError::new_err("scope must be a mapping"));
            }
            let scope = if let Ok(dict) = scope.cast::<PyDict>() {
                dict.clone()
            } else {
                py.get_type::<PyDict>()
                    .call1((scope,))?
                    .cast_into::<PyDict>()?
            };
            if let Some(existing) = &result {
                existing.bind(py).call_method1("update", (scope,))?;
            } else {
                result = Some(scope.unbind());
            }
        }
        if let Some(kwargs) = kwargs.filter(|kwargs| !kwargs.is_empty()) {
            if let Some(existing) = &result {
                existing.bind(py).call_method1("update", (kwargs,))?;
            } else {
                result = Some(kwargs.clone().unbind());
            }
        }
        Ok(Self {
            text,
            scope: result,
        })
    }
    #[getter]
    fn scope(&self, py: Python<'_>) -> Option<Py<PyDict>> {
        self.scope.as_ref().map(|scope| scope.clone_ref(py))
    }
    fn __str__(&self, py: Python<'_>) -> Py<PyString> {
        self.text.clone_ref(py)
    }
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "Code({}, {})",
            self.text.bind(py).repr()?,
            match &self.scope {
                Some(scope) => scope.bind(py).repr()?.to_string(),
                None => "None".to_owned(),
            }
        ))
    }
    fn __richcmp__(&self, other: &Bound<'_, PyAny>, op: CompareOp) -> PyResult<Py<PyAny>> {
        let py = other.py();
        if !matches!(op, CompareOp::Eq | CompareOp::Ne) {
            return Ok(py.NotImplemented());
        }
        let equal = if let Ok(other) = other.extract::<PyRef<'_, Self>>() {
            self.text.bind(py).as_any().eq(other.text.bind(py))?
                && match (&self.scope, &other.scope) {
                    (None, None) => true,
                    (Some(a), Some(b)) => a.bind(py).eq(b.bind(py))?,
                    _ => false,
                }
        } else {
            false
        };
        Ok((if matches!(op, CompareOp::Eq) {
            equal
        } else {
            !equal
        })
        .into_pyobject(py)?
        .to_owned()
        .into_any()
        .unbind())
    }
}

pub fn state<'py>(value: &Bound<'py, PyAny>) -> PyResult<Option<Bound<'py, Code>>> {
    if value.is_instance(crate::bridge::code(value.py())?.as_any())? {
        Ok(Some(value.getattr("_state")?.cast_into::<Code>()?))
    } else {
        Ok(None)
    }
}

#[pyfunction]
#[pyo3(signature = (cls, code, scope=None, **kwargs))]
fn code_new<'py>(
    cls: &Bound<'py, PyType>,
    code: &Bound<'py, PyAny>,
    scope: Option<&Bound<'py, PyAny>>,
    kwargs: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let state = Code::new(code, scope, kwargs)?;
    let obj = cls
        .py()
        .get_type::<PyString>()
        .getattr("__new__")?
        .call1((cls, state.text.bind(cls.py())))?;
    obj.setattr("_state", Py::new(cls.py(), state)?)?;
    Ok(obj)
}

#[pyfunction]
fn code_scope(value: &Bound<'_, PyAny>) -> PyResult<Option<Py<PyDict>>> {
    Ok(state(value)?
        .expect("Code receiver")
        .borrow()
        .scope(value.py()))
}

pub fn equal<'py>(
    obj: &Bound<'py, PyAny>,
    args: &Bound<'py, PyTuple>,
    _kwargs: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let other = args.get_item(0)?;
    let equal = match state(&other)? {
        Some(other) => state(obj)?
            .expect("Code receiver")
            .borrow()
            .__richcmp__(other.as_any(), CompareOp::Eq)?,
        None => false
            .into_pyobject(obj.py())?
            .to_owned()
            .into_any()
            .unbind(),
    };
    Ok(equal.into_bound(obj.py()))
}

pub fn not_equal<'py>(
    obj: &Bound<'py, PyAny>,
    args: &Bound<'py, PyTuple>,
    kwargs: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    Ok((!equal(obj, args, kwargs)?.is_truthy()?)
        .into_pyobject(obj.py())?
        .to_owned()
        .into_any())
}

pub fn repr<'py>(
    obj: &Bound<'py, PyAny>,
    _args: &Bound<'py, PyTuple>,
    _kwargs: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    Ok(state(obj)?
        .expect("Code receiver")
        .borrow()
        .__repr__(obj.py())?
        .into_pyobject(obj.py())?
        .into_any())
}

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let builtins = py.import("builtins")?;
    let attrs = PyDict::new(py);
    attrs.set_item("__module__", "elune.code")?;
    attrs.set_item(
        "__get_pydantic_core_schema__",
        builtins.getattr("classmethod")?.call1((wrap_pyfunction!(
            __get_pydantic_core_schema__, py
        )?,))?,
    )?;
    attrs.set_item("__slots__", ("_state",))?;
    attrs.set_item(
        "__new__",
        builtins
            .getattr("staticmethod")?
            .call1((wrap_pyfunction!(code_new, py)?,))?,
    )?;
    attrs.set_item(
        "scope",
        builtins
            .getattr("property")?
            .call1((wrap_pyfunction!(code_scope, py)?,))?,
    )?;
    attrs.set_item("__hash__", py.None())?;
    let cls = py
        .get_type::<PyType>()
        .call1(("Code", (py.get_type::<PyString>(),), attrs))?
        .cast_into::<PyType>()?;
    crate::builtins::install_code(&cls)?;
    crate::bridge::register_code(&cls)?;
    module.add("Code", cls)
}
