"""Unit tests for backend/services/samples.py"""
from backend.services.samples import normalize_pxrf_reading_no


def test_normalize_strips_whitespace():
    assert normalize_pxrf_reading_no("  42  ") == "42"


def test_normalize_integer_float():
    assert normalize_pxrf_reading_no("1.0") == "1"
    assert normalize_pxrf_reading_no("12.00") == "12"


def test_normalize_non_float_unchanged():
    assert normalize_pxrf_reading_no("ABC-01") == "ABC-01"


def test_normalize_plain_int():
    assert normalize_pxrf_reading_no("7") == "7"
