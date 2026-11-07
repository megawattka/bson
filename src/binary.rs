//! UUID conversion and generic BSON binary construction.
//! Legacy transforms are involutions: the same operation encodes and decodes.

use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict};

use crate::bridge;
use crate::codec_options::UuidRepresentation;

pub fn transform(mut bytes: [u8; 16], representation: UuidRepresentation) -> [u8; 16] {
    match representation {
        UuidRepresentation::JavaLegacy => {
            bytes[..8].reverse();
            bytes[8..].reverse();
        }
        UuidRepresentation::CSharpLegacy => {
            bytes[..4].reverse();
            bytes[4..6].reverse();
            bytes[6..8].reverse();
        }
        _ => {}
    }
    bytes
}

pub fn uuid_bytes(
    value: &Bound<'_, PyAny>,
    representation: UuidRepresentation,
) -> PyResult<[u8; 16]> {
    if representation == UuidRepresentation::Unspecified {
        return Err(PyValueError::new_err(
            "cannot encode native uuid.UUID with UuidRepresentation.UNSPECIFIED. Use Binary.from_uuid() or configure CodecOptions(uuid_representation=UuidRepresentation.STANDARD).",
        ));
    }
    let bytes = value.getattr("bytes")?;
    let bytes = bytes.downcast::<PyBytes>()?;
    let bytes = bytes
        .as_bytes()
        .try_into()
        .map_err(|_| PyValueError::new_err("UUID must contain exactly 16 bytes"))?;
    Ok(transform(bytes, representation))
}

pub fn as_uuid<'py>(
    py: Python<'py>,
    bytes: &[u8],
    representation: UuidRepresentation,
) -> PyResult<Bound<'py, PyAny>> {
    let bytes: [u8; 16] = bytes
        .try_into()
        .map_err(|_| PyValueError::new_err("UUID must contain exactly 16 bytes"))?;
    let bytes = transform(bytes, representation);
    let kwargs = PyDict::new(py);
    kwargs.set_item("bytes", PyBytes::new(py, &bytes))?;
    bridge::uuid(py)?.call((), Some(&kwargs))
}

pub fn build_binary<'py>(py: Python<'py>, bytes: &[u8], subtype: u8) -> PyResult<Bound<'py, PyAny>> {
    crate::builtins::build_binary(
        &bridge::binary(py)?,
        PyBytes::new(py, bytes).as_any(),
        subtype,
    )
}

pub fn _uuid_to_binary<'py>(
    uuid: &Bound<'py, PyAny>,
    uuid_representation: i64,
) -> PyResult<(Bound<'py, PyBytes>, u8)> {
    let py = uuid.py();
    if !uuid.is_instance(bridge::uuid(py)?.as_any())? {
        return Err(PyTypeError::new_err(
            "uuid must be an instance of uuid.UUID",
        ));
    }
    let representation = UuidRepresentation::parse(uuid_representation)?;
    let bytes = uuid_bytes(uuid, representation)?;
    Ok((PyBytes::new(py, &bytes), representation.subtype()))
}

pub fn _binary_as_uuid<'py>(
    data: &Bound<'py, PyBytes>,
    subtype: u8,
    uuid_representation: i64,
) -> PyResult<Bound<'py, PyAny>> {
    let representation = UuidRepresentation::parse(uuid_representation)?;
    if !representation.decodes(subtype) {
        return Err(PyValueError::new_err(
            "binary subtype does not match uuid_representation (UNSPECIFIED cannot decode UUIDs)",
        ));
    }
    as_uuid(data.py(), data.as_bytes(), representation)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reference_byte_orders() {
        let canonical = [
            0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd,
            0xee, 0xff,
        ];
        let java = [
            0x77, 0x66, 0x55, 0x44, 0x33, 0x22, 0x11, 0x00, 0xff, 0xee, 0xdd, 0xcc, 0xbb, 0xaa,
            0x99, 0x88,
        ];
        let csharp = [
            0x33, 0x22, 0x11, 0x00, 0x55, 0x44, 0x77, 0x66, 0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd,
            0xee, 0xff,
        ];
        for (rep, expected) in [
            (UuidRepresentation::Standard, canonical),
            (UuidRepresentation::PythonLegacy, canonical),
            (UuidRepresentation::JavaLegacy, java),
            (UuidRepresentation::CSharpLegacy, csharp),
        ] {
            assert_eq!(transform(canonical, rep), expected);
            assert_eq!(transform(expected, rep), canonical);
        }
    }
}
