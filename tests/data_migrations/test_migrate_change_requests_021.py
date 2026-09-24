"""Pins the 021 conversion (issue #122 PR-B): every reactor_change_requests row
with a resolvable experiment becomes ONE dated 'modification' note plus ONE
ModificationsLog snapshot; NULL-experiment and blank rows are reported, not
converted; a second run converts nothing; a dry run writes nothing."""
from __future__ import annotations

import datetime

from sqlalchemy import select, func

from database.data_migrations.migrate_reactor_change_requests_021 import (
    SOURCE_TAG,
    apply_plan,
    build_plan,
)
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus, NoteType
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.notion_sync import ReactorChangeRequest

D1 = datetime.date(2026, 8, 1)
D2 = datetime.date(2026, 8, 3)
T0 = datetime.datetime(2026, 8, 1, 9, 30, tzinfo=datetime.timezone.utc)


def _exp(db, eid, num, reactor=None):
    exp = Experiment(experiment_id=eid, experiment_number=num, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    if reactor is not None:
        db.add(ExperimentalConditions(experiment_fk=exp.id, experiment_id=eid,
                                      reactor_number=reactor, experiment_type="HPHT"))
        db.flush()
    return exp


def _cr(db, label, eid, text_, day, **kw):
    row = ReactorChangeRequest(reactor_label=label, experiment_id=eid, requested_change=text_,
                               sync_date=day, created_at=kw.pop("created_at", T0), **kw)
    db.add(row)
    db.flush()
    return row


def _notes(db, exp):
    return db.execute(
        select(ExperimentNotes).where(ExperimentNotes.experiment_fk == exp.id).order_by(ExperimentNotes.id)
    ).scalars().all()


def test_converts_dashboard_and_notion_rows_alike(migration_session):
    db = migration_session
    exp = _exp(db, "CR021_001", 81001, reactor=5)
    typed = _cr(db, "R05", exp.experiment_id, "  Swapped stir shaft  ", D1)
    imported = _cr(db, "R05", exp.experiment_id, "Topped up catalyst", D2,
                   notion_page_id="a" * 32, notion_status="Done", carried_forward=True)
    plan = build_plan(db)
    assert [r.id for r in plan.convertible] == [typed.id, imported.id]
    ids = apply_plan(db, plan)
    db.commit()
    notes = _notes(db, exp)
    assert [n.id for n in notes] == ids
    assert [n.note_text for n in notes] == ["Swapped stir shaft", "Topped up catalyst"]
    assert all(n.note_type is NoteType.modification for n in notes)
    assert [n.event_date for n in notes] == [D1, D2]
    assert all(n.result_id is None for n in notes)
    assert all(n.created_by == SOURCE_TAG for n in notes)
    assert notes[0].created_at == T0


def test_null_experiment_rows_are_reported_not_converted(migration_session):
    db = migration_session
    _exp(db, "CR021_002", 81002)
    orphan = _cr(db, "R07", None, "reactor cleaned", D1)
    plan = build_plan(db)
    assert [r.id for r in plan.orphaned] == [orphan.id]
    assert plan.convertible == []
    apply_plan(db, plan)
    db.commit()
    assert db.execute(select(func.count()).select_from(ExperimentNotes)).scalar_one() == 0


def test_blank_text_rows_are_reported_not_converted(migration_session):
    db = migration_session
    exp = _exp(db, "CR021_003", 81003)
    blank = _cr(db, "R01", exp.experiment_id, "   ", D1)
    plan = build_plan(db)
    assert [r.id for r in plan.blank] == [blank.id]
    assert plan.convertible == []


def test_snapshot_shape(migration_session):
    db = migration_session
    exp = _exp(db, "CR021_004", 81004, reactor=9)
    row = _cr(db, "R09", exp.experiment_id, "Vented headspace", D1, notion_status="In progress")
    plan = build_plan(db)
    (note_id,) = apply_plan(db, plan)
    db.commit()
    log = db.execute(
        select(ModificationsLog).where(ModificationsLog.modified_table == "reactor_change_requests")
    ).scalar_one()
    assert log.modification_type == "update"
    assert log.modified_by == SOURCE_TAG
    assert log.experiment_fk == exp.id
    assert log.experiment_id == exp.experiment_id
    assert log.new_values == {"note_id": note_id}
    assert log.old_values["id"] == row.id
    assert log.old_values["reactor_label"] == "R09"
    assert log.old_values["requested_change"] == "Vented headspace"
    assert log.old_values["notion_status"] == "In progress"
    assert log.old_values["carried_forward"] is False
    assert log.old_values["sync_date"] == "2026-08-01"
    assert log.old_values["notion_page_id"] is None
    assert log.old_values["created_at"] == T0.isoformat()


def test_second_run_is_a_no_op(migration_session):
    db = migration_session
    exp = _exp(db, "CR021_005", 81005)
    _cr(db, "R02", exp.experiment_id, "Replaced septum", D1)
    first = build_plan(db)
    apply_plan(db, first)
    db.commit()
    second = build_plan(db)
    assert second.convertible == []
    assert len(second.already_converted) == 1
    apply_plan(db, second)
    db.commit()
    assert len(_notes(db, exp)) == 1
    assert db.execute(select(func.count()).select_from(ModificationsLog)
                      .where(ModificationsLog.modified_table == "reactor_change_requests")).scalar_one() == 1


def test_same_experiment_date_text_under_two_labels_collapses_to_one_note(migration_session):
    # Review Focus 2: the unique key allows this pair; the idempotency key does not.
    db = migration_session
    exp = _exp(db, "CR021_006", 81006)
    a = _cr(db, "R03", exp.experiment_id, "moved to R04", D1)
    b = _cr(db, "R04", exp.experiment_id, "moved to R04", D1)
    plan = build_plan(db)
    assert [r.id for r in plan.convertible] == [a.id]
    assert [r.id for r in plan.collapsed] == [b.id]
    apply_plan(db, plan)
    db.commit()
    assert len(_notes(db, exp)) == 1


def test_label_disagreement_is_counted_informationally(migration_session):
    db = migration_session
    exp = _exp(db, "CR021_007", 81007, reactor=5)        # reactor_slot derives to R05
    _cr(db, "R05", exp.experiment_id, "agrees", D1)
    _cr(db, "R06", exp.experiment_id, "disagrees", D2)
    plan = build_plan(db)
    assert plan.label_disagreements == 1
    assert len(plan.convertible) == 2                     # informational only, both convert


def test_dry_run_writes_nothing(migration_session):
    db = migration_session
    exp = _exp(db, "CR021_008", 81008)
    _cr(db, "R08", exp.experiment_id, "dry", D1)
    build_plan(db)                                        # no apply_plan
    db.commit()
    assert _notes(db, exp) == []
    assert db.execute(select(func.count()).select_from(ModificationsLog)).scalar_one() == 0
