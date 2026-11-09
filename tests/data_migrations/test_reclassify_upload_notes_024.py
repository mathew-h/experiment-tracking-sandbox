"""Pins the 024 reclassification: parser-signed result-scoped 'observation'
notes become 'result_note' with one ModificationsLog snapshot each; a taken
slot is skipped; researcher, 020-backfill and experiment-level observations are
left alone; a dry run writes nothing; a second run is a no-op."""
from __future__ import annotations

import pytest
from sqlalchemy import delete, func, select

from backend.services.notes import UPLOAD_SLOT_SIGNERS
from database.data_migrations.reclassify_upload_notes_024 import (
    SOURCE_TAG,
    UPLOAD_SIGNERS,
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
    e1, r1 = _exp(db, "RN024_001", 84001)
    e2, r2 = _exp(db, "RN024_002", 84002)
    obs, rn = NoteType.observation, NoteType.result_note
    s = {
        "master": _note(db, e1, "Liq cloudy", obs, "master_bulk_upload", r1),
        "scalar": _note(db, e2, "Clear", obs, "scalar_results", r2),
        "quick": _note(db, e2, "Headspace", obs, "quick_upload", r2),
        "master_mod": _note(db, e1, "Swapped brine", NoteType.modification, "master_bulk_upload", r1),
        "researcher": _note(db, e1, "Looked orange", obs, "a@addisenergy.com", r1),
        "legacy": _note(db, e1, "legacy text", obs, "reclassify_notes_020", r1),
        "exp_level": _note(db, e2, "unscoped", obs, "master_bulk_upload"),
        # r2 already has a scalar_results result_note -> the scalar observation is skipped.
        "taken": _note(db, e2, "already result note", rn, "scalar_results", r2),
    }
    return db, s


def _count(db, model):
    return db.execute(select(func.count()).select_from(model)).scalar_one()


def test_signers_match_the_service():
    assert UPLOAD_SIGNERS == UPLOAD_SLOT_SIGNERS


def test_dry_run_changes_nothing(seeded, capsys):
    db, s = seeded
    logs_before = _count(db, ModificationsLog)
    print_report(build_plan(db))
    assert "targets" in capsys.readouterr().out
    assert _count(db, ModificationsLog) == logs_before
    db.refresh(s["master"])
    assert s["master"].note_type == NoteType.observation


def test_build_plan_buckets(seeded):
    db, s = seeded
    plan = build_plan(db)
    ids = {n.id for n in plan.targets}
    assert {s["master"].id, s["quick"].id} <= ids
    for key in ("scalar", "master_mod", "researcher", "legacy", "exp_level", "taken"):
        assert s[key].id not in ids, key
    assert s["scalar"].id in {n.id for n in plan.slot_taken}
    assert plan.other_authors["a@addisenergy.com"] >= 1
    assert plan.other_authors["reclassify_notes_020"] >= 1


def test_apply_retypes_and_audits_then_is_idempotent(seeded):
    db, s = seeded
    plan = build_plan(db)
    changed = apply_plan(db, plan)
    assert set(changed) == {n.id for n in plan.targets}
    for key in ("master", "quick"):
        db.refresh(s[key])
        assert s[key].note_type == NoteType.result_note
    for key, ntype in (("scalar", NoteType.observation), ("researcher", NoteType.observation),
                       ("legacy", NoteType.observation), ("exp_level", NoteType.observation),
                       ("master_mod", NoteType.modification)):
        db.refresh(s[key])
        assert s[key].note_type == ntype, key
    log = db.execute(
        select(ModificationsLog).where(
            ModificationsLog.modified_by == SOURCE_TAG,
            ModificationsLog.experiment_id == "RN024_001",
        )
    ).scalar_one()
    assert log.modification_type == "update"
    assert log.modified_table == "experiment_notes"
    assert log.old_values == {"id": s["master"].id, "note_type": "observation",
                              "result_id": s["master"].result_id,
                              "created_by": "master_bulk_upload"}
    assert log.new_values == {"note_type": "result_note"}
    again = build_plan(db)
    assert not ({n.id for n in again.targets} & {s["master"].id, s["quick"].id})
