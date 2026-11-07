//! BSON wire primitives, independent of Python.

use std::collections::TryReserveError;

#[derive(Debug)]
pub enum WriteError {
    TooLarge,
    Allocation(TryReserveError),
}

pub struct Writer {
    data: Vec<u8>,
}

impl Writer {
    pub fn new() -> Self {
        // A modest initial allocation avoids tiny growth steps without reserving
        // kilobytes for every small document. Larger payloads grow on demand.
        Self {
            data: Vec::with_capacity(256),
        }
    }

    pub fn write(&mut self, bytes: &[u8]) -> Result<(), WriteError> {
        self.ensure_capacity(bytes.len())?;
        self.data.extend_from_slice(bytes);
        Ok(())
    }

    #[inline]
    pub fn int32(&mut self, value: i32) -> Result<(), WriteError> {
        self.ensure_capacity(4)?;
        self.data.extend_from_slice(&value.to_le_bytes());
        Ok(())
    }

    #[inline]
    pub fn int64(&mut self, value: i64) -> Result<(), WriteError> {
        self.ensure_capacity(8)?;
        self.data.extend_from_slice(&value.to_le_bytes());
        Ok(())
    }

    pub fn header(&mut self, tag: u8, name: &[u8]) -> Result<(), WriteError> {
        let size = 1usize
            .checked_add(name.len())
            .and_then(|size| size.checked_add(1))
            .ok_or(WriteError::TooLarge)?;
        self.ensure_capacity(size)?;
        self.data.push(tag);
        self.data.extend_from_slice(name);
        self.data.push(0);
        Ok(())
    }

    pub fn begin_document(&mut self) -> Result<usize, WriteError> {
        let start = self.data.len();
        self.ensure_capacity(4)?;
        self.data.extend_from_slice(&[0; 4]);
        Ok(start)
    }

    pub fn end_document(&mut self, start: usize) -> Result<(), WriteError> {
        self.ensure_capacity(1)?;
        self.data.push(0);
        let length = i32::try_from(self.data.len() - start).map_err(|_| WriteError::TooLarge)?;
        self.data[start..start + 4].copy_from_slice(&length.to_le_bytes());
        Ok(())
    }

    pub fn length(&mut self, length: usize) -> Result<(), WriteError> {
        let length = i32::try_from(length).map_err(|_| WriteError::TooLarge)?;
        self.write(&length.to_le_bytes())
    }

    pub fn finish_length(&mut self, start: usize) -> Result<(), WriteError> {
        let length = i32::try_from(self.data.len() - start).map_err(|_| WriteError::TooLarge)?;
        self.data[start..start + 4].copy_from_slice(&length.to_le_bytes());
        Ok(())
    }

    pub fn into_bytes(self) -> Vec<u8> {
        self.data
    }

    fn ensure_capacity(&mut self, additional: usize) -> Result<(), WriteError> {
        let size = self
            .data
            .len()
            .checked_add(additional)
            .ok_or(WriteError::TooLarge)?;
        if size > i32::MAX as usize {
            return Err(WriteError::TooLarge);
        }
        if size > self.data.capacity() {
            // A large payload is normally followed by document terminators or
            // another field. Reserving exactly its size forces a second growth
            // (and potentially a full payload copy) for the very next byte.
            let capacity = size.saturating_add(64).min(i32::MAX as usize);
            self.data
                .try_reserve(capacity - self.data.len())
                .map_err(WriteError::Allocation)?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_document() {
        let mut writer = Writer::new();
        let start = writer.begin_document().unwrap();
        writer.end_document(start).unwrap();
        assert_eq!(writer.into_bytes(), [5, 0, 0, 0, 0]);
    }

    #[test]
    fn nested_document_lengths() {
        let mut writer = Writer::new();
        let root = writer.begin_document().unwrap();
        writer.header(3, b"x").unwrap();
        let nested = writer.begin_document().unwrap();
        writer.end_document(nested).unwrap();
        writer.end_document(root).unwrap();
        assert_eq!(
            writer.into_bytes(),
            [13, 0, 0, 0, 3, b'x', 0, 5, 0, 0, 0, 0, 0]
        );
    }

    #[test]
    fn reject_length_overflow_without_allocating() {
        let mut writer = Writer::new();
        assert!(matches!(
            writer.length(i32::MAX as usize + 1),
            Err(WriteError::TooLarge)
        ));
    }

    #[test]
    fn integer_writes_and_buffer_growth() {
        let mut writer = Writer::new();
        writer.int32(i32::MIN).unwrap();
        writer.int64(i64::MAX).unwrap();
        let payload = vec![0x5a; 65_536];
        writer.write(&payload).unwrap();
        let bytes = writer.into_bytes();
        assert_eq!(&bytes[..4], &i32::MIN.to_le_bytes());
        assert_eq!(&bytes[4..12], &i64::MAX.to_le_bytes());
        assert_eq!(&bytes[12..], payload);
    }

    #[test]
    fn large_payload_leaves_room_for_document_tail() {
        let mut writer = Writer::new();
        let root = writer.begin_document().unwrap();
        writer.header(5, b"payload").unwrap();
        writer.length(65_536).unwrap();
        writer.write(&[0]).unwrap();
        writer.write(&vec![0x5a; 65_536]).unwrap();
        let capacity = writer.data.capacity();
        let pointer = writer.data.as_ptr();
        writer.end_document(root).unwrap();
        assert_eq!(writer.data.capacity(), capacity);
        assert_eq!(writer.data.as_ptr(), pointer);
        assert_eq!(writer.data.len(), 65_555);
    }
}
