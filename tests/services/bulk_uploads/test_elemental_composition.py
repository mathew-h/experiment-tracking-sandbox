"""Tests for ElementalCompositionService."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from database import Analyte, ElementalAnalysis, SampleInfo
from database.models.analysis import ExternalAnalysis
from backend.services.bulk_uploads.actlabs_titration_data import ElementalCompositionService

from .excel_helpers import make_excel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_sample(db: Session, sample_id: str) -> SampleInfo:
    sample = SampleInfo(sample_id=sample_id)
    db.add(sample)
    db.flush()
    return sample


def _seed_analyte(db: Session, symbol: str, unit: str = "wt%") -> Analyte:
    analyte = Analyte(analyte_symbol=symbol, unit=unit)
    db.add(analyte)
    db.flush()
    return analyte


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_creates_elemental_analysis_for_known_analyte(db_session: Session):
    """Valid file with a known analyte creates ElementalAnalysis rows."""
    _seed_sample(db_session, "S_ELEM001")
    _seed_analyte(db_session, "SiO2")

    xlsx = make_excel(
        ["sample_id", "SiO2"],
        [["S_ELEM001", 47.2]],
    )
    created, updated, skipped, errors = ElementalCompositionService.bulk_upsert_wide_from_excel(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    db_session.flush()
    analysis = (
        db_session.query(ElementalAnalysis)
        .join(Analyte, Analyte.id == ElementalAnalysis.analyte_id)
        .filter(Analyte.analyte_symbol == "SiO2")
        .first()
    )
    assert analysis is not None
    assert analysis.analyte_composition == pytest.approx(47.2)
    assert analysis.sample_id == "S_ELEM001"


def test_auto_creates_external_analysis_stub(db_session: Session):
    """Service auto-creates a 'Bulk Elemental Composition' ExternalAnalysis stub."""
    _seed_sample(db_session, "S_ELEM_STUB")
    _seed_analyte(db_session, "CaO")

    xlsx = make_excel(["sample_id", "CaO"], [["S_ELEM_STUB", 5.1]])
    ElementalCompositionService.bulk_upsert_wide_from_excel(db_session, xlsx)

    db_session.flush()
    stub = (
        db_session.query(ExternalAnalysis)
        .filter(
            ExternalAnalysis.sample_id == "S_ELEM_STUB",
            ExternalAnalysis.analysis_type == "Bulk Elemental Composition",
        )
        .first()
    )
    assert stub is not None


def test_unknown_analyte_without_default_unit_skipped(db_session: Session):
    """Unknown analyte header with no default_unit → silently skipped."""
    _seed_sample(db_session, "S_ELEM002")

    xlsx = make_excel(
        ["sample_id", "UnknownOxide"],
        [["S_ELEM002", 5.0]],
    )
    created, updated, skipped, errors = ElementalCompositionService.bulk_upsert_wide_from_excel(
        db_session, xlsx, default_unit=None
    )

    assert errors == []
    assert created == 0
    count = (
        db_session.query(ElementalAnalysis)
        .join(Analyte, Analyte.id == ElementalAnalysis.analyte_id)
        .filter(Analyte.analyte_symbol == "UnknownOxide")
        .count()
    )
    assert count == 0


def test_unknown_analyte_with_default_unit_auto_created(db_session: Session):
    """Unknown analyte header with default_unit → auto-created Analyte and data stored."""
    _seed_sample(db_session, "S_ELEM003")

    xlsx = make_excel(
        ["sample_id", "NewElement"],
        [["S_ELEM003", 12.5]],
    )
    created, updated, skipped, errors = ElementalCompositionService.bulk_upsert_wide_from_excel(
        db_session, xlsx, default_unit="ppm"
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    db_session.flush()
    analyte = (
        db_session.query(Analyte)
        .filter(Analyte.analyte_symbol == "NewElement")
        .first()
    )
    assert analyte is not None
    assert analyte.unit == "ppm"


def test_unknown_sample_id_recorded_as_error(db_session: Session):
    """Row with a sample_id not in the DB is recorded as an error."""
    _seed_analyte(db_session, "Al2O3")

    xlsx = make_excel(
        ["sample_id", "Al2O3"],
        [["S_NOTEXIST", 13.5]],
    )
    created, updated, skipped, errors = ElementalCompositionService.bulk_upsert_wide_from_excel(
        db_session, xlsx
    )

    assert created == 0
    assert any("S_NOTEXIST" in e for e in errors)


def test_updates_existing_elemental_analysis(db_session: Session):
    """Re-uploading the same sample+analyte updates, not creates."""
    _seed_sample(db_session, "S_ELEM004")
    _seed_analyte(db_session, "Fe2O3")

    xlsx1 = make_excel(["sample_id", "Fe2O3"], [["S_ELEM004", 10.0]])
    ElementalCompositionService.bulk_upsert_wide_from_excel(db_session, xlsx1)
    db_session.flush()

    xlsx2 = make_excel(["sample_id", "Fe2O3"], [["S_ELEM004", 15.0]])
    created, updated, skipped, errors = ElementalCompositionService.bulk_upsert_wide_from_excel(
        db_session, xlsx2
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert updated == 1
    assert created == 0


def test_no_sample_id_column_returns_error(db_session: Session):
    """File without a 'sample_id' column returns an error immediately."""
    xlsx = make_excel(
        ["SiO2", "Al2O3"],
        [[47.2, 13.5]],
    )
    created, updated, skipped, errors = ElementalCompositionService.bulk_upsert_wide_from_excel(
        db_session, xlsx
    )

    assert created == 0
    assert any("sample_id" in e.lower() for e in errors)


def test_blank_sample_id_rows_skipped(db_session: Session):
    """Rows with blank sample_id are skipped."""
    _seed_analyte(db_session, "MgO")

    xlsx = make_excel(
        ["sample_id", "MgO"],
        [["   ", 8.5]],  # spaces-only → .strip() → "" → skipped
    )
    created, updated, skipped, errors = ElementalCompositionService.bulk_upsert_wide_from_excel(
        db_session, xlsx
    )

    assert created == 0
    assert skipped == 1
