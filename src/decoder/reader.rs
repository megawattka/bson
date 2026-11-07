//! Bounds-checked BSON wire reader. This layer has no Python dependencies.

use std::fmt;

#[derive(Debug)]
pub struct ReadError {
    offset: usize,
    message: &'static str,
}

impl fmt::Display for ReadError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} at byte {}", self.message, self.offset)
    }
}

pub struct Reader<'a> {
    bytes: &'a [u8],
    position: usize,
    limit: usize,
}

impl<'a> Reader<'a> {
    pub fn new(bytes: &'a [u8]) -> Self {
        Self {
            bytes,
            position: 0,
            limit: bytes.len(),
        }
    }

    pub fn position(&self) -> usize {
        self.position
    }

    pub fn limit(&self) -> usize {
        self.limit
    }

    /// Only set to a previously validated enclosing document boundary.
    pub fn set_limit(&mut self, limit: usize) {
        debug_assert!(limit <= self.bytes.len());
        self.limit = limit;
    }

    pub fn error(&self, message: &'static str) -> ReadError {
        ReadError {
            offset: self.position,
            message,
        }
    }

    pub fn read(&mut self, length: usize) -> Result<&'a [u8], ReadError> {
        if length > self.limit.saturating_sub(self.position) {
            return Err(self.error("truncated BSON value"));
        }
        let start = self.position;
        self.position += length;
        Ok(&self.bytes[start..self.position])
    }

    pub fn array<const N: usize>(&mut self) -> Result<[u8; N], ReadError> {
        let mut bytes = [0; N];
        bytes.copy_from_slice(self.read(N)?);
        Ok(bytes)
    }

    pub fn byte(&mut self) -> Result<u8, ReadError> {
        Ok(self.array::<1>()?[0])
    }

    pub fn int32(&mut self) -> Result<i32, ReadError> {
        Ok(i32::from_le_bytes(self.array()?))
    }

    pub fn int64(&mut self) -> Result<i64, ReadError> {
        Ok(i64::from_le_bytes(self.array()?))
    }

    pub fn double(&mut self) -> Result<f64, ReadError> {
        Ok(f64::from_le_bytes(self.array()?))
    }

    pub fn cstring(&mut self) -> Result<&'a [u8], ReadError> {
        let remaining = &self.bytes[self.position..self.limit];
        let length = remaining
            .iter()
            .position(|byte| *byte == 0)
            .ok_or_else(|| self.error("unterminated BSON field name"))?;
        let start = self.position;
        self.position += length + 1;
        Ok(&self.bytes[start..start + length])
    }

    pub fn string(&mut self) -> Result<&'a [u8], ReadError> {
        let length = self.int32()?;
        if length < 1 {
            return Err(self.error("BSON string length must be positive"));
        }
        let bytes = self.read(length as usize)?;
        if bytes[bytes.len() - 1] != 0 {
            return Err(self.error("BSON string is missing its NUL terminator"));
        }
        Ok(&bytes[..bytes.len() - 1])
    }

    /// Read a document header and validate it against the enclosing boundary.
    /// The returned end includes the trailing NUL; position is left at the body.
    pub fn document(&mut self) -> Result<usize, ReadError> {
        let start = self.position;
        let length = self.int32()?;
        if length < 5 {
            return Err(self.error("BSON document length must be at least 5"));
        }
        let end = start
            .checked_add(length as usize)
            .filter(|end| *end <= self.limit)
            .ok_or_else(|| self.error("BSON document exceeds its enclosing boundary"))?;
        if self.bytes[end - 1] != 0 {
            return Err(self.error("BSON document is missing its NUL terminator"));
        }
        Ok(end)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn primitives_and_unaligned_reads() {
        let mut bytes = vec![42];
        bytes.extend_from_slice(&(-123i32).to_le_bytes());
        bytes.extend_from_slice(&i64::MIN.to_le_bytes());
        bytes.extend_from_slice(&1.5f64.to_le_bytes());
        let mut reader = Reader::new(&bytes);
        assert_eq!(reader.byte().unwrap(), 42);
        assert_eq!(reader.int32().unwrap(), -123);
        assert_eq!(reader.int64().unwrap(), i64::MIN);
        assert_eq!(reader.double().unwrap(), 1.5);
        assert!(reader.byte().is_err());
    }

    #[test]
    fn failed_reads_do_not_advance() {
        let mut reader = Reader::new(&[1, 2, 3]);
        assert!(reader.read(usize::MAX).is_err());
        assert_eq!(reader.position(), 0);
        assert!(reader.int32().is_err());
        assert_eq!(reader.position(), 0);
    }

    #[test]
    fn respect_enclosing_boundaries() {
        let mut reader = Reader::new(b"a\0b\0");
        reader.set_limit(1);
        assert!(reader.cstring().is_err());
        reader.set_limit(4);
        assert_eq!(reader.cstring().unwrap(), b"a");
        assert_eq!(reader.cstring().unwrap(), b"b");
    }

    #[test]
    fn document_headers() {
        let mut reader = Reader::new(&[5, 0, 0, 0, 0]);
        assert_eq!(reader.document().unwrap(), 5);
        assert_eq!(reader.position(), 4);
        for bytes in [
            vec![4, 0, 0, 0, 0],
            vec![6, 0, 0, 0, 0],
            vec![5, 0, 0, 0, 1],
            vec![255; 5],
        ] {
            assert!(Reader::new(&bytes).document().is_err());
        }
    }
}
