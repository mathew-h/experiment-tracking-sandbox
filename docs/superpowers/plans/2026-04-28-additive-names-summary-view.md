# Add v_experiment_additive_names_summary View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `v_experiment_additive_names_summary` PostgreSQL view that returns one row per experiment with a comma-separated, alphabetically sorted list of additive compound names.

**Architecture:** Append a single entry to the `_VIEWS` list in `database/event_listeners.py` immediately after `v_experiment_additives_summary`. The existing drop-and-recreate loop handles lifecycle automatically. Tests follow the pattern established in `tests/views/test_dim_timepoints.py`, using a real PostgreSQL test DB with per-test savepoints.

**Tech Stack:** PostgreSQL `STRING_AGG`, SQLAlchemy, pytest

---

## File Map

| File | Action |
|------|--------|
| `database/event_listeners.py` | Modify — insert new `_VIEWS` entry at line 217 |
| `tests/views/test_additive_names_summary.py` | Create — new test file |
| `docs/working/issue-log.md` | Modify — log completed task |

> `MODELS.md` is a `.claude/rules/` file — the hook auto-syncs it. No direct update needed.

---

### Task 1: Write the failing tests

**Files:**
- Create: `tests/views/test_additive_names_summary.py`

- [ ] **Step 1: Create the test file**

```python
"""Tests for the v_experiment_additive_names_summary reporting view."""
import datetime
import pytest
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker, Session

from database import Base
from database.models import (
    Experiment, ExperimentalConditions, ChemicalAdditive, Compound
)

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"


@pytest.fixture(scope="module")
def view_engine():
    engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def view_db(view_engine):
    """Per-test session wrapped in a savepoint; creates views then rolls back."""
    connection = view_engine.connect()
    transaction = connection.begin()

    from database.event_listeners import _VIEWS
    for view_name, view_sql in _VIEWS:
        try:
            connection.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
            connection.execute(text(view_sql))
        except Exception:
            pass

    TestSession = sessionmaker(bind=connection)
    db = TestSession()
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()


def _make_experiment(db: Session, exp_id: str, number: int) -> Experiment:
    exp = Experiment(
        experiment_id=exp_id,
        experiment_number=number,
        status="ONGOING",
        date=datetime.date(2026, 1, 1),
    )
    cond = ExperimentalConditions(
        experiment_id=exp_id,
        rock_mass_g=100.0,
        water_volume_mL=500.0,
    )
    exp.conditions = cond
    db.add(exp)
    db.flush()
    cond.experiment_fk = exp.id
    return exp


def _make_compound(db: Session, name: str, n: int) -> Compound:
    c = Compound(name=name, formula=f"X{n}", molecular_weight_g_mol=100.0)
    db.add(c)
    db.flush()
    return c


def _add_additive(db: Session, cond: ExperimentalConditions, compound: Compound) -> None:
    ca = ChemicalAdditive(
        experiment_id=cond.id,
        compound_id=compound.id,
        amount=1.0,
        unit="g",
    )
    db.add(ca)
    db.flush()


class TestViewQueryable:
    def test_view_exists_and_returns_no_rows_on_empty_db(self, view_db):
        rows = view_db.execute(
            text("SELECT * FROM v_experiment_additive_names_summary")
        ).fetchall()
        assert rows == []


class TestNoAdditives:
    def test_experiment_with_no_additives_appears_with_null(self, view_db):
        _make_experiment(view_db, "EXP_001", 1)
        view_db.commit()

        rows = view_db.execute(
            text("SELECT experiment_id, additive_names FROM v_experiment_additive_names_summary")
        ).fetchall()
        assert len(rows) == 1
        row = rows[0]._mapping
        assert row["experiment_id"] == "EXP_001"
        assert row["additive_names"] is None


class TestSingleAdditive:
    def test_single_additive_returns_compound_name(self, view_db):
        exp = _make_experiment(view_db, "EXP_001", 1)
        compound = _make_compound(view_db, "Nickel Chloride", 1)
        _add_additive(view_db, exp.conditions, compound)
        view_db.commit()

        row = view_db.execute(
            text("SELECT additive_names FROM v_experiment_additive_names_summary WHERE experiment_id = 'EXP_001'")
        ).fetchone()
        assert row._mapping["additive_names"] == "Nickel Chloride"


class TestMultipleAdditives:
    def test_multiple_additives_alphabetically_sorted(self, view_db):
        exp = _make_experiment(view_db, "EXP_001", 1)
        copper = _make_compound(view_db, "Copper Sulfate", 1)
        nickel = _make_compound(view_db, "Nickel Chloride", 2)
        _add_additive(view_db, exp.conditions, nickel)   # insert nickel first
        _add_additive(view_db, exp.conditions, copper)   # copper should sort before nickel
        view_db.commit()

        row = view_db.execute(
            text("SELECT additive_names FROM v_experiment_additive_names_summary WHERE experiment_id = 'EXP_001'")
        ).fetchone()
        assert row._mapping["additive_names"] == "Copper Sulfate, Nickel Chloride"


class TestOneRowPerExperiment:
    def test_two_experiments_two_rows(self, view_db):
        exp1 = _make_experiment(view_db, "EXP_001", 1)
        exp2 = _make_experiment(view_db, "EXP_002", 2)
        compound = _make_compound(view_db, "Copper Sulfate", 1)
        _add_additive(view_db, exp1.conditions, compound)
        view_db.commit()

        rows = view_db.execute(
            text("SELECT experiment_id FROM v_experiment_additive_names_summary ORDER BY experiment_id")
        ).fetchall()
        ids = [r._mapping["experiment_id"] for r in rows]
        assert ids == ["EXP_001", "EXP_002"]

    def test_experiment_count_matches_experiments_table(self, view_db):
        _make_experiment(view_db, "EXP_001", 1)
        _make_experiment(view_db, "EXP_002", 2)
        _make_experiment(view_db, "EXP_003", 3)
        view_db.commit()

        view_count = view_db.execute(
            text("SELECT COUNT(*) FROM v_experiment_additive_names_summary")
        ).scalar()
        exp_count = view_db.execute(
            text("SELECT COUNT(*) FROM experiments")
        ).scalar()
        assert view_count == exp_count
```

- [ ] **Step 2: Run to confirm ALL tests fail (view does not exist yet)**

```bash
.venv/Scripts/pytest tests/views/test_additive_names_summary.py -v 2>&1 | head -40
```

Expected: tests fail — either `UndefinedTable` error on the view query, or the view fixture skips it and asserts fail.

---

### Task 2: Add the view to `_VIEWS`

**Files:**
- Modify: `database/event_listeners.py` (insert after line 216, after the `v_experiment_additives_summary` entry closing `"""),`)

- [ ] **Step 1: Insert the new view entry**

In `database/event_listeners.py`, after the closing `"""),` of `v_experiment_additives_summary` (currently line 216) and before the `v_sample_info` comment block, insert:

```python
    # ------------------------------------------------------------------
    # v_experiment_additive_names_summary
    # One row per experiment — compound names only, comma-separated and
    # alphabetically sorted.  additive_names is NULL for experiments with
    # no additives.  Use COALESCE(additive_names, '') at the consumer if
    # an empty string is preferred.
    # ------------------------------------------------------------------
    ("v_experiment_additive_names_summary", """
        CREATE VIEW v_experiment_additive_names_summary AS
        SELECT
            e.experiment_id,
            STRING_AGG(c.name, ', ' ORDER BY c.name) AS additive_names
        FROM experiments e
        LEFT JOIN experimental_conditions ec ON ec.experiment_fk = e.id
        LEFT JOIN chemical_additives ca      ON ca.experiment_id = ec.id
        LEFT JOIN compounds c                ON c.id = ca.compound_id
        GROUP BY e.experiment_id
    """),
```

- [ ] **Step 2: Run the tests to confirm they pass**

```bash
.venv/Scripts/pytest tests/views/test_additive_names_summary.py -v
```

Expected output (all 6 tests pass):
```
PASSED tests/views/test_additive_names_summary.py::TestViewQueryable::test_view_exists_and_returns_no_rows_on_empty_db
PASSED tests/views/test_additive_names_summary.py::TestNoAdditives::test_experiment_with_no_additives_appears_with_null
PASSED tests/views/test_additive_names_summary.py::TestSingleAdditive::test_single_additive_returns_compound_name
PASSED tests/views/test_additive_names_summary.py::TestMultipleAdditives::test_multiple_additives_alphabetically_sorted
PASSED tests/views/test_additive_names_summary.py::TestOneRowPerExperiment::test_two_experiments_two_rows
PASSED tests/views/test_additive_names_summary.py::TestOneRowPerExperiment::test_experiment_count_matches_experiments_table
```

- [ ] **Step 3: Run the full views test suite to confirm no regressions**

```bash
.venv/Scripts/pytest tests/views/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add database/event_listeners.py tests/views/test_additive_names_summary.py
git commit -m "[#52] add v_experiment_additive_names_summary view

- Tests added: yes
- Docs updated: no"
```

---

### Task 3: Documentation and issue log

**Files:**
- Modify: `docs/working/issue-log.md`

- [ ] **Step 1: Append to issue log**

Append to the bottom of `docs/working/issue-log.md`:

```markdown
## 2026-04-28 | issue #52 — Add v_experiment_additive_names_summary view
- **Files changed:**
  - `database/event_listeners.py` — added `v_experiment_additive_names_summary` to `_VIEWS` immediately after `v_experiment_additives_summary`
  - `tests/views/test_additive_names_summary.py` — new file: 6 tests covering queryable, null for no additives, single additive, alphabetical sort, one-row-per-experiment, count match
- **Tests added:** yes — 6 view integration tests
- **Decision logged:** no
```

- [ ] **Step 2: Commit**

```bash
git add docs/working/issue-log.md
git commit -m "[#52] update issue log

- Tests added: no
- Docs updated: yes"
```
