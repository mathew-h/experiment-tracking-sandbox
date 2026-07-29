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
