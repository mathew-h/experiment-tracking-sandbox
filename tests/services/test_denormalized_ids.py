"""Unit tests for the single definition of the rename fan-out (issue #109 follow-up)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import (
    Experiment,
    ExperimentNotes,
    ExperimentalConditions,
    ExternalAnalysis,
    ModificationsLog,
    XRDPhase,
)
from database.models.enums import ExperimentStatus
from backend.services.denormalized_ids import sync_denormalized_experiment_id


def _seed(db: Session, exp_id: str, number: int) -> Experiment:
    """Create an experiment with one row in each of the five denormalized tables."""
    exp = Experiment(
        experiment_id=exp_id,
        experiment_number=number,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.flush()
    db.add_all([
        ExperimentalConditions(experiment_id=exp_id, experiment_fk=exp.id, temperature_c=250.0),
        ExperimentNotes(experiment_id=exp_id, experiment_fk=exp.id, note_text="seed note"),
        ModificationsLog(
            experiment_id=exp_id, experiment_fk=exp.id,
            modified_by="test", modification_type="create", modified_table="experiments",
        ),
        ExternalAnalysis(experiment_id=exp_id, experiment_fk=exp.id, analysis_type="XRD"),
        XRDPhase(
            experiment_id=exp_id, experiment_fk=exp.id,
            mineral_name="Magnetite", amount=12.5, time_post_reaction_days=7.0,
        ),
    ])
    db.flush()
    return exp


def test_syncs_all_five_tables(db_session: Session):
    """Every denormalized copy follows the new id, and each is counted."""
    exp = _seed(db_session, "SYNC_TEST_001", 8801001)
    exp.experiment_id = "SYNC_TEST_001a-t7"
    db_session.flush()

    result = sync_denormalized_experiment_id(db_session, exp.id, "SYNC_TEST_001a-t7")
    db_session.flush()

    assert result.conditions == 1
    assert result.notes == 1
    assert result.modifications == 1
    assert result.external_analyses == 1
    assert result.xrd_phases == 1
    assert result.xrd_phases_skipped == []

    for model in (ExperimentalConditions, ExperimentNotes, ModificationsLog,
                  ExternalAnalysis, XRDPhase):
        rows = db_session.query(model).filter(model.experiment_fk == exp.id).all()
        assert rows, f"{model.__name__} row vanished"
        for row in rows:
            assert row.experiment_id == "SYNC_TEST_001a-t7", (
                f"{model.__name__}.experiment_id still stale: {row.experiment_id!r}"
            )


def test_conditions_string_is_the_regression_target(db_session: Session):
    """The column that produced all 187 stale strings, asserted on its own."""
    exp = _seed(db_session, "SYNC_TEST_002", 8801002)
    exp.experiment_id = "SYNC_TEST_002b-t3"
    db_session.flush()

    sync_denormalized_experiment_id(db_session, exp.id, "SYNC_TEST_002b-t3")
    db_session.flush()

    cond = (
        db_session.query(ExperimentalConditions)
        .filter(ExperimentalConditions.experiment_fk == exp.id)
        .one()
    )
    assert cond.experiment_id == "SYNC_TEST_002b-t3"


def test_in_session_objects_see_the_new_string(db_session: Session):
    """An already-loaded ORM object must not keep serving the stale string.

    The bulk parser processes its conditions sheet AFTER the rename block and
    resolves the row by experiment_fk into the same session, so a Core UPDATE
    that left the identity map stale would hand it the old value.
    """
    exp = _seed(db_session, "SYNC_TEST_003", 8801003)
    note = (
        db_session.query(ExperimentNotes)
        .filter(ExperimentNotes.experiment_fk == exp.id)
        .one()
    )
    assert note.experiment_id == "SYNC_TEST_003"  # loaded into the identity map

    exp.experiment_id = "SYNC_TEST_003c"
    db_session.flush()
    sync_denormalized_experiment_id(db_session, exp.id, "SYNC_TEST_003c")

    assert note.experiment_id == "SYNC_TEST_003c", "identity map left stale"


def test_no_rows_is_not_an_error(db_session: Session):
    """An experiment with no children syncs to all-zero counts, no exception."""
    exp = Experiment(
        experiment_id="SYNC_TEST_004",
        experiment_number=8801004,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(exp)
    db_session.flush()

    result = sync_denormalized_experiment_id(db_session, exp.id, "SYNC_TEST_004a")

    assert (result.conditions, result.notes, result.modifications,
            result.external_analyses, result.xrd_phases) == (0, 0, 0, 0, 0)


def test_other_experiments_are_untouched(db_session: Session):
    """The fan-out is scoped to one experiment_fk and never reaches a sibling."""
    keep = _seed(db_session, "SYNC_TEST_005", 8801005)
    other = _seed(db_session, "SYNC_TEST_006", 8801006)

    keep.experiment_id = "SYNC_TEST_005a"
    db_session.flush()
    sync_denormalized_experiment_id(db_session, keep.id, "SYNC_TEST_005a")
    db_session.flush()

    other_cond = (
        db_session.query(ExperimentalConditions)
        .filter(ExperimentalConditions.experiment_fk == other.id)
        .one()
    )
    assert other_cond.experiment_id == "SYNC_TEST_006"


def test_xrd_slot_collision_is_skipped_not_raised(db_session: Session):
    """uq_xrd_phase_experiment_time_mineral is on the STRING. When another row
    already holds (new_id, time, mineral), renaming into it would raise an
    IntegrityError and abort the whole rename — so that row is left alone and
    reported instead."""
    victim = _seed(db_session, "SYNC_TEST_007", 8801007)
    # Debris already parked on the target slot, owned by a different experiment.
    blocker_owner = Experiment(
        experiment_id="SYNC_TEST_008",
        experiment_number=8801008,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(blocker_owner)
    db_session.flush()
    db_session.add(XRDPhase(
        experiment_id="SYNC_TEST_007a",     # the id `victim` is about to take
        experiment_fk=blocker_owner.id,
        mineral_name="Magnetite", amount=9.0, time_post_reaction_days=7.0,
    ))
    db_session.flush()

    victim.experiment_id = "SYNC_TEST_007a"
    db_session.flush()

    result = sync_denormalized_experiment_id(db_session, victim.id, "SYNC_TEST_007a")
    db_session.flush()  # must NOT raise IntegrityError

    victim_phase = (
        db_session.query(XRDPhase)
        .filter(XRDPhase.experiment_fk == victim.id)
        .one()
    )
    assert result.xrd_phases == 0
    assert result.xrd_phases_skipped == [victim_phase.id]
    assert victim_phase.experiment_id == "SYNC_TEST_007"  # left stale on purpose
    # Everything else still synced.
    assert result.conditions == 1
