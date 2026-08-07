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


def _upload(db: Session, xlsx: bytes) -> tuple:
    """(created, updated, skipped, errors, feedbacks) for the positional tests.

    Deliberately local to the tests. The parser no longer offers a return shape
    that drops `warnings` — MasterUploadResult.as_tuple and the two entry points
    that called it were deleted by issue #114 item 4, because anything wired to
    them would compute warnings and throw them away. Tests that assert on
    warnings use from_bytes_ex directly.
    """
    r = MasterBulkUploadService.from_bytes_ex(db, xlsx)
    return r.created, r.updated, r.skipped, r.errors, r.feedbacks


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
    """Uploading a valid Dashboard sheet creates a scalar result."""
    _seed_experiment(db_session, "HPHT_MAST001", 7701)

    xlsx = _master_excel([
        ["HPHT_MAST001", 7.0, "Day 7", None, None, None, None,
         5.2, None, None, None, 7.1, 12.5, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = _upload(
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
    _upload(db_session, xlsx1)

    xlsx2 = _master_excel([["HPHT_MAST002", 7.0, "Day 7 updated", None, None, None, None,
                             6.5, None, None, None, 7.2, None, None, "TRUE"]])
    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, feedbacks = _upload(
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


def test_missing_duration_rows_skipped(db_session: Session):
    """Rows with no Duration (Days) value are counted as skipped, not errors."""
    _seed_experiment(db_session, "HPHT_MAST004", 7704)

    xlsx = _master_excel([
        # Experiment ID present but Duration (Days) is None → skipped
        ["HPHT_MAST004", None, "missing duration", None, None, None, None,
         5.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, feedbacks = _upload(
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
    created, updated, skipped, errors, feedbacks = _upload(
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
    created, updated, skipped, errors, feedbacks = _upload(
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
    created, updated, skipped, errors, feedbacks = _upload(
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
    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, feedbacks = _upload(
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
    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, _ = _upload(
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

    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, feedbacks = _upload(
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
    created, updated, skipped, errors, feedbacks = _upload(
        db_session, xlsx
    )

    assert created == 1
    assert any("single letter" in e for e in errors)
    assert feedbacks[0]["experiment_id"] == "P3MAST_702a"


# ---------------------------------------------------------------------------
# ID-encoded timepoints (issue #81)
# ---------------------------------------------------------------------------

def test_whitespace_duration_counts_as_blank_and_defers_to_the_id(db_session: Session):
    """A Duration of ' ' is blank, so the '-t' token supplies the day.

    The Dashboard's Duration column mirrors the Sampling sheet, whose formula is
    `=IF(ISBLANK([Date Started]), " ", D-C)` — an undated row therefore arrives
    as a single SPACE, not an empty cell. Treating it as a number produced
    `invalid Duration (Days) ' '` on all 36 rows of a real sheet whose
    timepoints had deliberately been left blank.
    """
    _seed_experiment(db_session, "SERUM_WS_001a-t3", 8901)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_WS_001a-t3", " ", description="undated row", nh4=1.0),
    ])
    created, updated, skipped, errors, _ = _upload(
        db_session, xlsx
    )

    assert errors == [], f"a space must not be an invalid Duration: {errors}"
    assert created == 1
    assert skipped == 0

    result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "SERUM_WS_001a-t3")
        .one()
    )
    assert result.time_post_reaction_days == 3.0


def test_whitespace_duration_without_a_token_is_skipped(db_session: Session):
    """Blank Duration and no '-t' token: nothing identifies the timepoint, so
    the row is skipped silently — same as a genuinely empty cell."""
    _seed_experiment(db_session, "SERUM_WS_002", 8902)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_WS_002", "  ", description="no day anywhere", nh4=1.0),
    ])
    created, updated, skipped, errors, _ = _upload(
        db_session, xlsx
    )

    assert errors == []
    assert created == 0
    assert skipped == 1


def test_non_numeric_duration_is_still_an_error(db_session: Session):
    """Only whitespace is blank. A real non-numeric value is still reported —
    the fix must not swallow genuinely bad data."""
    _seed_experiment(db_session, "SERUM_WS_003a-t3", 8903)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_WS_003a-t3", "three", description="typo", nh4=1.0),
    ])
    created, updated, skipped, errors, _ = _upload(
        db_session, xlsx
    )

    assert created == 0
    assert len(errors) == 1
    assert "invalid Duration (Days)" in errors[0]
    assert "three" in errors[0]


def test_master_blank_duration_filled_from_id(db_session: Session):
    """A -t7 ID with an empty Duration (Days) cell is no longer skipped —
    the result lands at day 7."""
    _seed_experiment(db_session, "SERUM_090a-t7", 8190)

    xlsx = _master_excel([
        ["SERUM_090a-t7", None, "vial day 7", None, None, None, None,
         2.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = _upload(
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


def test_master_conflicting_duration_warns_and_the_id_wins(db_session: Session):
    """A -t7 ID with Duration = 3.0 uploads at day 7, with a warning.

    Behaviour changed 2026-07-30 (Mat): the '-t<days>' token IS the vial's
    elapsed days, so it wins outright rather than the row being rejected. The
    Duration column on the real sheet is a formula derived from sampling dates,
    and letting it veto the ID rejected an entire sheet's readings over
    provenance the ID already settles. Note this deliberately diverges from
    POST /api/results, which still 400s on the same conflict.
    """
    _seed_experiment(db_session, "SERUM_091a-t7", 8191)

    xlsx = _master_excel([
        ["SERUM_091a-t7", 3.0, "wrong day", None, None, None, None,
         2.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"a conflict must no longer reject the row: {result.errors}"
    assert result.created == 1
    assert len(result.warnings) == 1
    assert "disagrees with the ID's -t token" in result.warnings[0]

    row = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "SERUM_091a-t7")
        .one()
    )
    assert row.time_post_reaction_days == 7.0, "the ID's day, not the column's 3.0"


def test_post_results_still_rejects_a_conflicting_timepoint():
    """The shared helper is unchanged — only the bulk path became permissive.

    POST /api/results has a single author who can correct the entry, so a
    conflict there is still a hard 400. Guards against a future refactor
    'simplifying' the two paths back together.
    """
    import pytest as _pytest

    from backend.services.result_merge_utils import apply_id_timepoint

    with _pytest.raises(ValueError, match="canonical"):
        apply_id_timepoint(7.0, 3.0)
    assert apply_id_timepoint(7.0, None) == 7.0
    assert apply_id_timepoint(None, 3.0) == 3.0


def test_master_matching_duration_accepted(db_session: Session):
    """Duration matching the -t token uploads normally."""
    _seed_experiment(db_session, "SERUM_092a-t7", 8192)

    xlsx = _master_excel([
        ["SERUM_092a-t7", 7.0, "right day", None, None, None, None,
         2.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, _ = _upload(
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
    gc_date: str | None = None,
) -> list:
    """Build one Dashboard row in _V3_HEADERS order."""
    return [
        experiment_id, description, None, duration, nh4,
        fl_h2, fl_vol, fl_psi,
        ph, None, None, None,
        None, None, gc_date, None,
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
    created, updated, skipped, errors, _ = _upload(
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
    _upload(db_session, first)

    # Repeat NH4 but leave Sample pH blank, with OVERWRITE set.
    second = _master_excel_v3([
        _v3_row("HPHT_FL002", 7.0, description="Day 7 revised",
                nh4=6.5, ph=None, overwrite=1.0),
    ])
    created, updated, skipped, errors, _ = _upload(
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

    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, _ = _upload(
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


def test_di_wins_ignores_stray_full_loop_gas_geometry(db_session: Session):
    """When DI supplies the concentration, FL gas volume/pressure are ignored.

    Load-bearing, not defensive (issue #114 addendum, 2026-07-30). Measured on
    the live v3 Dashboard: 35 rows resolve to DI, and every one of them also
    carries populated Full Loop geometry left over from a previous run — the GC
    sheets always carry some stale columns. Geometry therefore has to come from
    the block that won the concentration. Had precedence been built as
    "concentration from the winner, geometry from Full Loop", all 35 rows would
    compute h2_micromoles from 4235 mL instead of 30 mL — a 141x overstatement
    that produces a plausible-looking number, with nothing to flag it.

    The mirror of test_full_loop_wins_when_both_present.
    """
    _seed_experiment(db_session, "HPHT_MIX01", 8881)

    xlsx = _master_excel_v3([
        # FL geometry is real carryover magnitude; DI's is a real injection.
        _v3_row("HPHT_MIX01", 7.0,
                fl_h2=None, fl_vol=4235.0, fl_psi=90.0,
                di_h2=42.0, di_vol=30.0, di_psi=14.7),
    ])
    created, updated, skipped, errors, _ = _upload(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_MIX01")
        .one()
    ).scalar_data
    assert scalar.h2_concentration == pytest.approx(42.0)
    assert scalar.gas_sampling_volume_ml == pytest.approx(30.0), (
        "must be DI's 30 mL injection volume, never FL's 4235 mL carryover"
    )
    assert scalar.gas_sampling_pressure_MPa == pytest.approx(14.7 * _PSI_TO_MPA, rel=1e-3), (
        "must be DI's 14.7 psi, never FL's 90 psi"
    )


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
    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, _ = _upload(
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


def test_geometry_without_a_concentration_is_not_stored(db_session: Session):
    """Carryover gas columns with no reading attached are dropped.

    The GC sheets always carry stale values in some columns (Mat, 2026-07-30) and
    the field of record is 'H2 (ppm)'. Measured on the v3 Dashboard, 207 rows
    carry FL geometry with no FL concentration; storing it would put 4235 mL into
    ScalarResults where no later reader could tell it from a real measurement.
    Nothing is computed from it either way — _calculate_hydrogen requires a
    concentration.
    """
    _seed_experiment(db_session, "HPHT_GEO01", 8895)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_GEO01", 7.0, nh4=5.0,
                fl_h2=None, fl_vol=4235.0, fl_psi=90.0,
                di_h2=None, di_vol=30.0, di_psi=14.7),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"Unexpected errors: {result.errors}"
    assert result.created == 1, "the row must still upload — NH4 is real data"

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_GEO01")
        .one()
    ).scalar_data
    assert scalar.gross_ammonium_concentration_mM == pytest.approx(5.0)
    assert scalar.h2_concentration is None
    assert scalar.gas_sampling_volume_ml is None, "carryover volume must not be stored"
    assert scalar.gas_sampling_pressure_MPa is None, "carryover pressure must not be stored"


def test_overwrite_clears_stale_geometry_when_the_reading_goes_away(db_session: Session):
    """OVERWRITE on a concentration-less row clears geometry instead of rewriting carryover.

    gas_sampling_volume_ml and gas_sampling_pressure_MPa are both in
    SCALAR_UPDATABLE_FIELDS (backend/services/scalar_results_service.py:17), so
    with overwrite=True every field absent from the row is set to None. Dropping
    the carryover geometry therefore also stops a re-upload from re-asserting a
    volume the second sheet no longer claims a reading for.
    """
    _seed_experiment(db_session, "HPHT_GEO02", 8896)

    first = _master_excel_v3([
        _v3_row("HPHT_GEO02", 7.0, fl_h2=115.0, fl_vol=4235.0, fl_psi=90.0),
    ])
    MasterBulkUploadService.from_bytes_ex(db_session, first)

    second = _master_excel_v3([
        _v3_row("HPHT_GEO02", 7.0, fl_h2=None, fl_vol=4235.0, fl_psi=90.0, overwrite=1.0),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, second)

    assert result.errors == [], f"Unexpected errors: {result.errors}"
    assert result.updated == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_GEO02")
        .one()
    ).scalar_data
    assert scalar.h2_concentration is None
    assert scalar.gas_sampling_volume_ml is None
    assert scalar.gas_sampling_pressure_MPa is None


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
    # GC date supplied so the strict `warnings == []` below still means
    # "no H2S/H2O misdetection" and not "no #115 missing-GC-date warning".
    row = _v3_row("HPHT_WARN07", 7.0, fl_h2=115.0, gc_date="2026-01-01") + [12.0, 3.0]
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

    superseded = [w for w in result.warnings if "instead of direct injection" in w]
    assert len(superseded) == 1, (
        f"exactly one file-level warning, not one per row, got: {result.warnings}"
    )
    assert "1 row" in superseded[0], superseded[0]
    assert "(2)" in superseded[0], (
        f"the warning must name the sheet row so it can be found, got: {superseded[0]}"
    )


def test_no_supersede_warning_when_precedence_is_uncontested(db_session: Session):
    """The warning fires only when a DI value actually lost.

    A warning that appears on ordinary sheets is a warning researchers learn to
    ignore. FL-only, DI-only and neither-block rows are all the normal case —
    measured on the v3 Dashboard, 0 of 499 rows carry a reading in both blocks.
    """
    _seed_experiment(db_session, "HPHT_SUP01", 8891)
    _seed_experiment(db_session, "HPHT_SUP02", 8892)
    _seed_experiment(db_session, "HPHT_SUP03", 8893)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_SUP01", 7.0, fl_h2=115.0),              # FL only
        _v3_row("HPHT_SUP02", 7.0, di_h2=42.0, di_vol=30.0),  # DI only
        _v3_row("HPHT_SUP03", 7.0, nh4=5.0),                  # neither
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"Unexpected errors: {result.errors}"
    assert result.created == 3
    assert [w for w in result.warnings if "direct injection" in w] == []


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
    created, updated, skipped, errors, _ = _upload(
        db_session, xlsx
    )

    assert created == 0, "neither row may be written"
    assert updated == 0
    assert len(errors) == 1, f"one error for the group, got: {errors}"
    assert "SERUM_DUP01a" in errors[0]
    assert "Rows 2, 3" in errors[0], f"both rows must be named: {errors[0]}"

    assert (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "SERUM_DUP01a")
        .count()
    ) == 0


# ---------------------------------------------------------------------------
# Error ordering (issue #114 item 3)
# ---------------------------------------------------------------------------

def test_errors_are_listed_in_sheet_row_order(db_session: Session):
    """The error list reads top-down against the spreadsheet.

    _process_bytes resolves every row's identity (Phase 1) before upserting any
    row (Phase 2), so appending in execution order put EVERY Phase-1 error above
    EVERY Phase-2 one. Here row 2 fails in Phase 2 (no such experiment) and row 3
    fails in Phase 1 (unparseable Duration); before issue #114 the row 3 message
    came first, which is the opposite of how the sheet reads.

    Nothing is seeded on purpose. create_scalar_result_ex falls back to
    auto_create_treatment_experiment (backend/services/scalar_results_service.py
    :86-95), which needs an existing parent experiment — with an empty table
    there is none, so the not-found ValueError is guaranteed.
    """
    xlsx = _master_excel_v3([
        _v3_row("HPHT_ORD_MISSING", 7.0),   # sheet row 2 — Phase 2: experiment not found
        _v3_row("HPHT_ORD02", "not a day"),  # sheet row 3 — Phase 1: invalid Duration
    ])

    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert len(result.errors) == 2, f"expected one error per row, got: {result.errors}"
    assert result.errors[0].startswith("Row 2 ("), (
        f"the row 2 Phase-2 failure must come first, got: {result.errors}"
    )
    assert result.errors[1].startswith("Row 3:"), (
        f"the row 3 Phase-1 failure must come second, got: {result.errors}"
    )


def test_same_vial_different_timepoints_is_fine(db_session: Session):
    """The same vial at two different days is two legitimate rows."""
    _seed_experiment(db_session, "SERUM_DUP02a", 8832)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP02a", 1.0, description="day 1", fl_h2=10.0),
        _v3_row("SERUM_DUP02a", 3.0, description="day 3", fl_h2=20.0),
    ])
    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, _ = _upload(
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
    created, updated, skipped, errors, _ = _upload(
        db_session, xlsx
    )

    assert created == 0
    assert len(errors) == 1, f"one error for the group, got: {errors}"
    assert "Rows 2, 3" in errors[0]


def test_case_variant_ids_at_one_timepoint_are_a_duplicate(db_session: Session):
    """Two spellings that resolve to ONE experiment are a duplicate, not two rows.

    The pre-pass used to key on the raw ID string while the DB lookup keys on
    _id_match.normalize_id, so 'SERUM_cation_001c-t5' and 'SERUM_Cation_001c-t5'
    produced two different keys, both passed the guard, and both upserted onto
    the single stored experiment — the second reading silently overwriting the
    first with no error and no warning. Three such pairs are live in
    Master_Results_Tracker_v3.xlsx (sheet rows 29/194, 32/195, 35/196).
    """
    _seed_experiment(db_session, "SERUM_DUP06c-t5", 8866)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_dup06c-t5", 5.0, description="first", fl_h2=10.0),
        _v3_row("SERUM_DUP06C-t5", 5.0, description="second", fl_h2=20.0),
    ])
    created, updated, skipped, errors, _ = _upload(db_session, xlsx)

    assert created == 0, "neither row may be written"
    assert updated == 0
    assert errors, "the collision must be reported"

    assert (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "SERUM_DUP06c-t5")
        .count()
    ) == 0


def test_padding_variant_ids_at_one_timepoint_are_a_duplicate(db_session: Session):
    """Zero-padding differences collapse the same way case differences do.

    normalize_id strips leading zeros per digit run, so 'HPHT_007' and 'HPHT_7'
    are one experiment to the finder and must be one row to the guard.
    """
    _seed_experiment(db_session, "HPHT_DUP07", 8867)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_DUP07", 7.0, description="unpadded", fl_h2=10.0),
        _v3_row("HPHT_DUP0007", 7.0, description="padded", fl_h2=20.0),
    ])
    created, updated, skipped, errors, _ = _upload(db_session, xlsx)

    assert created == 0
    assert errors, "the collision must be reported"


def test_duplicate_group_is_one_error_naming_every_row(db_session: Session):
    """One collision produces one error listing all its rows, not one per row.

    A researcher reads this list against the sheet: 'row 2 is a duplicate' with
    no sibling row number means opening the file and searching for the partner
    by hand. The team's v3 workbook had 26 collisions reported as 52 lines.
    Same shape as the ambiguous-ID fix in commit de379a1.
    """
    _seed_experiment(db_session, "SERUM_DUP08a", 8868)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP08a", 7.0, description="first", fl_h2=10.0),
        _v3_row("SERUM_DUP08a", 7.0, description="second", fl_h2=20.0),
        _v3_row("SERUM_DUP08a", 7.0, description="third", fl_h2=30.0),
    ])
    created, updated, skipped, errors, _ = _upload(db_session, xlsx)

    assert created == 0
    assert len(errors) == 1, f"one error for the group, got: {errors}"
    assert "Rows 2, 3, 4" in errors[0], f"every row must be named: {errors[0]}"
    assert "SERUM_DUP08a" in errors[0]
    assert "day 7" in errors[0]


def test_duplicate_group_names_both_spellings(db_session: Session):
    """When the colliding rows are spelled differently, the message says so.

    'Rows 29, 194 (SERUM_pH_001a-t1)' would look like a plain repeat; the
    researcher needs to see that the two cells do not read the same, or they
    will search the sheet for a string that is only in one of them.
    """
    _seed_experiment(db_session, "SERUM_DUP09c-t5", 8869)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_dup09c-t5", 5.0, description="first", fl_h2=10.0),
        _v3_row("SERUM_DUP09C-t5", 5.0, description="second", fl_h2=20.0),
    ])
    created, updated, skipped, errors, _ = _upload(db_session, xlsx)

    assert len(errors) == 1, f"one error for the group, got: {errors}"
    assert "SERUM_dup09c-t5" in errors[0], f"first spelling missing: {errors[0]}"
    assert "SERUM_DUP09C-t5" in errors[0], f"second spelling missing: {errors[0]}"
    assert "resolve to one experiment" in errors[0], (
        f"the message must explain why differing spellings collided: {errors[0]}"
    )


def test_duplicate_group_error_sorts_at_its_first_row(db_session: Session):
    """The group error sits where its earliest row sits in the sheet order.

    Errors are sorted by row number so the list reads top-down against the
    spreadsheet (issue #114 item 3). A group spanning rows 2 and 4 must appear
    above a single-row failure on row 3, not after it.
    """
    _seed_experiment(db_session, "SERUM_DUP10a", 8870)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP10a", 7.0, description="dup one", fl_h2=10.0),
        _v3_row("HPHT_DUP10_MISSING", 7.0, description="no such experiment"),
        _v3_row("SERUM_DUP10a", 7.0, description="dup two", fl_h2=20.0),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert len(result.errors) == 2, f"one group + one row error: {result.errors}"
    assert result.errors[0].startswith("Rows 2, 4 ("), (
        f"the group anchored at row 2 must come first: {result.errors}"
    )
    assert result.errors[1].startswith("Row 3 ("), (
        f"the row 3 failure must come second: {result.errors}"
    )


def test_duplicate_does_not_block_other_rows(db_session: Session):
    """A duplicate pair is rejected; unrelated rows in the same file still land."""
    _seed_experiment(db_session, "SERUM_DUP05a", 8861)
    _seed_experiment(db_session, "SERUM_DUP05b", 8862)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP05a", 7.0, description="dup one", fl_h2=10.0),
        _v3_row("SERUM_DUP05a", 7.0, description="dup two", fl_h2=20.0),
        _v3_row("SERUM_DUP05b", 7.0, description="fine", fl_h2=30.0),
    ])
    created, updated, skipped, errors, feedbacks = _upload(
        db_session, xlsx
    )

    assert created == 1
    assert len(errors) == 1, f"one error for the group, got: {errors}"
    assert "Rows 2, 3" in errors[0]
    assert [f["experiment_id"] for f in feedbacks] == ["SERUM_DUP05b"]


def test_blank_nan_experiment_id_is_skipped_not_duplicated(db_session: Session):
    """An empty Experiment ID cell is a silent skip, not an experiment named "nan".

    float('nan') is truthy, so `str(cell or "")` yields "nan" — blank spacer rows
    then look like a real experiment, fail lookup, and (since #111 added collision
    detection) collide with each other on ("nan", day). The team's real workbook
    has 21 such rows.
    """
    _seed_experiment(db_session, "HPHT_NAN01", 8871)

    xlsx = _master_excel_v3([
        _v3_row(None, 7.0, description="blank spacer", nh4=1.0),
        _v3_row(None, 7.0, description="another blank", nh4=2.0),
        _v3_row("HPHT_NAN01", 7.0, description="real row", nh4=3.0),
    ])
    created, updated, skipped, errors, feedbacks = _upload(
        db_session, xlsx
    )

    assert errors == [], f"blank rows must not produce errors: {errors}"
    assert skipped == 2
    assert created == 1
    assert [f["experiment_id"] for f in feedbacks] == ["HPHT_NAN01"]


def test_zero_experiment_id_is_skipped_not_treated_as_an_experiment(db_session: Session):
    """A numeric 0 in the Experiment ID column is a blank, not experiment "0".

    Excel table formulas whose cache is stale read back as 0.0 — v3 does this on
    all 499 rows. The pre-#111 guard `str(cell or "")` skipped them because 0 is
    falsy; the NaN fix must not lose that.
    """
    _seed_experiment(db_session, "HPHT_ZERO01", 8891)

    xlsx = _master_excel_v3([
        _v3_row(0.0, 7.0, description="stale formula cache", nh4=1.0),
        _v3_row(0.0, 7.0, description="another stale row", nh4=2.0),
        _v3_row("HPHT_ZERO01", 7.0, description="real row", nh4=3.0),
    ])
    created, updated, skipped, errors, feedbacks = _upload(
        db_session, xlsx
    )

    assert errors == [], f"zero-ID rows must not error: {errors}"
    assert skipped == 2
    assert created == 1
    assert [f["experiment_id"] for f in feedbacks] == ["HPHT_ZERO01"]


# ---------------------------------------------------------------------------
# Missing GC Run Date warning (issue #115)
# ---------------------------------------------------------------------------

def test_warns_when_h2_reading_has_no_gc_run_date(db_session: Session):
    """An H2 reading with a blank 'GC Run Date' is named in one file warning.

    The reading is stored and no error is raised, so nothing else tells the
    researcher that the Dashboard's GC Measurements card (issue #85) will not
    count this row. 115 of 1056 dev-DB scalar rows carry a GC run date and all
    fall in Mar-May 2026 while H2 readings kept arriving -- that silence is the
    bug reported in issue #115.

    Also pins the denominator (rows carrying an H2 reading, not all rows) is
    right when some of those rows DO have a date: 2 rows carry H2 here, one
    missing its date, so the warning must read "1 of 2", not "1 of 1".
    """
    _seed_experiment(db_session, "HPHT_GCW01", 8901)
    _seed_experiment(db_session, "HPHT_GCW02", 8902)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_GCW01", 7.0, fl_h2=115.0),                          # H2, no date
        _v3_row("HPHT_GCW02", 7.0, fl_h2=120.0, gc_date="2026-07-29"),    # H2 + date
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"Unexpected errors: {result.errors}"
    assert result.created == 2

    missing = [w for w in result.warnings if "GC Run Date" in w]
    assert len(missing) == 1, (
        f"exactly one file-level warning, not one per row, got: {result.warnings}"
    )
    assert "1 of 2 rows" in missing[0], (
        f"the denominator must count only H2-bearing rows, got: {missing[0]}"
    )
    assert "The reading was stored" in missing[0], (
        f"singular clause must be used at n=1, got: {missing[0]}"
    )
    assert "(2)" in missing[0], (
        f"at or below the 10-row threshold the sheet row must be named, got: {missing[0]}"
    )
    assert "(3)" not in missing[0], (
        f"row 3 supplied a GC run date and must not be named, got: {missing[0]}"
    )


def test_no_gc_date_warning_when_row_has_no_h2_reading(db_session: Session):
    """A row with no H2 reading did no GC work, so a blank date is not notable.

    Same reasoning as the DI-supersede warning above: a warning that fires on
    ordinary sheets is one researchers learn to ignore.
    """
    _seed_experiment(db_session, "HPHT_GCW03", 8903)

    xlsx = _master_excel_v3([_v3_row("HPHT_GCW03", 7.0, nh4=5.0)])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"Unexpected errors: {result.errors}"
    assert result.created == 1
    assert [w for w in result.warnings if "GC Run Date" in w] == []


def test_warns_with_coverage_form_above_the_row_list_threshold(db_session: Session):
    """Above 10 missing rows, the warning reports a ratio, not a row list.

    ~128 H2-bearing scalar rows exist Mar-May 2026 alone, and a full Master
    Results re-upload processes every row, so this many-rows branch is the
    realistic first firing in production -- not a corner case. Enumerating
    every row number here would be exactly the noise the file otherwise
    avoids, so above the <=10 threshold (matching the #114 supersede warning)
    the warning reports n/total with no row list and no "and N more".
    """
    rows = []
    for i in range(11):
        exp_id = f"HPHT_GCM{i:02d}"
        _seed_experiment(db_session, exp_id, 8920 + i)
        rows.append(_v3_row(exp_id, 7.0, fl_h2=100.0 + i))

    xlsx = _master_excel_v3(rows)
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"Unexpected errors: {result.errors}"
    assert result.created == 11

    missing = [w for w in result.warnings if "GC Run Date" in w]
    assert len(missing) == 1, (
        f"exactly one file-level warning, not one per row, got: {result.warnings}"
    )
    assert "11 of 11 rows" in missing[0], missing[0]
    assert "H2 reading (" not in missing[0], (
        f"above the threshold no row-number list should follow the phrase, got: {missing[0]}"
    )
    assert "more" not in missing[0], (
        f"the overflow phrasing ('and N more') must not appear here, got: {missing[0]}"
    )


# ---------------------------------------------------------------------------
# Overwrite scope: the sheet may only clear the fields it has columns for
# (issue #116)
# ---------------------------------------------------------------------------

# The eight SCALAR_UPDATABLE_FIELDS entries the Dashboard sheet has no column
# for. Entered through the UI, never through this upload -- so an OVERWRITE row
# has nothing to say about them and must leave them alone.
_UI_ONLY_FIELDS = {
    "background_ammonium_concentration_mM": 0.85,
    "ammonium_quant_method": "NMR",
    "final_nitrate_concentration_mM": 1.4,
    "final_alkalinity_mg_L": 120.0,
    "co2_partial_pressure_MPa": 0.31,
    "final_dissolved_oxygen_mg_L": 6.2,
    "background_experiment_id": "SERUM_BLANK_01",
    "ferrous_iron_yield": 12.5,
}


def _scalar_for(db: Session, experiment_id: str):
    """The single scalar row of a one-result experiment."""
    return (
        db.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == experiment_id)
        .one()
    ).scalar_data


def _seed_row_with_ui_fields(db: Session, experiment_id: str, exp_num: int) -> None:
    """Create a scalar row via upload, then set the UI-only fields on it.

    Mirrors the real sequence: the row arrives from a Master Results upload, and
    a researcher later fills in the fields the spreadsheet does not carry.
    """
    _seed_experiment(db, experiment_id, exp_num)
    MasterBulkUploadService.from_bytes_ex(db, _master_excel_v3([
        _v3_row(experiment_id, 7.0, nh4=3.1, ph=7.0),
    ]))
    scalar = _scalar_for(db, experiment_id)
    for field, value in _UI_ONLY_FIELDS.items():
        setattr(scalar, field, value)
    db.flush()


def test_overwrite_preserves_background_ammonium_the_sheet_never_carries(
    db_session: Session,
):
    """An OVERWRITE row correcting NH4 must not clear the background it can't see.

    This is the one of the eight that changes a reported number rather than
    merely losing provenance. Net ammonium is max(0, gross - background) and
    background defaults to 0.2 mM when NULL (docs/CALCULATIONS.md), so wiping a
    recorded 0.85 silently moves net from 2.55 to 3.2 mM with no error.
    """
    _seed_row_with_ui_fields(db_session, "SERUM_OW116A", 9161)

    result = MasterBulkUploadService.from_bytes_ex(db_session, _master_excel_v3([
        _v3_row("SERUM_OW116A", 7.0, nh4=3.4, ph=7.0, overwrite=1.0),
    ]))

    assert result.errors == [], f"Unexpected errors: {result.errors}"
    assert result.updated == 1

    scalar = _scalar_for(db_session, "SERUM_OW116A")
    assert scalar.gross_ammonium_concentration_mM == pytest.approx(3.4), (
        "the correction the upload was actually for must still land"
    )
    assert scalar.background_ammonium_concentration_mM == pytest.approx(0.85), (
        "the sheet has no background column, so OVERWRITE has no authority to clear it"
    )


def test_overwrite_preserves_every_field_absent_from_the_sheet_schema(
    db_session: Session,
):
    """All eight UI-only fields survive an OVERWRITE row, not just the ammonium one."""
    _seed_row_with_ui_fields(db_session, "SERUM_OW116B", 9162)

    result = MasterBulkUploadService.from_bytes_ex(db_session, _master_excel_v3([
        _v3_row("SERUM_OW116B", 7.0, nh4=3.4, ph=7.0, overwrite=1.0),
    ]))

    assert result.errors == [], f"Unexpected errors: {result.errors}"

    scalar = _scalar_for(db_session, "SERUM_OW116B")
    wiped = [f for f, expected in _UI_ONLY_FIELDS.items() if getattr(scalar, f) != expected]
    assert wiped == [], f"OVERWRITE cleared fields the sheet has no column for: {wiped}"


def test_overwrite_still_clears_a_mapped_column_left_blank(db_session: Session):
    """The other half of the rule: a column the sheet DOES carry still clears.

    Without this, the #116 fix would be indistinguishable from "OVERWRITE never
    clears anything", which would re-assert the stale GC carryover geometry that
    issue #114 removed. Conductivity is used here rather than the gas columns so
    the assertion does not depend on _resolve_h2's precedence logic.
    """
    _seed_experiment(db_session, "SERUM_OW116C", 9163)
    MasterBulkUploadService.from_bytes_ex(db_session, _master_excel_v3([
        _v3_row("SERUM_OW116C", 7.0, nh4=3.1, ph=7.0),
    ]))
    scalar = _scalar_for(db_session, "SERUM_OW116C")
    scalar.final_conductivity_mS_cm = 12.5
    db_session.flush()

    result = MasterBulkUploadService.from_bytes_ex(db_session, _master_excel_v3([
        _v3_row("SERUM_OW116C", 7.0, nh4=3.4, ph=7.0, overwrite=1.0),
    ]))

    assert result.errors == [], f"Unexpected errors: {result.errors}"

    scalar = _scalar_for(db_session, "SERUM_OW116C")
    assert scalar.final_conductivity_mS_cm is None, (
        "'Sample Conductivity (mS/cm)' is a sheet column left blank -- OVERWRITE clears it"
    )


# ---------------------------------------------------------------------------
# Aggregated Duration-vs-ID disagreement warning
# ---------------------------------------------------------------------------

def test_duration_disagreements_are_one_aggregated_warning(db_session: Session):
    """Many disagreeing rows produce ONE warning, not one per row.

    The Dashboard's Duration column is a formula off the Sampling sheet and has
    drifted from the '-t<days>' tokens wholesale: 109 of 202 resolvable rows in
    the team's v3 workbook disagreed (2026-08-07). One line per row buries the
    other warnings, so this follows the coverage form the DI-supersede (#114)
    and GC-run-date (#115) warnings already use.
    """
    rows = []
    for i in range(3):
        exp_id = f"SERUM_DIS{i:02d}a-t7"
        _seed_experiment(db_session, exp_id, 8940 + i)
        rows.append(_v3_row(exp_id, 3.0, nh4=1.0))

    xlsx = _master_excel_v3(rows)
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"a disagreement must not reject a row: {result.errors}"
    assert result.created == 3

    disagreements = [w for w in result.warnings if "-t token" in w]
    assert len(disagreements) == 1, (
        f"exactly one file-level warning, not one per row: {result.warnings}"
    )
    assert "3 of 3" in disagreements[0], (
        f"the denominator must count comparable rows: {disagreements[0]}"
    )
    assert "(2, 3, 4)" in disagreements[0], (
        f"at or below the 10-row threshold the rows must be named: {disagreements[0]}"
    )


def test_duration_disagreement_denominator_counts_comparable_rows_only(
    db_session: Session,
):
    """The denominator is rows where a comparison was possible, not all rows.

    A row with no '-t' token, or with a blank Duration cell, has nothing to
    disagree with and must not inflate the denominator — the same reasoning
    that makes the GC-date warning count only H2-bearing rows.
    """
    _seed_experiment(db_session, "SERUM_DIS10a-t7", 8950)   # token + duration: comparable
    _seed_experiment(db_session, "SERUM_DIS11a-t7", 8951)   # token + duration: comparable
    _seed_experiment(db_session, "SERUM_DIS12", 8952)       # no token: not comparable
    _seed_experiment(db_session, "SERUM_DIS13a-t7", 8953)   # blank duration: not comparable

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DIS10a-t7", 3.0, nh4=1.0),    # disagrees
        _v3_row("SERUM_DIS11a-t7", 7.0, nh4=2.0),    # agrees
        _v3_row("SERUM_DIS12", 5.0, nh4=3.0),        # no token
        _v3_row("SERUM_DIS13a-t7", None, nh4=4.0),   # blank duration, ID supplies day 7
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"Unexpected errors: {result.errors}"
    assert result.created == 4

    disagreements = [w for w in result.warnings if "-t token" in w]
    assert len(disagreements) == 1, f"got: {result.warnings}"
    assert "1 of 2" in disagreements[0], (
        f"only the two token+duration rows are comparable: {disagreements[0]}"
    )
    assert "(2)" in disagreements[0], f"only row 2 disagreed: {disagreements[0]}"


def test_no_disagreement_warning_when_every_row_agrees(db_session: Session):
    """A sheet whose Durations match its tokens says nothing.

    A warning that fires on ordinary sheets is one researchers learn to ignore
    — the same rule the DI-supersede warning follows.
    """
    _seed_experiment(db_session, "SERUM_DIS20a-t7", 8960)

    xlsx = _master_excel_v3([_v3_row("SERUM_DIS20a-t7", 7.0, nh4=1.0)])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == []
    assert result.created == 1
    assert [w for w in result.warnings if "-t token" in w] == []


def test_disagreement_warning_drops_the_row_list_above_ten(db_session: Session):
    """Above 10 disagreeing rows the warning reports a ratio and no row list.

    Matches the <=10 threshold the supersede and GC-date warnings use. The real
    workbook disagrees on 109 rows; enumerating them is exactly the noise this
    change removes.
    """
    rows = []
    for i in range(11):
        exp_id = f"SERUM_DIS3{i:02d}a-t7"
        _seed_experiment(db_session, exp_id, 8970 + i)
        rows.append(_v3_row(exp_id, 3.0, nh4=1.0))

    xlsx = _master_excel_v3(rows)
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    disagreements = [w for w in result.warnings if "-t token" in w]
    assert len(disagreements) == 1, f"got: {result.warnings}"
    assert "11 of 11" in disagreements[0]
    assert "(" not in disagreements[0].split("rows")[1][:5], (
        f"no row list above the threshold: {disagreements[0]}"
    )


def test_rejected_rows_are_not_counted_in_the_disagreement_warning(db_session: Session):
    """Only rows actually written are counted and named.

    The warning says the reading "was recorded at the day its ID encodes",
    which is false for a row that was never written — and that row's own error
    says "No row for this vial-day was written". Counting in Phase 2 after the
    upsert (as the sibling GC-run-date warning does) keeps the two messages
    from contradicting each other about the same row. The team's real workbook
    has this overlap on its rows 185-211 re-entry block and on its
    missing-experiment rows.
    """
    _seed_experiment(db_session, "SERUM_DIS40a-t7", 8980)
    _seed_experiment(db_session, "SERUM_DIS41a-t7", 8981)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DIS40a-t7", 3.0, description="dup one", nh4=1.0),
        _v3_row("SERUM_DIS40a-t7", 3.0, description="dup two", nh4=2.0),
        _v3_row("SERUM_DIS41a-t7", 3.0, description="written", nh4=3.0),
        _v3_row("SERUM_DIS42a-t7", 3.0, description="no such experiment", nh4=4.0),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.created == 1
    assert len(result.errors) == 2, f"duplicate group + not found: {result.errors}"

    disagreements = [w for w in result.warnings if "-t token" in w]
    assert len(disagreements) == 1, f"got: {result.warnings}"
    assert "1 of 1" in disagreements[0], (
        f"only the written row counts: {disagreements[0]}"
    )
    assert "(4)" in disagreements[0], (
        f"row 4 is the one that was written: {disagreements[0]}"
    )
    assert "(2" not in disagreements[0], (
        f"rejected duplicate rows must not be named: {disagreements[0]}"
    )
    assert "5)" not in disagreements[0], (
        f"the failed-upsert row must not be named: {disagreements[0]}"
    )
