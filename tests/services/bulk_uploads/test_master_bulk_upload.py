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

# ---------------------------------------------------------------------------
# Standard-row skipping tests (Issue #39)
# ---------------------------------------------------------------------------

def test_standard_row_skipped_silently(db_session: Session):
    """Rows where Experiment ID contains 'Standard' are skipped, not errored."""
    xlsx = _master_excel([
        ["150uL NMR Standard", 7.0, "Day 7", None, None, None, None,
         5.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Standard rows must not produce errors: {errors}"
    assert skipped == 1
    assert created == 0
    assert feedbacks == []


def test_nmr_standard_row_skipped(db_session: Session):
    """'NMR Standard' (no volume prefix) is also skipped."""
    xlsx = _master_excel([
        ["NMR Standard", 7.0, "Day 7", None, None, None, None,
         None, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == []
    assert skipped == 1
    assert created == 0


def test_real_experiment_not_affected_by_standard_filter(db_session: Session):
    """A real experiment ID like 'CF-015-GC-01' is looked up normally, not skipped."""
    _seed_experiment(db_session, "CF-015-GC-01", 9001)

    xlsx = _master_excel([
        ["CF-015-GC-01", 7.0, "Day 7", None, None, None, None,
         5.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1
    assert skipped == 0
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

    result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_VOL003")
        .first()
    )
    assert result is not None
    assert result.scalar_data is not None
    assert result.scalar_data.sampling_volume_mL is None


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


# ---------------------------------------------------------------------------
# XRD Run Date tests (Issue #46)
# ---------------------------------------------------------------------------

def test_xrd_run_date_parsed_and_stored(db_session: Session):
    """Master upload stores xrd_run_date when 'XRD Run Date' column is present."""
    from database.models.experiments import Experiment
    from database.models.results import ExperimentalResults, ScalarResults
    from sqlalchemy import select

    _seed_experiment(db_session, "HPHT_XRD001", 7780)

    xrd_headers = [
        "Experiment ID", "Duration (Days)", "Description", "Sample Date",
        "NMR Run Date", "ICP Run Date", "GC Run Date", "XRD Run Date",
        "NH4 (mM)", "H2 (ppm)", "Gas Volume (mL)", "Gas Pressure (psi)",
        "Sample pH", "Sample Conductivity (mS/cm)",
        "Sampled Solution Volume (mL)", "Modification", "Overwrite",
    ]
    xlsx = make_excel_multisheet({"Dashboard": (xrd_headers, [
        ["HPHT_XRD001", 7.0, "Day 7 XRD", None, None, None, None, "2026-04-15",
         5.0, None, None, None, 7.1, None, None, None, "FALSE"],
    ])})

    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    exp = db_session.execute(
        select(Experiment).where(Experiment.experiment_id == "HPHT_XRD001")
    ).scalar_one()
    er = db_session.execute(
        select(ExperimentalResults).where(ExperimentalResults.experiment_fk == exp.id)
    ).scalar_one()
    scalar = db_session.execute(
        select(ScalarResults).where(ScalarResults.result_id == er.id)
    ).scalar_one()

    assert scalar.xrd_run_date is not None
    assert scalar.xrd_run_date.year == 2026
    assert scalar.xrd_run_date.month == 4
    assert scalar.xrd_run_date.day == 15


# ---------------------------------------------------------------------------
# Replicate routing (issue #70 P3)
# ---------------------------------------------------------------------------

def _master_excel_with_replicate(rows: list[list]) -> bytes:
    headers = [
        "Experiment ID", "Replicate", "Duration (Days)", "Description", "Sample Date",
        "NMR Run Date", "ICP Run Date", "GC Run Date",
        "NH4 (mM)", "H2 (ppm)", "Gas Volume (mL)", "Gas Pressure (psi)",
        "Sample pH", "Sample Conductivity (mS/cm)", "Modification", "Overwrite",
    ]
    return make_excel_multisheet({"Dashboard": (headers, rows)})


def test_replicate_column_routes_to_sibling(db_session: Session):
    """A base ID + Replicate letter lands the row on the lettered sibling."""
    _seed_experiment(db_session, "P3MAST_701", 7901)
    _seed_experiment(db_session, "P3MAST_701a", 7902)

    xlsx = _master_excel_with_replicate([
        ["P3MAST_701", "a", 7.0, "Day 7", None, None, None, None,
         5.2, None, None, None, 7.1, None, None, "FALSE"],
        ["P3MAST_701", None, 7.0, "Day 7 parent", None, None, None, None,
         4.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 2
    assert feedbacks[0]["experiment_id"] == "P3MAST_701a"

    sibling_result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "P3MAST_701a")
        .one()
    )
    assert sibling_result.scalar_data.gross_ammonium_concentration_mM == 5.2

    parent_result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "P3MAST_701")
        .one()
    )
    assert parent_result.scalar_data.gross_ammonium_concentration_mM == 4.0


def test_invalid_replicate_is_per_row_error(db_session: Session):
    """A malformed Replicate value skips that row only; the rest still upload."""
    _seed_experiment(db_session, "P3MAST_702", 7911)
    _seed_experiment(db_session, "P3MAST_702a", 7912)

    xlsx = _master_excel_with_replicate([
        ["P3MAST_702", "ab", 7.0, "bad", None, None, None, None,
         5.0, None, None, None, None, None, None, "FALSE"],
        ["P3MAST_702", "a", 7.0, "good", None, None, None, None,
         6.0, None, None, None, None, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert created == 1
    assert any("single letter" in e for e in errors)
    assert feedbacks[0]["experiment_id"] == "P3MAST_702a"


# ---------------------------------------------------------------------------
# ID-encoded timepoints (issue #81)
# ---------------------------------------------------------------------------

def test_master_blank_duration_filled_from_id(db_session: Session):
    """A -t7 ID with an empty Duration (Days) cell is no longer skipped —
    the result lands at day 7."""
    _seed_experiment(db_session, "SERUM_090a-t7", 8190)

    xlsx = _master_excel([
        ["SERUM_090a-t7", None, "vial day 7", None, None, None, None,
         2.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1
    assert skipped == 0

    result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "SERUM_090a-t7")
        .one()
    )
    assert result.time_post_reaction_days == 7.0


def test_master_conflicting_duration_errors_row(db_session: Session):
    """A -t7 ID with Duration = 3.0 is a per-row error; nothing is created."""
    _seed_experiment(db_session, "SERUM_091a-t7", 8191)

    xlsx = _master_excel([
        ["SERUM_091a-t7", 3.0, "wrong day", None, None, None, None,
         2.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert created == 0
    assert len(errors) == 1
    assert "canonical" in errors[0]


def test_master_matching_duration_accepted(db_session: Session):
    """Duration matching the -t token uploads normally."""
    _seed_experiment(db_session, "SERUM_092a-t7", 8192)

    xlsx = _master_excel([
        ["SERUM_092a-t7", 7.0, "right day", None, None, None, None,
         2.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1


def test_master_blank_duration_without_token_still_skipped(db_session: Session):
    """Regression: untokened IDs with blank Duration keep the pre-#81 skip."""
    _seed_experiment(db_session, "SERUM_093", 8193)

    xlsx = _master_excel([
        ["SERUM_093", None, "no duration", None, None, None, None,
         2.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == []
    assert created == 0
    assert skipped == 1


# --- #81 I1: Replicate column + '-t<days>' ID token combo must be rejected ---
# Reuses the `_master_excel_with_replicate` helper (Replicate as 2nd column)
# defined above under "Replicate routing (issue #70 P3)".

def test_master_token_id_with_replicate_letter_errors_row(db_session: Session):
    """A token ID combined with a real Replicate letter is a per-row error;
    the rest of the batch still uploads."""
    _seed_experiment(db_session, "SERUM_094", 8194)

    xlsx = _master_excel_with_replicate([
        ["SERUM_094-t7", "a", None, "bad combo", None, None, None, None,
         2.0, None, None, None, 7.0, None, None, "FALSE"],
        ["SERUM_094", None, 5.0, "good row", None, None, None, None,
         1.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert created == 1  # the good row still lands
    assert len(errors) == 1
    assert "-t<days>" in errors[0]


def test_master_token_id_with_blank_replicate_uploads_fine(db_session: Session):
    """A blank Replicate cell alongside a token ID is a no-op — uploads with
    the token intact."""
    _seed_experiment(db_session, "SERUM_095a-t7", 8195)

    xlsx = _master_excel_with_replicate([
        ["SERUM_095a-t7", None, None, "blank replicate", None, None, None, None,
         2.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "SERUM_095a-t7")
        .one()
    )
    assert result.time_post_reaction_days == 7.0


# ---------------------------------------------------------------------------
# v3 Dashboard headers (issue #111)
# ---------------------------------------------------------------------------

# The v3 Dashboard as of 2026-07-30. One row per unique experiment ID: the
# wide 'DI a/b/c' block collapsed to a single 'DI H2 (ppm)' because a/b/c were
# replicate vials, and each vial now gets its own row.
_V3_HEADERS = [
    "Experiment ID", "Description", "Sample Date", "Duration (Days)", "NH4 (mM)",
    "FL H2 (ppm)", "FL Gas Volume (mL)", "FL Gas Pressure (psi)",
    "Sample pH", "Sample Conductivity (mS/cm)", "Modification", "NMR Run Date",
    "Sampled Solution Volume (mL)", "ICP Run Date", "GC Run Date", "XRD Run Date",
    "OVERWRITE",
    "DI H2 (ppm)", "DI gas volume (mL)", "DI gas pressure (psi)",
]


def _v3_row(
    experiment_id: str,
    duration: float | None = 7.0,
    *,
    description: str = "Day 7",
    nh4: float | None = None,
    fl_h2: float | None = None,
    fl_vol: float | None = None,
    fl_psi: float | None = None,
    ph: float | None = 7.0,
    overwrite=None,
    di_h2: float | None = None,
    di_vol: float | None = None,
    di_psi: float | None = None,
) -> list:
    """Build one Dashboard row in _V3_HEADERS order."""
    return [
        experiment_id, description, None, duration, nh4,
        fl_h2, fl_vol, fl_psi,
        ph, None, None, None,
        None, None, None, None,
        overwrite,
        di_h2, di_vol, di_psi,
    ]


def _master_excel_v3(rows: list[list]) -> bytes:
    return make_excel_multisheet({"Dashboard": (_V3_HEADERS, rows)})


def test_v3_fl_h2_columns_are_ingested(db_session: Session):
    """'FL H2 (ppm)' / 'FL Gas Volume (mL)' / 'FL Gas Pressure (psi)' are read.

    Before #111 these were dropped silently: the parser looked for the pre-rename
    'H2 (ppm)' spelling, found nothing, and the None-filter removed the field.
    """
    _seed_experiment(db_session, "HPHT_FL001", 8801)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_FL001", 7.0, fl_h2=115.04, fl_vol=3935.0, fl_psi=90.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_FL001")
        .one()
    ).scalar_data
    assert scalar.h2_concentration == pytest.approx(115.04)
    assert scalar.h2_concentration_unit == "ppm"
    assert scalar.gas_sampling_volume_ml == pytest.approx(3935.0)
    assert scalar.gas_sampling_pressure_MPa == pytest.approx(90.0 * _PSI_TO_MPA, rel=1e-3)


def test_v3_uppercase_overwrite_header_is_honoured(db_session: Session):
    """The sheet spells it 'OVERWRITE'; the parser used to look for 'Overwrite'.

    The difference is only observable on a field the second upload leaves
    BLANK. `create_scalar_result_ex` (backend/services/scalar_results_service.py
    :129-135) writes every SCALAR_UPDATABLE_FIELDS entry when overwrite is True
    — clearing ones absent from the row — but only the fields actually present
    when it is False. A test that repeats the same populated field in both
    uploads passes either way and proves nothing.
    """
    _seed_experiment(db_session, "HPHT_FL002", 8802)

    first = _master_excel_v3([_v3_row("HPHT_FL002", 7.0, nh4=5.0, ph=7.0)])
    MasterBulkUploadService.from_bytes(db_session, first)

    # Repeat NH4 but leave Sample pH blank, with OVERWRITE set.
    second = _master_excel_v3([
        _v3_row("HPHT_FL002", 7.0, description="Day 7 revised",
                nh4=6.5, ph=None, overwrite=1.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, second
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert updated == 1
    assert created == 0

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_FL002")
        .one()
    ).scalar_data
    assert scalar.gross_ammonium_concentration_mM == pytest.approx(6.5)
    assert scalar.final_ph is None, (
        "OVERWRITE=TRUE must clear a field the new row leaves blank; a "
        "surviving 7.0 means the OVERWRITE header was not recognised"
    )


def test_legacy_h2_header_still_parses(db_session: Session):
    """Archived workbooks using the pre-rename 'H2 (ppm)' block keep working."""
    _seed_experiment(db_session, "HPHT_FL004", 8804)

    xlsx = _master_excel([
        ["HPHT_FL004", 7.0, "Day 7", None, None, None, None,
         5.0, 88.0, 500.0, 145.0, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_FL004")
        .one()
    ).scalar_data
    assert scalar.h2_concentration == pytest.approx(88.0)
    assert scalar.gas_sampling_volume_ml == pytest.approx(500.0)
