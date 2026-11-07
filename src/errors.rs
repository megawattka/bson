//! Shared public exception hierarchy for BSON operations.

use pyo3::exceptions::PyException;

pyo3::create_exception!(bson.errors, BSONError, PyException);
pyo3::create_exception!(bson.errors, InvalidDocument, BSONError);
pyo3::create_exception!(bson.errors, InvalidBSON, BSONError);
pyo3::create_exception!(bson.errors, InvalidId, BSONError);
