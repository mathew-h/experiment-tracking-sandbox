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


def test_duplicate_replicate_id_skips_with_clear_warning_not_crash(db_session: Session):
    """Creating a replicate ID that already exists (overwrite=False) must produce a
    clear warning and skip the row — never raise or silently overwrite."""
    _seed_experiment(db_session, "HPHT_I69_001a", 69001, status=ExperimentStatus.ONGOING)

    xlsx = _experiments_excel([
        ["HPHT_I69_001a", None, None, "MH", "2026-02-01", "ONGOING", None, False],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == []
    assert created == 0
    assert updated == 0
    assert any("already exists" in w and "HPHT_I69_001a" in w for w in warnings), (
        f"expected a clear conflict warning naming the ID, got: {warnings}"
    )


def test_old_experiment_id_without_overwrite_conflicts_not_creates(db_session: Session):
    """issue #100: old_experiment_id provided with overwrite falsy must not silently
    fall through to standard matching and CREATE a duplicate — it must emit an
    explicit conflict naming both IDs and skip the row (2026-07-28 SERUM_Catalyst
    incident: 80 intended renames became 80 creates this way)."""
    _seed_experiment(db_session, "SERUM_I100_001", 100001, status=ExperimentStatus.ONGOING)

    xlsx = _experiments_excel([
        ["SERUM_I100_001_New", "SERUM_I100_001", None, None, None, None, None, False],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == []
    assert created == 0, "row must not silently create a duplicate experiment"
    assert updated == 0

    ghost = db_session.query(Experiment).filter_by(experiment_id="SERUM_I100_001_New").first()
    assert ghost is None, "duplicate experiment was created instead of being blocked"

    original = db_session.query(Experiment).filter_by(experiment_id="SERUM_I100_001").first()
    assert original is not None, "original experiment must be untouched"

    assert any(
        "SERUM_I100_001" in w and "SERUM_I100_001_New" in w and "overwrite" in w.lower()
        for w in warnings
    ), f"expected an explicit conflict warning naming both IDs, got: {warnings}"


def test_creating_three_replicates_via_bulk_upload(db_session: Session):
    """Creating SERUM_001a/b/c in one upload yields three experiments sharing a base."""
    xlsx = _experiments_excel([
        ["HPHT_I69_010a", None, None, "MH", "2026-02-01", "ONGOING", "Replicate a", False],
        ["HPHT_I69_010b", None, None, "MH", "2026-02-01", "ONGOING", "Replicate b", False],
        ["HPHT_I69_010c", None, None, "MH", "2026-02-01", "ONGOING", "Replicate c", False],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == []
    assert created == 3

    rep_a = db_session.query(Experiment).filter_by(experiment_id="HPHT_I69_010a").first()
    rep_b = db_session.query(Experiment).filter_by(experiment_id="HPHT_I69_010b").first()
    rep_c = db_session.query(Experiment).filter_by(experiment_id="HPHT_I69_010c").first()

    assert rep_a.base_experiment_id == "HPHT_I69_010"
    assert rep_b.base_experiment_id == "HPHT_I69_010"
    assert rep_c.base_experiment_id == "HPHT_I69_010"
    assert {rep_a.replicate_label, rep_b.replicate_label, rep_c.replicate_label} == {"a", "b", "c"}
