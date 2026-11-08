"""set_background_flags_023 (issue #152): flags a confirmed list of experiments
as backgrounds, audits each change, never clears, and skips unknown IDs."""
from __future__ import annotations

from pathlib import Path

from database.data_migrations.set_background_flags_023 import (
    SOURCE_TAG, apply_plan, build_plan, read_ids,
)
from database.models.enums import ExperimentStatus
from database.models.experiments import Experiment, ModificationsLog


def _exp(db, exp_id, number, background=False):
    exp = Experiment(experiment_id=exp_id, experiment_number=number,
                     status=ExperimentStatus.COMPLETED, is_background=background)
    db.add(exp)
    db.flush()
    return exp


def test_read_ids_plain_list(tmp_path: Path):
    f = tmp_path / "ids.txt"
    f.write_text("# confirmed by MH\nSERUM_BO3_002a\n\n SERUM_BO3_002b \nSERUM_BO3_002a\n", encoding="utf-8")
    assert read_ids(f) == ["SERUM_BO3_002a", "SERUM_BO3_002b"]


def test_read_ids_csv_with_header(tmp_path: Path):
    f = tmp_path / "ids.csv"
    f.write_text("﻿Group,Experiment_ID,Answer\nSERUM_BO3,SERUM_BO3_002a,yes\nSERUM_BO3,SERUM_BO3_004a,yes\n",
                 encoding="utf-8")
    assert read_ids(f) == ["SERUM_BO3_002a", "SERUM_BO3_004a"]


def test_plan_sorts_ids(migration_session):
    db = migration_session
    _exp(db, "BGF_001", 99101)
    _exp(db, "BGF_002", 99102, background=True)
    plan = build_plan(db, ["BGF_001", "BGF_002", "BGF_NOPE"])
    assert plan.to_flag == ["BGF_001"]
    assert plan.already == ["BGF_002"]
    assert plan.unknown == ["BGF_NOPE"]


def test_apply_flags_and_audits_once(migration_session):
    db = migration_session
    exp = _exp(db, "BGF_010", 99110)
    _exp(db, "BGF_011", 99111, background=True)
    assert apply_plan(db, build_plan(db, ["BGF_010", "BGF_011"])) == 1
    db.refresh(exp)
    assert exp.is_background is True
    logs = db.query(ModificationsLog).filter(ModificationsLog.modified_by == SOURCE_TAG).all()
    assert [(log.experiment_id, log.old_values, log.new_values) for log in logs] == [
        ("BGF_010", {"is_background": False}, {"is_background": True}),
    ]
    # Idempotent: a second run has nothing to do.
    second = build_plan(db, ["BGF_010", "BGF_011"])
    assert second.to_flag == []
    assert apply_plan(db, second) == 0
