mod value;
mod writer;

use pyo3::exceptions::{PyMemoryError, PyRecursionError, PyTypeError};
use pyo3::prelude::*;
use pyo3::types::iter::BoundDictIterator;
use pyo3::types::{PyBytes, PyDict, PyList, PyString, PyTuple};

use crate::codec_options::{self, UuidRepresentation};
use crate::errors::InvalidDocument;
use writer::{WriteError, Writer};

// Includes the root document. Explicit frames avoid native stack exhaustion.
const MAX_DEPTH: usize = 100;

impl From<WriteError> for PyErr {
    fn from(error: WriteError) -> Self {
        match error {
            WriteError::TooLarge => {
                InvalidDocument::new_err("BSON document exceeds the int32 size limit")
            }
            WriteError::Allocation(error) => PyMemoryError::new_err(error.to_string()),
        }
    }
}

pub(super) fn invalid(message: impl Into<String>) -> PyErr {
    InvalidDocument::new_err(format!("Invalid document: {}", message.into()))
}

enum Items<'py> {
    Document {
        iterator: BoundDictIterator<'py>,
        root: bool,
        first_id: Option<Bound<'py, PyAny>>,
        root_id_present: bool,
    },
    List(Bound<'py, PyList>, usize),
    Tuple(Bound<'py, PyTuple>, usize),
}

struct Frame<'py> {
    items: Items<'py>,
    start: usize,
    identity: usize,
    code_start: Option<usize>,
    unchecked: bool,
}

enum Element<'py> {
    Field(Bound<'py, PyAny>, Bound<'py, PyAny>),
    Id(Bound<'py, PyAny>),
    Index(usize, Bound<'py, PyAny>),
}

impl<'py> Frame<'py> {
    fn document(document: Bound<'py, PyDict>, start: usize, root: bool) -> PyResult<Self> {
        let first_id = if root {
            document.get_item("_id")?
        } else {
            None
        };
        let root_id_present = first_id.is_some();
        Ok(Self {
            code_start: None,
            unchecked: false,
            identity: document.as_ptr() as usize,
            items: Items::Document {
                iterator: document.iter(),
                root,
                first_id,
                root_id_present,
            },
            start,
        })
    }

    fn next(&mut self) -> PyResult<Option<Element<'py>>> {
        match &mut self.items {
            Items::Document {
                iterator,
                root,
                first_id,
                root_id_present,
            } => {
                if let Some(value) = first_id.take() {
                    return Ok(Some(Element::Id(value)));
                }
                for (key, value) in iterator.by_ref() {
                    if *root_id_present
                        && *root
                        && key
                            .downcast::<PyString>()
                            .is_ok_and(|key| key.to_str().is_ok_and(|key| key == "_id"))
                    {
                        continue;
                    }
                    return Ok(Some(Element::Field(key, value)));
                }
                Ok(None)
            }
            Items::List(list, index) => {
                if *index >= list.len() {
                    return Ok(None);
                }
                let current = *index;
                *index += 1;
                Ok(Some(Element::Index(current, list.get_item(current)?)))
            }
            Items::Tuple(tuple, index) => {
                if *index >= tuple.len() {
                    return Ok(None);
                }
                let current = *index;
                *index += 1;
                Ok(Some(Element::Index(current, tuple.get_item(current)?)))
            }
        }
    }
}

pub(super) struct Encoder<'py> {
    writer: Writer,
    stack: Vec<Frame<'py>>,
    check_keys: bool,
    uuid: UuidRepresentation,
    registry: Option<Py<crate::codec_options::TypeRegistry>>,
}

impl<'py> Encoder<'py> {
    fn push(&mut self, mut frame: Frame<'py>) -> PyResult<()> {
        frame.unchecked |= self.stack.last().is_some_and(|parent| parent.unchecked);
        if self
            .stack
            .iter()
            .any(|active| active.identity == frame.identity)
        {
            return Err(invalid("cannot encode a cyclic document or array"));
        }
        if self.stack.len() >= MAX_DEPTH {
            return Err(PyRecursionError::new_err(
                "BSON nesting exceeds 100 containers",
            ));
        }
        self.stack.push(frame);
        Ok(())
    }

    fn field(&mut self, key: Bound<'py, PyAny>, value: Bound<'py, PyAny>) -> PyResult<()> {
        let unchecked = self.stack.last().is_some_and(|frame| frame.unchecked);
        let name = field_name(&key, self.check_keys && !unchecked)?;
        self.value(name, value)
    }

    fn run(mut self, document: Bound<'py, PyDict>) -> PyResult<Vec<u8>> {
        let start = self.writer.begin_document()?;
        self.push(Frame::document(document, start, true)?)?;
        while let Some(frame) = self.stack.last_mut() {
            match frame.next()? {
                Some(Element::Field(key, value)) => self.field(key, value)?,
                Some(Element::Id(value)) => self.value(b"_id", value)?,
                Some(Element::Index(mut index, value)) => {
                    let mut digits = [0; 20];
                    let mut position = digits.len();
                    loop {
                        position -= 1;
                        digits[position] = b'0' + (index % 10) as u8;
                        index /= 10;
                        if index == 0 {
                            break;
                        }
                    }
                    self.value(&digits[position..], value)?;
                }
                None => {
                    let frame = self.stack.pop().expect("frame exists while traversing");
                    self.writer.end_document(frame.start)?;
                    if let Some(start) = frame.code_start {
                        self.writer.finish_length(start)?;
                    }
                }
            }
        }
        Ok(self.writer.into_bytes())
    }
}

fn field_name<'a>(key: &'a Bound<'_, PyAny>, check_keys: bool) -> PyResult<&'a [u8]> {
    let key = key.downcast::<PyString>().map_err(|_| {
        invalid(format!(
            "documents must have only string keys, key was {}",
            key.repr().map_or_else(
                |_| "<unprintable>".into(),
                |s| s.to_string_lossy().into_owned()
            )
        ))
    })?;
    let name = key.to_str()?;
    if name.as_bytes().contains(&0) {
        return Err(invalid("Key names must not contain the NULL byte"));
    }
    if check_keys {
        if name.starts_with('$') {
            return Err(invalid(format!(
                "key {} must not start with '$'",
                key.repr()?
            )));
        }
        if name.contains('.') {
            return Err(invalid(format!("key {} must not contain '.'", key.repr()?)));
        }
    }
    Ok(name.as_bytes())
}

/// Avoid the intermediate Vec and its payload copy for large binary envelopes.
fn binary_document<'py>(
    dict: &Bound<'py, PyDict>,
    check_keys: bool,
) -> PyResult<Option<Bound<'py, PyBytes>>> {
    if dict.len() != 1 {
        return Ok(None);
    }
    let Some((key, value)) = dict.iter().next() else {
        return Ok(None);
    };
    let Ok(bytes) = value.downcast::<PyBytes>() else {
        return Ok(None);
    };
    let payload = bytes.as_bytes();
    if payload.len() < 4096 {
        return Ok(None);
    }
    let name = field_name(&key, check_keys)?;
    let subtype = value::binary_subtype(&value)?;
    let extra = if subtype == 2 { 4 } else { 0 };
    let size = name
        .len()
        .checked_add(12)
        .and_then(|size| size.checked_add(extra))
        .and_then(|size| size.checked_add(payload.len()))
        .filter(|size| *size <= i32::MAX as usize)
        .ok_or(WriteError::TooLarge)?;
    Ok(Some(PyBytes::new_with(dict.py(), size, |output| {
        output[..4].copy_from_slice(&(size as i32).to_le_bytes());
        output[4] = 0x05;
        output[5..5 + name.len()].copy_from_slice(name);
        output[5 + name.len()] = 0;
        let offset = 6 + name.len();
        output[offset..offset + 4].copy_from_slice(&((payload.len() + extra) as i32).to_le_bytes());
        output[offset + 4] = subtype;
        let start = offset + 5 + extra;
        if subtype == 2 {
            output[offset + 5..start].copy_from_slice(&(payload.len() as i32).to_le_bytes());
        }
        output[start..start + payload.len()].copy_from_slice(payload);
        output[size - 1] = 0;
        Ok(())
    })?))
}

/// Encode a dictionary as BSON. Nested dictionaries must also have string keys.
#[pyfunction]
#[pyo3(signature = (document, check_keys=false, codec_options=None))]
pub fn encode<'py>(
    document: &Bound<'py, PyAny>,
    check_keys: bool,
    codec_options: Option<&Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyBytes>> {
    let options = codec_options::resolve_all(codec_options)?;
    let dict = document
        .downcast::<PyDict>()
        .map_err(|_| PyTypeError::new_err("document must be a dict with string keys"))?;
    if let Some(bytes) = binary_document(dict, check_keys)? {
        return Ok(bytes);
    }
    let encoder = Encoder {
        writer: Writer::new(),
        stack: Vec::new(),
        check_keys,
        uuid: options.uuid,
        registry: options.type_registry,
    };
    let bytes = encoder.run(dict.clone())?;
    Ok(PyBytes::new(document.py(), &bytes))
}
