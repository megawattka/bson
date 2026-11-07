//! Integer-only datetime conversion compatible with the limited Python ABI.

use crate::codec_options::{self, CodecOptions, DatetimeConversion};
use pyo3::basic::CompareOp;
use pyo3::exceptions::{PyOverflowError, PyTypeError};
use pyo3::prelude::*;
use pyo3::sync::GILOnceCell;
use pyo3::types::PyType;
use pyo3::types::{PyDict, PyInt};

pub const MIN_MS: i64 = -62_135_596_800_000;
pub const MAX_MS: i64 = 253_402_300_799_999;

pub fn is_datetime(value: &Bound<'_, PyAny>) -> PyResult<bool> {
    value.is_instance(types(value.py())?.datetime.bind(value.py()))
}

pub fn to_millis(value: &Bound<'_, PyAny>) -> PyResult<i64> {
    if !is_datetime(value)? {
        return Err(PyTypeError::new_err("value must be a datetime.datetime"));
    }
    datetime_millis(value)
}

/// Internal conversion after the caller has checked the datetime type.
pub fn datetime_millis(value: &Bound<'_, PyAny>) -> PyResult<i64> {
    // Match datetime subtraction semantics, including sub-millisecond offsets.
    let offset = value.call_method0("utcoffset")?;
    let value = if offset.is_none() {
        value.clone()
    } else {
        value.call_method1("__sub__", (offset,))?
    };
    let component = |name: &str| value.getattr(name)?.extract::<i64>();
    let days = unix_days(component("year")?, component("month")?, component("day")?);
    Ok((days * 86400
        + component("hour")? * 3600
        + component("minute")? * 60
        + component("second")?)
        * 1000
        + component("microsecond")? / 1000)
}

pub fn from_millis(
    py: Python<'_>,
    millis: i64,
    options: CodecOptions,
) -> PyResult<Bound<'_, PyAny>> {
    let mode = options.datetime_conversion;
    if mode == DatetimeConversion::DATETIME_MS
        || (mode == DatetimeConversion::DATETIME_AUTO && !(MIN_MS..=MAX_MS).contains(&millis))
    {
        return Ok(Py::new(py, DatetimeMS { value: millis })?
            .into_bound(py)
            .into_any());
    }
    let millis = if mode == DatetimeConversion::DATETIME_CLAMP {
        millis.clamp(MIN_MS, MAX_MS)
    } else {
        millis
    };
    if !(MIN_MS..=MAX_MS).contains(&millis) {
        return Err(crate::errors::InvalidBSON::new_err(
            "datetime value out of range; use DatetimeConversion.DATETIME_AUTO or DATETIME_MS",
        ));
    }
    let types = types(py)?;
    let delta = types.timedelta.bind(py).call1((
        millis.div_euclid(86_400_000),
        millis.rem_euclid(86_400_000) / 1000,
        millis.rem_euclid(1000) * 1000,
    ))?;
    let epoch = if options.tz_aware {
        &types.aware_epoch
    } else {
        &types.epoch
    };
    epoch.bind(py).call_method1("__add__", (delta,))
}

#[pyclass(module = "bson.datetime_ms", frozen)]
#[derive(Clone, Copy)]
pub struct DatetimeMS {
    pub value: i64,
}

#[pymethods]
impl DatetimeMS {
    #[new]
    fn new(value: &Bound<'_, PyAny>) -> PyResult<Self> {
        let value = if value.is_instance_of::<PyInt>() {
            value.extract()?
        } else {
            to_millis(value)?
        };
        Ok(Self { value })
    }
    fn __int__(&self) -> i64 {
        self.value
    }
    fn __repr__(&self) -> String {
        format!("DatetimeMS({})", self.value)
    }
    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        self.value.into_pyobject(py)?.hash()
    }
    fn __richcmp__(&self, other: &Bound<'_, PyAny>, op: CompareOp) -> PyResult<Py<PyAny>> {
        let py = other.py();
        let number = if let Ok(other) = other.extract::<PyRef<'_, Self>>() {
            other.value.into_pyobject(py)?.into_any()
        } else if matches!(op, CompareOp::Eq | CompareOp::Ne) {
            return Ok(matches!(op, CompareOp::Ne)
                .into_pyobject(py)?
                .to_owned()
                .into_any()
                .unbind());
        } else if other.is_instance_of::<PyInt>() {
            other.clone()
        } else {
            return Ok(py.NotImplemented());
        };
        Ok(self
            .value
            .into_pyobject(py)?
            .rich_compare(number, op)?
            .unbind())
    }
    #[pyo3(signature = (codec_options=None))]
    fn as_datetime<'py>(
        &self,
        py: Python<'py>,
        codec_options: Option<&Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        from_millis(py, self.value, codec_options::resolve_all(codec_options)?)
    }
}

struct DatetimeTypes {
    datetime: Py<PyType>,
    utc: Py<PyAny>,
    timedelta: Py<PyAny>,
    epoch: Py<PyAny>,
    aware_epoch: Py<PyAny>,
}

static TYPES: GILOnceCell<DatetimeTypes> = GILOnceCell::new();
static STRUCT_ERROR: GILOnceCell<Py<PyAny>> = GILOnceCell::new();

fn types(py: Python<'_>) -> PyResult<&DatetimeTypes> {
    TYPES.get_or_try_init(py, || {
        let module = py.import("datetime")?;
        let datetime = module.getattr("datetime")?.downcast_into::<PyType>()?;
        let utc = module.getattr("timezone")?.getattr("utc")?;
        let epoch = datetime.call1((1970, 1, 1))?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("tzinfo", &utc)?;
        let aware_epoch = epoch.call_method("replace", (), Some(&kwargs))?;
        Ok(DatetimeTypes {
            datetime: datetime.unbind(),
            utc: utc.unbind(),
            timedelta: module.getattr("timedelta")?.unbind(),
            epoch: epoch.unbind(),
            aware_epoch: aware_epoch.unbind(),
        })
    })
}

// Gregorian civil date to Unix days, with no floating point or platform time_t.
fn unix_days(year: i64, month: i64, day: i64) -> i64 {
    let year = year - i64::from(month <= 2);
    let era = year.div_euclid(400);
    let yoe = year - era * 400;
    let month = month + if month > 2 { -3 } else { 9 };
    let doy = (153 * month + 2) / 5 + day - 1;
    era * 146_097 + yoe * 365 + yoe / 4 - yoe / 100 + doy - 719_468
}

pub fn objectid_seconds(value: &Bound<'_, PyAny>) -> PyResult<u32> {
    let py = value.py();
    if !value.is_instance(types(py)?.datetime.bind(py))? {
        return Err(PyTypeError::new_err(
            "generation_time must be a datetime.datetime",
        ));
    }
    let component = |name: &str| value.getattr(name)?.extract::<i64>();
    let days = unix_days(component("year")?, component("month")?, component("day")?);
    let seconds = days * 86_400
        + component("hour")? * 3600
        + component("minute")? * 60
        + component("second")?;
    let mut micros = seconds * 1_000_000 + component("microsecond")?;
    // Calling tzinfo is necessary for user-defined timezones; calendar arithmetic
    // and timedelta allocation are not. datetime.utcoffset validates the offset.
    let offset = value.call_method0("utcoffset")?;
    if !offset.is_none() {
        let days: i64 = offset.getattr("days")?.extract()?;
        let seconds: i64 = offset.getattr("seconds")?.extract()?;
        let microseconds: i64 = offset.getattr("microseconds")?.extract()?;
        micros -= (days * 86_400 + seconds) * 1_000_000 + microseconds;
    }
    if !(unix_days(1, 1, 1) * 86_400 * 1_000_000
        ..(unix_days(9999, 12, 31) + 1) * 86_400 * 1_000_000)
        .contains(&micros)
    {
        return Err(PyOverflowError::new_err("date value out of range"));
    }
    u32::try_from(micros.div_euclid(1_000_000)).map_err(|_| {
        // Only the exceptional path needs struct.error; never use struct.pack.
        let error = STRUCT_ERROR.get_or_try_init(py, || -> PyResult<_> {
            Ok(py.import("struct")?.getattr("error")?.unbind())
        });
        match error.and_then(|cls| {
            cls.bind(py)
                .call1(("'I' format requires 0 <= number <= 4294967295",))
        }) {
            Ok(instance) => PyErr::from_value(instance),
            Err(error) => error,
        }
    })
}

pub fn from_timestamp(py: Python<'_>, seconds: u32) -> PyResult<Bound<'_, PyAny>> {
    let types = types(py)?;
    types
        .datetime
        .bind(py)
        .call_method1("fromtimestamp", (seconds, types.utc.bind(py)))
}

#[cfg(test)]
mod tests {
    use super::unix_days;

    #[test]
    fn civil_dates() {
        assert_eq!(unix_days(1970, 1, 1), 0);
        assert_eq!(unix_days(1969, 12, 31), -1);
        assert_eq!(unix_days(2000, 1, 1), 10957);
        assert_eq!(unix_days(2000, 3, 1) - unix_days(2000, 2, 28), 2);
        assert_eq!(unix_days(1900, 3, 1) - unix_days(1900, 2, 28), 1);
    }
}
