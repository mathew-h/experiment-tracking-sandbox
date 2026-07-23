"""End-to-end replicate routing through the Solution Chemistry upload (issue #70 P3)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import Experiment, ExperimentalResults
from database.models.enums import ExperimentStatus

from .excel_helpers import make_excel


def _seed_experiment(db: Session, experiment_id: str, exp_num: int) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=exp_num,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.flush()  # before_flush listener wires base_experiment_id / replicate_label
    return exp


def _seed_replicate_set(db: Session, base: str, start_num: int, letters: str = "ab"):
    _seed_experiment(db, base, start_num)
    for i, letter in enumerate(letters, start=1):
        _seed_experiment(db, f"{base}{letter}", start_num + i)


def _upload(db: Session, headers, rows):
    from backend.services.bulk_uploads.scalar_results import ScalarResultsUploadService

    xlsx = make_excel(headers, rows)
    return ScalarResultsUploadService.bulk_upsert_from_excel_ex(db, xlsx)


def _gross_for(db: Session, experiment_id: str, time_days: float):
    result = (
        db.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(
            Experiment.experiment_id == experiment_id,
            ExperimentalResults.time_post_reaction_days == time_days,
        )
        .one()
    )
    assert result.scalar_data is not None
    return result.scalar_data.gross_ammonium_concentration_mM


_HEADERS = ["Experiment ID", "Replicate", "Time (days)", "Gross Ammonium (mM)"]


def test_base_plus_replicate_column_routes_to_siblings(db_session):
    _seed_replicate_set(db_session, "P3SCAL_701", 7801)
    created, updated, skipped, errors, feedbacks = _upload(db_session, _HEADERS, [
        ["P3SCAL_701", "a", 7, 5.0],
        ["P3SCAL_701", "b", 7, 6.0],
        ["P3SCAL_701", 0, 7, 4.0],  # 0 = group parent
    ])
    assert errors == []
    assert created == 3
    assert _gross_for(db_session, "P3SCAL_701a", 7.0) == 5.0
    assert _gross_for(db_session, "P3SCAL_701b", 7.0) == 6.0
    assert _gross_for(db_session, "P3SCAL_701", 7.0) == 4.0


def test_unresolved_sibling_errors_without_aborting(db_session):
    _seed_replicate_set(db_session, "P3SCAL_702", 7811, letters="a")
    created, updated, skipped, errors, feedbacks = _upload(db_session, _HEADERS, [
        ["P3SCAL_702", "a", 7, 5.0],
        ["P3SCAL_702", "c", 7, 6.0],  # no 'c' sibling exists
    ])
    assert created == 1
    assert any("P3SCAL_702c" in e and "not found" in e for e in errors)
    error_rows = [fb for fb in feedbacks if fb["status"] == "error"]
    assert len(error_rows) == 1
    assert _gross_for(db_session, "P3SCAL_702a", 7.0) == 5.0


def test_conflicting_letter_errors_without_aborting(db_session):
    _seed_replicate_set(db_session, "P3SCAL_703", 7821)
    created, updated, skipped, errors, feedbacks = _upload(db_session, _HEADERS, [
        ["P3SCAL_703a", "b", 7, 5.0],  # ID letter and column letter disagree
        ["P3SCAL_703b", "b", 7, 6.0],  # redundant but consistent -> OK
    ])
    assert created == 1
    assert any("conflicts" in e for e in errors)
    assert _gross_for(db_session, "P3SCAL_703b", 7.0) == 6.0


def test_full_replicate_ids_route_without_column(db_session):
    """Pins today's behavior: full lettered IDs route with no Replicate column."""
    _seed_replicate_set(db_session, "P3SCAL_704", 7831)
    headers = ["Experiment ID", "Time (days)", "Gross Ammonium (mM)"]
    created, updated, skipped, errors, _ = _upload(db_session, headers, [
        ["P3SCAL_704a", 7, 5.0],
        ["P3SCAL_704b", 7, 6.0],
    ])
    assert errors == []
    assert created == 2
    assert _gross_for(db_session, "P3SCAL_704a", 7.0) == 5.0
    assert _gross_for(db_session, "P3SCAL_704b", 7.0) == 6.0


def test_sheet_without_replicate_column_is_unchanged(db_session):
    """Regression: files that never had the column behave exactly as before."""
    _seed_experiment(db_session, "P3SCAL_705", 7841)
    headers = ["Experiment ID", "Time (days)", "Gross Ammonium (mM)"]
    created, updated, skipped, errors, _ = _upload(db_session, headers, [
        ["P3SCAL_705", 7, 5.0],
    ])
    assert errors == []
    assert created == 1
    assert _gross_for(db_session, "P3SCAL_705", 7.0) == 5.0
