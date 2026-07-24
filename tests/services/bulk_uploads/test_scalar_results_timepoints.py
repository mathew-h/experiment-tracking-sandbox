"""Issue #81: '-t<days>' timepoint resolution in the Solution Chemistry upload."""
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


_HEADERS = ["Experiment ID", "Time (days)", "Gross Ammonium (mM)"]


def test_blank_time_filled_from_id(db_session):
    _seed_experiment(db_session, "SERUM_080a-t7", 8080)
    created, updated, skipped, errors, feedbacks = _upload(
        db_session,
        _HEADERS,
        [["SERUM_080a-t7", None, 2.0]],
    )
    assert errors == []
    assert created == 1
    assert _gross_for(db_session, "SERUM_080a-t7", 7.0) == 2.0


def test_conflicting_time_errors_row(db_session):
    _seed_experiment(db_session, "SERUM_081a-t7", 8081)
    created, updated, skipped, errors, feedbacks = _upload(
        db_session,
        _HEADERS,
        [["SERUM_081a-t7", 3.0, 2.0]],
    )
    assert created == 0
    assert len(errors) == 1
    assert "canonical" in errors[0]
    error_fb = [f for f in feedbacks if f["status"] == "error"]
    assert len(error_fb) == 1


def test_matching_time_accepted(db_session):
    _seed_experiment(db_session, "SERUM_082a-t7", 8082)
    created, updated, skipped, errors, feedbacks = _upload(
        db_session,
        _HEADERS,
        [["SERUM_082a-t7", 7.0, 2.0]],
    )
    assert errors == []
    assert created == 1


def test_error_row_does_not_abort_batch(db_session):
    _seed_experiment(db_session, "SERUM_083a-t7", 8083)
    _seed_experiment(db_session, "SERUM_084", 8084)
    created, updated, skipped, errors, feedbacks = _upload(
        db_session,
        _HEADERS,
        [["SERUM_083a-t7", 3.0, 2.0], ["SERUM_084", 5.0, 1.0]],
    )
    assert created == 1  # the good row lands
    assert len(errors) == 1


def test_untokened_sheet_unchanged(db_session):
    _seed_experiment(db_session, "SERUM_085", 8085)
    created, updated, skipped, errors, feedbacks = _upload(
        db_session,
        _HEADERS,
        [["SERUM_085", 5.0, 1.0]],
    )
    assert errors == []
    assert created == 1


# --- #81 I1: Replicate column + '-t<days>' ID token combo must be rejected ---

_HEADERS_WITH_REPLICATE = ["Experiment ID", "Replicate", "Time (days)", "Gross Ammonium (mM)"]


def test_token_id_with_replicate_letter_errors_row(db_session):
    """A token ID combined with a real Replicate letter is a per-row error;
    the rest of the batch still uploads."""
    _seed_experiment(db_session, "SERUM_086", 8086)
    created, updated, skipped, errors, feedbacks = _upload(
        db_session,
        _HEADERS_WITH_REPLICATE,
        [
            ["SERUM_086-t7", "a", None, 2.0],
            ["SERUM_086", None, 5.0, 1.0],
        ],
    )
    assert created == 1  # the good row still lands
    assert len(errors) == 1
    assert "-t<days>" in errors[0]


def test_token_id_with_blank_replicate_uploads_fine(db_session):
    """A blank Replicate cell alongside a token ID is a no-op — uploads with
    the token intact."""
    _seed_experiment(db_session, "SERUM_087a-t7", 8087)
    created, updated, skipped, errors, feedbacks = _upload(
        db_session,
        _HEADERS_WITH_REPLICATE,
        [["SERUM_087a-t7", None, None, 2.0]],
    )
    assert errors == []
    assert created == 1
    assert _gross_for(db_session, "SERUM_087a-t7", 7.0) == 2.0
