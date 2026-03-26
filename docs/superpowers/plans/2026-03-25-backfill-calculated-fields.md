# Backfill All Calculated Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a one-shot data migration script that runs the M3 calculation registry over every existing `ExperimentalConditions`, `ChemicalAdditive`, and `ScalarResults` row, populating all derived fields for pre-existing data.

**Architecture:** A standalone script in `database/data_migrations/` follows the established pattern: `SessionLocal` from `database`, chunked commits, per-row error isolation. Core logic is split into injectable helper functions (`_backfill_conditions`, `_backfill_scalars`) so tests can pass a session directly rather than needing to mock `SessionLocal`. Processing order is conditions → scalars: `conditions_calcs.py` already internally propagates to all linked `ScalarResults` (lines 48–57), so the explicit scalar pass is a safety net for any scalars whose conditions relationship is null.

**Tech Stack:** Python, SQLAlchemy ORM, `backend.services.calculations` registry, pytest (SQLite in-memory via the `test_db` fixture from `tests/conftest.py`).

---

## Schema Note — Two Ferrous Iron Columns

`ExperimentalConditions` has two separate columns:

| Column | Written by | Read by |
|--------|-----------|---------|
| `total_ferrous_iron_g` | `conditions_calcs.py` (from rock elemental data via `ExternalAnalysis`) | nothing yet |
| `total_ferrous_iron` | manual entry / legacy | `scalar_calcs.py` line 86 (for ferrous iron yield %) |

The scalar calculator reads `total_ferrous_iron` (the old column). The conditions registry writes `total_ferrous_iron_g` (the new column). These are independent. The backfill will populate `total_ferrous_iron_g` from elemental characterization data, but `ferrous_iron_yield_h2_pct` and `ferrous_iron_yield_nh3_pct` on scalar rows will remain NULL if `total_ferrous_iron` was never set manually — that is expected behavior and not a bug in this migration.

---

## File Map

| Action | Path |
|--------|------|
| Create | `database/data_migrations/recalculate_all_registry_012.py` |
| Create | `tests/data_migrations/__init__.py` |
| Create | `tests/data_migrations/test_recalculate_all_registry_012.py` |

---

### Task 1: Conditions and Additive Backfill

**Files:**
- Create: `database/data_migrations/recalculate_all_registry_012.py`
- Create: `tests/data_migrations/__init__.py`
- Create: `tests/data_migrations/test_recalculate_all_registry_012.py`

- [ ] **Step 1: Create the test package directory**

```bash
# Create empty __init__.py so pytest can discover tests/data_migrations/
touch tests/data_migrations/__init__.py
```

- [ ] **Step 2: Write the failing test for conditions + additive backfill**

```python
# tests/data_migrations/test_recalculate_all_registry_012.py
import pytest
from sqlalchemy.orm import Session

import backend.services.calculations as _calcs  # noqa: F401 — registers all calculators
from database.data_migrations.recalculate_all_registry_012 import _backfill_conditions
from database.models import Experiment, ExperimentalConditions, Compound, ChemicalAdditive
from database.models.enums import AmountUnit


def test_backfill_conditions_computes_water_to_rock_ratio(test_db: Session):
    """_backfill_conditions should set water_to_rock_ratio on a pre-existing conditions row."""
    experiment = Experiment(experiment_id="BACKFILL_001", experiment_number=901)
    test_db.add(experiment)
    test_db.flush()

    conditions = ExperimentalConditions(
        experiment_id="BACKFILL_001",
        experiment_fk=experiment.id,
        rock_mass_g=100.0,
        water_volume_mL=500.0,
    )
    conditions.water_to_rock_ratio = None  # simulate pre-existing NULL
    test_db.add(conditions)
    test_db.commit()

    _backfill_conditions(test_db)

    test_db.refresh(conditions)
    assert conditions.water_to_rock_ratio == pytest.approx(5.0)


def test_backfill_conditions_computes_additive_mass(test_db: Session):
    """_backfill_conditions should trigger additive recalculation via the registry."""
    experiment = Experiment(experiment_id="BACKFILL_002", experiment_number=902)
    test_db.add(experiment)
    test_db.flush()

    conditions = ExperimentalConditions(
        experiment_id="BACKFILL_002",
        experiment_fk=experiment.id,
        rock_mass_g=100.0,
        water_volume_mL=500.0,
    )
    test_db.add(conditions)
    test_db.flush()

    compound = Compound(name="NaCl", formula="NaCl", molecular_weight_g_mol=58.44)
    test_db.add(compound)
    test_db.flush()

    additive = ChemicalAdditive(
        experiment_id=conditions.id,
        compound_id=compound.id,
        amount=500.0,
        unit=AmountUnit.MG,
    )
    additive.mass_in_grams = None  # simulate pre-existing NULL
    test_db.add(additive)
    test_db.commit()

    _backfill_conditions(test_db)

    test_db.refresh(additive)
    assert additive.mass_in_grams == pytest.approx(0.5)
```

- [ ] **Step 3: Run tests to confirm they fail**

```
pytest tests/data_migrations/test_recalculate_all_registry_012.py -v
```
Expected: `ModuleNotFoundError` — migration file does not exist yet.

- [ ] **Step 4: Create the migration file with `_backfill_conditions`**

```python
# database/data_migrations/recalculate_all_registry_012.py
"""
Data migration 012 — Backfill all calculated fields using the M3 registry.

Processes rows in dependency order:
  1. ExperimentalConditions  (computes water_to_rock_ratio, total_ferrous_iron_g)
     - conditions_calcs.py internally propagates to all linked ScalarResults
     - this also recalculates all ChemicalAdditive rows via the registry
  2. ScalarResults (safety-net pass for any rows whose conditions link is absent)

NOTE: total_ferrous_iron_g (new column, from rock elemental characterisation) is
independent of total_ferrous_iron (old column, manual entry). Ferrous iron yield
fields (ferrous_iron_yield_h2_pct / _nh3_pct) on ScalarResults depend on the old
column and will remain NULL if it was never set — that is expected.

Run:
  .venv/Scripts/python database/data_migrations/recalculate_all_registry_012.py

Dry-run (no commit):
  .venv/Scripts/python database/data_migrations/recalculate_all_registry_012.py --dry-run
"""
from __future__ import annotations

import sys
import os
import argparse

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import backend.services.calculations as _calcs  # noqa: F401 — registers all calculators
from backend.services.calculations.registry import recalculate
from sqlalchemy.orm import Session, joinedload
from database.models.conditions import ExperimentalConditions
from database.models.results import ScalarResults, ExperimentalResults
from database.models.experiments import Experiment


CHUNK_SIZE = 500


def _chunked(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def _backfill_conditions(db: Session, dry_run: bool = False) -> tuple[int, int]:
    """Recalculate ExperimentalConditions and their ChemicalAdditives.

    The conditions registry function also propagates recalculation to all linked
    ScalarResults internally (conditions_calcs.py lines 48-57).

    Returns (conditions_updated, additives_updated).
    """
    all_conditions = (
        db.query(ExperimentalConditions)
        .options(
            joinedload(ExperimentalConditions.chemical_additives),
            joinedload(ExperimentalConditions.experiment)
            .joinedload(Experiment.results)
            .joinedload(ExperimentalResults.scalar_data),
        )
        .all()
    )

    cond_ok = cond_err = add_ok = add_err = 0

    for batch in _chunked(all_conditions, CHUNK_SIZE):
        for conditions in batch:
            try:
                recalculate(conditions, db)
                cond_ok += 1
            except Exception as exc:
                print(f"  [WARN] conditions id={conditions.id}: {exc}")
                cond_err += 1

            for additive in list(getattr(conditions, 'chemical_additives', []) or []):
                try:
                    recalculate(additive, db)
                    add_ok += 1
                except Exception as exc:
                    print(f"  [WARN] additive id={additive.id}: {exc}")
                    add_err += 1

        if not dry_run:
            db.commit()
        print(
            f"  batch done — conditions ok={cond_ok} err={cond_err}, "
            f"additives ok={add_ok} err={add_err}"
        )

    return cond_ok, add_ok
```

- [ ] **Step 5: Run tests to confirm they pass**

```
pytest tests/data_migrations/test_recalculate_all_registry_012.py -v
```
Expected: 2 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add database/data_migrations/recalculate_all_registry_012.py \
        tests/data_migrations/__init__.py \
        tests/data_migrations/test_recalculate_all_registry_012.py
git commit -m "chore: add registry backfill migration 012 — conditions and additives"
```

---

### Task 2: Scalar Safety-Net Pass and `run_migration` Entrypoint

**Files:**
- Modify: `database/data_migrations/recalculate_all_registry_012.py`
- Modify: `tests/data_migrations/test_recalculate_all_registry_012.py`

- [ ] **Step 1: Write the failing test for scalar backfill**

Append to `tests/data_migrations/test_recalculate_all_registry_012.py`:

```python
from database.data_migrations.recalculate_all_registry_012 import _backfill_scalars
from database.models import ExperimentalResults, ScalarResults


def test_backfill_scalars_computes_grams_per_ton_yield(test_db: Session):
    """_backfill_scalars should populate grams_per_ton_yield from gross ammonium + rock mass."""
    experiment = Experiment(experiment_id="BACKFILL_003", experiment_number=903)
    test_db.add(experiment)
    test_db.flush()

    conditions = ExperimentalConditions(
        experiment_id="BACKFILL_003",
        experiment_fk=experiment.id,
        rock_mass_g=100.0,
        water_volume_mL=500.0,
    )
    test_db.add(conditions)
    test_db.flush()

    result_entry = ExperimentalResults(
        experiment_fk=experiment.id,
        time_post_reaction_days=7.0,
        time_post_reaction_bucket_days=7,
        description="t=7d",
        is_primary_timepoint_result=True,
    )
    test_db.add(result_entry)
    test_db.flush()

    scalar = ScalarResults(
        result_id=result_entry.id,
        gross_ammonium_concentration_mM=10.0,
        background_ammonium_concentration_mM=0.3,
        sampling_volume_mL=100.0,
        grams_per_ton_yield=None,  # simulate pre-existing NULL
    )
    test_db.add(scalar)
    test_db.commit()

    _backfill_scalars(test_db)

    test_db.refresh(scalar)
    # net = 9.7 mM, vol = 0.1 L → ammonia_mass_g = (9.7/1000) * 0.1 * 18.04 ≈ 0.01750 g
    # yield = 1e6 * 0.01750 / 100 ≈ 174.99 g/t
    assert scalar.grams_per_ton_yield is not None
    assert scalar.grams_per_ton_yield == pytest.approx(174.99, rel=0.01)
```

- [ ] **Step 2: Run test to confirm it fails**

```
pytest tests/data_migrations/test_recalculate_all_registry_012.py::test_backfill_scalars_computes_grams_per_ton_yield -v
```
Expected: `ImportError` — `_backfill_scalars` not defined yet.

- [ ] **Step 3: Add `_backfill_scalars` and `run_migration` to the migration file**

Append to `recalculate_all_registry_012.py`:

```python
from database.database import SessionLocal


def _backfill_scalars(db: Session, dry_run: bool = False) -> int:
    """Safety-net pass: recalculate ScalarResults rows whose conditions propagation may have missed.

    The conditions backfill already propagates to scalars via conditions_calcs.py.
    This pass catches any ScalarResults rows where the conditions relationship was
    absent during the conditions pass.

    Returns count of rows processed.
    """
    all_scalars = (
        db.query(ScalarResults)
        .options(
            joinedload(ScalarResults.result_entry)
            .joinedload(ExperimentalResults.experiment)
            .joinedload(Experiment.conditions)
        )
        .all()
    )

    ok = err = 0

    for batch in _chunked(all_scalars, CHUNK_SIZE):
        for scalar in batch:
            try:
                recalculate(scalar, db)
                ok += 1
            except Exception as exc:
                print(f"  [WARN] scalar id={scalar.id}: {exc}")
                err += 1

        if not dry_run:
            db.commit()
        print(f"  batch done — scalars ok={ok} err={err}")

    return ok


def run_migration(dry_run: bool = False) -> None:
    """Run the full backfill. Import and call for scripted use, or invoke via CLI."""
    db: Session = SessionLocal()
    try:
        print(f"Starting migration 012 — recalculate all registry fields (dry_run={dry_run})")

        print("\n[1/2] Backfilling ExperimentalConditions + ChemicalAdditives ...")
        print("      (conditions_calcs.py propagates to ScalarResults internally)")
        cond_ok, add_ok = _backfill_conditions(db, dry_run=dry_run)

        print("\n[2/2] ScalarResults safety-net pass ...")
        scalar_ok = _backfill_scalars(db, dry_run=dry_run)

        print("\nMigration 012 complete.")
        print(f"  conditions updated : {cond_ok}")
        print(f"  additives updated  : {add_ok}")
        print(f"  scalars updated    : {scalar_ok}")
        if dry_run:
            print("  DRY RUN — no changes committed.")

    except Exception as exc:
        print(f"Fatal error: {exc}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill all M3 calculated fields.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without committing.")
    args = parser.parse_args()
    run_migration(dry_run=args.dry_run)
```

- [ ] **Step 4: Run all tests to confirm they pass**

```
pytest tests/data_migrations/test_recalculate_all_registry_012.py -v
```
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add database/data_migrations/recalculate_all_registry_012.py \
        tests/data_migrations/test_recalculate_all_registry_012.py
git commit -m "chore: add scalar backfill and run_migration entrypoint for migration 012"
```

---

### Task 3: Verify Against the Live Database

No code changes — manual verification only.

- [ ] **Step 1: Dry-run against the live DB**

```powershell
cd C:\Apps\experiment-tracking
.venv\Scripts\python database/data_migrations/recalculate_all_registry_012.py --dry-run
```
Expected: row counts printed per batch, "DRY RUN — no changes committed" at the end, no `[WARN]` lines (or review any that appear before proceeding).

- [ ] **Step 2: Run the full migration**

```powershell
.venv\Scripts\python database/data_migrations/recalculate_all_registry_012.py
```
Expected: "Migration 012 complete" with non-zero counts for conditions and additives; zero `[WARN]` lines.

- [ ] **Step 3: Spot-check via the API**

Open `http://localhost:8000/docs` → `GET /api/experiments/{id}/results` on an experiment that has ammonium data. Confirm `grams_per_ton_yield` is now a non-null number.

- [ ] **Step 4: Final commit (tests only — migration script already committed)**

No additional commit needed unless docs or test fixes were made in this step.
