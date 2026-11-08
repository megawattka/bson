use pyo3::exceptions::PyOverflowError;
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyBytes, PyDict, PyFloat, PyInt, PyList, PyString, PyTuple};

use super::{Encoder, Frame, Items, invalid};
use crate::objectid::ObjectId;
use crate::{binary, bridge};
use crate::{
    datetime::DatetimeMS,
    decimal128::Decimal128,
    keys::{MaxKey, MinKey},
    regex::Regex,
    timestamp::Timestamp,
};

impl<'py> Encoder<'py> {
    pub(super) fn value(&mut self, name: &[u8], value: Bound<'py, PyAny>) -> PyResult<()> {
        if let Some(transformed) = crate::codec_options::encode_registered(
            value.py(), &value, self.registry.as_ref(),
        )? {
            return self.value(name, transformed);
        }
        // Builtins and their subclasses share handlers. Only Int64 and Binary
        // need special handling within their respective builtin families.
        if value.is_none() {
            self.writer.header(0x0a, name)?;
            return Ok(());
        }
        if value.is_exact_instance_of::<PyBool>() {
            self.writer.header(0x08, name)?;
            self.writer.write(&[u8::from(value.extract::<bool>()?)])?;
            return Ok(());
        }
        if value.is_instance_of::<PyInt>() {
            let number = value.extract::<i64>().map_err(|_| {
                PyOverflowError::new_err("MongoDB can only handle up to 8-byte ints")
            })?;
            let force_int64 = !value.is_exact_instance_of::<PyInt>()
                && value.is_instance(bridge::int64(value.py())?.as_any())?;
            if let Ok(number) = i32::try_from(number)
                && !force_int64
            {
                self.writer.header(0x10, name)?;
                self.writer.int32(number)?;
            } else {
                self.writer.header(0x12, name)?;
                self.writer.int64(number)?;
            }
            return Ok(());
        }
        if value.is_instance_of::<PyFloat>() {
            self.writer.header(0x01, name)?;
            self.writer.write(&value.extract::<f64>()?.to_le_bytes())?;
            return Ok(());
        }
        if let Ok(text) = value.downcast::<PyString>() {
            if !value.is_exact_instance_of::<PyString>()
                && let Some(state) = crate::code::state(&value)?
            {
                let code = state.borrow();
                let text = text.to_str()?.as_bytes();
                if let Some(scope) = &code.scope {
                    self.writer.header(0x0f, name)?;
                    let code_start = self.writer.begin_document()?;
                    self.string(text)?;
                    let start = self.writer.begin_document()?;
                    let mut frame = Frame::document(scope.bind(value.py()).clone(), start, false)?;
                    frame.code_start = Some(code_start);
                    self.push(frame)?;
                } else {
                    self.writer.header(0x0d, name)?;
                    self.string(text)?;
                }
                return Ok(());
            }
            let text = text.to_str()?.as_bytes();
            self.writer.header(0x02, name)?;
            self.string(text)?;
            return Ok(());
        }
        if let Ok(bytes) = value.downcast::<PyBytes>() {
            let subtype = binary_subtype(&value)?;
            self.binary(name, bytes.as_bytes(), subtype)?;
            return Ok(());
        }
        if let Ok(reference) = value.extract::<PyRef<'_, crate::dbref::DBRef>>() {
            self.writer.header(0x03, name)?;
            let start = self.writer.begin_document()?;
            let mut frame = Frame::document(reference.as_doc(value.py())?, start, false)?;
            frame.identity = value.as_ptr() as usize;
            frame.unchecked = true;
            self.push(frame)?;
            return Ok(());
        }
        if let Ok(document) = value.downcast::<PyDict>() {
            self.writer.header(0x03, name)?;
            let start = self.writer.begin_document()?;
            self.push(Frame::document(document.clone(), start, false)?)?;
            return Ok(());
        }
        if let Ok(list) = value.downcast::<PyList>() {
            self.writer.header(0x04, name)?;
            let start = self.writer.begin_document()?;
            self.push(Frame {
                start,
                identity: value.as_ptr() as usize,
                items: Items::List(list.clone(), 0),
                code_start: None,
                unchecked: false,
            })?;
            return Ok(());
        }
        if let Ok(tuple) = value.downcast::<PyTuple>() {
            self.writer.header(0x04, name)?;
            let start = self.writer.begin_document()?;
            self.push(Frame {
                start,
                identity: value.as_ptr() as usize,
                items: Items::Tuple(tuple.clone(), 0),
                code_start: None,
                unchecked: false,
            })?;
            return Ok(());
        }
        // ObjectId is checked before containers and scalar fallbacks. This is
        // both the common BSON-special-type fast path and avoids constructing
        // its Python `binary` property.
        if value.is_instance_of::<ObjectId>() {
            let oid = value.extract::<PyRef<'_, ObjectId>>()?;
            self.writer.header(0x07, name)?;
            self.writer.write(oid.as_bytes())?;
        } else if let Ok(decimal) = value.extract::<PyRef<'_, Decimal128>>() {
            self.writer.header(0x13, name)?;
            self.writer.write(&decimal.bytes)?;
        } else if let Ok(timestamp) = value.extract::<PyRef<'_, Timestamp>>() {
            self.writer.header(0x11, name)?;
            self.writer.int32(timestamp.inc as i32)?;
            self.writer.int32(timestamp.time as i32)?;
        } else if let Ok(date) = value.extract::<PyRef<'_, DatetimeMS>>() {
            self.writer.header(0x09, name)?;
            self.writer.int64(date.value)?;
        } else if value.is_instance_of::<MinKey>() {
            self.writer.header(0xff, name)?;
        } else if value.is_instance_of::<MaxKey>() {
            self.writer.header(0x7f, name)?;
        } else if let Ok(regex) = value.extract::<PyRef<'_, Regex>>() {
            self.regex(name, regex.pattern.bind(value.py()), regex.flags)?;
        } else if crate::datetime::is_datetime(&value)? {
            self.writer.header(0x09, name)?;
            self.writer
                .int64(crate::datetime::datetime_millis(&value)?)?;
        } else if crate::regex::is_native(&value)? {
            self.regex(
                name,
                &value.getattr("pattern")?,
                value.getattr("flags")?.extract()?,
            )?;
        } else if value.is_instance(bridge::uuid(value.py())?.as_any())? {
            let bytes = binary::uuid_bytes(&value, self.uuid)?;
            self.binary(name, &bytes, self.uuid.subtype())?;
        } else {
            if let Some(transformed) = crate::codec_options::encode_custom(
                value.py(), &value, self.registry.as_ref(),
            )? {
                return self.value(name, transformed);
            }
            if let Some(registry) = self.registry.as_ref() {
                let registry = registry.bind(value.py()).borrow();
                if let Some(fallback) = &registry.fallback {
                    let transformed = fallback.bind(value.py()).call1((value,))?;
                    return self.value(name, transformed);
                }
            }
            return Err(invalid(format!(
                "cannot encode object: {}, of type: {}",
                value.repr()?,
                value.get_type()
            )));
        }
        Ok(())
    }

    fn binary(&mut self, name: &[u8], bytes: &[u8], subtype: u8) -> PyResult<()> {
        self.writer.header(0x05, name)?;
        // Old binary subtype 2 embeds a second length inside the payload.
        if subtype == 2 {
            self.writer.length(
                bytes
                    .len()
                    .checked_add(4)
                    .ok_or(super::writer::WriteError::TooLarge)?,
            )?;
            self.writer.write(&[subtype])?;
            self.writer.length(bytes.len())?;
        } else {
            self.writer.length(bytes.len())?;
            self.writer.write(&[subtype])?;
        }
        self.writer.write(bytes)?;
        Ok(())
    }

    fn string(&mut self, text: &[u8]) -> PyResult<()> {
        self.writer.length(
            text.len()
                .checked_add(1)
                .ok_or(super::writer::WriteError::TooLarge)?,
        )?;
        self.writer.write(text)?;
        self.writer.write(&[0])?;
        Ok(())
    }

    fn regex(&mut self, name: &[u8], pattern: &Bound<'_, PyAny>, flags: i64) -> PyResult<()> {
        let bytes = if let Ok(text) = pattern.downcast::<PyString>() {
            text.to_str()?.as_bytes()
        } else {
            pattern.downcast::<PyBytes>()?.as_bytes()
        };
        if bytes.contains(&0) {
            return Err(invalid("regex patterns must not contain the NULL byte"));
        }
        std::str::from_utf8(bytes).map_err(|_| invalid("regex pattern must be valid UTF-8"))?;
        self.writer.header(0x0b, name)?;
        self.writer.write(bytes)?;
        self.writer.write(&[0])?;
        for (ch, bit) in crate::regex::FLAGS {
            if flags & bit != 0 {
                self.writer.write(&[ch as u8])?;
            }
        }
        self.writer.write(&[0])?;
        Ok(())
    }
}

pub(super) fn binary_subtype(value: &Bound<'_, PyAny>) -> PyResult<u8> {
    if !value.is_exact_instance_of::<PyBytes>()
        && value.is_instance(bridge::binary(value.py())?.as_any())?
    {
        value.getattr("subtype")?.extract::<u8>()
    } else {
        Ok(0)
    }
}
