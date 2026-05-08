# Issue #59: `cumulative_ferrous_iron_yield_h2_pct` in `v_results_scalar`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a running-sum window function column `cumulative_ferrous_iron_yield_h2_pct` to the `v_results_scalar` reporting view so Power BI can plot a cumulative Fe(II)→H₂ conversion curve across experiment chains without DAX aggregation.

**Architecture:** One SQL window function added to the existing `v_results_scalar` view string in `database/event_listeners.py`. No Alembic migration needed — views drop and recreate at startup. `docs/POWERBI_MODEL.md` updated to document the new column.

**Tech Stack:** PostgreSQL window functions, SQLAlchemy `text()`, pytest, existing `tests/views/` fixture pattern.

---

## Files

| Action | Path |
|--------|------|
| Create | `tests/views/test_v_results_scalar_cum_fe.py` |
| Modify | `database/event_listeners.py` — `v_results_scalar` view SQL only |
| Modify | `docs/POWERBI_MODEL.md` — Result Views table, `v_results_scalar` row |

---

### Task 1: Write the failing tests

**Files:**
- Create: `tests/views/test_v_results_scalar_cum_fe.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for cumulative_ferrous_iron_yield_h2_pct column in v_results_scalar."""
import datetime
import pytest
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker, Session

from database import Base
from database.models import (
    Experiment, ExperimentalConditions, ExperimentalResults, ScalarResults
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


def _make_experiment(db: Session, exp_id: str, number: int, base_id: str = None) -> Experiment:
    exp = Experiment(
        experiment_id=exp_id,
        experiment_number=number,
        status="ONGOING",
        date=datetime.date(2026, 1, 1),
        base_experiment_id=base_id,
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
    cumulative_days: float,
    is_primary: bool = True,
) -> ExperimentalResults:
    er = ExperimentalResults(
        experiment_fk=experiment.id,
        time_post_reaction_days=cumulative_days,
        time_post_reaction_bucket_days=cumulative_days,
        cumulative_time_post_reaction_days=cumulative_days,
        is_primary_timepoint_result=is_primary,
        description=f"Result at {cumulative_days}d",
    )
    db.add(er)
    db.flush()
    return er


def _make_scalar(db: Session, result: ExperimentalResults, fe_h2_pct: float = None) -> ScalarResults:
    sr = ScalarResults(result_id=result.id, ferrous_iron_yield_h2_pct=fe_h2_pct)
    db.add(sr)
    db.flush()
    return sr


class TestColumnExists:
    def test_cumulative_column_present(self, view_db):
        """v_results_scalar exposes cumulative_ferrous_iron_yield_h2_pct."""
        # The view returns zero rows on an empty DB; querying it should not raise.
        result = view_db.execute(
            text("SELECT cumulative_ferrous_iron_yield_h2_pct FROM v_results_scalar")
        )
        assert result.fetchall() == []


class TestCumulativeSum:
    def test_single_experiment_running_total(self, view_db):
        """Cumulative sum accumulates across timepoints within one experiment."""
        exp = _make_experiment(view_db, "CUM001", 1)
        er1 = _make_result(view_db, exp, cumulative_days=1.0)
        er2 = _make_result(view_db, exp, cumulative_days=7.0)
        er3 = _make_result(view_db, exp, cumulative_days=14.0)
        _make_scalar(view_db, er1, fe_h2_pct=10.0)
        _make_scalar(view_db, er2, fe_h2_pct=5.0)
        _make_scalar(view_db, er3, fe_h2_pct=3.0)
        view_db.commit()

        rows = view_db.execute(
            text("""
                SELECT cumulative_ferrous_iron_yield_h2_pct
                FROM v_results_scalar
                WHERE experiment_id = 'CUM001'
                ORDER BY cumulative_time_post_reaction_days
            """)
        ).fetchall()

        assert len(rows) == 3
        assert rows[0][0] == pytest.approx(10.0)
        assert rows[1][0] == pytest.approx(15.0)
        assert rows[2][0] == pytest.approx(18.0)

    def test_null_h2_contributes_zero(self, view_db):
        """Timepoints with NULL ferrous_iron_yield_h2_pct contribute 0 to running sum."""
        exp = _make_experiment(view_db, "CUM002", 2)
        er1 = _make_result(view_db, exp, cumulative_days=1.0)
        er2 = _make_result(view_db, exp, cumulative_days=7.0)
        er3 = _make_result(view_db, exp, cumulative_days=14.0)
        _make_scalar(view_db, er1, fe_h2_pct=8.0)
        _make_scalar(view_db, er2, fe_h2_pct=None)   # NULL — should contribute 0
        _make_scalar(view_db, er3, fe_h2_pct=4.0)
        view_db.commit()

        rows = view_db.execute(
            text("""
                SELECT cumulative_ferrous_iron_yield_h2_pct
                FROM v_results_scalar
                WHERE experiment_id = 'CUM002'
                ORDER BY cumulative_time_post_reaction_days
            """)
        ).fetchall()

        assert len(rows) == 3
        assert rows[0][0] == pytest.approx(8.0)
        assert rows[1][0] == pytest.approx(8.0)   # NULL added 0
        assert rows[2][0] == pytest.approx(12.0)

    def test_no_scalar_row_contributes_zero(self, view_db):
        """Timepoints with no scalar_results row (LEFT JOIN miss) also contribute 0."""
        exp = _make_experiment(view_db, "CUM003", 3)
        er1 = _make_result(view_db, exp, cumulative_days=1.0)
        er2 = _make_result(view_db, exp, cumulative_days=7.0)   # no ScalarResults row
        _make_scalar(view_db, er1, fe_h2_pct=6.0)
        # er2 intentionally has no _make_scalar call
        view_db.commit()

        rows = view_db.execute(
            text("""
                SELECT cumulative_ferrous_iron_yield_h2_pct
                FROM v_results_scalar
                WHERE experiment_id = 'CUM003'
                ORDER BY cumulative_time_post_reaction_days
            """)
        ).fetchall()

        assert len(rows) == 2
        assert rows[0][0] == pytest.approx(6.0)
        assert rows[1][0] == pytest.approx(6.0)   # no scalar row → contributed 0

    def test_two_independent_experiments_do_not_share_sums(self, view_db):
        """Partition by experiment chain — unrelated experiments accumulate independently."""
        expA = _make_experiment(view_db, "IND_A", 10)
        expB = _make_experiment(view_db, "IND_B", 11)
        erA = _make_result(view_db, expA, cumulative_days=1.0)
        erB = _make_result(view_db, expB, cumulative_days=1.0)
        _make_scalar(view_db, erA, fe_h2_pct=20.0)
        _make_scalar(view_db, erB, fe_h2_pct=5.0)
        view_db.commit()

        rows = view_db.execute(
            text("""
                SELECT experiment_id, cumulative_ferrous_iron_yield_h2_pct
                FROM v_results_scalar
                WHERE experiment_id IN ('IND_A', 'IND_B')
                ORDER BY experiment_id
            """)
        ).fetchall()

        by_exp = {r[0]: r[1] for r in rows}
        assert by_exp["IND_A"] == pytest.approx(20.0)
        assert by_exp["IND_B"] == pytest.approx(5.0)
```

- [ ] **Step 2: Run the test to verify it fails**

```
cd "C:\Users\MathewHearl\OneDrive - Addis Energy\Documents\0x_Software\database_sandbox\experiment_tracking_sandbox"
.venv\Scripts\pytest tests/views/test_v_results_scalar_cum_fe.py -v
```

Expected: `FAILED` — `ProgrammingError: column "cumulative_ferrous_iron_yield_h2_pct" does not exist`

---

### Task 2: Add the window function to `v_results_scalar`

**Files:**
- Modify: `database/event_listeners.py`

- [ ] **Step 3: Add the column to the view SQL**

In `database/event_listeners.py`, find the `v_results_scalar` tuple (around line 473). Replace the block containing `sr.ferrous_iron_yield_h2_pct,` with the following — the only change is inserting four lines immediately after that column:

**Before:**
```python
            sr.ferrous_iron_yield_h2_pct,
            sr.ferrous_iron_yield_nh3_pct,
```

**After:**
```python
            sr.ferrous_iron_yield_h2_pct,
            SUM(COALESCE(sr.ferrous_iron_yield_h2_pct, 0)) OVER (
                PARTITION BY COALESCE(e.base_experiment_id, e.experiment_id)
                ORDER BY er.cumulative_time_post_reaction_days
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS cumulative_ferrous_iron_yield_h2_pct,
            sr.ferrous_iron_yield_nh3_pct,
```

No other line in the view changes. `e` is already in the FROM clause (`JOIN experiments e ON e.id = er.experiment_fk`) and `er.cumulative_time_post_reaction_days` is already selected — no additional joins needed.

- [ ] **Step 4: Run tests to verify they pass**

```
.venv\Scripts\pytest tests/views/test_v_results_scalar_cum_fe.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Run the full view test suite to check for regressions**

```
.venv\Scripts\pytest tests/views/ -v
```

Expected: all existing tests still pass.

---

### Task 3: Update `docs/POWERBI_MODEL.md`

**Files:**
- Modify: `docs/POWERBI_MODEL.md`

- [ ] **Step 6: Add the new column to the key columns list for `v_results_scalar`**

In the Result Views table, find the `public.v_results_scalar` row. It currently lists `ferrous_iron_yield_h2_pct` followed by `ferrous_iron_yield_nh3_pct`. Insert `cumulative_ferrous_iron_yield_h2_pct` between them:

**Before:**
```
… `ferrous_iron_yield_h2_pct`, `ferrous_iron_yield_nh3_pct`, …
```

**After:**
```
… `ferrous_iron_yield_h2_pct`, `cumulative_ferrous_iron_yield_h2_pct`, `ferrous_iron_yield_nh3_pct`, …
```

The full updated row (for copy-paste accuracy):

```markdown
| `public.v_results_scalar` | `result_id`, `experiment_id`, `experiment_fk`, `sampling_description`, `time_post_reaction_days`, `time_post_reaction_bucket_days`, `cumulative_time_post_reaction_days`, `gross_ammonium_concentration_mM`, `background_ammonium_concentration_mM`, `net_ammonium_concentration`, `grams_per_ton_yield`, `final_ph`, `final_nitrate_concentration_mM`, `ferrous_iron_yield`, `ferrous_iron_yield_h2_pct`, `cumulative_ferrous_iron_yield_h2_pct`, `ferrous_iron_yield_nh3_pct`, `final_dissolved_oxygen_mg_L`, `final_conductivity_mS_cm`, `final_alkalinity_mg_L`, `co2_partial_pressure_MPa`, `sampling_volume_mL`, `ammonium_quant_method`, `background_experiment_fk`, `scalar_measurement_date`, `nmr_run_date` |
```

---

### Task 4: Commit

- [ ] **Step 7: Stage and commit all three files**

```
git add tests/views/test_v_results_scalar_cum_fe.py
git add database/event_listeners.py
git add docs/POWERBI_MODEL.md docs/project_context/POWERBI_MODEL.md
git commit -m "[#59] add cumulative_ferrous_iron_yield_h2_pct to v_results_scalar

- Tests added: yes
- Docs updated: yes"
```

---

## Self-Review

**Spec coverage:**

| Requirement | Task |
|---|---|
| `ferrous_iron_yield_h2_pct` unchanged in SELECT list | Task 2 — existing line untouched, new line inserted after |
| `cumulative_ferrous_iron_yield_h2_pct` immediately follows it | Task 2 — confirmed in SQL placement |
| `PARTITION BY COALESCE(e.base_experiment_id, e.experiment_id)` | Task 2 — exact phrase in window spec |
| `ORDER BY er.cumulative_time_post_reaction_days` | Task 2 — exact phrase in window spec |
| `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | Task 2 — exact frame clause |
| `POWERBI_MODEL.md` lists new column under `v_results_scalar` | Task 3 |
| `v_dim_timepoints` not touched | No task modifies it — correct |
| No other view modified | Only `v_results_scalar` tuple in `_VIEWS` changes |

**Placeholder scan:** No TBDs, no deferred steps, all code complete.

**Type consistency:** `ferrous_iron_yield_h2_pct` is `Float` in `ScalarResults`; `SUM(COALESCE(Float, 0))` returns `Float` — consistent with how `net_ammonium_concentration` (also a computed float expression) is handled in the same view.
