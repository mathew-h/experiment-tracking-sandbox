"""Tests for the additives-phase fixes in issue #96: method truncation + savepoint isolation."""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import Experiment, ChemicalAdditive, Compound, ExperimentalConditions
from database.models.enums import ExperimentStatus
from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH
from backend.services.bulk_uploads.new_experiments import NewExperimentsUploadService

from .excel_helpers import make_excel_multisheet

_EXP_HEADERS = [
    "experiment_id", "old_experiment_id", "sample_id", "researcher",
    "date", "status", "initial_note", "overwrite",
]
_ADD_HEADERS = ["experiment_id", "compound", "amount", "unit", "order", "method"]


def _seed_experiment(db: Session, experiment_id: str, exp_num: int) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=exp_num,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.flush()
    return exp


def test_85_char_method_round_trips_intact(db_session: Session):
    """Reproduces the exact issue #96 example: an 85-char value must survive unmodified."""
    _seed_experiment(db_session, "ADD_I96_A001", 960001)
    long_method = "11.8 mL master stock diluted to 20 mL total with DI water; no rock (background blank)"
    assert len(long_method) == 85

    xlsx = make_excel_multisheet({
        "experiments": (_EXP_HEADERS, []),
        "additives": (_ADD_HEADERS, [
            ["ADD_I96_A001", "Iron Oxide I96", 5.0, "g", 1, long_method],
        ]),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )
    assert errors == [], f"Unexpected errors: {errors}"
    assert not any("truncated" in w for w in warnings), f"Should not truncate an 85-char value: {warnings}"

    additive = (
        db_session.query(ChemicalAdditive)
        .join(Compound)
        .filter(Compound.name == "Iron Oxide I96")
        .one()
    )
    assert additive.addition_method == long_method


def test_method_over_max_length_is_truncated_with_warning(db_session: Session):
    _seed_experiment(db_session, "ADD_I96_A002", 960002)
    over_length = "y" * (ADDITION_METHOD_MAX_LENGTH + 100)

    xlsx = make_excel_multisheet({
        "experiments": (_EXP_HEADERS, []),
        "additives": (_ADD_HEADERS, [
            ["ADD_I96_A002", "Iron Oxide I96 B", 5.0, "g", 1, over_length],
        ]),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )
    assert errors == [], f"Unexpected errors: {errors}"
    assert any("truncated" in w and "Row 2" in w for w in warnings), (
        f"Expected a truncation warning for row 2, got: {warnings}"
    )

    additive = (
        db_session.query(ChemicalAdditive)
        .join(Compound)
        .filter(Compound.name == "Iron Oxide I96 B")
        .one()
    )
    assert len(additive.addition_method) == ADDITION_METHOD_MAX_LENGTH
    assert additive.addition_method == over_length[:ADDITION_METHOD_MAX_LENGTH]


def test_duplicate_compound_row_failure_does_not_poison_other_rows(db_session: Session):
    """A row that fails mid-write (unique constraint violation) must roll back only itself —
    other rows in the same batch, and the session itself, must remain usable (issue #96 Defect B)."""
    _seed_experiment(db_session, "ADD_I96_A003", 960003)

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["ADD_I96_A003", None, None, None, None, "ONGOING", None, True]],
        ),
        "additives": (_ADD_HEADERS, [
            ["ADD_I96_A003", "Dup Compound I96", 5.0, "g", 1, "first insert"],
            ["ADD_I96_A003", "Dup Compound I96", 3.0, "g", 2, "duplicate - should fail"],
            ["ADD_I96_A003", "Other Compound I96", 2.0, "g", 3, "third row - must still land"],
        ]),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )
    assert errors == [], f"Unexpected top-level errors: {errors}"

    row_warnings = [w for w in warnings if w.startswith("[additives] Row 3:")]
    assert len(row_warnings) == 1, f"Expected exactly one warning for row 3, got: {warnings}"

    # Regression guard: the session must not be left in a rollback-pending state.
    count = db_session.query(Experiment).count()
    assert count >= 1

    additives = (
        db_session.query(ChemicalAdditive)
        .join(Compound)
        .filter(Compound.name.in_(["Dup Compound I96", "Other Compound I96"]))
        .all()
    )
    names = sorted(a.compound.name for a in additives)
    assert names == ["Dup Compound I96", "Other Compound I96"], (
        f"Expected exactly one surviving 'Dup Compound I96' additive plus 'Other Compound I96', got: {names}"
    )


def test_stale_compound_cache_evicted_after_row_rollback(db_session: Session, monkeypatch):
    """Regression test for the issue #96 code review finding: `name_to_compound` must not
    retain a reference to a Compound whose INSERT was undone by the row's own savepoint
    rollback. Row 1 auto-creates a brand-new compound and then fails later in the SAME row
    (simulated `recalculate` failure) — its savepoint rollback must undo the Compound INSERT
    too. Row 2, later in the same batch, references the same (still-novel) compound name and
    must get a freshly created Compound row, not a broken reference to the rolled-back one."""
    _seed_experiment(db_session, "ADD_I96_A004", 960004)

    import backend.services.bulk_uploads.new_experiments as new_experiments_module

    real_recalculate = new_experiments_module.recalculate
    marker_name = "Stale Compound I96"
    # Fail only the FIRST call for a compound named `marker_name` (row 1's brand-new
    # compound). If the fix works, row 2 creates a genuinely NEW Compound row (different
    # id) with the same name after the cache eviction — that second, distinct compound
    # must be allowed to succeed; only the original one is meant to blow up.
    already_failed_once = {"done": False}

    def fake_recalculate(instance, db):
        compound = db.query(Compound).filter(Compound.id == instance.compound_id).first()
        if compound is not None and compound.name == marker_name and not already_failed_once["done"]:
            already_failed_once["done"] = True
            raise RuntimeError("Simulated recalculate failure for stale-cache regression test")
        return real_recalculate(instance, db)

    monkeypatch.setattr(new_experiments_module, "recalculate", fake_recalculate)

    xlsx = make_excel_multisheet({
        "experiments": (_EXP_HEADERS, []),
        "additives": (_ADD_HEADERS, [
            ["ADD_I96_A004", marker_name, 5.0, "g", 1, "row 1 - will fail after compound insert"],
            ["ADD_I96_A004", marker_name, 3.0, "g", 2, "row 2 - must still land with a fresh compound"],
        ]),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )
    assert errors == [], f"Unexpected top-level errors: {errors}"

    row1_warnings = [w for w in warnings if w.startswith("[additives] Row 2:")]
    assert len(row1_warnings) == 1, f"Expected row 1 (sheet row 2) to fail with a warning, got: {warnings}"
    assert "Simulated recalculate failure" in row1_warnings[0]

    row2_warnings = [w for w in warnings if w.startswith("[additives] Row 3:")]
    assert row2_warnings == [], f"Row 2 (sheet row 3) must succeed cleanly, got warnings: {warnings}"

    # Regression guard: exactly one surviving additive (row 2's), with row 2's amount.
    surviving = (
        db_session.query(ChemicalAdditive)
        .join(Compound)
        .filter(Compound.name == marker_name)
        .all()
    )
    assert len(surviving) == 1, f"Expected exactly one surviving additive for '{marker_name}', got: {len(surviving)}"
    assert surviving[0].amount == 3.0

    # Exactly one Compound row named marker_name should exist: row 1's insert was rolled
    # back with its savepoint, and row 2 must have created a genuinely fresh one (not reused
    # a stale cached reference to the rolled-back row).
    compounds = db_session.query(Compound).filter(Compound.name == marker_name).all()
    assert len(compounds) == 1, f"Expected exactly one Compound row for '{marker_name}', got: {len(compounds)}"
