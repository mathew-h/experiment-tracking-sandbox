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


def test_both_spellings_of_one_field_do_not_collide(db_session: Session):
    """A sheet carrying both 'H2 (ppm)' and 'FL H2 (ppm)' must not produce two
    columns with the same name.

    Duplicate column names make pandas hand `row.get()` a Series instead of a
    scalar; `_parse_float` raises on it and its `except Exception` returns None,
    silently dropping the value — the exact failure issue #111 exists to fix.
    The literal v3 column wins; the aliased one keeps its raw header.
    """
    from backend.services.bulk_uploads.master_bulk_upload import _normalize_headers

    for columns, expected in (
        (["H2 (ppm)", "FL H2 (ppm)"], ["H2 (ppm)", "FL H2 (ppm)"]),
        (["FL H2 (ppm)", "H2 (ppm)"], ["FL H2 (ppm)", "H2 (ppm)"]),
        (["DI avg H2 (ppm)", "DI H2 (ppm)"], ["DI avg H2 (ppm)", "DI H2 (ppm)"]),
        # Two aliases of one canonical, neither spelled canonically.
        (["gas volume (ml)", "Gas Volume (mL)"],
         ["FL Gas Volume (mL)", "Gas Volume (mL)"]),
    ):
        result = _normalize_headers(columns)
        assert result == expected, f"{columns} -> {result}"
        assert len(set(result)) == len(result), f"duplicate columns from {columns}"

    # Ordinary single-spelling mapping is unaffected.
    assert _normalize_headers(["H2 (ppm)"]) == ["FL H2 (ppm)"]
    assert _normalize_headers(["OVERWRITE"]) == ["Overwrite"]


def test_both_spellings_end_to_end_keeps_the_v3_value(db_session: Session):
    """The collision case survives a real upload: the v3 column's value lands."""
    _seed_experiment(db_session, "HPHT_FL005", 8805)

    headers = ["H2 (ppm)"] + list(_V3_HEADERS)
    row = [999.0] + _v3_row("HPHT_FL005", 7.0, fl_h2=115.0, fl_vol=3935.0, fl_psi=90.0)
    xlsx = make_excel_multisheet({"Dashboard": (headers, [row])})

    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_FL005")
        .one()
    ).scalar_data
    assert scalar.h2_concentration == pytest.approx(115.0), (
        "the literal 'FL H2 (ppm)' column must win, and its value must not be "
        "lost to a duplicate-column Series"
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


def test_full_loop_wins_when_both_present(db_session: Session):
    """Full Loop takes precedence over DI (Mat, 2026-07-30).

    Gas volume and pressure come from the SAME block as the winning
    concentration — _calculate_hydrogen() combines all three, so mixing blocks
    would compute micromoles from a volume that injection never used.
    """
    _seed_experiment(db_session, "HPHT_PREC01", 8811)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_PREC01", 7.0,
                fl_h2=115.0, fl_vol=3935.0, fl_psi=90.0,
                di_h2=42.0, di_vol=10.0, di_psi=15.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_PREC01")
        .one()
    ).scalar_data
    assert scalar.h2_concentration == pytest.approx(115.0)
    assert scalar.gas_sampling_volume_ml == pytest.approx(3935.0)
    assert scalar.gas_sampling_pressure_MPa == pytest.approx(90.0 * _PSI_TO_MPA, rel=1e-3)


def test_di_used_when_full_loop_absent(db_session: Session):
    """A blank Full Loop cell falls back to 'DI H2 (ppm)' and DI's own gas
    volume and pressure."""
    _seed_experiment(db_session, "HPHT_PREC02", 8812)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_PREC02", 7.0, fl_h2=None, di_h2=42.0, di_vol=10.0, di_psi=15.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_PREC02")
        .one()
    ).scalar_data
    assert scalar.h2_concentration == pytest.approx(42.0)
    assert scalar.h2_concentration_unit == "ppm"
    assert scalar.gas_sampling_volume_ml == pytest.approx(10.0)
    assert scalar.gas_sampling_pressure_MPa == pytest.approx(15.0 * _PSI_TO_MPA, rel=1e-3)


def test_zero_h2_is_a_real_measurement(db_session: Session):
    """A Full Loop reading of exactly 0 ppm is stored, not treated as blank.

    Mat is rewriting the Excel formulas so an absent peak area leaves the cell
    empty; a 0 that survives that rewrite means a genuine zero. Do NOT route H2
    through _parse_measurement_float (the pH/conductivity zero-suppressor).
    """
    _seed_experiment(db_session, "HPHT_PREC03", 8813)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_PREC03", 7.0, fl_h2=0.0, fl_vol=3785.0, fl_psi=30.0, di_h2=99.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_PREC03")
        .one()
    ).scalar_data
    assert scalar.h2_concentration == 0.0, "0 ppm must not fall through to DI"
    assert scalar.h2_micromoles == pytest.approx(0.0)


def test_v2_di_avg_header_maps_onto_di_h2(db_session: Session):
    """A v2 workbook's 'DI avg H2 (ppm)' still lands on h2_concentration.

    v2 is not the reference format any more, but an archived workbook must not
    lose its DI reading just because the column was renamed in v3. The alias
    itself is Task 1's, but nothing reads a DI column until _resolve_h2 exists,
    so the test belongs here.
    """
    _seed_experiment(db_session, "HPHT_PREC05", 8815)

    headers = list(_V3_HEADERS)
    headers[headers.index("DI H2 (ppm)")] = "DI avg H2 (ppm)"
    xlsx = make_excel_multisheet({"Dashboard": (headers, [
        _v3_row("HPHT_PREC05", 7.0, di_h2=42.0, di_vol=10.0, di_psi=15.0),
    ])})
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_PREC05")
        .one()
    ).scalar_data
    assert scalar.h2_concentration == pytest.approx(42.0)


def test_no_gc_reading_leaves_h2_unset(db_session: Session):
    """Both GC blocks blank → h2_concentration stays None and the row still lands."""
    _seed_experiment(db_session, "HPHT_PREC04", 8814)

    xlsx = _master_excel_v3([_v3_row("HPHT_PREC04", 7.0, nh4=5.0)])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_PREC04")
        .one()
    ).scalar_data
    assert scalar.h2_concentration is None
    assert scalar.h2_concentration_unit is None


# ---------------------------------------------------------------------------
# Warnings and per-row H2 source feedback (issue #111 — Task 3)
# ---------------------------------------------------------------------------

def test_unrecognized_h2_column_warns(db_session: Session):
    """A column mentioning H2 that the parser cannot map is reported.

    This is the guard for the class of bug #111 itself was: a renamed column
    that upserts every other field successfully while the H2 value vanishes.
    """
    _seed_experiment(db_session, "HPHT_WARN01", 8821)

    headers = list(_V3_HEADERS)
    headers[headers.index("FL H2 (ppm)")] = "GC Loop H2 ppm"  # a future rename
    xlsx = make_excel_multisheet({"Dashboard": (headers, [
        _v3_row("HPHT_WARN01", 7.0, fl_h2=115.0),
    ])})

    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"Unexpected errors: {result.errors}"
    assert result.created == 1, "The row must still upload — this is a warning, not a failure"
    assert any("GC Loop H2 ppm" in w for w in result.warnings)


def test_no_h2_column_at_all_warns(db_session: Session):
    """A Dashboard with neither GC block warns once, at file level."""
    _seed_experiment(db_session, "HPHT_WARN02", 8822)

    keep = [h for h in _V3_HEADERS if "H2" not in h]
    row = [v for h, v in zip(_V3_HEADERS, _v3_row("HPHT_WARN02", 7.0, nh4=5.0))
           if "H2" not in h]
    xlsx = make_excel_multisheet({"Dashboard": (keep, [row])})

    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == []
    assert result.created == 1
    assert any("no recognized H2 column" in w for w in result.warnings)


def test_wide_di_columns_warn_about_one_row_per_vial(db_session: Session):
    """A v2 sheet still carrying 'DI a/b/c H2 (ppm)' is told to split the rows.

    v3 collapsed those to one 'DI H2 (ppm)' because a/b/c are replicate vials
    that each get their own experiment ID now. The columns are ignored, not
    guessed at.
    """
    _seed_experiment(db_session, "HPHT_WARN03", 8823)

    headers = list(_V3_HEADERS) + ["DI a H2 (ppm)", "DI b H2 (ppm)", "DI c H2 (ppm)"]
    row = _v3_row("HPHT_WARN03", 7.0, nh4=5.0) + [10.0, 11.0, 12.0]
    xlsx = make_excel_multisheet({"Dashboard": (headers, [row])})

    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == []
    assert result.created == 1
    assert any("one row per experiment ID" in w for w in result.warnings)

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_WARN03")
        .one()
    ).scalar_data
    assert scalar.h2_concentration is None, "wide DI values must not be guessed at"


def test_h2s_column_is_not_reported_as_a_dropped_h2_reading(db_session: Session):
    """'H2S (ppm)' must not be flagged as an unrecognized hydrogen column.

    The warning exists so a researcher trusts it when it fires. A substring
    match on 'h2' would also hit H2S and H2O and cry wolf about a hydrogen
    value that was never there.
    """
    _seed_experiment(db_session, "HPHT_WARN07", 8827)

    headers = list(_V3_HEADERS) + ["H2S (ppm)", "H2O (%)"]
    row = _v3_row("HPHT_WARN07", 7.0, fl_h2=115.0) + [12.0, 3.0]
    xlsx = make_excel_multisheet({"Dashboard": (headers, [row])})

    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == []
    assert result.created == 1
    assert result.warnings == [], f"H2S/H2O must not warn, got: {result.warnings}"

    # A genuine rename still warns — the guard narrows, it does not disable.
    renamed = list(_V3_HEADERS)
    renamed[renamed.index("FL H2 (ppm)")] = "GC Loop H2 ppm"
    xlsx2 = make_excel_multisheet({"Dashboard": (renamed, [
        _v3_row("HPHT_WARN07", 8.0, fl_h2=115.0),
    ])})
    result2 = MasterBulkUploadService.from_bytes_ex(db_session, xlsx2)
    assert any("GC Loop H2 ppm" in w for w in result2.warnings)


def test_superseded_di_flag_comes_from_the_resolver(db_session: Session):
    """h2_di_superseded is derived from _resolve_h2's own DI parse.

    Guards against the flag and the precedence decision drifting apart if the
    DI branch later gains unit conversion or a sanity bound.
    """
    from backend.services.bulk_uploads.master_bulk_upload import _resolve_h2

    both = {"FL H2 (ppm)": 115.0, "DI H2 (ppm)": 42.0}
    fl_only = {"FL H2 (ppm)": 115.0, "DI H2 (ppm)": None}
    di_only = {"FL H2 (ppm)": None, "DI H2 (ppm)": 42.0}
    neither = {"FL H2 (ppm)": None, "DI H2 (ppm)": None}

    assert _resolve_h2(both)[3:] == ("full_loop", 42.0)
    assert _resolve_h2(fl_only)[3:] == ("full_loop", None)
    assert _resolve_h2(di_only)[3:] == ("di", 42.0)
    assert _resolve_h2(neither)[3:] == (None, None)


def test_feedback_records_which_gc_block_was_used(db_session: Session):
    """Each row reports its H2 source so a discarded DI reading is visible."""
    _seed_experiment(db_session, "HPHT_WARN04", 8824)
    _seed_experiment(db_session, "HPHT_WARN05", 8825)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_WARN04", 7.0, fl_h2=115.0, di_h2=42.0),   # DI superseded
        _v3_row("HPHT_WARN05", 7.0, fl_h2=None, di_h2=42.0),    # DI used
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == []
    assert result.created == 2

    by_id = {f["experiment_id"]: f for f in result.feedbacks}
    assert by_id["HPHT_WARN04"]["h2_source"] == "full_loop"
    assert by_id["HPHT_WARN04"]["h2_di_superseded"] is True
    assert by_id["HPHT_WARN05"]["h2_source"] == "di"
    assert by_id["HPHT_WARN05"]["h2_di_superseded"] is False


def test_from_bytes_tuple_shape_unchanged(db_session: Session):
    """from_bytes() still returns the legacy 5-tuple — no caller breaks."""
    _seed_experiment(db_session, "HPHT_WARN06", 8826)

    xlsx = _master_excel_v3([_v3_row("HPHT_WARN06", 7.0, nh4=5.0)])
    out = MasterBulkUploadService.from_bytes(db_session, xlsx)

    assert len(out) == 5
    created, updated, skipped, errors, feedbacks = out
    assert created == 1
    assert isinstance(errors, list) and isinstance(feedbacks, list)


# ---------------------------------------------------------------------------
# Duplicate vial-timepoint rejection (issue #111)
# ---------------------------------------------------------------------------

def test_duplicate_vial_and_timepoint_is_an_error(db_session: Session):
    """Two rows for the same vial at the same day are both rejected.

    v3 is one row per unique experiment ID. A repeated (ID, duration) pair is
    the old wide-format habit leaking through, and silently letting the second
    row win would destroy the first reading.
    """
    _seed_experiment(db_session, "SERUM_DUP01a", 8831)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP01a", 7.0, description="first", fl_h2=10.0),
        _v3_row("SERUM_DUP01a", 7.0, description="second", fl_h2=20.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert created == 0, "neither row may be written"
    assert updated == 0
    assert len(errors) == 2, f"both rows must be reported, got: {errors}"
    assert all("SERUM_DUP01a" in e for e in errors)
    assert any("row 2" in e.lower() for e in errors)
    assert any("row 3" in e.lower() for e in errors)

    assert (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "SERUM_DUP01a")
        .count()
    ) == 0


def test_same_vial_different_timepoints_is_fine(db_session: Session):
    """The same vial at two different days is two legitimate rows."""
    _seed_experiment(db_session, "SERUM_DUP02a", 8832)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP02a", 1.0, description="day 1", fl_h2=10.0),
        _v3_row("SERUM_DUP02a", 3.0, description="day 3", fl_h2=20.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 2


def test_replicate_letters_are_distinct_vials(db_session: Session):
    """SERUM_001a/b/c at one timepoint are three rows, not a duplicate.

    This is the shape the pivot exists to support: three replicate vials, each
    with its own experiment ID, all at day 1.
    """
    for letter, num in (("a", 8841), ("b", 8842), ("c", 8843)):
        _seed_experiment(db_session, f"SERUM_DUP03{letter}", num)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP03a", 1.0, fl_h2=10.0),
        _v3_row("SERUM_DUP03b", 1.0, fl_h2=20.0),
        _v3_row("SERUM_DUP03c", 1.0, fl_h2=30.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 3


def test_duplicate_detected_after_timepoint_token_resolution(db_session: Session):
    """'SERUM_X-t7' with a blank Duration collides with 'SERUM_X' at day 7.

    Duplicate detection runs on the RESOLVED (id, time) pair, not on the raw
    cells — the -t token fills a blank Duration, so these are the same vial-day.
    """
    _seed_experiment(db_session, "SERUM_DUP04-t7", 8851)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP04-t7", None, description="from token", fl_h2=10.0),
        _v3_row("SERUM_DUP04-t7", 7.0, description="explicit", fl_h2=20.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert created == 0
    assert len(errors) == 2


def test_duplicate_does_not_block_other_rows(db_session: Session):
    """A duplicate pair is rejected; unrelated rows in the same file still land."""
    _seed_experiment(db_session, "SERUM_DUP05a", 8861)
    _seed_experiment(db_session, "SERUM_DUP05b", 8862)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP05a", 7.0, description="dup one", fl_h2=10.0),
        _v3_row("SERUM_DUP05a", 7.0, description="dup two", fl_h2=20.0),
        _v3_row("SERUM_DUP05b", 7.0, description="fine", fl_h2=30.0),
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert created == 1
    assert len(errors) == 2
    assert [f["experiment_id"] for f in feedbacks] == ["SERUM_DUP05b"]
