# Issue #17: Add `v_dim_timepoints` View — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a conformed timepoint dimension view (`v_dim_timepoints`) so PowerBI report authors have a single authoritative source for time-axis fields, preventing silent cross-filtering failures when combining measures from `v_results_scalar`, `v_results_h2`, and `v_results_icp`.

**Architecture:** A new SQL view is inserted into the existing `_VIEWS` list in `database/event_listeners.py`, positioned before the three result fact views. The view selects from `experimental_results JOIN experiments` where `is_primary_timepoint_result = TRUE`, producing one row per primary timepoint per experiment. No existing views are modified. Documentation in `docs/POWERBI_MODEL.md` is updated to reflect the new view, updated relationships, and field visibility guidance.

**Tech Stack:** PostgreSQL views (SQL), SQLAlchemy `text()` execution, pytest + SQLite in-memory for testing.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `database/event_listeners.py` (lines 427-433) | Insert `v_dim_timepoints` into `_VIEWS` list before `v_results_scalar` |
| Create | `tests/views/test_dim_timepoints.py` | Tests: view creation, row correctness, result_id alignment with fact views |
| Create | `tests/views/__init__.py` | Package marker |
| Modify | `docs/POWERBI_MODEL.md` | Add view docs, update relationships, add field visibility guide, XRD note |

---

## Task 1: Write failing tests for `v_dim_timepoints`

**Files:**
- Create: `tests/views/__init__.py`
- Create: `tests/views/test_dim_timepoints.py`

The test DB fixture (`tests/conftest.py`) uses SQLite in-memory and creates tables via `Base.metadata.create_all()`. Views are NOT created by that — they're raw SQL in `event_listeners.py`. Our tests need a helper that creates the view on the test engine.

- [ ] **Step 1: Create the test package and test file**

Create `tests/views/__init__.py` (empty) and `tests/views/test_dim_timepoints.py`:

```python
"""Tests for the v_dim_timepoints reporting view."""
import datetime
import pytest
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from database import Base
from database.models import Experiment, ExperimentalConditions, ExperimentalResults, ScalarResults, ICPResults


@pytest.fixture
def view_db():
    """Create a test DB with tables AND the v_dim_timepoints view."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    # Create the view under test — must match event_listeners.py exactly.
    # Import the SQL from the source of truth.
    from database.event_listeners import _VIEWS

    with engine.connect() as conn:
        for view_name, view_sql in _VIEWS:
            # SQLite uses TRUE/FALSE as 1/0, PostgreSQL uses TRUE — both work
            try:
                conn.execute(text(view_sql))
            except Exception:
                pass  # Some views may reference tables not in test scope; skip
        conn.commit()

    TestSession = sessionmaker(bind=engine)
    db = TestSession()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def _make_experiment(db: Session, exp_id: str, number: int) -> Experiment:
    """Helper: create an experiment with conditions."""
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


def _make_result(
    db: Session,
    experiment: Experiment,
    time_days: float,
    bucket_days: float,
    cumulative_days: float,
    is_primary: bool = True,
) -> ExperimentalResults:
    """Helper: create an experimental result row."""
    er = ExperimentalResults(
        experiment_fk=experiment.id,
        time_post_reaction_days=time_days,
        time_post_reaction_bucket_days=bucket_days,
        cumulative_time_post_reaction_days=cumulative_days,
        is_primary_timepoint_result=is_primary,
        description=f"Result at {time_days}d",
    )
    db.add(er)
    db.flush()
    return er


class TestDimTimepointsViewExists:
    """v_dim_timepoints is queryable after view creation."""

    def test_view_is_queryable(self, view_db):
        """View exists and returns zero rows on empty DB."""
        rows = view_db.execute(text("SELECT * FROM v_dim_timepoints")).fetchall()
        assert rows == []


class TestDimTimepointsOnlyPrimaryRows:
    """View contains only rows where is_primary_timepoint_result = TRUE."""

    def test_primary_rows_included(self, view_db):
        exp = _make_experiment(view_db, "EXP_001", 1)
        _make_result(view_db, exp, 1.0, 1.0, 1.0, is_primary=True)
        _make_result(view_db, exp, 1.0, 1.0, 1.0, is_primary=False)  # non-primary
        view_db.commit()

        rows = view_db.execute(text("SELECT * FROM v_dim_timepoints")).fetchall()
        assert len(rows) == 1

    def test_multiple_timepoints_multiple_experiments(self, view_db):
        exp1 = _make_experiment(view_db, "EXP_001", 1)
        exp2 = _make_experiment(view_db, "EXP_002", 2)
        _make_result(view_db, exp1, 1.0, 1.0, 1.0, is_primary=True)
        _make_result(view_db, exp1, 7.0, 7.0, 7.0, is_primary=True)
        _make_result(view_db, exp2, 1.0, 1.0, 1.0, is_primary=True)
        view_db.commit()

        rows = view_db.execute(text("SELECT * FROM v_dim_timepoints")).fetchall()
        assert len(rows) == 3


class TestDimTimepointsColumns:
    """View exposes the correct columns with correct values."""

    def test_columns_match_spec(self, view_db):
        exp = _make_experiment(view_db, "EXP_001", 1)
        er = _make_result(view_db, exp, 3.5, 4.0, 10.5, is_primary=True)
        view_db.commit()

        row = view_db.execute(text("SELECT * FROM v_dim_timepoints")).fetchone()
        # Access by key name
        assert row._mapping["result_id"] == er.id
        assert row._mapping["experiment_id"] == "EXP_001"
        assert row._mapping["time_post_reaction_days"] == 3.5
        assert row._mapping["time_post_reaction_bucket_days"] == 4.0
        assert row._mapping["cumulative_time_post_reaction_days"] == 10.5


class TestDimTimepointsResultIdAlignment:
    """result_id values match those in v_results_scalar, v_results_h2, v_results_icp."""

    def test_result_id_matches_scalar_view(self, view_db):
        exp = _make_experiment(view_db, "EXP_001", 1)
        er = _make_result(view_db, exp, 1.0, 1.0, 1.0, is_primary=True)
        sr = ScalarResults(result_id=er.id, final_ph=7.0)
        view_db.add(sr)
        view_db.commit()

        dim_ids = {
            r._mapping["result_id"]
            for r in view_db.execute(text("SELECT result_id FROM v_dim_timepoints"))
        }
        scalar_ids = {
            r._mapping["result_id"]
            for r in view_db.execute(text("SELECT result_id FROM v_results_scalar"))
        }
        assert dim_ids & scalar_ids == dim_ids  # all dim IDs are in scalar

    def test_result_id_matches_icp_view(self, view_db):
        exp = _make_experiment(view_db, "EXP_001", 1)
        er = _make_result(view_db, exp, 1.0, 1.0, 1.0, is_primary=True)
        icp = ICPResults(result_id=er.id, fe=10.0)
        view_db.add(icp)
        view_db.commit()

        dim_ids = {
            r._mapping["result_id"]
            for r in view_db.execute(text("SELECT result_id FROM v_dim_timepoints"))
        }
        icp_ids = {
            r._mapping["result_id"]
            for r in view_db.execute(text("SELECT result_id FROM v_results_icp"))
        }
        assert dim_ids & icp_ids == icp_ids  # all ICP IDs are in dim
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
.venv/Scripts/python -m pytest tests/views/test_dim_timepoints.py -v
```

Expected: FAIL — `v_dim_timepoints` does not exist yet in `_VIEWS`, so the view won't be created. Tests that query it will get `OperationalError: no such table: v_dim_timepoints`.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/views/__init__.py tests/views/test_dim_timepoints.py
git commit -m "[#17] Add failing tests for v_dim_timepoints view

- Tests added: yes
- Docs updated: no"
```

---

## Task 2: Implement `v_dim_timepoints` in `event_listeners.py`

**Files:**
- Modify: `database/event_listeners.py` (insert between line 426 and line 428)

The new view entry goes into the `_VIEWS` list **after** `v_sample_xrd` (line 426) and **before** `v_results_scalar` (line 428). This matches the issue's instruction to "insert before v_results_scalar".

- [ ] **Step 1: Add the view definition to `_VIEWS`**

In `database/event_listeners.py`, insert the following tuple into the `_VIEWS` list immediately after the `v_sample_xrd` entry (after line 426's closing `"""),`) and before the `v_results_scalar` comment block:

```python
    # ------------------------------------------------------------------
    # v_dim_timepoints
    # Conformed time dimension: one row per primary result timepoint per
    # experiment.  Sits between v_experiments and the result fact views
    # (v_results_scalar, v_results_h2, v_results_icp) so PowerBI report
    # authors have a single authoritative source for time-axis fields.
    # ------------------------------------------------------------------
    ("v_dim_timepoints", """
        CREATE VIEW v_dim_timepoints AS
        SELECT
            er.id                                  AS result_id,
            e.experiment_id,
            er.time_post_reaction_days,
            er.time_post_reaction_bucket_days,
            er.cumulative_time_post_reaction_days
        FROM experimental_results er
        JOIN experiments e ON e.id = er.experiment_fk
        WHERE er.is_primary_timepoint_result = TRUE
    """),
```

This is the exact SQL from the issue spec. No changes to any other view entry.

- [ ] **Step 2: Run the tests to verify they pass**

Run:
```bash
.venv/Scripts/python -m pytest tests/views/test_dim_timepoints.py -v
```

Expected: All tests PASS. The `view_db` fixture iterates `_VIEWS` and creates all views including the new one.

- [ ] **Step 3: Run the full test suite to check for regressions**

Run:
```bash
.venv/Scripts/python -m pytest tests/ -v --timeout=60
```

Expected: No regressions. The new view is additive — no existing views are modified, no columns removed.

- [ ] **Step 4: Commit**

```bash
git add database/event_listeners.py
git commit -m "[#17] Add v_dim_timepoints conformed time dimension view

- Inserts before v_results_scalar in _VIEWS list
- One row per primary timepoint per experiment
- Tests added: yes (Task 1)
- Docs updated: no (next task)"
```

---

## Task 3: Update `docs/POWERBI_MODEL.md`

**Files:**
- Modify: `docs/POWERBI_MODEL.md`

Four documentation changes per the issue acceptance criteria:
1. Add `v_dim_timepoints` to the "Views in the Model" tables
2. Update the relationship diagram
3. Add a "Field Visibility Guide" section
4. Add a note about why `v_experiment_xrd` time is intentionally independent

- [ ] **Step 1: Add `v_dim_timepoints` to the Experiment Views table**

In `docs/POWERBI_MODEL.md`, in the `## Experiment Views` table (after the `v_experiment_additives_summary` row and before the `v_experiment_xrd` row), add this row. This is a dimension view, not a result fact, so it belongs in the experiment/dimension section:

Add after the `v_experiment_additives_summary` row:

```markdown
| `public.v_dim_timepoints` | `result_id`, `experiment_id`, `time_post_reaction_days`, `time_post_reaction_bucket_days`, `cumulative_time_post_reaction_days` |
```

- [ ] **Step 2: Update the Relationships section**

Replace the entire `## Relationships` code block with the updated diagram showing `v_dim_timepoints` between `v_experiments` and the result fact views:

````markdown
## Relationships

```
v_experiments (experiment_id)    1 ──── 1 v_experiment_conditions (experiment_id)
v_experiments (experiment_id)    1 ──── * v_chemical_additives (experiment_id)
v_experiments (experiment_id)    1 ──── 1 v_experiment_additives_summary (experiment_id)
v_experiments (experiment_id)    1 ──── * v_experiment_xrd (experiment_id)
v_experiments (experiment_id)    1 ──── * v_dim_timepoints (experiment_id)

v_dim_timepoints (result_id)    1 ──── 1 v_results_scalar (result_id)
v_dim_timepoints (result_id)    1 ──── 1 v_results_h2 (result_id)
v_dim_timepoints (result_id)    1 ──── 1 v_results_icp (result_id)

v_sample_info (sample_id)       1 ──── * v_experiments (sample_id)
v_sample_info (sample_id)       1 ──── * v_sample_characterization (sample_id)
v_sample_info (sample_id)       1 ──── * v_pxrf_characterization (sample_id)
v_sample_info (sample_id)       1 ──── * v_sample_elemental_comp (sample_id)
v_sample_info (sample_id)       1 ──── * v_sample_xrd (sample_id)
```
````

Key change: `v_results_scalar`, `v_results_h2`, and `v_results_icp` no longer connect directly to `v_experiments`. They connect to `v_dim_timepoints` via `result_id`, and `v_dim_timepoints` connects up to `v_experiments` via `experiment_id`. Filter flow: `v_experiments` → `v_dim_timepoints` → result facts.

- [ ] **Step 3: Add the Field Visibility Guide section**

Add this new section immediately after `## Relationships` and before `## Notes`:

```markdown
---

## Field Visibility Guide

When configuring the PowerBI model, hide duplicate join keys in child tables so report
authors can only select them from the authoritative dimension. This prevents the
cross-filtering trap described in [issue #17](https://github.com/mathew-h/experiment-tracking-sandbox/issues/17).

### `v_dim_timepoints`

| Field | Visible? | Reason |
|-------|----------|--------|
| `time_post_reaction_days` | Yes | Authoritative source for time axis |
| `time_post_reaction_bucket_days` | Yes | Authoritative source for bucketed time axis |
| `cumulative_time_post_reaction_days` | Yes | Authoritative source for cumulative time |
| `experiment_id` | **Hide** | Users get `experiment_id` from `v_experiments` |
| `result_id` | **Hide** | Join key only |

### `v_results_scalar`

| Field | Action |
|-------|--------|
| `experiment_id` | **Hide** (already hidden today) |
| `experiment_fk` | **Hide** |
| `time_post_reaction_days` | **Hide** — use `v_dim_timepoints` |
| `time_post_reaction_bucket_days` | **Hide** — use `v_dim_timepoints` |
| `cumulative_time_post_reaction_days` | **Hide** — use `v_dim_timepoints` |

### `v_results_h2`

| Field | Action |
|-------|--------|
| `experiment_id` | **Hide** (already hidden today) |
| `experiment_fk` | **Hide** |
| `time_post_reaction_days` | **Hide** — use `v_dim_timepoints` |
| `time_post_reaction_bucket_days` | **Hide** — use `v_dim_timepoints` |

### `v_results_icp`

| Field | Action |
|-------|--------|
| `experiment_id` | **Hide** (already hidden today) |
| `experiment_fk` | **Hide** |
| `time_post_reaction_days` | **Hide** — use `v_dim_timepoints` |
| `time_post_reaction_bucket_days` | **Hide** — use `v_dim_timepoints` |
```

- [ ] **Step 4: Update the Notes section**

Add this bullet to the existing `## Notes` section at the end:

```markdown
- `v_experiment_xrd` retains its own `time_post_reaction_days` and connects directly to
  `v_experiments` via `experiment_id` — it is intentionally **not** routed through
  `v_dim_timepoints`. XRD measurements follow a different schedule than scalar/H2/ICP
  results and may not align with primary result timepoints.
```

- [ ] **Step 5: Verify the doc renders correctly**

Read back the file to confirm all sections are present and formatted correctly. Check that:
- The new view appears in the table
- The relationship diagram is updated
- The field visibility guide is a complete new section
- The XRD note is in the Notes section

- [ ] **Step 6: Commit**

```bash
git add docs/POWERBI_MODEL.md
git commit -m "[#17] Update POWERBI_MODEL.md for v_dim_timepoints

- Add view to Experiment Views table
- Update relationship diagram (results now via dim_timepoints)
- Add Field Visibility Guide section
- Add XRD independent-time note
- Tests added: no
- Docs updated: yes"
```

---

## Task 4: Final verification and acceptance check

**Files:** None (verification only)

- [ ] **Step 1: Run all view tests**

```bash
.venv/Scripts/python -m pytest tests/views/ -v
```

Expected: All tests PASS.

- [ ] **Step 2: Run full test suite**

```bash
.venv/Scripts/python -m pytest tests/ -v --timeout=60
```

Expected: No regressions.

- [ ] **Step 3: Verify acceptance criteria**

Check each criterion from the issue:

| Criterion | How to verify |
|-----------|---------------|
| `v_dim_timepoints` created at startup alongside existing views | View is in `_VIEWS` list; creation runs at import time |
| One row per primary timepoint per experiment | `WHERE er.is_primary_timepoint_result = TRUE`; tested in `test_primary_rows_included` and `test_multiple_timepoints_multiple_experiments` |
| `result_id` values match result fact views | Tested in `test_result_id_matches_scalar_view` and `test_result_id_matches_icp_view` |
| PowerBI 1:1 relationships possible | `result_id` is unique per row (one primary per timepoint); tested via alignment checks |
| `v_experiment_xrd` independent | Not modified; documented in Notes |
| `POWERBI_MODEL.md` updated | New view, relationships, field visibility, XRD note all present |
| No existing views modified | Diff shows only insertions in `event_listeners.py`; no view SQL changed |

- [ ] **Step 4: Run `/complete-task`**
