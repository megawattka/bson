use pyo3::basic::CompareOp;
use pyo3::exceptions::{PyAttributeError, PyTypeError, PyValueError};
use pyo3::gc::{PyTraverseError, PyVisit};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyString, PyTuple, PyType};

/// A MongoDB reference, represented on the wire as an embedded document.
#[pyclass(module = "elune.dbref", subclass)]
pub struct DBRef {
    #[pyo3(get)]
    collection: Py<PyString>,
    #[pyo3(get)]
    id: Py<PyAny>,
    #[pyo3(get)]
    database: Option<Py<PyString>>,
    extra: Py<PyDict>,
}

#[pymethods]
impl DBRef {
    #[classmethod]
    fn __get_pydantic_core_schema__<'py>(
        cls: &Bound<'py, PyType>,
        _source_type: &Bound<'py, PyAny>,
        _handler: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyDict>> {
        crate::schema::value_schema(cls, crate::schema::Kind::DBRef)
    }

    #[new]
    #[pyo3(signature = (collection, id, database=None, _extra=None, **kwargs))]
    fn new(
        collection: &Bound<'_, PyAny>,
        id: Py<PyAny>,
        database: Option<&Bound<'_, PyAny>>,
        _extra: Option<&Bound<'_, PyAny>>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Self> {
        let py = collection.py();
        let collection = collection
            .cast::<PyString>()
            .map_err(|_| PyTypeError::new_err("collection must be an instance of str"))?
            .clone()
            .unbind();
        let database = database
            .filter(|value| !value.is_none())
            .map(|value| {
                value
                    .cast::<PyString>()
                    .map(|value| value.clone().unbind())
                    .map_err(|_| PyTypeError::new_err("database must be an instance of str"))
            })
            .transpose()?;
        let extra = match kwargs {
            Some(kwargs) => kwargs.copy()?,
            None => PyDict::new(py),
        };
        if let Some(value) = _extra.filter(|value| !value.is_none()) {
            extra.call_method1("update", (value,))?;
        }
        Ok(Self {
            collection,
            id,
            database,
            extra: extra.unbind(),
        })
    }

    pub fn as_doc<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let doc = PyDict::new(py);
        doc.set_item("$ref", self.collection.bind(py))?;
        doc.set_item("$id", self.id.bind(py))?;
        if let Some(database) = &self.database {
            doc.set_item("$db", database.bind(py))?;
        }
        for (key, value) in self.extra.bind(py).iter() {
            doc.set_item(key, value)?;
        }
        Ok(doc)
    }

    fn __getattr__(&self, py: Python<'_>, name: &str) -> PyResult<Py<PyAny>> {
        self.extra
            .bind(py)
            .get_item(name)?
            .map(Bound::unbind)
            .ok_or_else(|| PyAttributeError::new_err(name.to_owned()))
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let mut result = format!(
            "DBRef({}, {}",
            self.collection.bind(py).repr()?,
            self.id.bind(py).repr()?
        );
        if let Some(database) = &self.database {
            result.push_str(&format!(", {}", database.bind(py).repr()?));
        }
        for (key, value) in self.extra.bind(py).iter() {
            result.push_str(&format!(", {}={}", key.str()?, value.repr()?));
        }
        result.push(')');
        Ok(result)
    }

    fn __richcmp__(&self, other: &Bound<'_, PyAny>, op: CompareOp) -> PyResult<Py<PyAny>> {
        let py = other.py();
        if !matches!(op, CompareOp::Eq | CompareOp::Ne) {
            return Ok(py.NotImplemented());
        }
        let Ok(other) = other.extract::<PyRef<'_, Self>>() else {
            return Ok(py.NotImplemented());
        };
        let equal = self
            .collection
            .bind(py)
            .as_any()
            .eq(other.collection.bind(py))?
            && self.id.bind(py).eq(other.id.bind(py))?
            && match (&self.database, &other.database) {
                (Some(a), Some(b)) => a.bind(py).as_any().eq(b.bind(py))?,
                (None, None) => true,
                _ => false,
            }
            && self.extra.bind(py).eq(other.extra.bind(py))?;
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

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        let items = py
            .import("builtins")?
            .getattr("sorted")?
            .call1((self.extra.bind(py).items(),))?;
        PyTuple::new(
            py,
            [
                self.collection.bind(py).as_any().clone(),
                self.id.bind(py).clone(),
                self.database
                    .as_ref()
                    .map_or_else(|| py.None().into_bound(py), |v| v.bind(py).as_any().clone()),
                py.get_type::<PyTuple>().call1((items,))?,
            ],
        )?
        .hash()
    }

    fn __deepcopy__(&self, py: Python<'_>, memo: &Bound<'_, PyAny>) -> PyResult<Self> {
        let copy = py.import("copy")?.getattr("deepcopy")?;
        Ok(Self {
            collection: self.collection.clone_ref(py),
            id: copy.call1((self.id.bind(py), memo))?.unbind(),
            database: self.database.as_ref().map(|v| v.clone_ref(py)),
            extra: copy
                .call1((self.extra.bind(py), memo))?
                .cast_into::<PyDict>()?
                .unbind(),
        })
    }

    fn __traverse__(&self, visit: PyVisit<'_>) -> Result<(), PyTraverseError> {
        visit.call(&self.collection)?;
        visit.call(&self.id)?;
        visit.call(&self.database)?;
        visit.call(&self.extra)
    }

    fn __clear__(&mut self, py: Python<'_>) {
        self.id = py.None();
        self.extra = PyDict::new(py).unbind();
    }
}

impl DBRef {
    pub(crate) fn schema_document<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        for key in ["$ref", "$id", "$db"] {
            if self.extra.bind(py).contains(key)? {
                return Err(PyValueError::new_err("DBRef extra must not overwrite reserved fields"));
            }
        }
        self.as_doc(py)
    }
}

pub fn from_document<'py>(doc: Bound<'py, PyDict>) -> PyResult<Bound<'py, PyAny>> {
    let Some(collection) = doc.get_item("$ref")? else {
        return Ok(doc.into_any());
    };
    let Some(id) = doc.get_item("$id")? else {
        return Ok(doc.into_any());
    };
    let database = doc.get_item("$db")?;
    if !collection.is_instance_of::<PyString>()
        || database
            .as_ref()
            .is_some_and(|v| !v.is_none() && !v.is_instance_of::<PyString>())
    {
        return Ok(doc.into_any());
    }
    doc.del_item("$ref")?;
    doc.del_item("$id")?;
    if database.is_some() {
        doc.del_item("$db")?;
    }
    let reference = DBRef::new(
        &collection,
        id.unbind(),
        database.as_ref(),
        Some(doc.as_any()),
        None,
    )?;
    Ok(Py::new(doc.py(), reference)?
        .into_bound(doc.py())
        .into_any())
}
