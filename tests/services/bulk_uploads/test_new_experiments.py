"""Tests for NewExperimentsUploadService.bulk_upsert_from_excel overwrite behavior.

Regression coverage for issue #68: db.expire_all() (called after the experiments-sheet
loop) was discarding unflushed status/sample_id/researcher/date writes made in the
update-existing-experiment branch before they were ever persisted.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import Experiment, ExperimentalConditions, SampleInfo
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads.new_experiments import NewExperimentsUploadService

from .excel_helpers import make_excel, make_excel_multisheet

_EXP_HEADERS = [
    "experiment_id", "old_experiment_id", "sample_id", "researcher",
    "date", "status", "initial_note", "overwrite",
]


def _seed_experiment(
    db: Session,
    experiment_id: str,
    exp_num: int,
    status: ExperimentStatus = ExperimentStatus.ONGOING,
    sample_id: str | None = None,
    researcher: str | None = None,
) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=exp_num,
        status=status,
        sample_id=sample_id,
        researcher=researcher,
    )
    db.add(exp)
    db.flush()
    return exp


def _seed_sample(db: Session, sample_id: str) -> SampleInfo:
    sample = SampleInfo(sample_id=sample_id)
    db.add(sample)
    db.flush()
    return sample


def _experiments_excel(rows: list[list]) -> bytes:
    return make_excel(_EXP_HEADERS, rows, sheet_name="experiments")


def test_overwrite_persists_status_sample_researcher_date(db_session: Session):
    """overwrite=True on an existing experiment must persist status/sample_id/researcher/date."""
    _seed_experiment(db_session, "HPHT_I68_001", 68001, status=ExperimentStatus.ONGOING)
    _seed_sample(db_session, "SAMPLE-I68-001")

    xlsx = _experiments_excel([
        ["HPHT_I68_001", None, "SAMPLE-I68-001", "JD", "2026-02-01", "QUEUED", None, True],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert updated == 1
    assert created == 0

    exp = db_session.query(Experiment).filter_by(experiment_id="HPHT_I68_001").first()
    assert exp.status == ExperimentStatus.QUEUED, "status overwrite was silently discarded"
    assert exp.sample_id == "SAMPLE-I68-001", "sample_id overwrite was silently discarded"
    assert exp.researcher == "JD", "researcher overwrite was silently discarded"
    assert exp.date is not None and exp.date.date().isoformat() == "2026-02-01", (
        "date overwrite was silently discarded"
    )


def test_reactivation_via_overwrite_demotes_prior_reactor_occupant(db_session: Session):
    """Setting an existing experiment back to ONGOING in an occupied reactor (via overwrite)
    must trigger manage_reactor_occupancy and demote the current occupant."""
    occupant = _seed_experiment(db_session, "HPHT_I68_010", 68010, status=ExperimentStatus.ONGOING)
    occupant_conditions = ExperimentalConditions(
        experiment_id=occupant.experiment_id,
        experiment_fk=occupant.id,
        reactor_number=7,
        experiment_type="HPHT",
    )
    db_session.add(occupant_conditions)
    _seed_experiment(db_session, "HPHT_I68_011", 68011, status=ExperimentStatus.COMPLETED)
    db_session.flush()

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["HPHT_I68_011", None, None, None, None, "ONGOING", None, True]],
        ),
        "conditions": (
            ["experiment_id", "reactor_number"],
            [["HPHT_I68_011", 7]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"

    reactivated = db_session.query(Experiment).filter_by(experiment_id="HPHT_I68_011").first()
    demoted = db_session.query(Experiment).filter_by(experiment_id="HPHT_I68_010").first()
    assert reactivated.status == ExperimentStatus.ONGOING
    assert demoted.status == ExperimentStatus.COMPLETED, (
        "reactor occupancy check saw the stale (pre-overwrite) status and never fired"
    )
    assert any("Auto-completed" in m for m in info), (
        f"expected an auto-completion info message, got: {info}"
    )


def test_rename_with_status_change_persists_both(db_session: Session):
    """old_experiment_id rename combined with a status change in the same row must
    persist both the rename and the status change."""
    _seed_experiment(db_session, "HPHT_I68_020", 68020, status=ExperimentStatus.ONGOING)

    xlsx = _experiments_excel([
        ["HPHT_I68_020_Renamed", "HPHT_I68_020", None, None, None, "QUEUED", None, True],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert updated == 1

    renamed = db_session.query(Experiment).filter_by(experiment_id="HPHT_I68_020_Renamed").first()
    assert renamed is not None, "rename was not persisted"
    assert renamed.status == ExperimentStatus.QUEUED, "status change alongside rename was discarded"


def test_new_experiment_creation_path_unaffected(db_session: Session):
    """New-experiment creation (flushed immediately, before expire_all runs) must be unaffected."""
    xlsx = _experiments_excel([
        ["HPHT_I68_030", None, None, "AB", "2026-01-10", "ONGOING", "Created via test", False],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1
    assert updated == 0

    exp = db_session.query(Experiment).filter_by(experiment_id="HPHT_I68_030").first()
    assert exp is not None
    assert exp.status == ExperimentStatus.ONGOING
    assert exp.researcher == "AB"
