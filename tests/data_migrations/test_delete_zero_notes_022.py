"""Pins the 022 cleanup (zero-note-cells fix C): only master_bulk_upload-signed
'0' modification/observation notes are deleted, each with a ModificationsLog
snapshot; every other look-alike is reported and left alone; a second run is a
no-op; a dry run writes nothing."""
from __future__ import annotations

import pytest
from sqlalchemy import delete, func, select

from database.data_migrations.delete_zero_notes_022 import (
    SOURCE_TAG,
    TARGET_AUTHOR,
    apply_plan,
    build_plan,
    print_report,
)
from database.models.enums import ExperimentStatus, NoteType
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.results import ExperimentalResults


def _exp(db, eid, num):
    exp = Experiment(experiment_id=eid, experiment_number=num, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    res = ExperimentalResults(experiment_fk=exp.id, time_post_reaction_days=1.0)
    db.add(res)
    db.flush()
    return exp, res


def _note(db, exp, text_, ntype, created_by, result=None):
    n = ExperimentNotes(
        experiment_fk=exp.id, experiment_id=exp.experiment_id, note_text=text_,
        note_type=ntype, created_by=created_by,
        result_id=result.id if result is not None else None,
    )
    db.add(n)
    db.flush()
    return n


@pytest.fixture
def seeded(migration_session):
    db = migration_session
    db.execute(delete(ModificationsLog).where(ModificationsLog.modified_by == SOURCE_TAG))
    db.flush()
    e1, r1 = _exp(db, "ZN022_001", 82001)
    e2, r2 = _exp(db, "ZN022_002", 82002)
    s = {}
    s["mod0"] = _note(db, e1, "0", NoteType.modification, TARGET_AUTHOR, r1)
    s["obs0"] = _note(db, e1, "0", NoteType.observation, TARGET_AUTHOR, r1)
    s["joined"] = _note(db, e1, "0; Liq", NoteType.observation, TARGET_AUTHOR, r1)
    s["real"] = _note(db, e2, "Swapped brine", NoteType.modification, TARGET_AUTHOR, r2)
    s["researcher"] = _note(db, e2, "0", NoteType.observation, "a@addisenergy.com", r2)
    s["null_desc"] = _note(db, e2, "0", NoteType.description, None)
    s["nan"] = _note(db, e1, "nan", NoteType.observation, None)
    return db, s


def _count(db, model):
    return db.execute(select(func.count()).select_from(model)).scalar_one()


def test_dry_run_changes_nothing(seeded, capsys):
    db, _ = seeded
    notes_before, logs_before = _count(db, ExperimentNotes), _count(db, ModificationsLog)
    plan = build_plan(db)
    print_report(plan)
    out = capsys.readouterr().out
    for word in ("target", "joined", "other", "null", "nan"):
        assert word in out.lower()
    assert _count(db, ExperimentNotes) == notes_before
    assert _count(db, ModificationsLog) == logs_before


def test_build_plan_buckets(seeded):
    db, s = seeded
    plan = build_plan(db)
    ids = lambda lst: [n.id for n in lst]  # noqa: E731
    assert set(ids(plan.targets)) >= {s["mod0"].id, s["obs0"].id}
    own = {s[k].id for k in s}
    assert [i for i in ids(plan.targets) if i in own] == sorted([s["mod0"].id, s["obs0"].id])
    assert s["joined"].id in ids(plan.joined_zero)
    assert s["researcher"].id in ids(plan.other_author_zero)
    assert s["null_desc"].id in ids(plan.null_author_zero)
    assert s["nan"].id in ids(plan.nan_notes)
    assert s["real"].id not in ids(plan.targets + plan.joined_zero + plan.other_author_zero
                                   + plan.null_author_zero + plan.nan_notes)


def test_apply_deletes_only_the_targets(seeded):
    db, s = seeded
    plan = build_plan(db)
    texts = {k: (v.id, v.note_text) for k, v in s.items()}
    deleted = apply_plan(db, plan)
    assert {s["mod0"].id, s["obs0"].id} <= set(deleted)
    remaining = {n.id: n.note_text for n in db.execute(select(ExperimentNotes)).scalars()}
    for k, (nid, txt) in texts.items():
        if k in ("mod0", "obs0"):
            assert nid not in remaining
        else:
            assert remaining[nid] == txt


def test_apply_writes_one_snapshot_per_deleted_note(seeded):
    db, s = seeded
    expected = {
        s["mod0"].id: (NoteType.modification.value, s["mod0"].result_id),
        s["obs0"].id: (NoteType.observation.value, s["obs0"].result_id),
    }
    plan = build_plan(db)
    deleted = apply_plan(db, plan)
    logs = db.execute(
        select(ModificationsLog).where(ModificationsLog.modified_by == SOURCE_TAG)
    ).scalars().all()
    assert len(logs) == len(deleted)
    by_id = {log.old_values["id"]: log for log in logs}
    for nid, (ntype, rid) in expected.items():
        log = by_id[nid]
        assert log.modification_type == "delete"
        assert log.modified_table == "experiment_notes"
        assert log.new_values is None
        assert log.old_values == {
            "id": nid, "note_text": "0", "note_type": ntype, "result_id": rid,
            "created_by": TARGET_AUTHOR, "needs_review": False,
        }


def test_second_run_is_a_no_op(seeded):
    db, _ = seeded
    apply_plan(db, build_plan(db))
    plan2 = build_plan(db)
    assert plan2.targets == []
    logs_before = _count(db, ModificationsLog)
    assert apply_plan(db, plan2) == []
    assert _count(db, ModificationsLog) == logs_before
