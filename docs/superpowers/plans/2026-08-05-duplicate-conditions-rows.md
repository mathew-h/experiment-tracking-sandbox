# Duplicate `experimental_conditions` Rows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `experiment_fk` the single identity for a conditions row — clean up the one existing duplicate and 187 stale `experiment_id` strings, stop new duplicates at both the API and the DB, and make every 1:1 reader survive a violation instead of returning 500.

**Architecture:** `experimental_conditions` carries two identities: `experiment_fk` (authoritative, FK, non-null) and a denormalized `experiment_id` string that no rename path updates. Reads that resolve by the string miss the row, the UI then offers "Add Details", and `POST /api/conditions` inserts a second row because nothing — app or DB — forbids it. The fix moves every read onto the FK, adds a `UNIQUE (experiment_fk)` constraint, and cleans the data that the string-based reads produced.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 ORM + PostgreSQL 18, Alembic, pytest.

## Global Constraints

- Task type is **issue** (#109 investigation spin-off). Branch already created: `fix/issue-109-duplicate-experiment-ids`.
- **Never start, stop, or restart uvicorn or the Vite dev server.** Assume both are running (ports 8000 / 5173). If unreachable, report it.
- Python entry points use the venv prefix: `.venv/Scripts/python`, `.venv/Scripts/pytest`, `.venv/Scripts/alembic`. Bare `alembic` / `pytest` are not on PATH.
- `structlog` only — never `print()` in application code. Data-migration scripts under `database/data_migrations/` print to stdout by established convention (see `demote_stale_t3_prefix_rows_017.py`) and that is correct there.
- **Never run two pytest processes at once** — `experiments_test` is shared and an interrupted run leaves a schema `create_all` cannot repair.
- `tests/test_pg_backup_restore.py` has **3 pre-existing failures** on `develop`. They are the documented baseline, not a regression. Confirm on `develop` before blaming this work.
- The conditions and experiments routers **commit**, so rows created by API tests land for real in `experiments_test`. Every new API test file/section needs an autouse cleanup fixture — copy the `_cleanup_slot_rows` pattern at `tests/api/test_conditions.py:12-28`.
- `database/models/` is **locked**. Task 5 modifies `database/models/conditions.py`; this is authorized by explicit user instruction on 2026-08-05 (scope selection "Above + unique constraint … + defensive reads"). Change nothing else in that directory.
- Every Alembic migration implements both `upgrade` and `downgrade`. Never delete, rewrite, or squash an existing migration file.
- Current Alembic head: `1c1ef9b555e0`. New revision's `down_revision` must be exactly that string.
- All new/changed Python must pass `flake8` without adding warnings.
- Do not modify anything in `backend/services/bulk_uploads/` except where a task explicitly says so. All three of its conditions-creation sites already resolve by `experiment_fk` and need no change.

## Background — the confirmed failure chain

Measured against the production dump `experiments_20260805_010002.sql` (1012 experiments, 1013 conditions rows):

| Fact | Value |
|---|---|
| Experiments with 2 conditions rows | **1** — `SERUM_Cation_011a-t5` (exp id 901): cond **901** (string `'SERUM_cation_031'`, created 2026-07-15) and cond **1062** (string `'SERUM_Cation_011a-t5'`, created 2026-08-04) |
| Are the two rows equivalent? | Yes — every scientific column identical (90 °C, pH 9.89, 1 g, 20 mL, 75-212 µm); each carries one Mg(OH)₂ 0.149 g additive (ids 2342 on cond 901, 2657 on cond 1062) |
| Conditions rows whose string ≠ their FK's real `experiment_id` | **187 of 1013 (18%)** |
| Of those, experiments whose real ID appears on **no** conditions row → `by-experiment` 404s → "Add Details" creates a duplicate | **175** |
| Of those, rows whose string names a **different** experiment that has its own row → detail page shows the wrong conditions | **12** |
| Conditions strings appearing on >1 row → `by-experiment` raises `MultipleResultsFound` → 500 | **6** (`AUTO_JW_007`, `HPHT_JW_005-3_Desorption`, `HPHT_JW_005-4`, `HPHT_MH_029-6`, `OTHER_JW_001`, `SERUM_JW_046`) |
| Experiments named `SERUM_cation_031` | **0** — it exists only as a stale string |
| `UNIQUE` on `experiments.experiment_id` in production | **Present** (`ix_experiments_experiment_id`) — duplicate *experiments* are impossible |
| `UNIQUE` on `experimental_conditions.experiment_fk` | **Absent** — this is the hole |

The chain: `ExperimentDetail/index.tsx:66` → `GET /api/conditions/by-experiment/{id}` → `conditions.py:49` filters the **string** → 404 → `conditions = null` → ConditionsTab renders "Add Details" → `POST /api/conditions` (`conditions.py:56-71`, no existence check) → second row. Then:

- `backend/api/routers/experiments.py:72-74` (`_build_list_item`) `scalar_one_or_none()` → `MultipleResultsFound` → **500 on the experiments list page containing that row**
- `backend/api/routers/experiments.py:134-137` — the list's outer join fans out; the comment at `:132` asserts it cannot
- `v_experiments` / `v_experiment_conditions` LEFT JOIN conditions → duplicate `experiment_id` key → **Power BI relationship rejected**
- `backend/services/experiment_deletion.py:226-228` (`serialize_experiment_snapshot`) → same exception inside `delete_experiment_cascade` → the bulk-delete row lands in `failed` with "Multiple rows were found when one or none was required". **This, not `experiment_deletion_bulk.py:140`, is why the delete tool could not remove it.**

Note `Experiment.conditions` is `uselist=False` with `cascade="all, delete-orphan"` (`database/models/experiments.py:30`): with two rows SQLAlchemy loads one and the cascade deletes only that one. Do not rely on the relationship to clean up the second row.

**Why `experiment_deletion_bulk.py:140` is deliberately left unchanged.** The original request was to make the bulk-delete parser tolerate a duplicate `experiment_id`. That line's `scalar_one_or_none()` cannot raise: `experiments.experiment_id` carries a `UNIQUE` index in production, verified in the 2026-08-05 dump's schema, so two rows sharing an ID are impossible. Loosening it would defend against an unreachable state while leaving the real fault — one table deeper, in the conditions read — in place. Task 4 fixes the line that actually raised, and its bulk-upload regression test asserts the user-visible outcome (the ID lands in `deleted`, not `failed`).

## File Structure

| File | Responsibility |
|---|---|
| `database/data_migrations/dedupe_conditions_and_backfill_ids_018.py` | **Create.** One-off, rule-based, dry-run-by-default cleanup: delete equivalent duplicate conditions rows, then backfill every stale `experiment_id` string from its FK. |
| `tests/data_migrations/test_dedupe_conditions_018.py` | **Create.** Pins the selection rules, the refuse-when-not-equivalent guard, and the backfill. |
| `backend/api/routers/conditions.py` | **Modify.** `by-experiment` resolves through `experiment_fk`; `POST` returns 409 when a row already exists. |
| `tests/api/test_conditions.py` | **Modify.** Add the 409 guard and FK-resolution cases. |
| `backend/api/routers/experiments.py:69-95, 129-137` | **Modify.** `_build_list_item` tolerates a duplicate; correct the stale "cannot fan out" comment. |
| `backend/services/experiment_deletion.py:226-228` | **Modify.** `serialize_experiment_snapshot` tolerates a duplicate so deletion is never blocked by one. |
| `tests/services/test_experiment_deletion.py` | **Modify.** Regression: an experiment with two conditions rows deletes cleanly. |
| `tests/services/bulk_uploads/test_experiment_deletion_bulk.py` | **Modify.** Regression: such an experiment lands in `deleted`, not `failed`. |
| `tests/api/test_experiments.py` | **Modify.** Regression: the list endpoint does not 500 and does not double-count. |
| `database/models/conditions.py` | **Modify (locked, authorized).** Add `UniqueConstraint("experiment_fk")`. |
| `alembic/versions/<rev>_unique_conditions_per_experiment.py` | **Create.** Adds the constraint, with a pre-flight check that fails loudly if duplicates remain. |
| `tests/models/test_conditions_unique_experiment_fk.py` | **Create.** Second row for the same `experiment_fk` raises `IntegrityError`. |
| `docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md` | **Create.** The investigation record and the production numbers above. |
| `.claude/rules/MODELS.md`, `docs/api/API_REFERENCE.md` | **Modify.** Document the constraint, the FK-is-authoritative rule, and the 409. |

---

### Task 1: One-off data cleanup — dedupe + backfill

**Files:**
- Create: `database/data_migrations/dedupe_conditions_and_backfill_ids_018.py`
- Test: `tests/data_migrations/test_dedupe_conditions_018.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `find_duplicate_groups(db) -> list[DuplicateGroup]`, `find_stale_strings(db) -> list[StaleString]`, `dedupe(db, groups) -> tuple[list[int], list[str]]` (deleted conditions ids, refusal messages), `backfill_strings(db) -> int` (rows updated). `DuplicateGroup` is a dataclass with fields `experiment_fk: int`, `experiment_id: str`, `keep_id: int`, `delete_ids: list[int]`, `blocked_reason: str | None`. `StaleString` is a dataclass with `conditions_id: int`, `current: str`, `correct: str`.

- [ ] **Step 1: Write the failing test**

Create `tests/data_migrations/test_dedupe_conditions_018.py`. Follow `tests/data_migrations/test_swap_reactor_4_7_015.py` for style.

**Use the `migration_session` fixture, not `db_session`.** `tests/data_migrations/conftest.py` re-exports only `create_test_tables` from `tests/api/conftest.py`, so `db_session` is not available in this package; `migration_session` wraps each test in a savepoint so an internal `db.commit()` cannot escape the outer rollback.

```python
"""Pins the 018 cleanup: which duplicate row survives, when the script refuses,
and that the backfill rewrites a stale string from its FK."""
from sqlalchemy import select

from database.data_migrations.dedupe_conditions_and_backfill_ids_018 import (
    backfill_strings,
    dedupe,
    find_duplicate_groups,
    find_stale_strings,
)
from database.models.chemicals import ChemicalAdditive, Compound
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus
from database.models.experiments import Experiment


def _exp(db, eid, num):
    exp = Experiment(experiment_id=eid, experiment_number=num, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _cond(db, exp, string, **kw):
    cond = ExperimentalConditions(experiment_fk=exp.id, experiment_id=string, **kw)
    db.add(cond)
    db.flush()
    return cond


def test_keeps_the_row_whose_string_matches_the_experiment(migration_session):
    """The survivor is chosen by correctness of the string, not by age."""
    exp = _exp(migration_session, "DEDUP_001", 61001)
    stale = _cond(migration_session, exp, "DEDUP_OLD_NAME", temperature_c=90.0)
    correct = _cond(migration_session, exp, "DEDUP_001", temperature_c=90.0)

    groups = [g for g in find_duplicate_groups(migration_session) if g.experiment_fk == exp.id]
    assert len(groups) == 1
    assert groups[0].keep_id == correct.id
    assert groups[0].delete_ids == [stale.id]
    assert groups[0].blocked_reason is None

    deleted, refusals = dedupe(migration_session, groups)
    assert deleted == [stale.id]
    assert refusals == []
    remaining = migration_session.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
    ).scalars().all()
    assert [c.id for c in remaining] == [correct.id]


def test_keeps_lowest_id_when_neither_string_is_correct(migration_session):
    exp = _exp(migration_session, "DEDUP_002", 61002)
    first = _cond(migration_session, exp, "WRONG_A", temperature_c=80.0)
    second = _cond(migration_session, exp, "WRONG_B", temperature_c=80.0)

    group = next(g for g in find_duplicate_groups(migration_session) if g.experiment_fk == exp.id)
    assert group.keep_id == min(first.id, second.id)


def test_refuses_when_measurement_values_differ(migration_session):
    """Not equivalent means a human decides — the script must not pick for them."""
    exp = _exp(migration_session, "DEDUP_003", 61003)
    _cond(migration_session, exp, "DEDUP_003", temperature_c=90.0)
    _cond(migration_session, exp, "DEDUP_OTHER", temperature_c=120.0)

    group = next(g for g in find_duplicate_groups(migration_session) if g.experiment_fk == exp.id)
    assert group.blocked_reason is not None
    assert "temperature_c" in group.blocked_reason

    deleted, refusals = dedupe(migration_session, [group])
    assert deleted == []
    assert len(refusals) == 1
    survivors = migration_session.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
    ).scalars().all()
    assert len(survivors) == 2


def test_refuses_when_the_doomed_row_holds_an_additive_the_survivor_lacks(migration_session):
    """ChemicalAdditive.experiment_id is an integer FK to experimental_conditions.id,
    so deleting a row destroys its additives via delete-orphan."""
    compound = Compound(name="Dedup Test Magnetite", molecular_weight_g_mol=231.5)
    migration_session.add(compound)
    migration_session.flush()

    exp = _exp(migration_session, "DEDUP_004", 61004)
    _cond(migration_session, exp, "DEDUP_004", temperature_c=90.0)
    doomed = _cond(migration_session, exp, "DEDUP_OLD", temperature_c=90.0)
    migration_session.add(ChemicalAdditive(
        experiment_id=doomed.id, compound_id=compound.id, amount=1.0, unit="g"
    ))
    migration_session.flush()

    group = next(g for g in find_duplicate_groups(migration_session) if g.experiment_fk == exp.id)
    assert group.blocked_reason is not None
    assert "additive" in group.blocked_reason.lower()


def test_allows_deletion_when_both_rows_carry_the_same_additive(migration_session):
    """The real production case: 'Add Details' re-entered an identical additive."""
    compound = Compound(name="Dedup Test Brucite", molecular_weight_g_mol=58.3)
    migration_session.add(compound)
    migration_session.flush()

    exp = _exp(migration_session, "DEDUP_005", 61005)
    keep = _cond(migration_session, exp, "DEDUP_005", temperature_c=90.0)
    doomed = _cond(migration_session, exp, "DEDUP_OLD_5", temperature_c=90.0)
    for cond_id in (keep.id, doomed.id):
        migration_session.add(ChemicalAdditive(
            experiment_id=cond_id, compound_id=compound.id, amount=0.149, unit="g"
        ))
    migration_session.flush()

    group = next(g for g in find_duplicate_groups(migration_session) if g.experiment_fk == exp.id)
    assert group.blocked_reason is None
    deleted, refusals = dedupe(migration_session, [group])
    assert deleted == [doomed.id]
    assert refusals == []


def test_backfill_rewrites_a_stale_string_from_its_fk(migration_session):
    exp = _exp(migration_session, "STALE_001", 61010)
    cond = _cond(migration_session, exp, "STALE_OLD_NAME", temperature_c=70.0)

    stale = [s for s in find_stale_strings(migration_session) if s.conditions_id == cond.id]
    assert len(stale) == 1
    assert stale[0].current == "STALE_OLD_NAME"
    assert stale[0].correct == "STALE_001"

    assert backfill_strings(migration_session) >= 1
    migration_session.refresh(cond)
    assert cond.experiment_id == "STALE_001"


def test_backfill_leaves_a_correct_string_alone(migration_session):
    exp = _exp(migration_session, "STALE_002", 61011)
    cond = _cond(migration_session, exp, "STALE_002", temperature_c=70.0)
    assert [s for s in find_stale_strings(migration_session) if s.conditions_id == cond.id] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest tests/data_migrations/test_dedupe_conditions_018.py -v`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'database.data_migrations.dedupe_conditions_and_backfill_ids_018'`

- [ ] **Step 3: Write the migration script**

Create `database/data_migrations/dedupe_conditions_and_backfill_ids_018.py`.

```python
"""One-time cleanup: collapse duplicate experimental_conditions rows, then
backfill every stale denormalized experiment_id string from its experiment_fk.

Background
----------
experimental_conditions carries two identities: experiment_fk (authoritative,
non-null FK) and a denormalized experiment_id string that no rename path
updates. As of the 2026-08-05 production dump, 187 of 1013 rows (18%) carry a
string that is not their experiment's ID -- almost all of it rename debris from
the replicate/-t<days> ID migration (e.g. cond 901 still says
'SERUM_cation_031' for the experiment now called 'SERUM_Cation_011a-t5').

That mismatch is what produced the duplicate. GET /api/conditions/by-experiment
resolved conditions by the STRING, so it 404'd for 175 experiments that do have
a conditions row; the detail page then offered "Add Details", and POST
/api/conditions inserted a second row with no existence check. Exactly one
experiment reached that state: SERUM_Cation_011a-t5, cond 901 + cond 1062,
value-identical, each with its own copy of the same Mg(OH)2 0.149 g additive.

Downstream, a duplicate 500s the experiments list (_build_list_item), fans out
the list join, duplicates the Power BI dimension key in v_experiments, and
blocks deletion (serialize_experiment_snapshot).

Order matters
-------------
Dedupe runs BEFORE backfill. Backfilling first would set both rows of a
duplicate pair to the same string, and the 6 strings that already appear on two
rows would multiply. --apply runs both in that order.

Selection is by rule, not by hardcoded id
-----------------------------------------
Survivor: the row whose experiment_id already equals its experiment's real ID;
if none (or several) qualify, the lowest id. A duplicate is deleted only when it
is EQUIVALENT to the survivor -- every measurement column equal, and no additive
that the survivor does not also have (ChemicalAdditive.experiment_id is an
integer FK to experimental_conditions.id, and the relationship is
delete-orphan, so deleting a row destroys its additives). Anything else is
reported and left alone for a human.

reactor_slot is NOT affected
----------------------------
Per MODELS.md's bulk-update caveat, a Core/bulk UPDATE does not fire the
set_reactor_slot mapper listener. This script's backfill touches only
experiment_id, and reactor_slot derives from (reactor_number, experiment_type),
so no recompute is needed. The dedupe path deletes through the ORM.

See docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md

Usage:
    # Dry run (preview only, no writes)
    python database/data_migrations/dedupe_conditions_and_backfill_ids_018.py

    # Apply
    python database/data_migrations/dedupe_conditions_and_backfill_ids_018.py --apply
"""
import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from database import get_db  # noqa: E402
from database.models.chemicals import ChemicalAdditive  # noqa: E402
from database.models.conditions import ExperimentalConditions  # noqa: E402
from database.models.experiments import Experiment  # noqa: E402

# Identity, audit and derived columns are never compared -- they are expected to
# differ between a row created with the experiment and one added later.
_IGNORED_COLUMNS = {
    "id", "experiment_id", "experiment_fk", "created_at", "updated_at",
    "water_to_rock_ratio", "total_ferrous_iron_g", "catalyst_percentage",
    "catalyst_ppm", "reactor_slot",
}


@dataclass
class DuplicateGroup:
    experiment_fk: int
    experiment_id: str
    keep_id: int
    delete_ids: list[int] = field(default_factory=list)
    blocked_reason: str | None = None


@dataclass
class StaleString:
    conditions_id: int
    current: str
    correct: str


def _comparable_columns() -> list[str]:
    return [c.name for c in ExperimentalConditions.__table__.columns
            if c.name not in _IGNORED_COLUMNS]


def _additive_key(additive: ChemicalAdditive) -> tuple:
    return (additive.compound_id, additive.amount, additive.unit)


def _additive_keys(db: Session, conditions_id: int) -> list[tuple]:
    rows = db.execute(
        select(ChemicalAdditive).where(ChemicalAdditive.experiment_id == conditions_id)
    ).scalars().all()
    return sorted(_additive_key(a) for a in rows)


def find_duplicate_groups(db: Session) -> list[DuplicateGroup]:
    """One entry per experiment holding more than one conditions row."""
    fks = db.execute(text("""
        SELECT experiment_fk FROM experimental_conditions
        GROUP BY experiment_fk HAVING COUNT(*) > 1 ORDER BY experiment_fk
    """)).scalars().all()

    groups: list[DuplicateGroup] = []
    for fk in fks:
        exp = db.get(Experiment, fk)
        real_id = exp.experiment_id if exp else ""
        rows = db.execute(
            select(ExperimentalConditions)
            .where(ExperimentalConditions.experiment_fk == fk)
            .order_by(ExperimentalConditions.id)
        ).scalars().all()

        correct = [r for r in rows if r.experiment_id == real_id]
        keep = correct[0] if len(correct) == 1 else rows[0]
        doomed = [r for r in rows if r.id != keep.id]

        reasons: list[str] = []
        keep_additives = _additive_keys(db, keep.id)
        for row in doomed:
            for column in _comparable_columns():
                if getattr(row, column) != getattr(keep, column):
                    reasons.append(
                        f"cond {row.id} differs from survivor {keep.id} on "
                        f"{column} ({getattr(row, column)!r} vs "
                        f"{getattr(keep, column)!r})"
                    )
            for key in _additive_keys(db, row.id):
                if key not in keep_additives:
                    reasons.append(
                        f"cond {row.id} holds an additive the survivor {keep.id} "
                        f"does not: compound_id={key[0]} amount={key[1]} unit={key[2]}"
                    )

        groups.append(DuplicateGroup(
            experiment_fk=fk,
            experiment_id=real_id,
            keep_id=keep.id,
            delete_ids=[r.id for r in doomed],
            blocked_reason="; ".join(reasons) or None,
        ))
    return groups


def find_stale_strings(db: Session) -> list[StaleString]:
    """Conditions rows whose denormalized string is not their FK's real ID."""
    rows = db.execute(text("""
        SELECT ec.id, ec.experiment_id AS current, e.experiment_id AS correct
        FROM experimental_conditions ec
        JOIN experiments e ON e.id = ec.experiment_fk
        WHERE ec.experiment_id IS DISTINCT FROM e.experiment_id
        ORDER BY ec.id
    """)).mappings().all()
    return [StaleString(r["id"], r["current"], r["correct"]) for r in rows]


def dedupe(db: Session, groups: list[DuplicateGroup]) -> tuple[list[int], list[str]]:
    """Delete equivalent duplicates through the ORM. Flushes; does not commit."""
    deleted: list[int] = []
    refusals: list[str] = []
    for group in groups:
        if group.blocked_reason:
            refusals.append(
                f"{group.experiment_id} (experiment_fk={group.experiment_fk}): "
                f"{group.blocked_reason}"
            )
            continue
        for cond_id in group.delete_ids:
            row = db.get(ExperimentalConditions, cond_id)
            if row is not None:
                db.delete(row)  # delete-orphan removes its additives
                deleted.append(cond_id)
    db.flush()
    return deleted, refusals


def backfill_strings(db: Session) -> int:
    """Set every conditions.experiment_id to its FK's real ID. Flushes."""
    result = db.execute(text("""
        UPDATE experimental_conditions AS ec
        SET experiment_id = e.experiment_id
        FROM experiments AS e
        WHERE e.id = ec.experiment_fk
          AND ec.experiment_id IS DISTINCT FROM e.experiment_id
    """))
    db.flush()
    return result.rowcount or 0


def main(apply: bool) -> None:
    db = next(get_db())
    try:
        groups = find_duplicate_groups(db)
        stale = find_stale_strings(db)

        print(f"Experiments with duplicate conditions rows: {len(groups)}")
        for group in groups:
            verdict = "BLOCKED" if group.blocked_reason else "deletable"
            print(f"  {group.experiment_id} (experiment_fk={group.experiment_fk}): "
                  f"keep {group.keep_id}, delete {group.delete_ids} [{verdict}]")
            if group.blocked_reason:
                print(f"      {group.blocked_reason}")

        print(f"\nConditions rows with a stale experiment_id string: {len(stale)}")
        for row in stale[:20]:
            print(f"  cond {row.conditions_id}: {row.current!r} -> {row.correct!r}")
        if len(stale) > 20:
            print(f"  ... and {len(stale) - 20} more")

        if not apply:
            print("\nDry run -- pass --apply to commit changes.")
            return

        deleted, refusals = dedupe(db, groups)
        updated = backfill_strings(db)
        db.commit()

        print(f"\nDeleted {len(deleted)} duplicate conditions row(s): {deleted}")
        print(f"Backfilled {updated} experiment_id string(s).")
        if refusals:
            print(f"\nREFUSED {len(refusals)} group(s) -- resolve by hand:")
            for line in refusals:
                print(f"  {line}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit the changes")
    main(parser.parse_args().apply)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/data_migrations/test_dedupe_conditions_018.py -v`
Expected: 7 passed.

If `test_allows_deletion_when_both_rows_carry_the_same_additive` fails on the `unit` value, check `database/models/enums.py::AmountUnit` — pass the enum member the model expects rather than the string `"g"`, matching how `tests/api/test_additives.py` seeds additives.

- [ ] **Step 5: Dry-run against the dev database and read the output**

Run: `.venv/Scripts/python database/data_migrations/dedupe_conditions_and_backfill_ids_018.py`

The dev DB currently holds the **2026-08-01** restore, which predates the duplicate — expect `0` duplicate groups and ~187 stale strings. That is the correct result, not a failure. Do **not** pass `--apply` to dev yet; the deploy sequence in Task 6 covers it.

- [ ] **Step 6: Commit**

```bash
git add database/data_migrations/dedupe_conditions_and_backfill_ids_018.py tests/data_migrations/test_dedupe_conditions_018.py
git commit -m "$(cat <<'EOF'
[#109] Add conditions dedupe and experiment_id backfill

- Rule-based: survivor is the row whose string matches its experiment
- Refuses any group that is not value- and additive-equivalent
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Resolve conditions by `experiment_fk`, not by the string

**Files:**
- Modify: `backend/api/routers/conditions.py:41-53`
- Test: `tests/api/test_conditions.py`

**Interfaces:**
- Consumes: nothing from Task 1 (the endpoint fix stands alone and is what stops new duplicates being *invited*).
- Produces: `GET /api/conditions/by-experiment/{experiment_id}` resolving via `Experiment.experiment_id` → `ExperimentalConditions.experiment_fk`, returning the lowest-id row when several exist and 404 when the experiment or its conditions do not exist. Response shape is unchanged (`ConditionsResponse`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_conditions.py`. Add a cleanup fixture for the new prefixes by extending the existing `_cleanup_slot_rows` `like()` filters to also match `"BYFK_%"`, or add a second autouse fixture with the same shape.

```python
# --- by-experiment resolves through experiment_fk, not the denormalized string ---


def test_by_experiment_finds_conditions_whose_string_is_stale(client, db_session):
    """The real production bug: a rename left the conditions string pointing at
    the old ID, so a string-keyed lookup 404'd on a row that exists -- which is
    what made the UI offer 'Add Details' and create a duplicate."""
    from database.models.conditions import ExperimentalConditions

    exp = _make_experiment(db_session, "BYFK_001", 62001)
    db_session.add(ExperimentalConditions(
        experiment_fk=exp.id, experiment_id="BYFK_OLD_NAME", temperature_c=90.0
    ))
    db_session.commit()

    resp = client.get("/api/conditions/by-experiment/BYFK_001")
    assert resp.status_code == 200
    assert resp.json()["temperature_c"] == 90.0


def test_by_experiment_ignores_another_experiments_stale_string(client, db_session):
    """A stale string naming THIS experiment must not hand back another
    experiment's conditions."""
    from database.models.conditions import ExperimentalConditions

    target = _make_experiment(db_session, "BYFK_002", 62002)
    other = _make_experiment(db_session, "BYFK_003", 62003)
    db_session.add(ExperimentalConditions(
        experiment_fk=other.id, experiment_id="BYFK_002", temperature_c=180.0
    ))
    db_session.add(ExperimentalConditions(
        experiment_fk=target.id, experiment_id="BYFK_002", temperature_c=60.0
    ))
    db_session.commit()

    resp = client.get("/api/conditions/by-experiment/BYFK_002")
    assert resp.status_code == 200
    assert resp.json()["temperature_c"] == 60.0
    assert resp.json()["experiment_fk"] == target.id


def test_by_experiment_404s_for_an_experiment_with_no_conditions(client, db_session):
    _make_experiment(db_session, "BYFK_004", 62004)
    assert client.get("/api/conditions/by-experiment/BYFK_004").status_code == 404


def test_by_experiment_404s_for_an_unknown_experiment(client):
    assert client.get("/api/conditions/by-experiment/BYFK_NOPE").status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest tests/api/test_conditions.py -k by_experiment -v`
Expected: `test_by_experiment_finds_conditions_whose_string_is_stale` FAILS with 404 != 200; `test_by_experiment_ignores_another_experiments_stale_string` FAILS with a 500 (`MultipleResultsFound`) — that 500 is the current production behavior for the 6 duplicated strings.

- [ ] **Step 3: Rewrite the resolver**

In `backend/api/routers/conditions.py`, add `Experiment` to the imports:

```python
from database.models.experiments import Experiment
```

Replace the body of `get_conditions_by_experiment` (lines 47-53):

```python
    """Return conditions for a given experiment_id string. 404 if none exist.

    Resolved through experiment_fk, never through the denormalized
    ExperimentalConditions.experiment_id string: that string is not kept in sync
    by the rename paths (187 of 1013 rows were stale as of 2026-08-05), so a
    string-keyed lookup both missed rows that exist and matched rows belonging
    to another experiment. A 404 here is what made the detail page offer "Add
    Details" and create a duplicate conditions row -- see
    docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md

    .first() rather than .scalar_one_or_none(): UNIQUE (experiment_fk) makes a
    second row impossible going forward, but this endpoint must not 500 on a
    database that predates the constraint.
    """
    cond = db.execute(
        select(ExperimentalConditions)
        .join(Experiment, Experiment.id == ExperimentalConditions.experiment_fk)
        .where(Experiment.experiment_id == experiment_id)
        .order_by(ExperimentalConditions.id)
    ).scalars().first()
    if cond is None:
        raise HTTPException(status_code=404, detail="Conditions not found for this experiment")
    return ConditionsResponse.model_validate(cond)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/api/test_conditions.py -v`
Expected: all pass, including the 12 pre-existing tests in the file.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/conditions.py tests/api/test_conditions.py
git commit -m "$(cat <<'EOF'
[#109] Resolve conditions by experiment_fk not the ID string

- by-experiment joined through Experiment; tolerates a pre-constraint duplicate
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `POST /api/conditions` refuses a second row

**Files:**
- Modify: `backend/api/routers/conditions.py:56-71`
- Test: `tests/api/test_conditions.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `POST /api/conditions` returns **409** with `detail` naming the existing row's id when `payload.experiment_fk` already has a conditions row. 201 behavior for the first row is unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_conditions.py`:

```python
def test_post_conditions_rejects_a_second_row_for_the_same_experiment(client, db_session):
    """The duplicate's actual entry point: POST had no existence check, so a
    stale-string 404 on the detail page let 'Add Details' insert a second row."""
    exp = _make_experiment(db_session, "BYFK_005", 62005)
    first = client.post("/api/conditions", json={
        "experiment_fk": exp.id, "experiment_id": exp.experiment_id, "temperature_c": 90.0,
    })
    assert first.status_code == 201

    second = client.post("/api/conditions", json={
        "experiment_fk": exp.id, "experiment_id": exp.experiment_id, "temperature_c": 90.0,
    })
    assert second.status_code == 409
    assert str(first.json()["id"]) in second.json()["detail"]


def test_post_conditions_409_does_not_insert(client, db_session):
    from database.models.conditions import ExperimentalConditions

    exp = _make_experiment(db_session, "BYFK_006", 62006)
    client.post("/api/conditions", json={
        "experiment_fk": exp.id, "experiment_id": exp.experiment_id,
    })
    client.post("/api/conditions", json={
        "experiment_fk": exp.id, "experiment_id": exp.experiment_id,
    })
    rows = db_session.query(ExperimentalConditions).filter(
        ExperimentalConditions.experiment_fk == exp.id
    ).all()
    assert len(rows) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest tests/api/test_conditions.py -k "rejects_a_second_row or 409_does_not_insert" -v`
Expected: FAIL — the second POST currently returns 201 and two rows exist.

- [ ] **Step 3: Add the guard**

In `create_conditions`, insert immediately after the `_validate_reactor_number` call:

```python
    existing = db.execute(
        select(ExperimentalConditions.id)
        .where(ExperimentalConditions.experiment_fk == payload.experiment_fk)
        .order_by(ExperimentalConditions.id)
    ).scalars().first()
    if existing is not None:
        # ExperimentalConditions is 1:1 with Experiment. Before this check, a
        # stale-string 404 from by-experiment made the detail page render its
        # "no conditions" empty state for an experiment that had them, and
        # "Add Details" inserted a second row (issue #109 follow-up).
        raise HTTPException(
            status_code=409,
            detail=(
                f"Conditions already exist for this experiment (id={existing}). "
                "Reload the page and edit them instead of adding new details."
            ),
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/api/test_conditions.py -v`
Expected: all pass. `test_get_conditions` and the reactor-validation tests each POST once per fresh experiment, so none of them trip the new 409.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/conditions.py tests/api/test_conditions.py
git commit -m "$(cat <<'EOF'
[#109] Reject a second conditions row with 409

- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Defensive reads — a duplicate must degrade, not 500

**Files:**
- Modify: `backend/api/routers/experiments.py:69-95` and the comment at `:129-137`
- Modify: `backend/services/experiment_deletion.py:226-228`
- Test: `tests/services/test_experiment_deletion.py`, `tests/services/bulk_uploads/test_experiment_deletion_bulk.py`, `tests/api/test_experiments.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `_build_list_item` and `serialize_experiment_snapshot` both select the lowest-id conditions row via `.scalars().first()` instead of `.scalar_one_or_none()`. Signatures unchanged.

- [ ] **Step 1: Write the failing tests**

In `tests/services/test_experiment_deletion.py`, follow the seeding style at `:52`:

```python
def test_delete_succeeds_with_two_conditions_rows(db):
    """Regression (issue #109): serialize_experiment_snapshot used
    scalar_one_or_none on conditions, so a duplicate row raised
    MultipleResultsFound inside delete_experiment_cascade -- which is why the
    bulk-delete tool reported the row as failed and could not remove it."""
    exp = _make_experiment(db, "DUPCOND_001", 63001)
    db.add(ExperimentalConditions(experiment_fk=exp.id, experiment_id="DUPCOND_001",
                                  temperature_c=90.0))
    db.add(ExperimentalConditions(experiment_fk=exp.id, experiment_id="DUPCOND_OLD",
                                  temperature_c=90.0))
    db.commit()

    impact = delete_experiment_cascade(db, exp, modified_by="tester")

    assert impact.conditions == 2
    assert db.execute(
        select(Experiment).where(Experiment.experiment_id == "DUPCOND_001")
    ).scalar_one_or_none() is None
    assert db.execute(
        select(func.count()).select_from(ExperimentalConditions)
        .where(ExperimentalConditions.experiment_fk == exp.id)
    ).scalar_one() == 0
```

Reuse whatever `_make_experiment` helper and imports that file already defines; add `ExperimentalConditions`, `func` and `select` to its imports only if absent.

In `tests/services/bulk_uploads/test_experiment_deletion_bulk.py`, mirror the seeding used by its existing tests:

```python
def test_duplicate_conditions_row_does_not_block_bulk_delete(db_session):
    """The user-visible symptom: the ID came back in `failed` with 'Multiple rows
    were found when one or none was required' and was undeletable."""
    exp = _seed_experiment(db_session, "BULKDUP_001", 63010)
    for string in ("BULKDUP_001", "BULKDUP_STALE"):
        db_session.add(ExperimentalConditions(
            experiment_fk=exp.id, experiment_id=string, temperature_c=90.0
        ))
    db_session.commit()

    result = delete_experiments_from_file(
        db_session, _xlsx_bytes(["BULKDUP_001"]), "delete.xlsx", modified_by="tester"
    )

    assert result.deleted == ["BULKDUP_001"]
    assert result.failed == []
    assert result.missing == []
```

Use that file's existing helpers for seeding and for building the upload bytes — do not invent new ones. If it has no `_xlsx_bytes`-style helper, build the frame the same way its other tests do.

In `tests/api/test_experiments.py`:

```python
def test_list_experiments_survives_duplicate_conditions(client, db_session):
    """_build_list_item used scalar_one_or_none on conditions, so one duplicate
    row 500'd the whole experiments page (issue #109)."""
    from database.models.conditions import ExperimentalConditions

    exp = _make_experiment(db_session, "LISTDUP_001", 63020)
    for string in ("LISTDUP_001", "LISTDUP_STALE"):
        db_session.add(ExperimentalConditions(
            experiment_fk=exp.id, experiment_id=string, experiment_type="Serum"
        ))
    db_session.commit()

    resp = client.get("/api/experiments", params={"search": "LISTDUP_001"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["experiment_id"] for i in items] == ["LISTDUP_001"]
    assert resp.json()["total"] == 1
```

Match that file's own experiment-seeding helper name and its response-shape keys (`items` / `total`) — read a neighbouring list test first and copy its assertions' shape.

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```
.venv/Scripts/pytest tests/services/test_experiment_deletion.py -k two_conditions_rows tests/services/bulk_uploads/test_experiment_deletion_bulk.py -k duplicate_conditions tests/api/test_experiments.py -k survives_duplicate -v
```
Expected: all three FAIL with `MultipleResultsFound` (surfacing as a 500 for the API test, and as a `failed` entry for the bulk test).

- [ ] **Step 3: Make both readers tolerant**

In `backend/api/routers/experiments.py`, replace lines 72-74:

```python
    # .first() with an explicit order, not scalar_one_or_none(): UNIQUE
    # (experiment_fk) forbids a second row going forward, but one duplicate on a
    # pre-constraint database used to 500 this entire endpoint (issue #109).
    cond = db.execute(
        select(ExperimentalConditions)
        .where(ExperimentalConditions.experiment_fk == exp.id)
        .order_by(ExperimentalConditions.id)
    ).scalars().first()
```

Then correct the now-load-bearing claim in the comment at `:129-137` — replace the sentence "Both joins are at most 1 row per experiment (ExperimentalConditions is 1:1; note_sq is keyed by min note id), so this cannot fan out rows or inflate `total`." with:

```python
    # Both joins are at most 1 row per experiment, so this cannot fan out rows or
    # inflate `total`: note_sq is keyed by min note id, and ExperimentalConditions
    # is 1:1 with Experiment -- enforced by UNIQUE (experiment_fk) since
    # migration <rev> (issue #109). Before that constraint the 1:1 was assumed
    # here and nowhere enforced, and a single duplicate row did fan out.
```

Substitute the real revision id from Task 5 once it exists; if Task 5 has not run yet, write `since the uq_conditions_experiment_fk constraint` and leave the id out.

In `backend/services/experiment_deletion.py`, replace lines 226-228:

```python
    # .first(), not scalar_one_or_none(): a duplicate conditions row used to
    # raise MultipleResultsFound here, inside delete_experiment_cascade, which
    # made the experiment undeletable through both the single-delete endpoint
    # and the bulk uploader (issue #109). impact.conditions still counts every
    # row; only the snapshot narrows to one.
    conditions = db.execute(
        select(ExperimentalConditions)
        .where(ExperimentalConditions.experiment_fk == exp.id)
        .order_by(ExperimentalConditions.id)
    ).scalars().first()
```

Leave `collect_delete_impact` alone — it already counts with `len(condition_ids)`, so `impact.conditions` correctly reports 2.

- [ ] **Step 4: Run the tests to verify they pass**

Run the same command as Step 2. Expected: 3 passed.

Then run the affected suites whole, to catch a changed row count or a leaked row:
```
.venv/Scripts/pytest tests/services/test_experiment_deletion.py tests/services/bulk_uploads/test_experiment_deletion_bulk.py tests/api/test_experiments.py -q
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/experiments.py backend/services/experiment_deletion.py tests/services/test_experiment_deletion.py tests/services/bulk_uploads/test_experiment_deletion_bulk.py tests/api/test_experiments.py
git commit -m "$(cat <<'EOF'
[#109] Stop a duplicate conditions row 500ing list and delete

- _build_list_item and serialize_experiment_snapshot select the lowest-id row
- Corrected the list join's unenforced 1:1 claim
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `UNIQUE (experiment_fk)` on `experimental_conditions`

**Files:**
- Modify: `database/models/conditions.py` (locked — authorized, see Global Constraints)
- Create: `alembic/versions/<rev>_unique_conditions_per_experiment.py`
- Test: `tests/models/test_conditions_unique_experiment_fk.py`

**Interfaces:**
- Consumes: Task 1's script must have been run with `--apply` on any database that has duplicates, or this migration fails by design.
- Produces: constraint named `uq_conditions_experiment_fk` on `experimental_conditions(experiment_fk)`.

- [ ] **Step 1: Write the failing test**

Create `tests/models/test_conditions_unique_experiment_fk.py`, following `tests/models/test_is_outlier_column.py` for the engine fixture:

```python
"""ExperimentalConditions is 1:1 with Experiment. Before issue #109 that was
assumed by the list endpoint, the delete snapshot and the Power BI views, and
enforced nowhere -- one duplicate row 500'd the experiments page, duplicated the
v_experiments dimension key and blocked deletion."""
import pytest
from sqlalchemy.exc import IntegrityError

from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus
from database.models.experiments import Experiment


def test_second_conditions_row_for_one_experiment_is_rejected(db_session):
    exp = Experiment(experiment_id="UQCOND_001", experiment_number=64001,
                     status=ExperimentStatus.ONGOING)
    db_session.add(exp)
    db_session.flush()

    db_session.add(ExperimentalConditions(experiment_fk=exp.id,
                                          experiment_id="UQCOND_001"))
    db_session.flush()

    db_session.add(ExperimentalConditions(experiment_fk=exp.id,
                                          experiment_id="UQCOND_001"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_constraint_is_declared_on_the_model():
    names = {
        c.name for c in ExperimentalConditions.__table__.constraints if c.name
    }
    assert "uq_conditions_experiment_fk" in names
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/pytest tests/models/test_conditions_unique_experiment_fk.py -v`
Expected: both FAIL — no `IntegrityError` is raised, and the constraint name is absent.

- [ ] **Step 3: Add the constraint to the model**

In `database/models/conditions.py`, extend the import on line 1 with `UniqueConstraint`, then insert directly below `__tablename__`:

```python
    # ExperimentalConditions is 1:1 with Experiment, and experiment_fk is the
    # only authoritative link. The experiment_id String below is a denormalized
    # convenience copy that the rename paths do not keep in sync (187 of 1013
    # production rows were stale as of 2026-08-05) -- never resolve a conditions
    # row by it. See issue #109 follow-up:
    # docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md
    __table_args__ = (
        UniqueConstraint("experiment_fk", name="uq_conditions_experiment_fk"),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

`experiments_test` is built by `Base.metadata.create_all`, so the constraint appears without a migration.

Run: `.venv/Scripts/pytest tests/models/test_conditions_unique_experiment_fk.py -v`
Expected: 2 passed.

If the first test passes but leaves the session unusable for later files, confirm the `db_session` fixture rolls back — `tests/models/conftest.py` owns that.

- [ ] **Step 5: Write the Alembic migration**

Create `alembic/versions/<rev>_unique_conditions_per_experiment.py`. Generate the revision id with `.venv/Scripts/alembic revision -m "unique conditions per experiment"` and then replace the generated body — do **not** use `--autogenerate` here, because it would also try to emit unrelated drift.

```python
"""unique conditions per experiment

Revision ID: <rev>
Revises: 1c1ef9b555e0
Create Date: <generated>

ExperimentalConditions is 1:1 with Experiment. That was assumed by the
experiments list endpoint, the delete snapshot and the v_experiments /
v_experiment_conditions Power BI views, and enforced nowhere -- so one duplicate
row 500'd the experiments page, duplicated the Power BI dimension key and made
the experiment undeletable (issue #109 follow-up).

This migration FAILS LOUDLY if duplicates remain, rather than skipping: run
database/data_migrations/dedupe_conditions_and_backfill_ids_018.py --apply
first. The lab PC came up through this chain, so it is the path that matters.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '<rev>'
down_revision: Union[str, None] = '1c1ef9b555e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    duplicates = conn.execute(sa.text("""
        SELECT experiment_fk, COUNT(*) AS n
        FROM experimental_conditions
        GROUP BY experiment_fk HAVING COUNT(*) > 1
        ORDER BY experiment_fk
    """)).all()
    if duplicates:
        listed = ", ".join(f"experiment_fk={fk} ({n} rows)" for fk, n in duplicates)
        raise RuntimeError(
            "Cannot add uq_conditions_experiment_fk: duplicate conditions rows "
            f"still present -- {listed}. Run "
            "database/data_migrations/dedupe_conditions_and_backfill_ids_018.py "
            "--apply first."
        )
    op.create_unique_constraint(
        'uq_conditions_experiment_fk', 'experimental_conditions', ['experiment_fk']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'uq_conditions_experiment_fk', 'experimental_conditions', type_='unique'
    )
```

- [ ] **Step 6: Apply, verify, and test the downgrade against dev**

The dev DB holds the 2026-08-01 restore and has **no** duplicates, so the pre-flight passes. Run:

```bash
.venv/Scripts/alembic upgrade head
.venv/Scripts/alembic downgrade -1
.venv/Scripts/alembic upgrade head
```
Expected: all three succeed with no error.

Confirm the constraint landed:
```bash
psql -h localhost -U experiments_user -d experiments -c "\d experimental_conditions" | findstr uq_conditions
```
Expected: one line naming `uq_conditions_experiment_fk`.

- [ ] **Step 7: Run the full backend suite**

Run: `.venv/Scripts/pytest -q`
Expected: the same pass count as `develop` plus the new tests, with only the 3 documented `tests/test_pg_backup_restore.py` failures. If any other test now fails with `IntegrityError` on `uq_conditions_experiment_fk`, a fixture seeds two conditions rows for one experiment — fix the fixture, not the constraint, and report which one.

- [ ] **Step 8: Commit**

```bash
git add database/models/conditions.py alembic/versions/ tests/models/test_conditions_unique_experiment_fk.py
git commit -m "$(cat <<'EOF'
[#109] Enforce one conditions row per experiment

- UniqueConstraint on experiment_fk + migration with a duplicate pre-flight
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Documentation, issue record, and the production deploy sequence

**Files:**
- Create: `docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md`
- Modify: `.claude/rules/MODELS.md` (`ExperimentalConditions` section)
- Modify: `docs/api/API_REFERENCE.md` (conditions endpoints)
- Modify: `docs/working/issue-log.md`

**Interfaces:**
- Consumes: the revision id from Task 5 and the counts printed by Task 1's dry run.
- Produces: no code.

- [ ] **Step 1: Write the issue document**

Create `docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md` containing, verbatim from this plan's Background section: the failure chain, the measured production table, the four consumers that broke, and the resolution. Add a "Deploy to the lab PC" section with the exact sequence in Step 4 below. State plainly that `experiment_deletion_bulk.py:140` was **not** the fault, so the record does not mislead the next reader who greps for "one or none".

- [ ] **Step 2: Update `MODELS.md`**

In the `ExperimentalConditions` section, add — matching the density and tone of the neighbouring `reactor_slot` notes:

- `experiment_fk` is the **only** authoritative link to `Experiment`; `experiment_id` on this table is a denormalized copy the rename paths do not maintain (187 of 1013 rows stale as of 2026-08-05, backfilled by data migration 018). Never resolve a conditions row by it.
- `UNIQUE (experiment_fk)` (`uq_conditions_experiment_fk`, migration `<rev>`) enforces the 1:1 that `_build_list_item`, `serialize_experiment_snapshot`, `v_experiments` and `v_experiment_conditions` all assume. Before it, one duplicate row 500'd the experiments list, duplicated the Power BI dimension key and made the experiment undeletable.
- `POST /api/conditions` returns 409 when a row exists for that `experiment_fk`.
- The two readers above select the lowest-id row defensively, so a pre-constraint database degrades rather than 500ing.

Note the hook at `.claude/hooks/sync_docs_to_project_context.py` copies `docs/` writes to `docs/project_context/` automatically — never edit that copy by hand.

- [ ] **Step 3: Update `API_REFERENCE.md`**

For `GET /api/conditions/by-experiment/{experiment_id}`: state that resolution goes through `experiment_fk`, and that 404 means "this experiment has no conditions row" (an unknown experiment also 404s). For `POST /api/conditions`: document the 409 and its `detail` text.

- [ ] **Step 4: Record the production deploy sequence in the issue doc**

Order is load-bearing — the migration's pre-flight will refuse otherwise:

```bash
# On the lab PC, after pulling this branch's merge into main:
# 1. Preview. Expect 1 duplicate group (SERUM_Cation_011a-t5) and ~187 stale strings.
.venv/Scripts/python database/data_migrations/dedupe_conditions_and_backfill_ids_018.py

# 2. Apply the data cleanup.
.venv/Scripts/python database/data_migrations/dedupe_conditions_and_backfill_ids_018.py --apply

# 3. Only then add the constraint.
.venv/Scripts/alembic upgrade head

# 4. Refresh Power BI and confirm the v_experiments relationship loads.
```

Add: if step 1 reports any **BLOCKED** group, stop and escalate — the two rows are not equivalent and a human must choose which survives.

- [ ] **Step 5: Append the issue-log entry**

Add a `## 2026-08-05 | issue #109 follow-up — duplicate conditions rows` entry to `docs/working/issue-log.md` matching the existing entries' fields: Trigger, Files changed, Root cause, Shipped, Tests added, Verification, Scope notes, Decision logged, Docs updated. Record that the user's initial framing (two duplicate `experiments` rows) was not what the data showed, and that production's `UNIQUE` index on `experiments.experiment_id` rules that out.

- [ ] **Step 6: Commit**

```bash
git add docs/ .claude/rules/MODELS.md
git commit -m "$(cat <<'EOF'
[#109] Document conditions 1:1 enforcement and cleanup

- Tests added: no
- Docs updated: yes

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Out of scope — recorded, not fixed

Both were found during this investigation and are real. Neither is touched here.

1. **`_id_match.py::normalize_id` conflates 13 real experiment pairs.** It strips punctuation and leading zeros, so `SERUM_JW_010-2` and `SERUM_JW_102` both normalize to `serumjw102`; `fuzzy_find_experiment` returns `.first()` of whichever it finds, so a bulk upload can attach results to the wrong experiment silently. Full list of 13 pairs is in the issue doc. Fixing it touches locked `bulk_uploads` parsers and their suites — needs its own `/start-task`.
2. **`backend/services/experimental_conditions_service.py:39` creates a conditions row with no existence check.** It is reachable only from `legacy/streamlit_frontend/`, which the current app never imports, so the new constraint would surface it as an `IntegrityError` rather than a silent duplicate. Left alone as dead legacy code.
