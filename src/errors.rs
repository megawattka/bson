//! Shared public exception hierarchy for BSON operations.

use pyo3::exceptions::PyException;

pyo3::create_exception!(elune.errors, BSONError, PyException);
pyo3::create_exception!(elune.errors, InvalidDocument, BSONError);
pyo3::create_exception!(elune.errors, InvalidBSON, BSONError);
pyo3::create_exception!(elune.errors, InvalidId, BSONError);
