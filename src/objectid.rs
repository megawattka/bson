use std::sync::atomic::{AtomicU32, AtomicU64, Ordering};
use std::sync::{Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};

use pyo3::basic::CompareOp;
use pyo3::exceptions::{PyOSError, PyOverflowError, PyRuntimeError, PyTypeError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyString, PyType};

struct Generator {
    pid: AtomicU32,
    random: AtomicU64,
    counter: AtomicU32,
    reseed_lock: Mutex<()>,
}

static GENERATOR: OnceLock<Generator> = OnceLock::new();

fn generator() -> &'static Generator {
    GENERATOR.get_or_init(|| Generator {
        pid: AtomicU32::new(0),
        random: AtomicU64::new(0),
        counter: AtomicU32::new(0),
        reseed_lock: Mutex::new(()),
    })
}

fn generate() -> PyResult<[u8; 12]> {
    let pid = std::process::id();
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| PyOverflowError::new_err("ObjectId timestamp precedes the Unix epoch"))?
        .as_secs();
    let seconds = u32::try_from(seconds)
        .map_err(|_| PyOverflowError::new_err("ObjectId timestamp exceeds uint32"))?;

    let generator = generator();
    if generator.pid.load(Ordering::Acquire) != pid {
        let _reseed = generator
            .reseed_lock
            .lock()
            .map_err(|_| PyRuntimeError::new_err("ObjectId generator lock poisoned"))?;
        if generator.pid.load(Ordering::Acquire) != pid {
            // Request OS entropy only on initialization or after fork, never per ID.
            let mut seed = [0; 8];
            getrandom::fill(&mut seed).map_err(|error| {
                PyOSError::new_err(format!("ObjectId entropy source failed: {error}"))
            })?;
            let random = u64::from_be_bytes(seed) & 0x0000_ffff_ffff_ffff;
            generator.random.store(random, Ordering::Relaxed);
            generator.counter.store(
                u32::from_be_bytes([0, seed[5], seed[6], seed[7]]),
                Ordering::Relaxed,
            );
            generator.pid.store(pid, Ordering::Release);
        }
    }
    let mut bytes = [0; 12];
    bytes[..4].copy_from_slice(&seconds.to_be_bytes());
    bytes[4..9].copy_from_slice(&generator.random.load(Ordering::Relaxed).to_be_bytes()[3..]);
    bytes[9..].copy_from_slice(
        &((generator.counter.fetch_add(1, Ordering::Relaxed) & 0x00ff_ffff).to_be_bytes()[1..]),
    );
    Ok(bytes)
}

fn invalid_id(oid: &Bound<'_, PyAny>) -> PyResult<PyErr> {
    let message = format!(
        "{} is not a valid ObjectId, it must be a 12-byte input or a 24-character hex string",
        oid.repr()?
    );
    Ok(PyErr::from_value(
        oid.py()
            .import("bson.errors")?
            .getattr("InvalidId")?
            .call1((message,))?,
    ))
}

/// A MongoDB ObjectId: a timestamp, process-random bytes, and a counter.
#[pyclass(module = "bson.objectid", frozen, subclass)]
pub struct ObjectId {
    bytes: [u8; 12],
}

impl ObjectId {
    pub(crate) fn from_bytes(bytes: [u8; 12]) -> Self {
        Self { bytes }
    }

    pub(crate) fn as_bytes(&self) -> &[u8; 12] {
        &self.bytes
    }
}

#[pymethods]
impl ObjectId {
    #[new]
    #[pyo3(signature = (oid=None))]
    fn new(oid: Option<&Bound<'_, PyAny>>) -> PyResult<Self> {
        let Some(oid) = oid.filter(|oid| !oid.is_none()) else {
            return Ok(Self { bytes: generate()? });
        };
        if let Ok(other) = oid.extract::<PyRef<'_, Self>>() {
            return Ok(Self { bytes: other.bytes });
        }
        if let Ok(bytes) = oid.downcast::<PyBytes>()
            && let Ok(bytes) = bytes.as_bytes().try_into()
        {
            return Ok(Self { bytes });
        }
        if let Ok(text) = oid.downcast::<PyString>() {
            let text = text.to_string_lossy();
            if text.len() == 24 && text.bytes().all(|byte| byte.is_ascii_hexdigit()) {
                let mut bytes = [0; 12];
                for (i, byte) in bytes.iter_mut().enumerate() {
                    *byte = u8::from_str_radix(&text[i * 2..i * 2 + 2], 16).unwrap();
                }
                return Ok(Self { bytes });
            }
            return Err(invalid_id(oid)?);
        }
        Err(PyTypeError::new_err(format!(
            "id must be an instance of (bytes, str, ObjectId), not {}",
            oid.get_type()
        )))
    }

    /// Create a non-unique ObjectId for a datetime, treating naive values as UTC.
    #[classmethod]
    fn from_datetime<'py>(
        cls: &Bound<'py, PyType>,
        generation_time: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let py = cls.py();
        let seconds = crate::datetime::objectid_seconds(generation_time)?;
        let mut bytes = [0; 12];
        bytes[..4].copy_from_slice(&seconds.to_be_bytes());
        if cls.is(py.get_type::<Self>()) {
            Ok(Py::new(py, Self { bytes })?.into_bound(py).into_any())
        } else {
            // Respect Python subclass constructors on the less common path.
            cls.call1((PyBytes::new(py, &bytes),))
        }
    }

    #[classmethod]
    fn is_valid(_cls: &Bound<'_, PyType>, oid: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !oid.is_truthy()? {
            return Ok(false);
        }
        match Self::new(Some(oid)) {
            Ok(_) => Ok(true),
            Err(error) => {
                let invalid_id = oid.py().import("bson.errors")?.getattr("InvalidId")?;
                if error.is_instance_of::<PyTypeError>(oid.py())
                    || error.is_instance(oid.py(), &invalid_id)
                {
                    Ok(false)
                } else {
                    Err(error)
                }
            }
        }
    }

    #[getter]
    fn binary<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, &self.bytes)
    }

    #[getter]
    fn generation_time<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let timestamp = u32::from_be_bytes(self.bytes[..4].try_into().unwrap());
        crate::datetime::from_timestamp(py, timestamp)
    }

    fn __str__(&self) -> String {
        use std::fmt::Write;
        let mut hex = String::with_capacity(24);
        for byte in self.bytes {
            write!(hex, "{byte:02x}").unwrap();
        }
        hex
    }

    fn __repr__(&self) -> String {
        format!("ObjectId('{}')", self.__str__())
    }

    fn __richcmp__(
        &self,
        other: &Bound<'_, PyAny>,
        op: CompareOp,
        py: Python<'_>,
    ) -> PyResult<PyObject> {
        let Ok(other) = other.extract::<PyRef<'_, Self>>() else {
            return Ok(py.NotImplemented());
        };
        Ok(op
            .matches(self.bytes.cmp(&other.bytes))
            .into_pyobject(py)?
            .to_owned()
            .into_any()
            .unbind())
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        self.binary(py).hash()
    }
}
