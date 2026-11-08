//! Public API and iterative document traversal, shared by decode/decode_all.

mod reader;
mod value;

use std::borrow::Cow;

use pyo3::buffer::PyBuffer;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList, PyString};

use crate::codec_options::{self, CodecOptions};
use crate::errors::InvalidBSON;
use reader::{ReadError, Reader};
use value::{ContainerKind, Value};

const MAX_DEPTH: usize = 100;

// Per-call and bounded: repeated batch schemas reuse both Unicode objects and
// their cached Python hashes without interning attacker-controlled field names.
// Borrowed names remain valid because the input snapshot outlives traversal.
struct KeyCache<'a, 'py> {
    slots: [Option<(&'a [u8], Bound<'py, PyString>)>; 64],
}

impl<'a, 'py> KeyCache<'a, 'py> {
    fn new() -> Self {
        Self { slots: std::array::from_fn(|_| None) }
    }

    fn get(&mut self, py: Python<'py>, name: &'a [u8]) -> PyResult<Bound<'py, PyString>> {
        // Avoid retaining large keys. Byte equality, not this cheap index,
        // determines a cache hit, including for colliding and invalid UTF-8 keys.
        if name.len() > 64 {
            return value::text(py, name);
        }
        let index = (name.len()
            ^ usize::from(name.first().copied().unwrap_or(0))
            ^ (usize::from(name.last().copied().unwrap_or(0)) << 1)) & 63;
        if let Some((previous, key)) = &self.slots[index] {
            if *previous == name {
                return Ok(key.clone());
            }
        }
        let key = value::text(py, name)?;
        self.slots[index] = Some((name, key.clone()));
        Ok(key)
    }
}

impl From<ReadError> for PyErr {
    fn from(error: ReadError) -> Self {
        InvalidBSON::new_err(error.to_string())
    }
}

enum Container<'py> {
    Document(Bound<'py, PyDict>),
    Array(Bound<'py, PyList>),
}

impl<'py> Container<'py> {
    fn new(py: Python<'py>, kind: ContainerKind) -> Self {
        match kind {
            ContainerKind::Document => Self::Document(PyDict::new(py)),
            ContainerKind::Array => Self::Array(PyList::empty(py)),
        }
    }

    fn insert(&self, key: Option<Bound<'py, PyString>>, value: &Bound<'py, PyAny>) -> PyResult<()> {
        match self {
            Self::Document(document) => {
                let key = key.ok_or_else(|| InvalidBSON::new_err("missing document field name"))?;
                document.set_item(key, value)
            }
            Self::Array(array) => array.append(value),
        }
    }

    fn into_any(self) -> Bound<'py, PyAny> {
        match self {
            Self::Document(document) => document.into_any(),
            Self::Array(array) => array.into_any(),
        }
    }
}

struct Frame<'py> {
    container: Container<'py>,
    // Includes the document's final NUL, which values must never consume.
    end: usize,
    parent_key: Option<Bound<'py, PyString>>,
    code: Option<Bound<'py, PyString>>,
    // Only embedded documents containing this exact wire key can be DBRefs.
    has_ref: bool,
}

fn document<'a, 'py>(
    py: Python<'py>,
    reader: &mut Reader<'a>,
    options: CodecOptions,
    stack: &mut Vec<Frame<'py>>,
    mut keys: Option<&mut KeyCache<'a, 'py>>,
) -> PyResult<Bound<'py, PyDict>> {
    debug_assert!(stack.is_empty());
    let end = reader.document()?;
    // Keep the active frame on the native stack. Flat documents (including
    // empty ones) never allocate a traversal Vec or clone the root dict.
    let mut frame = Frame {
        container: Container::Document(PyDict::new(py)),
        end,
        parent_key: None,
        code: None,
        has_ref: false,
    };
    loop {
        reader.set_limit(frame.end - 1);
        if reader.position() == frame.end - 1 {
            reader.set_limit(frame.end);
            reader.byte()?; // Validated by Reader::document before entering.
            if let Some(parent) = stack.pop() {
                let value = if let Some(text) = frame.code {
                    let scope = frame.container.into_any().downcast_into::<PyDict>()?;
                    crate::bridge::code(py)?.call1((text, scope))?
                } else {
                    match frame.container {
                        Container::Document(doc) if frame.has_ref => crate::dbref::from_document(doc)?,
                        Container::Document(doc) => doc.into_any(),
                        Container::Array(array) => array.into_any(),
                    }
                };
                parent.container.insert(frame.parent_key, &value)?;
                frame = parent;
                continue;
            }
            return Ok(frame.container.into_any().downcast_into::<PyDict>()?);
        }
        let tag = reader.byte()?;
        if tag == 0 {
            return Err(reader.error("premature BSON document terminator").into());
        }
        let name = reader.cstring()?;
        if name == b"$ref" {
            frame.has_ref = true;
        }
        // BSON arrays are ordered values; PyMongo ignores their wire field names.
        let key = match frame.container {
            Container::Document(_) => Some(match keys.as_deref_mut() {
                Some(cache) => cache.get(py, name)?,
                None => value::text(py, name)?,
            }),
            Container::Array(_) => None,
        };
        match value::decode(py, reader, tag, options.clone())? {
            Value::Scalar(value) => {
                let value = codec_options::decode_custom(
                    py, value, options.type_registry.as_ref(),
                )?;
                frame.container.insert(key, &value)?;
            }
            Value::Container { kind, end } => {
                if stack.len() + 1 >= MAX_DEPTH {
                    return Err(InvalidBSON::new_err("BSON nesting exceeds 100 containers"));
                }
                let child = Frame {
                    container: Container::new(py, kind),
                    end,
                    parent_key: key,
                    code: None,
                    has_ref: false,
                };
                stack.push(std::mem::replace(&mut frame, child));
            }
            Value::CodeScope { text, end } => {
                if stack.len() + 1 >= MAX_DEPTH {
                    return Err(InvalidBSON::new_err("BSON nesting exceeds 100 containers"));
                }
                let child = Frame {
                    container: Container::Document(PyDict::new(py)),
                    end,
                    parent_key: key,
                    code: Some(text),
                    has_ref: false,
                };
                stack.push(std::mem::replace(&mut frame, child));
            }
        }
    }
}

fn input<'a>(data: &'a Bound<'_, PyAny>) -> PyResult<Cow<'a, [u8]>> {
    if let Ok(bytes) = data.downcast::<PyBytes>() {
        return Ok(Cow::Borrowed(bytes.as_bytes()));
    }
    // Snapshot mutable/exported buffers: never retain a Rust byte slice into
    // memory another exporter could mutate. PyBuffer also handles strided input.
    let buffer = PyBuffer::<u8>::get(data)?;
    Ok(Cow::Owned(buffer.to_vec(data.py())?))
}

/// Decode exactly one BSON document. Trailing data is an error.
#[pyfunction]
#[pyo3(signature = (data, codec_options=None))]
pub fn decode<'py>(
    data: &Bound<'py, PyAny>,
    codec_options: Option<&Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyDict>> {
    let options = codec_options::resolve_all(codec_options)?;
    let bytes = input(data)?;
    let mut reader = Reader::new(&bytes);
    let result = document(data.py(), &mut reader, options, &mut Vec::new(), None)?;
    if reader.position() != bytes.len() {
        return Err(InvalidBSON::new_err("trailing bytes after BSON document"));
    }
    Ok(result)
}

/// Decode a sequence of concatenated BSON documents. Empty input returns [].
#[pyfunction]
#[pyo3(signature = (data, codec_options=None))]
pub fn decode_all<'py>(
    data: &Bound<'py, PyAny>,
    codec_options: Option<&Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyList>> {
    let options = codec_options::resolve_all(codec_options)?;
    let bytes = input(data)?;
    let mut reader = Reader::new(&bytes);
    let result = PyList::empty(data.py());
    // Reuse nesting storage across the entire batch, not once per document.
    let mut stack = Vec::new();
    let mut keys = KeyCache::new();
    while reader.position() < bytes.len() {
        reader.set_limit(bytes.len());
        result.append(document(data.py(), &mut reader, options.clone(), &mut stack, Some(&mut keys))?)?;
    }
    Ok(result)
}
