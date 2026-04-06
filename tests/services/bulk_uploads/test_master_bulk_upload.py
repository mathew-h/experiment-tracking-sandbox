"""Tests for MasterBulkUploadService."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from database import Experiment, ExperimentalResults
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads.master_bulk_upload import MasterBulkUploadService

from .excel_helpers import make_excel_multisheet, make_excel

_PSI_TO_MPA = 0.00689476


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_experiment(db: Session, experiment_id: str, exp_num: int) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=exp_num,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.flush()
    return exp


def _master_excel(rows: list[list]) -> bytes:
    headers = [
        "Experiment ID", "Duration (Days)", "Description", "Sample Date",
        "NMR Run Date", "ICP Run Date", "GC Run Date",
        "NH4 (mM)", "H2 (ppm)", "Gas Volume (mL)", "Gas Pressure (psi)",
        "Sample pH", "Sample Conductivity (mS/cm)", "Modification", "Overwrite",
    ]
    return make_excel_multisheet({"Dashboard": (headers, rows)})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_from_bytes_creates_result_row(db_session: Session):
    """from_bytes() with a valid Dashboard sheet creates a scalar result."""
    _seed_experiment(db_session, "HPHT_MAST001", 7701)

    xlsx = _master_excel([
        ["HPHT_MAST001", 7.0, "Day 7", None, None, None, None,
         5.2, None, None, None, 7.1, 12.5, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1
    assert updated == 0
    assert feedbacks[0]["action"] == "created"


def test_from_bytes_updates_existing_result_with_overwrite(db_session: Session):
    """Second upload with Overwrite=TRUE updates the existing row."""
    _seed_experiment(db_session, "HPHT_MAST002", 7702)

    xlsx1 = _master_excel([["HPHT_MAST002", 7.0, "Day 7", None, None, None, None,
                             5.0, None, None, None, 7.0, None, None, "FALSE"]])
    MasterBulkUploadService.from_bytes(db_session, xlsx1)

    xlsx2 = _master_excel([["HPHT_MAST002", 7.0, "Day 7 updated", None, None, None, None,
                             6.5, None, None, None, 7.2, None, None, "TRUE"]])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx2
    )

    assert errors == []
    assert updated == 1
    assert created == 0


def test_missing_required_columns_returns_error(db_session: Session):
    """File missing 'Experiment ID' or 'Duration (Days)' returns an error."""
    xlsx = make_excel(
        ["Sample ID", "Days"],
        [["HPHT_MAST001", 7.0]],
    )
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert created == 0
    assert any("required" in e.lower() or "missing" in e.lower() for e in errors)


def test_gas_pressure_psi_converted_to_mpa(db_session: Session):
    """Gas Pressure (psi) column is converted to MPa before storage."""
    _seed_experiment(db_session, "HPHT_MAST003", 7703)

    psi_val = 200.0
    xlsx = _master_excel([
        ["HPHT_MAST003", 7.0, "Day 7", None, None, None, None,
         5.0, 120.0, 5.0, psi_val, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == []
    assert created == 1

    result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_MAST003")
        .first()
    )
    assert result is not None
    assert result.scalar_data is not None
    expected_mpa = pytest.approx(psi_val * _PSI_TO_MPA, rel=1e-3)
    assert result.scalar_data.gas_sampling_pressure_MPa == expected_mpa


def test_sync_from_path_file_not_found_returns_error(db_session: Session):
    """sync_from_path() returns a clear error when the configured file doesn't exist."""
    import os

    os.environ["MASTER_RESULTS_PATH"] = "/nonexistent/path/master.xlsx"
    # Invalidate cached settings so our env var is picked up
    try:
        from backend.config.settings import get_settings
        get_settings.cache_clear()
    except AttributeError:
        pass

    created, updated, skipped, errors, _ = MasterBulkUploadService.sync_from_path(db_session)

    assert created == 0
    assert any("not found" in e.lower() or "nonexistent" in e.lower() for e in errors)


def test_missing_duration_rows_skipped(db_session: Session):
    """Rows with no Duration (Days) value are counted as skipped, not errors."""
    _seed_experiment(db_session, "HPHT_MAST004", 7704)

    xlsx = _master_excel([
        # Experiment ID present but Duration (Days) is None → skipped
        ["HPHT_MAST004", None, "missing duration", None, None, None, None,
         5.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert created == 0
    assert skipped == 1


# ---------------------------------------------------------------------------
# Fuzzy-matching tests (Issue #14)
# ---------------------------------------------------------------------------

def test_from_bytes_matches_experiment_with_leading_zeros(db_session: Session):
    """DB stores 'HPHT_1'; spreadsheet contains 'HPHT_001' — should match."""
    _seed_experiment(db_session, "HPHT_1", 7801)

    xlsx = _master_excel([
        ["HPHT_001", 5.0, "Day 5", None, None, None, None,
         3.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1
    assert feedbacks[0]["action"] == "created"


def test_from_bytes_matches_experiment_with_dot_separator(db_session: Session):
    """DB stores 'Serum_MH_101'; spreadsheet contains 'Serum.MH.101' — should match."""
    _seed_experiment(db_session, "Serum_MH_101", 7802)

    xlsx = _master_excel([
        ["Serum.MH.101", 10.0, "Day 10", None, None, None, None,
         None, None, None, None, 6.8, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1
    assert feedbacks[0]["action"] == "created"


def test_from_bytes_matches_experiment_with_leading_zeros_and_symbols(db_session: Session):
    """Combined: DB stores 'HPHT_14B'; spreadsheet uses 'HPHT-014B' — should match."""
    _seed_experiment(db_session, "HPHT_14B", 7803)

    xlsx = _master_excel([
        ["HPHT-014B", 3.0, "Day 3", None, None, None, None,
         None, None, None, None, 7.5, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1
    assert feedbacks[0]["action"] == "created"


# ---------------------------------------------------------------------------
# Sampled Solution Volume tests (Issue #31)
# ---------------------------------------------------------------------------

def test_sampled_solution_volume_parsed(db_session: Session):
    """Sampled Solution Volume (mL) cell with a value is saved to sampling_volume_mL."""
    _seed_experiment(db_session, "HPHT_VOL001", 8001)

    headers = [
        "Experiment ID", "Duration (Days)", "Description", "Sample Date",
        "NMR Run Date", "ICP Run Date", "GC Run Date",
        "NH4 (mM)", "H2 (ppm)", "Gas Volume (mL)", "Gas Pressure (psi)",
        "Sample pH", "Sample Conductivity (mS/cm)",
        "Sampled Solution Volume (mL)",
        "Modification", "Overwrite",
    ]
    xlsx = make_excel_multisheet({"Dashboard": (headers, [
        ["HPHT_VOL001", 7.0, "Day 7", None, None, None, None,
         None, None, None, None, 7.0, None, 15.5, None, "FALSE"],
    ])})
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_VOL001")
        .first()
    )
    assert result is not None
    assert result.scalar_data is not None
    assert result.scalar_data.sampling_volume_mL == pytest.approx(15.5)


def test_sampled_solution_volume_blank(db_session: Session):
    """Blank Sampled Solution Volume cell → sampling_volume_mL is None; row not skipped."""
    _seed_experiment(db_session, "HPHT_VOL002", 8002)

    headers = [
        "Experiment ID", "Duration (Days)", "Description", "Sample Date",
        "NMR Run Date", "ICP Run Date", "GC Run Date",
        "NH4 (mM)", "H2 (ppm)", "Gas Volume (mL)", "Gas Pressure (psi)",
        "Sample pH", "Sample Conductivity (mS/cm)",
        "Sampled Solution Volume (mL)",
        "Modification", "Overwrite",
    ]
    xlsx = make_excel_multisheet({"Dashboard": (headers, [
        ["HPHT_VOL002", 7.0, "Day 7", None, None, None, None,
         None, None, None, None, 7.0, None, None, None, "FALSE"],
    ])})
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1, "Row must not be skipped when volume cell is blank"

    result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_VOL002")
        .first()
    )
    assert result is not None
    assert result.scalar_data is not None
    assert result.scalar_data.sampling_volume_mL is None


def test_sampled_solution_volume_column_absent(db_session: Session):
    """Legacy file without Sampled Solution Volume column processes without KeyError."""
    _seed_experiment(db_session, "HPHT_VOL003", 8003)

    # _master_excel() does NOT include the new column — simulates an older Dashboard file
    xlsx = _master_excel([
        ["HPHT_VOL003", 7.0, "Day 7", None, None, None, None,
         None, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1


def test_sampled_solution_volume_case_insensitive(db_session: Session):
    """Lowercase header 'sampled solution volume (ml)' is normalised and parsed correctly."""
    _seed_experiment(db_session, "HPHT_VOL004", 8004)

    headers = [
        "Experiment ID", "Duration (Days)", "Description", "Sample Date",
        "NMR Run Date", "ICP Run Date", "GC Run Date",
        "NH4 (mM)", "H2 (ppm)", "Gas Volume (mL)", "Gas Pressure (psi)",
        "Sample pH", "Sample Conductivity (mS/cm)",
        "sampled solution volume (ml)",  # intentionally lowercase
        "Modification", "Overwrite",
    ]
    xlsx = make_excel_multisheet({"Dashboard": (headers, [
        ["HPHT_VOL004", 7.0, "Day 7", None, None, None, None,
         None, None, None, None, 7.0, None, 20.0, None, "FALSE"],
    ])})
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_VOL004")
        .first()
    )
    assert result is not None
    assert result.scalar_data is not None
    assert result.scalar_data.sampling_volume_mL == pytest.approx(20.0)
