//! Codec policy is parsed once per API call and passed through the traversal.

use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum UuidRepresentation {
    #[default]
    Unspecified = 0,
    Standard = 4,
    PythonLegacy = 3,
    JavaLegacy = 5,
    CSharpLegacy = 6,
}

impl UuidRepresentation {
    pub fn parse(value: i64) -> PyResult<Self> {
        match value {
            0 => Ok(Self::Unspecified),
            4 => Ok(Self::Standard),
            3 => Ok(Self::PythonLegacy),
            5 => Ok(Self::JavaLegacy),
            6 => Ok(Self::CSharpLegacy),
            _ => Err(PyValueError::new_err(
                "uuid_representation must be a value from bson.binary.UuidRepresentation",
            )),
        }
    }

    pub fn subtype(self) -> u8 {
        if self == Self::Standard { 4 } else { 3 }
    }

    pub fn decodes(self, subtype: u8) -> bool {
        self != Self::Unspecified && self.subtype() == subtype
    }
}

#[allow(non_camel_case_types)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DatetimeConversion {
    DATETIME = 1,
    DATETIME_CLAMP = 2,
    DATETIME_MS = 3,
    DATETIME_AUTO = 4,
}

impl DatetimeConversion {
    fn parse(value: u8) -> PyResult<Self> {
        match value {
            1 => Ok(Self::DATETIME),
            2 => Ok(Self::DATETIME_CLAMP),
            3 => Ok(Self::DATETIME_MS),
            4 => Ok(Self::DATETIME_AUTO),
            _ => Err(PyValueError::new_err(
                "datetime_conversion must be a DatetimeConversion value",
            )),
        }
    }
}

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let int_enum = py.import("enum")?.getattr("IntEnum")?;
    let values = pyo3::types::PyDict::new(py);
    values.set_item("DATETIME", 1)?;
    values.set_item("DATETIME_CLAMP", 2)?;
    values.set_item("DATETIME_MS", 3)?;
    values.set_item("DATETIME_AUTO", 4)?;
    let conversion = int_enum.call1(("DatetimeConversion", values))?;
    conversion.setattr("__module__", "bson.codec_options")?;
    module.add("DatetimeConversion", conversion)?;
    Ok(())
}

/// Codec policies parsed once per operation.
#[pyclass(module = "bson.codec_options", frozen)]
#[derive(Clone, Copy)]
pub struct CodecOptions {
    pub uuid: UuidRepresentation,
    pub tz_aware: bool,
    pub datetime_conversion: DatetimeConversion,
}

impl Default for CodecOptions {
    fn default() -> Self {
        Self {
            uuid: UuidRepresentation::Unspecified,
            tz_aware: false,
            datetime_conversion: DatetimeConversion::DATETIME,
        }
    }
}

#[pymethods]
impl CodecOptions {
    #[new]
    #[pyo3(signature = (uuid_representation=0, *, tz_aware=false, datetime_conversion=1))]
    fn new(uuid_representation: i64, tz_aware: bool, datetime_conversion: u8) -> PyResult<Self> {
        let datetime_conversion = DatetimeConversion::parse(datetime_conversion)?;
        Ok(Self {
            uuid: UuidRepresentation::parse(uuid_representation)?,
            tz_aware,
            datetime_conversion,
        })
    }

    #[getter]
    fn uuid_representation(&self) -> u8 {
        self.uuid as u8
    }

    #[getter]
    fn tz_aware(&self) -> bool {
        self.tz_aware
    }

    #[getter]
    fn datetime_conversion(&self) -> u8 {
        self.datetime_conversion as u8
    }

    #[pyo3(signature = (*, uuid_representation=None, tz_aware=None, datetime_conversion=None))]
    fn with_options(
        &self,
        uuid_representation: Option<i64>,
        tz_aware: Option<bool>,
        datetime_conversion: Option<u8>,
    ) -> PyResult<Self> {
        Self::new(
            uuid_representation.unwrap_or(self.uuid as i64),
            tz_aware.unwrap_or(self.tz_aware),
            datetime_conversion.unwrap_or(self.datetime_conversion as u8),
        )
    }

    fn __repr__(&self) -> String {
        format!(
            "CodecOptions(uuid_representation={}, tz_aware={}, datetime_conversion={})",
            self.uuid as u8, self.tz_aware, self.datetime_conversion as u8
        )
    }
}

pub fn resolve_all(options: Option<&Bound<'_, PyAny>>) -> PyResult<CodecOptions> {
    match options.filter(|value| !value.is_none()) {
        None => Ok(CodecOptions::default()),
        Some(value) => value
            .extract::<PyRef<'_, CodecOptions>>()
            .map(|value| *value)
            .map_err(|_| PyTypeError::new_err("codec_options must be an instance of CodecOptions")),
    }
}
