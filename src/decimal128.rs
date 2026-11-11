//! IEEE 754 decimal128 BID storage. Decimal validation uses Python's standard
//! decimal.Context; bit packing/unpacking is native and independent of PyMongo.
use pyo3::basic::CompareOp;
use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList, PyString, PyTuple, PyType};

use crate::schema::{self, py_dict};

const SIGN: u64 = 1 << 63;
const INF: u64 = 0x7800_0000_0000_0000;
const NAN: u64 = 0x7c00_0000_0000_0000;
const SNAN: u64 = 0x7e00_0000_0000_0000;
const STEERING: u64 = 3 << 61;

fn default_decimal128_context(py: Python<'_>, trap: bool) -> PyResult<Bound<'_, PyAny>> {
    let decimal = py.import("decimal")?;
    let kwargs = PyDict::new(py);
    for (key, value) in [
        ("prec", 34),
        ("Emin", -6143),
        ("Emax", 6144),
        ("capitals", 1),
        ("clamp", 1),
    ] {
        kwargs.set_item(key, value)?;
    }
    kwargs.set_item("rounding", decimal.getattr("ROUND_HALF_EVEN")?)?;
    kwargs.set_item("flags", PyList::empty(py))?;
    let traps = PyList::empty(py);
    if trap {
        for name in ["InvalidOperation", "Overflow", "Inexact"] {
            traps.append(decimal.getattr(name)?)?;
        }
    }
    kwargs.set_item("traps", traps)?;
    decimal.getattr("Context")?.call((), Some(&kwargs))
}

#[pyfunction]
pub fn create_decimal128_context(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    default_decimal128_context(py, false)
}

#[pyclass(module = "elune.decimal128", frozen)]
#[derive(Clone)]
pub struct Decimal128 {
    pub bytes: [u8; 16],
}

impl Decimal128 {
    fn words(&self) -> (u64, u64) {
        (
            u64::from_le_bytes(self.bytes[8..].try_into().unwrap()),
            u64::from_le_bytes(self.bytes[..8].try_into().unwrap()),
        )
    }
    fn from_words(high: u64, low: u64) -> Self {
        let mut bytes = [0; 16];
        bytes[..8].copy_from_slice(&low.to_le_bytes());
        bytes[8..].copy_from_slice(&high.to_le_bytes());
        Self { bytes }
    }
}

#[pyfunction]
fn validate_decimal128(value: &Bound<'_, PyAny>) -> PyResult<Decimal128> {
    match Decimal128::new(value) {
        Ok(value) => Ok(value),
        Err(error) => {
            let py = value.py();
            let decimal_exception = py.import("decimal")?.getattr("DecimalException")?;
            if error.is_instance(py, &decimal_exception) {
                Err(PyValueError::new_err(format!(
                    "invalid Decimal128: {error}"
                )))
            } else {
                Err(error)
            }
        }
    }
}

#[pyfunction]
fn serialize_decimal128(value: PyRef<'_, Decimal128>) -> PyResult<String> {
    Ok(value.to_decimal(value.py())?.str()?.to_str()?.to_owned())
}

#[pymethods]
impl Decimal128 {
    #[classmethod]
    fn __get_pydantic_core_schema__<'py>(
        cls: &Bound<'py, PyType>,
        _source_type: &Bound<'py, PyAny>,
        _handler: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyDict>> {
        let py = cls.py();
        let string = py_dict!(py, {
            "type" => "str",
            "strict" => true,
        })?;
        let validate = wrap_pyfunction!(validate_decimal128, py)?;
        let from_string = schema::after_validator(validate.as_any(), &string)?;
        let decimal_type = py
            .import("decimal")?
            .getattr("Decimal")?
            .cast_into::<PyType>()?;
        let decimal = schema::is_instance(&decimal_type)?;
        let from_decimal = schema::after_validator(validate.as_any(), &decimal)?;
        let python = schema::union(
            py,
            &[
                schema::is_instance(cls)?,
                from_string.clone(),
                from_decimal,
            ],
        )?;
        let serialize = wrap_pyfunction!(serialize_decimal128, py)?;
        let serialization = schema::json_serializer(serialize.as_any(), &string)?;
        schema::json_or_python(&from_string, &python, &serialization)
    }

    #[new]
    fn new(value: &Bound<'_, PyAny>) -> PyResult<Self> {
        let py = value.py();
        if value.is_instance_of::<PyTuple>() || value.is_instance_of::<PyList>() {
            if value.len()? != 2 {
                return Err(PyValueError::new_err(
                    "BID requires exactly two elements (high, low)",
                ));
            }
            return Ok(Self::from_words(
                value.get_item(0)?.extract()?,
                value.get_item(1)?.extract()?,
            ));
        }
        if !value.is_instance_of::<PyString>()
            && !value.is_instance(&py.import("decimal")?.getattr("Decimal")?)?
        {
            return Err(PyTypeError::new_err(
                "value must be str, Decimal, or (high, low)",
            ));
        }
        let decimal = default_decimal128_context(py, true)?
            .call_method1("create_decimal", (value,))?;
        let tuple = decimal.call_method0("as_tuple")?;
        let sign: bool = tuple.get_item(0)?.extract::<u8>()? != 0;
        let sign = if sign { SIGN } else { 0 };
        if decimal.call_method0("is_infinite")?.is_truthy()? {
            return Ok(Self::from_words(sign | INF, 0));
        }
        let digits: Vec<u8> = tuple.get_item(1)?.extract()?;
        if decimal.call_method0("is_nan")?.is_truthy()? {
            if !digits.is_empty() {
                return Err(PyValueError::new_err(
                    "NaN with debug payload is not supported",
                ));
            }
            return Ok(Self::from_words(
                sign | if decimal.call_method0("is_snan")?.is_truthy()? {
                    SNAN
                } else {
                    NAN
                },
                0,
            ));
        }
        let coefficient = digits
            .iter()
            .fold(0u128, |value, digit| value * 10 + u128::from(*digit));
        let exponent = tuple.get_item(2)?.extract::<i64>()? + 6176;
        Ok(Self::from_words(
            sign | ((exponent as u64) << 49) | ((coefficient >> 64) as u64),
            coefficient as u64,
        ))
    }
    #[staticmethod]
    fn from_bid(value: &Bound<'_, PyAny>) -> PyResult<Self> {
        let bytes = value
            .cast::<PyBytes>()
            .map_err(|_| PyTypeError::new_err("value must be bytes"))?;
        Ok(Self {
            bytes: bytes
                .as_bytes()
                .try_into()
                .map_err(|_| PyValueError::new_err("value must be exactly 16 bytes"))?,
        })
    }
    #[getter]
    fn bid<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, &self.bytes)
    }
    fn to_decimal<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let (high, low) = self.words();
        let sign = u8::from(high & SIGN != 0);
        let decimal = py.import("decimal")?.getattr("Decimal")?;
        for (mask, exponent) in [(SNAN, "N"), (NAN, "n"), (INF, "F")] {
            if high & mask == mask {
                return decimal.call1(((sign, (), exponent),));
            }
        }
        let exponent = if high & STEERING == STEERING {
            ((high & 0x1fff_e000_0000_0000) >> 47) as i64 - 6176
        } else {
            ((high & 0x7fff_8000_0000_0000) >> 49) as i64 - 6176
        };
        let coefficient = if high & STEERING == STEERING {
            0
        } else {
            (u128::from(high & 0x0001_ffff_ffff_ffff) << 64) | u128::from(low)
        };
        let digits: Vec<u8> = coefficient
            .to_string()
            .bytes()
            .map(|byte| byte - b'0')
            .collect();
        let tuple = (sign, PyTuple::new(py, digits)?, exponent);
        default_decimal128_context(py, true)?
            .call_method1("create_decimal", (tuple,))
    }

    fn __str__(&self, py: Python<'_>) -> PyResult<String> {
        let decimal = self.to_decimal(py)?;
        if decimal.call_method0("is_nan")?.is_truthy()? {
            Ok("NaN".into())
        } else {
            Ok(decimal.str()?.to_string())
        }
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!("Decimal128('{}')", self.__str__(py)?))
    }

    fn __richcmp__(&self, other: &Bound<'_, PyAny>, op: CompareOp) -> PyResult<Py<PyAny>> {
        let py = other.py();
        let Ok(other) = other.extract::<PyRef<'_, Self>>() else {
            return Ok(py.NotImplemented());
        };
        match op {
            CompareOp::Eq | CompareOp::Ne => Ok((if matches!(op, CompareOp::Eq) {
                self.bytes == other.bytes
            } else {
                self.bytes != other.bytes
            })
            .into_pyobject(py)?
            .to_owned()
            .into_any()
            .unbind()),
            _ => Ok(py.NotImplemented()),
        }
    }
}
