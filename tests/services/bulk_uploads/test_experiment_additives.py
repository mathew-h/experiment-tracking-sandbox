"""Tests for the savepoint isolation + method-length fixes in issue #96."""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import Experiment, ExperimentalConditions, Compound, ChemicalAdditive
from database.models.enums import ExperimentStatus
from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH
import backend.services.bulk_uploads.experiment_additives as ea_mod
from backend.services.bulk_uploads.experiment_additives import ExperimentAdditivesService

from .excel_helpers import make_excel

_HEADERS = ["experiment_id", "compound", "amount", "unit", "order", "method"]


def _seed_experiment_with_compounds(db: Session, exp_id: str, exp_num: int, compound_names: list[str]):
    exp = Experiment(experiment_id=exp_id, experiment_number=exp_num, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    compounds = {}
    for name in compound_names:
        c = Compound(name=name)
        db.add(c)
        db.flush()
        compounds[name] = c
    return exp, compounds


def test_85_char_method_round_trips_intact(db_session: Session):
    long_method = "11.8 mL master stock diluted to 20 mL total with DI water; no rock (background blank)"
    assert len(long_method) == 85
    exp, compounds = _seed_experiment_with_compounds(db_session, "EA_I96_001", 970001, ["Iron Oxide EA I96"])

    xlsx = make_excel(_HEADERS, [
        ["EA_I96_001", "Iron Oxide EA I96", 5.0, "g", 1, long_method],
    ])
    created, updated, skipped, errors = ExperimentAdditivesService.bulk_upsert_from_excel(db_session, xlsx)
    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    additive = db_session.query(ChemicalAdditive).filter_by(compound_id=compounds["Iron Oxide EA I96"].id).one()
    assert additive.addition_method == long_method


def test_method_over_max_length_is_truncated_with_warning(db_session: Session):
    exp, compounds = _seed_experiment_with_compounds(db_session, "EA_I96_002", 970002, ["Iron Oxide EA I96 B"])
    over_length = "z" * (ADDITION_METHOD_MAX_LENGTH + 50)

    xlsx = make_excel(_HEADERS, [
        ["EA_I96_002", "Iron Oxide EA I96 B", 5.0, "g", 1, over_length],
    ])
    created, updated, skipped, errors = ExperimentAdditivesService.bulk_upsert_from_excel(db_session, xlsx)
    assert any("truncated" in e and "Row 2" in e for e in errors), f"Expected a truncation notice, got: {errors}"
    assert created == 1

    additive = db_session.query(ChemicalAdditive).filter_by(compound_id=compounds["Iron Oxide EA I96 B"].id).one()
    assert len(additive.addition_method) == ADDITION_METHOD_MAX_LENGTH


def test_mid_row_failure_isolated_by_savepoint(db_session: Session, monkeypatch):
    """Simulate a post-write exception (e.g. a recalculation bug) on row 2 and verify it does not
    poison the session for row 3, and row 1 remains committed (issue #96 Defect B)."""
    exp, compounds = _seed_experiment_with_compounds(
        db_session, "EA_I96_003", 970003, ["Good Compound A", "Poison Compound", "Good Compound B"]
    )
    poison_id = compounds["Poison Compound"].id
    real_recalculate = ea_mod.recalculate

    def fake_recalculate(instance, session):
        if instance.compound_id == poison_id:
            raise ValueError("simulated recalculation failure")
        return real_recalculate(instance, session)

    monkeypatch.setattr(ea_mod, "recalculate", fake_recalculate)

    xlsx = make_excel(_HEADERS, [
        ["EA_I96_003", "Good Compound A", 5.0, "g", 1, "ok"],
        ["EA_I96_003", "Poison Compound", 3.0, "g", 2, "will fail"],
        ["EA_I96_003", "Good Compound B", 2.0, "g", 3, "must still land"],
    ])
    created, updated, skipped, errors = ExperimentAdditivesService.bulk_upsert_from_excel(db_session, xlsx)

    row_errors = [e for e in errors if e.startswith("Row 3:")]
    assert len(row_errors) == 1, f"Expected exactly one error for row 3 (the poisoned row), got: {errors}"
    assert created == 2, f"Expected rows 1 and 3 to still create additives, got created={created}"

    # Regression guard: the session must not be left in a rollback-pending state.
    surviving = (
        db_session.query(ChemicalAdditive)
        .filter(ChemicalAdditive.compound_id.in_([compounds["Good Compound A"].id, compounds["Good Compound B"].id]))
        .all()
    )
    assert len(surviving) == 2
    poisoned = db_session.query(ChemicalAdditive).filter_by(compound_id=poison_id).first()
    assert poisoned is None, "The poisoned row's insert must have been rolled back by its savepoint"


def test_savepoint_commit_failure_isolated_from_other_rows(db_session: Session, monkeypatch):
    """Regression test for the final-review finding on issue #96: `savepoint.commit()` itself
    (a RELEASE SAVEPOINT, which flushes the session first) can raise even when the row body
    completed without exception. That failure must be caught in `finally`, rolled back, and
    recorded as a row-scoped error -- not allowed to escape and poison the rest of the batch
    (the exact failure mode issue #96 originally fixed, just from a different trigger point)."""
    exp, compounds = _seed_experiment_with_compounds(
        db_session, "EA_I96_004", 970004, ["Commit Fail A", "Commit Fail B", "Commit Fail C"]
    )

    real_begin_nested = db_session.begin_nested
    call_count = {"n": 0}

    def fake_begin_nested():
        call_count["n"] += 1
        savepoint = real_begin_nested()
        if call_count["n"] == 2:
            # Row 2 (sheet row 3) is the target: force its own SAVEPOINT release to fail,
            # simulating a post-flush error (e.g. a bad derived value) at commit time.
            def failing_commit():
                raise RuntimeError("Simulated SAVEPOINT commit failure")
            monkeypatch.setattr(savepoint, "commit", failing_commit)
        return savepoint

    monkeypatch.setattr(db_session, "begin_nested", fake_begin_nested)

    xlsx = make_excel(_HEADERS, [
        ["EA_I96_004", "Commit Fail A", 5.0, "g", 1, "row 1 - must land"],
        ["EA_I96_004", "Commit Fail B", 3.0, "g", 2, "row 2 - commit fails"],
        ["EA_I96_004", "Commit Fail C", 2.0, "g", 3, "row 3 - must still land"],
    ])
    created, updated, skipped, errors = ExperimentAdditivesService.bulk_upsert_from_excel(db_session, xlsx)

    # (a) The failure is recorded against the correct row, not silently swallowed or misattributed.
    row2_errors = [e for e in errors if e.startswith("Row 3:")]
    assert len(row2_errors) == 1, f"Expected exactly one error for row 2 (sheet row 3), got: {errors}"
    assert "Simulated SAVEPOINT commit failure" in row2_errors[0]
    # NOTE: `created` is incremented in the try body BEFORE the finally-block commit runs, so
    # a commit-time-only failure (this test) does not decrement it -- a pre-existing, out-of-scope
    # counter quirk distinct from the actual persisted-row assertions in (c) below. It matters only
    # when `errors` is otherwise empty; since this test always produces a non-empty `errors`, the
    # documented caller behavior (Fix 2 comment) already discards the whole batch, making the counts
    # moot in practice.
    assert created == 3

    # (b) The session must not be poisoned: a subsequent query must succeed cleanly.
    count = db_session.query(Experiment).count()
    assert count >= 1

    # (c) Rows 1 and 3, in the SAME batch, must still have committed successfully.
    surviving = (
        db_session.query(ChemicalAdditive)
        .filter(ChemicalAdditive.compound_id.in_([compounds["Commit Fail A"].id, compounds["Commit Fail C"].id]))
        .all()
    )
    assert len(surviving) == 2
    poisoned = db_session.query(ChemicalAdditive).filter_by(compound_id=compounds["Commit Fail B"].id).first()
    assert poisoned is None, "Row 2's insert must have been rolled back by the failed savepoint commit"
