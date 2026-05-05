# Swap Reactor 4 and Reactor 7 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the database and dashboard to reflect the physical swap of reactors 4 and 7 in the lab — all historical experiment records attributed to reactor 4 are reassigned to reactor 7 and vice versa, and the hardware specs shown on the dashboard are swapped to match.

**Architecture:** A standalone data migration script (015) swaps `reactor_number` between 4 and 7 in `ExperimentalConditions` using a three-step atomic transaction with a temp value (9999). Dry-run mode works by doing the swap inside a nested savepoint that is always rolled back. Backend and frontend both hardcode reactor specs in static dicts — those entries are updated in place. No schema change, no Alembic migration.

**Tech Stack:** Python 3, SQLAlchemy 2 ORM, PostgreSQL, React 18 + TypeScript

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `database/data_migrations/swap_reactor_4_7_015.py` | Migration logic: count, swap, yield checksum, dry-run, CLI |
| Create | `tests/data_migrations/test_swap_reactor_4_7_015.py` | All migration tests (swap correctness, dry-run, rollback) |
| Modify | `backend/api/routers/dashboard.py:27-30` | Swap R4/R7 entries in `REACTOR_SPECS` dict |
| Modify | `frontend/src/pages/ReactorGrid.tsx:21-24` | Swap R04/R07 entries in `REACTOR_SPECS` constant |

---

### Task 1: Write failing migration tests (TDD)

**Files:**
- Create: `tests/data_migrations/test_swap_reactor_4_7_015.py`

- [ ] **Step 1: Create the test file**

```python
"""Tests for database/data_migrations/swap_reactor_4_7_015.py

Uses migration_session (savepoint isolation) from tests/data_migrations/conftest.py.
All tests seed their own data with experiment_number values in the 9000s to avoid
production ID collisions.
"""
import pytest
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models.experiments import Experiment
from database.models.conditions import ExperimentalConditions
from database.data_migrations.swap_reactor_4_7_015 import _swap_reactor_assignments


# ── Helpers ───────────────────────────────────────────────────────────────────

def _seed(db: Session, exp_id: str, exp_num: int, reactor: int | None) -> ExperimentalConditions:
    """Seed one Experiment + ExperimentalConditions row."""
    exp = Experiment(experiment_id=exp_id, experiment_number=exp_num)
    db.add(exp)
    db.flush()
    cond = ExperimentalConditions(
        experiment_id=exp_id,
        experiment_fk=exp.id,
        reactor_number=reactor,
    )
    db.add(cond)
    db.flush()
    return cond


def _count(db: Session, reactor_number: int) -> int:
    return (
        db.query(func.count(ExperimentalConditions.id))
        .filter(ExperimentalConditions.reactor_number == reactor_number)
        .scalar()
        or 0
    )


# ── Swap correctness ──────────────────────────────────────────────────────────

class TestSwapCorrectness:
    def test_reactor4_rows_become_reactor7(self, migration_session: Session):
        """All conditions with reactor_number=4 are reassigned to 7."""
        cond = _seed(migration_session, "SWAP_001", 9001, reactor=4)
        _swap_reactor_assignments(migration_session)
        migration_session.refresh(cond)
        assert cond.reactor_number == 7

    def test_reactor7_rows_become_reactor4(self, migration_session: Session):
        """All conditions with reactor_number=7 are reassigned to 4."""
        cond = _seed(migration_session, "SWAP_002", 9002, reactor=7)
        _swap_reactor_assignments(migration_session)
        migration_session.refresh(cond)
        assert cond.reactor_number == 4

    def test_counts_swap_correctly(self, migration_session: Session):
        """3 R4 rows + 2 R7 rows become 2 R4 rows + 3 R7 rows."""
        specs = [
            (4, 9010, "SWAP_CNT_000"), (4, 9011, "SWAP_CNT_001"), (4, 9012, "SWAP_CNT_002"),
            (7, 9013, "SWAP_CNT_003"), (7, 9014, "SWAP_CNT_004"),
        ]
        for rn, en, eid in specs:
            _seed(migration_session, eid, en, reactor=rn)

        result = _swap_reactor_assignments(migration_session)

        assert result["post_r4"] == 2
        assert result["post_r7"] == 3

    def test_total_count_unchanged(self, migration_session: Session):
        """Total experiment count across R4 + R7 is the same before and after."""
        for rn, en, eid in [(4, 9020, "SWAP_TOT_000"), (7, 9021, "SWAP_TOT_001"), (7, 9022, "SWAP_TOT_002")]:
            _seed(migration_session, eid, en, reactor=rn)

        result = _swap_reactor_assignments(migration_session)

        assert result["pre_r4"] + result["pre_r7"] == result["post_r4"] + result["post_r7"]

    def test_other_reactors_unaffected(self, migration_session: Session):
        """Reactors 1, 3, and 8 are untouched by the swap."""
        for rn, en, eid in [(1, 9030, "SWAP_OTH_001"), (3, 9031, "SWAP_OTH_003"), (8, 9032, "SWAP_OTH_008")]:
            _seed(migration_session, eid, en, reactor=rn)

        pre_r1 = _count(migration_session, 1)
        pre_r3 = _count(migration_session, 3)
        pre_r8 = _count(migration_session, 8)

        _swap_reactor_assignments(migration_session)

        assert _count(migration_session, 1) == pre_r1
        assert _count(migration_session, 3) == pre_r3
        assert _count(migration_session, 8) == pre_r8

    def test_null_reactor_unaffected(self, migration_session: Session):
        """Conditions with reactor_number=NULL are not affected."""
        cond = _seed(migration_session, "SWAP_NULL_001", 9040, reactor=None)
        _swap_reactor_assignments(migration_session)
        migration_session.refresh(cond)
        assert cond.reactor_number is None

    def test_summary_counts_are_correct(self, migration_session: Session):
        """Return dict accurately reports pre/post counts and moved-row counts."""
        _seed(migration_session, "SWAP_SUM_004", 9050, reactor=4)
        _seed(migration_session, "SWAP_SUM_007", 9051, reactor=7)

        result = _swap_reactor_assignments(migration_session)

        assert result["pre_r4"] == 1
        assert result["pre_r7"] == 1
        assert result["post_r4"] == 1
        assert result["post_r7"] == 1
        assert result["r4_moved"] == 1
        assert result["r7_moved"] == 1


# ── Dry-run and rollback ──────────────────────────────────────────────────────

class TestDryRunAndRollback:
    def test_dry_run_does_not_persist(self, migration_session: Session):
        """dry_run=True rolls back the swap via a nested savepoint; reactor_number stays 4."""
        cond = _seed(migration_session, "SWAP_DRY_001", 9060, reactor=4)

        result = _swap_reactor_assignments(migration_session, dry_run=True)

        migration_session.expire_all()
        fresh = migration_session.query(ExperimentalConditions).filter_by(
            experiment_id="SWAP_DRY_001"
        ).one()
        assert fresh.reactor_number == 4           # unchanged in DB
        assert result["r4_moved"] == 1             # but summary shows what would have moved

    def test_partial_migration_rolls_back_cleanly(self, migration_session: Session):
        """After a mid-migration rollback, no rows are stranded at the temp value (9999)."""
        cond = _seed(migration_session, "SWAP_RB_001", 9070, reactor=4)

        # Simulate step 1 only (partial migration — crash before steps 2 and 3)
        migration_session.query(ExperimentalConditions).filter(
            ExperimentalConditions.reactor_number == 4
        ).update({"reactor_number": 9999}, synchronize_session="fetch")

        # Explicit rollback (what run_migration's except block does)
        migration_session.rollback()
        migration_session.begin_nested()  # restart savepoint for test cleanup

        assert _count(migration_session, 9999) == 0
        fresh = migration_session.query(ExperimentalConditions).filter_by(
            experiment_id="SWAP_RB_001"
        ).first()
        assert fresh is not None
        assert fresh.reactor_number == 4
```

- [ ] **Step 2: Run tests to verify they all fail with ImportError**

```bash
.venv/Scripts/python -m pytest tests/data_migrations/test_swap_reactor_4_7_015.py -v
```

Expected: all 9 tests fail with `ModuleNotFoundError: No module named 'database.data_migrations.swap_reactor_4_7_015'`

---

### Task 2: Write the migration script

**Files:**
- Create: `database/data_migrations/swap_reactor_4_7_015.py`

- [ ] **Step 3: Create the migration script**

```python
"""Data migration 015 — Swap reactor assignments for reactors 4 and 7.

Background
----------
Reactors 4 and 7 were physically swapped in the lab. Every historical experiment
record attributed to reactor_number=4 was actually run on the physical unit now
labeled Reactor 7, and vice versa.

This migration corrects the database in a single atomic transaction using a
three-step approach with a temporary placeholder value (9999):
  Step 1: reactor_number=4  → 9999
  Step 2: reactor_number=7  → 4
  Step 3: reactor_number=9999 → 7

⚠️  One-time migration.  Running it a second time swaps back to the original
(incorrect) state.  Use --dry-run to preview before running live.

How to run
----------
From the project root (Windows)::

    # Preview — prints counts and checksums, no DB changes committed
    .venv\\Scripts\\python database/data_migrations/swap_reactor_4_7_015.py --dry-run

    # Live run — requires --confirm flag as a deliberate gate
    .venv\\Scripts\\python database/data_migrations/swap_reactor_4_7_015.py --confirm

Prerequisites
-------------
- Take a full database backup before running live.
- Review --dry-run output with Mat before running live.
- Do not run without explicit user sign-off.
"""

from __future__ import annotations
import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
from database.models.conditions import ExperimentalConditions
from database.models.experiments import Experiment
from database.models.results import ExperimentalResults, ScalarResults

log = structlog.get_logger(__name__)

_REACTOR_A = 4
_REACTOR_B = 7
_TEMP_VALUE = 9999  # transient placeholder — never persisted to disk


def _swap_reactor_assignments(db: Session, dry_run: bool = False) -> dict:
    """Swap reactor_number between _REACTOR_A (4) and _REACTOR_B (7).

    When dry_run=True the swap is executed inside a nested savepoint which is
    always rolled back, so the return dict reflects what would change without
    modifying any committed state.

    Returns a summary dict. Caller is responsible for db.commit() in live mode.
    """
    # ── Pre-migration counts ──────────────────────────────────────────────────
    pre_r4 = (
        db.query(func.count(ExperimentalConditions.id))
        .filter(ExperimentalConditions.reactor_number == _REACTOR_A)
        .scalar() or 0
    )
    pre_r7 = (
        db.query(func.count(ExperimentalConditions.id))
        .filter(ExperimentalConditions.reactor_number == _REACTOR_B)
        .scalar() or 0
    )

    # ── Pre-migration yield checksum ──────────────────────────────────────────
    # Sum of grams_per_ton_yield for experiments on R4 or R7. Must be unchanged
    # post-swap to confirm no scalar data was accidentally mutated.
    pre_yield_sum = (
        db.query(func.coalesce(func.sum(ScalarResults.grams_per_ton_yield), 0.0))
        .join(ExperimentalResults, ScalarResults.result_id == ExperimentalResults.id)
        .join(Experiment, ExperimentalResults.experiment_fk == Experiment.id)
        .join(
            ExperimentalConditions,
            ExperimentalConditions.experiment_fk == Experiment.id,
        )
        .filter(ExperimentalConditions.reactor_number.in_([_REACTOR_A, _REACTOR_B]))
        .scalar()
    ) or 0.0

    # ── Dry-run uses a nested savepoint so the swap is always rolled back ─────
    sp = db.begin_nested() if dry_run else None

    # Step 1: A → temp
    r4_moved = (
        db.query(ExperimentalConditions)
        .filter(ExperimentalConditions.reactor_number == _REACTOR_A)
        .update({"reactor_number": _TEMP_VALUE}, synchronize_session="fetch")
    )
    # Step 2: B → A
    db.query(ExperimentalConditions).filter(
        ExperimentalConditions.reactor_number == _REACTOR_B
    ).update({"reactor_number": _REACTOR_A}, synchronize_session="fetch")
    # Step 3: temp → B
    r7_moved = (
        db.query(ExperimentalConditions)
        .filter(ExperimentalConditions.reactor_number == _TEMP_VALUE)
        .update({"reactor_number": _REACTOR_B}, synchronize_session="fetch")
    )

    db.flush()

    # ── Post-migration counts ─────────────────────────────────────────────────
    post_r4 = (
        db.query(func.count(ExperimentalConditions.id))
        .filter(ExperimentalConditions.reactor_number == _REACTOR_A)
        .scalar() or 0
    )
    post_r7 = (
        db.query(func.count(ExperimentalConditions.id))
        .filter(ExperimentalConditions.reactor_number == _REACTOR_B)
        .scalar() or 0
    )

    # ── Post-migration yield checksum ─────────────────────────────────────────
    post_yield_sum = (
        db.query(func.coalesce(func.sum(ScalarResults.grams_per_ton_yield), 0.0))
        .join(ExperimentalResults, ScalarResults.result_id == ExperimentalResults.id)
        .join(Experiment, ExperimentalResults.experiment_fk == Experiment.id)
        .join(
            ExperimentalConditions,
            ExperimentalConditions.experiment_fk == Experiment.id,
        )
        .filter(ExperimentalConditions.reactor_number.in_([_REACTOR_A, _REACTOR_B]))
        .scalar()
    ) or 0.0

    # ── Validate counts ───────────────────────────────────────────────────────
    if post_r4 != pre_r7 or post_r7 != pre_r4:
        raise ValueError(
            f"Count mismatch after swap: "
            f"pre(R{_REACTOR_A}={pre_r4}, R{_REACTOR_B}={pre_r7}) → "
            f"post(R{_REACTOR_A}={post_r4}, R{_REACTOR_B}={post_r7})"
        )

    if dry_run and sp is not None:
        sp.rollback()

    return {
        "pre_r4": pre_r4,
        "pre_r7": pre_r7,
        "post_r4": post_r4,
        "post_r7": post_r7,
        "r4_moved": r4_moved,
        "r7_moved": r7_moved,
        "pre_yield_sum": pre_yield_sum,
        "post_yield_sum": post_yield_sum,
        "yield_sum_unchanged": abs(pre_yield_sum - post_yield_sum) < 0.001,
    }


def run_migration(dry_run: bool = False, confirm: bool = False) -> None:
    if not dry_run and not confirm:
        print("ERROR: Pass --confirm to run live, or --dry-run to preview.")
        sys.exit(1)

    db = SessionLocal()
    try:
        print("=" * 60)
        print(f"SWAP REACTOR {_REACTOR_A} ↔ {_REACTOR_B}  (migration 015)")
        print("=" * 60)
        if dry_run:
            print("DRY RUN — no changes will be committed\n")

        summary = _swap_reactor_assignments(db, dry_run=dry_run)

        print(f"Pre-migration:       R{_REACTOR_A}={summary['pre_r4']}  R{_REACTOR_B}={summary['pre_r7']}")
        print(f"Post-migration:      R{_REACTOR_A}={summary['post_r4']}  R{_REACTOR_B}={summary['post_r7']}")
        print(f"Rows moved:          R{_REACTOR_A}→R{_REACTOR_B}={summary['r4_moved']}   R{_REACTOR_B}→R{_REACTOR_A}={summary['r7_moved']}")
        print(
            f"Yield sum unchanged: {summary['yield_sum_unchanged']}  "
            f"(pre={summary['pre_yield_sum']:.4f} g/t  "
            f"post={summary['post_yield_sum']:.4f} g/t)"
        )

        if not dry_run:
            db.commit()
            print("\nMigration committed successfully.")
        else:
            print("\nDRY RUN complete — no changes committed.")

        print("=" * 60)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    dry_run_flag = "--dry-run" in sys.argv
    confirm_flag = "--confirm" in sys.argv
    run_migration(dry_run=dry_run_flag, confirm=confirm_flag)
```

- [ ] **Step 4: Run all tests — verify all 9 pass**

```bash
.venv/Scripts/python -m pytest tests/data_migrations/test_swap_reactor_4_7_015.py -v
```

Expected:
```
PASSED test_reactor4_rows_become_reactor7
PASSED test_reactor7_rows_become_reactor4
PASSED test_counts_swap_correctly
PASSED test_total_count_unchanged
PASSED test_other_reactors_unaffected
PASSED test_null_reactor_unaffected
PASSED test_summary_counts_are_correct
PASSED test_dry_run_does_not_persist
PASSED test_partial_migration_rolls_back_cleanly

9 passed in X.XXs
```

- [ ] **Step 5: Commit migration script and tests**

```bash
git add database/data_migrations/swap_reactor_4_7_015.py tests/data_migrations/test_swap_reactor_4_7_015.py
git commit -m "[#56] add reactor 4/7 swap migration script and tests

- Tests added: yes
- Docs updated: no"
```

---

### Task 3: Swap backend REACTOR_SPECS

**Files:**
- Modify: `backend/api/routers/dashboard.py:27-30`

- [ ] **Step 6: Swap R4 and R7 entries in the backend spec dict**

In `backend/api/routers/dashboard.py`, change lines 27–30 from:
```python
    4:  {"volume_mL": 300, "material": "Titanium",  "vendor": "Tan"},
    5:  {"volume_mL": 500, "material": "Titanium",  "vendor": "Yushen"},
    6:  {"volume_mL": 500, "material": "Titanium",  "vendor": "Yushen"},
    7:  {"volume_mL": 500, "material": "Titanium",  "vendor": "Yushen"},
```
to:
```python
    4:  {"volume_mL": 500, "material": "Titanium",  "vendor": "Yushen"},
    5:  {"volume_mL": 500, "material": "Titanium",  "vendor": "Yushen"},
    6:  {"volume_mL": 500, "material": "Titanium",  "vendor": "Yushen"},
    7:  {"volume_mL": 300, "material": "Titanium",  "vendor": "Tan"},
```

Reactor position 4's slot now holds the 500 mL Yushen unit (the physical vessel that was previously at position 7), and vice versa.

- [ ] **Step 7: Commit**

```bash
git add backend/api/routers/dashboard.py
git commit -m "[#56] swap reactor 4/7 hardware specs in backend dashboard

- Tests added: no
- Docs updated: no"
```

---

### Task 4: Swap frontend REACTOR_SPECS

**Files:**
- Modify: `frontend/src/pages/ReactorGrid.tsx:21-24`

- [ ] **Step 8: Swap R04 and R07 entries in the frontend spec constant**

In `frontend/src/pages/ReactorGrid.tsx`, change lines 21–24 from:
```typescript
  R04: { volume_mL: 300, material: 'Titanium',  vendor: 'Tan' },
  R05: { volume_mL: 500, material: 'Titanium',  vendor: 'Yushen' },
  R06: { volume_mL: 500, material: 'Titanium',  vendor: 'Yushen' },
  R07: { volume_mL: 500, material: 'Titanium',  vendor: 'Yushen' },
```
to:
```typescript
  R04: { volume_mL: 500, material: 'Titanium',  vendor: 'Yushen' },
  R05: { volume_mL: 500, material: 'Titanium',  vendor: 'Yushen' },
  R06: { volume_mL: 500, material: 'Titanium',  vendor: 'Yushen' },
  R07: { volume_mL: 300, material: 'Titanium',  vendor: 'Tan' },
```

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/ReactorGrid.tsx
git commit -m "[#56] swap reactor 4/7 hardware specs in frontend grid

- Tests added: no
- Docs updated: no"
```

---

### Task 5: Pre-run gate — dry-run review before live execution

This is a **human checkpoint**. No code changes. The migration script must not be run against production without a database backup and Mat's explicit review of the dry-run output.

- [ ] **Step 10: Take a full database backup on the lab PC**

```powershell
$ts = Get-Date -Format 'yyyyMMdd_HHmm'
pg_dump -U experiments_user experiments > "C:\Backups\experiments\pre_reactor_swap_$ts.sql"
Write-Host "Backup saved to C:\Backups\experiments\pre_reactor_swap_$ts.sql"
```

- [ ] **Step 11: Run dry-run from the project root on the lab PC**

```bash
.venv/Scripts/python database/data_migrations/swap_reactor_4_7_015.py --dry-run
```

Verify all of the following in the output:
- `R4` pre-count matches expected number of R4 experiments from lab records
- `R7` pre-count matches expected number of R7 experiments from lab records
- `Yield sum unchanged: True`
- No error raised

- [ ] **Step 12: Mat reviews dry-run output and approves — then run live**

After backup confirmation and dry-run review, Mat runs:

```bash
.venv/Scripts/python database/data_migrations/swap_reactor_4_7_015.py --confirm
```

Expected final lines:
```
...
Migration committed successfully.
============================================================
```

---

## Self-Review

**Spec coverage:**

| Requirement | Covered by |
|-------------|-----------|
| Swap dashboard display specs for R4/R7 | Tasks 3 + 4 |
| Data migration: swap reactor_number 4 ↔ 7 | Task 2 |
| Atomic transaction with rollback on error | Task 2 — `run_migration` except block; three-step within single session |
| Pre/post row count assertions (per reactor) | Task 2 — `_swap_reactor_assignments` validates `post_r4 == pre_r7`; test `test_counts_swap_correctly` |
| Derived field checksum (grams_per_ton_yield) | Task 2 — `yield_sum_unchanged` in summary |
| Seeded test DB with R4 + R7 experiments | Task 1 — all tests seed via `_seed()` helper |
| Assert R4 rows → R7 and R7 rows → R4 | Task 1 — `test_reactor4_rows_become_reactor7`, `test_reactor7_rows_become_reactor4` |
| Assert total count unchanged | Task 1 — `test_total_count_unchanged` |
| Assert no other reactors modified | Task 1 — `test_other_reactors_unaffected` |
| Assert rollback behavior | Task 1 — `test_partial_migration_rolls_back_cleanly` |
| Assert dry-run | Task 1 — `test_dry_run_does_not_persist` |
| `--dry-run` flag | Task 2 — `run_migration(dry_run=True)` |
| `--confirm` gate for live run | Task 2 — `run_migration` exits with error if neither flag is passed |
| Power BI / SQL view validation | No code change needed — views join on `experiment_fk` not `reactor_number`; `yield_sum_unchanged: True` in dry-run output confirms no scalar data mutation. Spot-check a known experiment after live run. |
| Database backup before live run | Task 5, Step 10 |
| Human dry-run review gate | Task 5, Steps 11–12 |

**Placeholder scan:** No TBDs, no "similar to" references, no unimplemented steps.

**Type consistency:**
- `_swap_reactor_assignments(db, dry_run)` defined in Task 2 Step 3, imported in Task 1 Step 1. ✓
- Return dict keys used in tests: `post_r4`, `post_r7`, `pre_r4`, `pre_r7`, `r4_moved`, `r7_moved` — all defined in the return statement in Task 2. ✓
- `_REACTOR_A = 4`, `_REACTOR_B = 7`, `_TEMP_VALUE = 9999` — referenced only inside the migration module. ✓
- `_seed(db, exp_id, exp_num, reactor)` defined once in test file, used by all test classes. ✓
