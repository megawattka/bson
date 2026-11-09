//! BSON tag dispatch. New scalar types belong here or in dedicated handlers.
//! Container traversal stays in the decoder, not in individual type handlers.

use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyString};

use super::reader::Reader;
use crate::codec_options::{CodecOptions, UuidRepresentation};
use crate::errors::InvalidBSON;
use crate::objectid::ObjectId;
use crate::{binary, bridge};
use crate::{
    decimal128::Decimal128,
    keys::{MaxKey, MinKey},
    regex::Regex,
    timestamp::Timestamp,
};

pub(super) enum ContainerKind {
    Document,
    Array,
}

pub(super) enum Value<'py> {
    Scalar(Bound<'py, PyAny>),
    Container {
        kind: ContainerKind,
        end: usize,
    },
    CodeScope {
        text: Bound<'py, PyString>,
        end: usize,
    },
}

pub(super) fn text<'py>(py: Python<'py>, bytes: &[u8]) -> PyResult<Bound<'py, PyString>> {
    // CPython validates UTF-8 while constructing the string. Validating it in
    // Rust first would scan every field name and string value twice.
    // SAFETY: bytes remains alive during the call, its length fits Py_ssize_t
    // (it is a slice of a Python-owned input), and NULL selects strict errors.
    let text = unsafe {
        Bound::from_owned_ptr_or_err(
            py,
            pyo3::ffi::PyUnicode_DecodeUTF8(
                bytes.as_ptr().cast(),
                bytes.len() as pyo3::ffi::Py_ssize_t,
                std::ptr::null(),
            ),
        )
    }
    .map_err(|error| InvalidBSON::new_err(format!("invalid UTF-8 in BSON: {error}")))?;
    // PyUnicode_DecodeUTF8 returns a Unicode object on success.
    Ok(text.cast_into::<PyString>()?)
}

fn binary<'py>(
    py: Python<'py>,
    reader: &mut Reader<'_>,
    uuid: UuidRepresentation,
) -> PyResult<Bound<'py, PyAny>> {
    let length = reader.int32()?;
    if length < 0 {
        return Err(reader.error("negative BSON binary length").into());
    }
    let subtype = reader.byte()?;
    let length = if subtype == 2 {
        if length < 4 {
            return Err(reader
                .error("old binary payload must include an inner length")
                .into());
        }
        let inner = reader.int32()?;
        if inner < 0 || inner != length - 4 {
            return Err(reader
                .error("old binary inner length does not match outer length")
                .into());
        }
        inner
    } else {
        length
    };
    let bytes = reader.read(length as usize)?;
    if subtype == 0 {
        return Ok(PyBytes::new(py, bytes).into_any());
    }
    if uuid.decodes(subtype) {
        if bytes.len() != 16 {
            return Err(reader.error("UUID must contain exactly 16 bytes").into());
        }
        return binary::as_uuid(py, bytes, uuid);
    }
    binary::build_binary(py, bytes, subtype)
}

pub(super) fn decode<'py>(
    py: Python<'py>,
    reader: &mut Reader<'_>,
    tag: u8,
    options: CodecOptions,
) -> PyResult<Value<'py>> {
    let scalar = match tag {
        0x01 => reader.double()?.into_pyobject(py)?.into_any(),
        0x02 => text(py, reader.string()?)?.into_any(),
        0x03 | 0x04 => {
            let end = reader.document()?;
            return Ok(Value::Container {
                kind: if tag == 0x03 {
                    ContainerKind::Document
                } else {
                    ContainerKind::Array
                },
                end,
            });
        }
        0x05 => binary(py, reader, options.uuid)?,
        0x09 => crate::datetime::from_millis(py, reader.int64()?, options)?,
        0x0b => {
            let pattern = text(py, reader.cstring()?)?;
            let flags = text(py, reader.cstring()?)?;
            Py::new(
                py,
                Regex::from_parts(pattern.as_any(), Some(flags.as_any()))?,
            )?
            .into_bound(py)
            .into_any()
        }
        0x0d => {
            let text = text(py, reader.string()?)?;
            bridge::code(py)?.call1((text,))?
        }
        0x0f => {
            let start = reader.position();
            let length = reader.int32()?;
            if length < 14 {
                return Err(reader
                    .error("code with scope length must be at least 14")
                    .into());
            }
            let end = start
                .checked_add(length as usize)
                .filter(|end| *end <= reader.limit())
                .ok_or_else(|| reader.error("code with scope exceeds enclosing boundary"))?;
            reader.set_limit(end);
            let text = text(py, reader.string()?)?;
            let scope_end = reader.document()?;
            if scope_end != end {
                return Err(reader
                    .error("code with scope length does not match scope document")
                    .into());
            }
            return Ok(Value::CodeScope { text, end });
        }
        0x11 => {
            let inc = u32::from_le_bytes(reader.array()?);
            let time = u32::from_le_bytes(reader.array()?);
            Py::new(py, Timestamp { time, inc })?
                .into_bound(py)
                .into_any()
        }
        0x13 => Py::new(
            py,
            Decimal128 {
                bytes: reader.array()?,
            },
        )?
        .into_bound(py)
        .into_any(),
        0x7f => Py::new(py, MaxKey)?.into_bound(py).into_any(),
        0xff => Py::new(py, MinKey)?.into_bound(py).into_any(),
        0x07 => Py::new(py, ObjectId::from_bytes(reader.array()?))?
            .into_bound(py)
            .into_any(),
        0x08 => {
            let byte = reader.byte()?;
            if byte > 1 {
                return Err(reader.error("BSON boolean must be 0 or 1").into());
            }
            (byte == 1).into_pyobject(py)?.to_owned().into_any()
        }
        0x0a => py.None().into_bound(py),
        0x10 => reader.int32()?.into_pyobject(py)?.into_any(),
        0x12 => bridge::int64(py)?.call1((reader.int64()?,))?,
        _ => {
            return Err(InvalidBSON::new_err(format!(
                "unsupported BSON type 0x{tag:02x} at byte {}",
                reader.position()
            )));
        }
    };
    Ok(Value::Scalar(scalar))
}
