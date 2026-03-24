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


import pytest
from database.models.samples import SampleInfo
from database.models.analysis import ExternalAnalysis, PXRFReading
from database.models.xrd import XRDAnalysis
from database.models.characterization import ElementalAnalysis, Analyte
from backend.services.samples import evaluate_characterized


def _sample(db, sid="CHAR_S01"):
    s = SampleInfo(sample_id=sid)
    db.add(s)
    db.flush()
    return s


def test_evaluate_no_analyses_returns_false(db_session):
    _sample(db_session)
    assert evaluate_characterized(db_session, "CHAR_S01") is False


def test_evaluate_xrd_with_analysis_returns_true(db_session):
    s = _sample(db_session, "CHAR_S02")
    ea = ExternalAnalysis(sample_id=s.sample_id, analysis_type="XRD")
    db_session.add(ea)
    db_session.flush()
    xrd = XRDAnalysis(external_analysis_id=ea.id, mineral_phases={})
    db_session.add(xrd)
    db_session.flush()
    assert evaluate_characterized(db_session, "CHAR_S02") is True


def test_evaluate_xrd_without_xrd_analysis_returns_false(db_session):
    s = _sample(db_session, "CHAR_S03")
    db_session.add(ExternalAnalysis(sample_id=s.sample_id, analysis_type="XRD"))
    db_session.flush()
    assert evaluate_characterized(db_session, "CHAR_S03") is False


def test_evaluate_elemental_with_rows_returns_true(db_session):
    s = _sample(db_session, "CHAR_S04")
    ea = ExternalAnalysis(sample_id=s.sample_id, analysis_type="Elemental")
    db_session.add(ea)
    db_session.flush()
    analyte = Analyte(analyte_symbol="SiO2", unit="%")
    db_session.add(analyte)
    db_session.flush()
    db_session.add(ElementalAnalysis(
        external_analysis_id=ea.id, sample_id=s.sample_id,
        analyte_id=analyte.id, analyte_composition=45.0,
    ))
    db_session.flush()
    assert evaluate_characterized(db_session, "CHAR_S04") is True


def test_evaluate_pxrf_with_existing_reading_returns_true(db_session):
    s = _sample(db_session, "CHAR_S05")
    db_session.add(PXRFReading(reading_no="99"))
    ea = ExternalAnalysis(
        sample_id=s.sample_id, analysis_type="pXRF", pxrf_reading_no="99"
    )
    db_session.add(ea)
    db_session.flush()
    assert evaluate_characterized(db_session, "CHAR_S05") is True


def test_evaluate_pxrf_with_missing_reading_returns_false(db_session):
    s = _sample(db_session, "CHAR_S06")
    db_session.add(ExternalAnalysis(
        sample_id=s.sample_id, analysis_type="pXRF", pxrf_reading_no="9999"
    ))
    db_session.flush()
    assert evaluate_characterized(db_session, "CHAR_S06") is False
