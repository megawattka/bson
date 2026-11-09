//! Codec policy is parsed once per API call and passed through the traversal.

use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyList, PyType};
use std::collections::HashMap;

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
#[pyclass(module = "bson.codec_options", subclass)]
pub struct TypeEncoder;

#[pymethods]
impl TypeEncoder {
    #[new]
    fn new() -> Self { Self }
    #[getter]
    fn python_type(&self) -> PyResult<Py<PyAny>> {
        Err(PyTypeError::new_err("TypeEncoder.python_type must be overridden"))
    }

    fn transform_python(&self, _value: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        Err(PyTypeError::new_err("TypeEncoder.transform_python must be overridden"))
    }
}

#[pyclass(module = "bson.codec_options", subclass)]
pub struct TypeDecoder;

#[pymethods]
impl TypeDecoder {
    #[new]
    fn new() -> Self { Self }
    #[getter]
    fn bson_type(&self) -> PyResult<Py<PyAny>> {
        Err(PyTypeError::new_err("TypeDecoder.bson_type must be overridden"))
    }

    fn transform_bson(&self, _value: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        Err(PyTypeError::new_err("TypeDecoder.transform_bson must be overridden"))
    }
}

#[pyclass(module = "bson.codec_options", subclass)]
pub struct TypeCodec;

#[pymethods]
impl TypeCodec {
    #[new]
    fn new() -> Self { Self }
}

#[pyclass(module = "bson.codec_options", frozen)]
pub struct TypeRegistry {
    pub codecs: Vec<Py<PyAny>>,
    pub fallback: Option<Py<PyAny>>,
    pub encoders: Vec<(Py<PyType>, Py<PyAny>)>,
    pub decoders: Vec<(Py<PyType>, Py<PyAny>)>,
    pub encoder_map: HashMap<usize, Py<PyAny>>,
    pub decoder_map: HashMap<usize, Py<PyAny>>,
}

pub fn encode_custom<'py>(
    py: Python<'py>, value: &Bound<'py, PyAny>, registry: Option<&Py<TypeRegistry>>,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let Some(registry) = registry else { return Ok(None) };
    let registry = registry.bind(py).borrow();
    if registry.encoders.is_empty() && registry.fallback.is_none() {
        return Ok(None);
    }
    let type_id = value.get_type().as_ptr() as usize;
    if let Some(transform) = registry.encoder_map.get(&type_id) {
        return Ok(Some(transform.bind(py).call1((value,))?));
    }
    Ok(None)
}

pub fn encode_registered<'py>(
    py: Python<'py>, value: &Bound<'py, PyAny>, registry: Option<&Py<TypeRegistry>>,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let Some(registry) = registry else { return Ok(None) };
    let registry = registry.bind(py).borrow();
    let type_id = value.get_type().as_ptr() as usize;
    let Some(transform) = registry.encoder_map.get(&type_id) else {
        return Ok(None);
    };
    Ok(Some(transform.bind(py).call1((value,))?))
}

pub fn decode_custom<'py>(
    py: Python<'py>, value: Bound<'py, PyAny>, registry: Option<&Py<TypeRegistry>>,
) -> PyResult<Bound<'py, PyAny>> {
    let Some(registry) = registry else { return Ok(value) };
    let registry = registry.bind(py).borrow();
    if registry.decoders.is_empty() {
        return Ok(value);
    }
    let type_id = value.get_type().as_ptr() as usize;
    if let Some(transform) = registry.decoder_map.get(&type_id) {
        return transform.bind(py).call1((value,));
    }
    Ok(value)
}

#[pymethods]
impl TypeRegistry {
    #[new]
    #[pyo3(signature = (type_codecs=None, fallback_encoder=None))]
    fn new(
        py: Python<'_>,
        type_codecs: Option<&Bound<'_, PyAny>>,
        fallback_encoder: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        let codecs = match type_codecs {
            None => Vec::new(),
            Some(value) => value
                .try_iter()?
                .map(|item| item.map(|item| item.unbind()))
                .collect::<PyResult<Vec<_>>>()?,
        };
        if let Some(fallback) = &fallback_encoder
            && !fallback.bind(py).is_callable()
        {
            return Err(PyTypeError::new_err(format!(
                "fallback_encoder {fallback:?} is not a callable"
            )));
        }
        let mut encoders = Vec::new();
        let mut decoders = Vec::new();
        let mut encoder_map = HashMap::new();
        let mut decoder_map = HashMap::new();
        for codec in &codecs {
            let value = codec.bind(py);
            let encoder = value.hasattr("python_type")? && value.hasattr("transform_python")?;
            let decoder = value.hasattr("bson_type")? && value.hasattr("transform_bson")?;
            if !encoder && !decoder {
                return Err(PyTypeError::new_err(format!(
                    "Expected an instance of TypeEncoder, TypeDecoder, or TypeCodec, got {value:?} instead"
                )));
            }
            if encoder {
                let python_type = value.getattr("python_type")?;
                if !python_type.is_instance_of::<PyType>() {
                    return Err(PyTypeError::new_err("python_type must be a type"));
                }
                if builtin_type(py, &python_type)? {
                    return Err(PyTypeError::new_err(
                        "TypeEncoders cannot change how built-in types are encoded",
                    ));
                }
                let python_type = python_type.cast::<PyType>()?.clone();
                let transform = value.getattr("transform_python")?;
                encoder_map.insert(python_type.as_ptr() as usize, transform.clone().unbind());
                encoders.push((python_type.unbind(), transform.unbind()));
            }
            if decoder {
                let bson_type = value.getattr("bson_type")?;
                if !bson_type.is_instance_of::<PyType>() {
                    return Err(PyTypeError::new_err("bson_type must be a type"));
                }
                let bson_type = bson_type.cast::<PyType>()?.clone();
                let transform = value.getattr("transform_bson")?;
                decoder_map.insert(bson_type.as_ptr() as usize, transform.clone().unbind());
                decoders.push((bson_type.unbind(), transform.unbind()));
            }
        }
        Ok(Self {
            codecs,
            fallback: fallback_encoder,
            encoders,
            decoders,
            encoder_map,
            decoder_map,
        })
    }

    #[getter]
    fn codecs(&self, py: Python<'_>) -> Py<PyList> {
        PyList::new(py, &self.codecs).unwrap().unbind()
    }

    #[getter]
    fn fallback_encoder(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.fallback.as_ref().map(|value| value.clone_ref(py))
    }

    fn __repr__(&self) -> String {
        "TypeRegistry(...)".to_owned()
    }
}

fn builtin_type(py: Python<'_>, candidate: &Bound<'_, PyAny>) -> PyResult<bool> {
    for name in ["bool", "bytes", "dict", "float", "int", "list", "str", "tuple"] {
        let builtins = py.import("builtins")?;
        let builtin = builtins.getattr(name)?;
        if candidate.cast::<PyType>()?.is_subclass(&builtin)? {
            return Ok(true);
        }
    }
    Ok(false)
}

#[pyclass(module = "bson.codec_options", frozen)]
pub struct CodecOptions {
    pub uuid: UuidRepresentation,
    pub tz_aware: bool,
    pub tzinfo: Option<Py<PyAny>>,
    pub datetime_conversion: DatetimeConversion,
    pub type_registry: Option<Py<TypeRegistry>>,
}

impl Clone for CodecOptions {
    fn clone(&self) -> Self {
        Python::attach(|py| Self {
            uuid: self.uuid,
            tz_aware: self.tz_aware,
            tzinfo: self.tzinfo.as_ref().map(|value| value.clone_ref(py)),
            datetime_conversion: self.datetime_conversion,
            type_registry: self.type_registry.as_ref().map(|value| value.clone_ref(py)),
        })
    }
}

impl Default for CodecOptions {
    fn default() -> Self {
        Self {
            uuid: UuidRepresentation::Unspecified,
            tz_aware: false,
            tzinfo: None,
            datetime_conversion: DatetimeConversion::DATETIME,
            type_registry: None,
        }
    }
}

#[pymethods]
impl CodecOptions {
    #[new]
    #[pyo3(signature = (uuid_representation=0, *, tz_aware=false, datetime_conversion=1, type_registry=None, tzinfo=None))]
    fn new(
        py: Python<'_>, uuid_representation: i64, tz_aware: bool,
        datetime_conversion: u8, type_registry: Option<Py<TypeRegistry>>,
        tzinfo: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        if let Some(zone) = &tzinfo {
            if !zone.bind(py).is_instance(&py.import("datetime")?.getattr("tzinfo")?)? {
                return Err(PyTypeError::new_err("tzinfo must be an instance of datetime.tzinfo"));
            }
            if !tz_aware {
                return Err(PyValueError::new_err("cannot specify tzinfo without also setting tz_aware=True"));
            }
        }
        let datetime_conversion = DatetimeConversion::parse(datetime_conversion)?;
        Ok(Self {
            uuid: UuidRepresentation::parse(uuid_representation)?,
            tz_aware,
            tzinfo,
            datetime_conversion,
            type_registry,
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
    fn tzinfo(&self, py: Python<'_>) -> Option<Py<PyAny>> {
        self.tzinfo.as_ref().map(|zone| zone.clone_ref(py))
    }

    #[getter]
    fn datetime_conversion(&self) -> u8 {
        self.datetime_conversion as u8
    }

    #[pyo3(signature = (*, uuid_representation=None, tz_aware=None, datetime_conversion=None, type_registry=None, tzinfo=None))]
    fn with_options(
        &self,
        py: Python<'_>,
        uuid_representation: Option<i64>,
        tz_aware: Option<bool>,
        datetime_conversion: Option<u8>,
        type_registry: Option<Py<TypeRegistry>>,
        tzinfo: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        Self::new(
            py,
            uuid_representation.unwrap_or(self.uuid as i64),
            tz_aware.unwrap_or(self.tz_aware),
            datetime_conversion.unwrap_or(self.datetime_conversion as u8),
            type_registry.or_else(|| self.type_registry.as_ref().map(|r| r.clone_ref(py))),
            tzinfo.or_else(|| self.tzinfo.as_ref().map(|zone| zone.clone_ref(py))),
        )
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let zone = match &self.tzinfo {
            Some(zone) => zone.bind(py).repr()?.to_string(),
            None => "None".to_owned(),
        };
        Ok(format!(
            "CodecOptions(uuid_representation={}, tz_aware={}, datetime_conversion={}, tzinfo={})",
            self.uuid as u8, self.tz_aware, self.datetime_conversion as u8, zone
        ))
    }
}

pub fn resolve_all(options: Option<&Bound<'_, PyAny>>) -> PyResult<CodecOptions> {
    match options.filter(|value| !value.is_none()) {
        None => Ok(CodecOptions::default()),
        Some(value) => value
            .extract::<PyRef<'_, CodecOptions>>()
            .map(|value| (*value).clone())
            .map_err(|_| PyTypeError::new_err("codec_options must be an instance of CodecOptions")),
    }
}
