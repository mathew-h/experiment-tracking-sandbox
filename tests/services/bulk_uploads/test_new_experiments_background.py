"""is_background on the new-experiments upload (issue #152; parser change
signed off by Mat, 2026-11-08).

Blank = inherit from the -N / _Text parent on create (else False) and leave the
stored value alone on overwrite; TRUE/FALSE, YES/NO, Y/N, 1/0 set it; anything
else skips that row only (the experiments sheet has a per-row SAVEPOINT).
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from backend.services.bulk_uploads.new_experiments import (
    NewExperimentsUploadService, parse_background_cell,
)
from database import Experiment
from database.models.enums import ExperimentStatus
from database.models.experiments import ModificationsLog

from .excel_helpers import make_excel

_HEADERS = ["experiment_id", "status", "is_background", "overwrite"]


def _upload(db: Session, rows: list[list]):
    xlsx = make_excel(_HEADERS, rows, sheet_name="experiments")
    return NewExperimentsUploadService.bulk_upsert_from_excel(db, xlsx)


def _flag(db: Session, exp_id: str):
    exp = db.query(Experiment).filter_by(experiment_id=exp_id).first()
    return None if exp is None else exp.is_background


def _seed(db: Session, exp_id: str, number: int, background: bool) -> Experiment:
    exp = Experiment(experiment_id=exp_id, experiment_number=number,
                     status=ExperimentStatus.ONGOING, is_background=background)
    db.add(exp)
    db.flush()
    return exp


@pytest.mark.parametrize("cell,expected", [
    (None, None), ("", None), ("  ", None), (float("nan"), None),
    (True, True), (False, False), (1, True), (0, False), (1.0, True), (0.0, False),
    ("TRUE", True), ("false", False), ("Yes", True), ("no", False), ("y", True), ("N", False),
    ("1", True), ("0", False), (" true ", True),
])
def test_parse_background_cell_accepts(cell, expected):
    assert parse_background_cell(cell) == (expected, None)


@pytest.mark.parametrize("cell", ["maybe", "bg", "2", 2, -1, "TRUE?"])
def test_parse_background_cell_rejects(cell):
    value, error = parse_background_cell(cell)
    assert value is None
    assert "is_background must be TRUE or FALSE" in error


def test_create_sets_or_defaults_the_flag(db_session: Session):
    created, _u, _s, errors, _w, _i = _upload(db_session, [
        ["SERUM_BGU_001", "ONGOING", "TRUE", None],
        ["SERUM_BGU_002", "ONGOING", None, None],
        ["SERUM_BGU_003", "ONGOING", "no", None],
    ])
    assert errors == []
    assert created == 3
    assert [_flag(db_session, f"SERUM_BGU_00{i}") for i in (1, 2, 3)] == [True, False, False]


def test_derivation_inherits_parent_flag_when_blank(db_session: Session):
    _seed(db_session, "SERUM_BGU_010", 98010, background=True)
    _seed(db_session, "SERUM_BGU_011", 98011, background=False)
    _c, _u, _s, errors, _w, _i = _upload(db_session, [
        ["SERUM_BGU_010-2", "ONGOING", None, None],
        ["SERUM_BGU_011-2", "ONGOING", None, None],
        ["SERUM_BGU_010-3", "ONGOING", "FALSE", None],  # explicit value wins
    ])
    assert errors == []
    assert _flag(db_session, "SERUM_BGU_010-2") is True
    assert _flag(db_session, "SERUM_BGU_011-2") is False
    assert _flag(db_session, "SERUM_BGU_010-3") is False


def test_overwrite_blank_leaves_flag_and_value_changes_it_with_audit(db_session: Session):
    exp = _seed(db_session, "SERUM_BGU_020", 98020, background=True)
    _seed(db_session, "SERUM_BGU_021", 98021, background=True)
    _c, updated, _s, errors, _w, _i = _upload(db_session, [
        ["SERUM_BGU_020", "ONGOING", "FALSE", "TRUE"],
        ["SERUM_BGU_021", "ONGOING", None, "TRUE"],
    ])
    assert errors == []
    assert updated == 2
    assert _flag(db_session, "SERUM_BGU_020") is False
    assert _flag(db_session, "SERUM_BGU_021") is True
    logs = db_session.query(ModificationsLog).filter(
        ModificationsLog.experiment_fk == exp.id, ModificationsLog.modified_table == "experiments",
    ).all()
    assert [(log.old_values, log.new_values, log.modified_by) for log in logs] == [
        ({"is_background": True}, {"is_background": False}, "new_experiments_upload"),
    ]


def test_invalid_cell_skips_only_that_row(db_session: Session):
    created, _u, _s, _e, warnings, _i = _upload(db_session, [
        ["SERUM_BGU_030", "ONGOING", "maybe", None],
        ["SERUM_BGU_031", "ONGOING", "TRUE", None],
    ])
    assert created == 1
    assert _flag(db_session, "SERUM_BGU_030") is None
    assert _flag(db_session, "SERUM_BGU_031") is True
    assert any("Row 2 (SERUM_BGU_030)" in w and "is_background must be TRUE or FALSE" in w for w in warnings)


def test_dry_run_plan_reports_the_change(db_session: Session):
    _seed(db_session, "SERUM_BGU_040", 98040, background=False)
    xlsx = make_excel(_HEADERS, [
        ["SERUM_BGU_040", "ONGOING", "TRUE", "TRUE"],
        ["SERUM_BGU_041", "ONGOING", "bogus", None],
    ], sheet_name="experiments")
    *_, plan = NewExperimentsUploadService.bulk_upsert_from_excel_ex(db_session, xlsx)
    overwrite = next(o for o in plan.overwrites if o.experiment_id == "SERUM_BGU_040")
    changes = [(c.field, c.old, c.new) for c in overwrite.fields_changed if c.field == "is_background"]
    assert changes == [("is_background", False, True)]
    assert [(c.row, c.kind) for c in plan.conflicts] == [(3, "invalid_is_background")]
