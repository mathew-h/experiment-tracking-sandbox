# Issue #70 P4 — Outlier Flag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users flag a bad replicate vial (`is_outlier`) so it drops out of `v_results_scalar_rollup` aggregates (mean/median/std AND `n_replicates`) while its individual data stays fully visible everywhere else.

**Architecture:** Additive `is_outlier` boolean on `Experiment` (single model, additive Alembic migration that also recreates the rollup view in both directions). One `AND NOT COALESCE(e.is_outlier, false)` line added to `v_results_scalar_rollup`'s WHERE in `database/event_listeners.py` — no other view changes. Flag flows through the existing generic PATCH `/api/experiments/{id}` setattr loop (only schema + ModificationsLog additions needed) and surfaces in the React detail page (toggle + badge) and GroupedResultsView (member annotation).

**Tech Stack:** SQLAlchemy 2.x + Alembic + PostgreSQL, FastAPI + Pydantic v2, React 18 + TanStack Query + vitest, pytest.

## Global Constraints

- **Branch:** all work on `feat/issue-70-p4-outlier-flag` (already created from `develop`). Commit format: `[#70] <imperative, <50 chars>` with `- Tests added:` / `- Docs updated:` trailer lines.
- **Locked-component authorization:** `database/models/experiments.py` is locked; issue #70 P4 explicitly authorizes this exact single-model additive change. **No bulk upload parser changes anywhere in P4.** No enum changes. Never edit existing files in `alembic/versions/` — only add the one new migration.
- **Migration rules:** purely additive; both `upgrade()` and `downgrade()` must work; verify round-trip `.venv/Scripts/alembic downgrade -1 && .venv/Scripts/alembic upgrade head`. Down-revision base is `fe48608cabb7` (current head — verify with `.venv/Scripts/alembic heads` before generating).
- **View scope:** only `v_results_scalar_rollup` changes. `v_results_scalar`, `v_results_h2`, `v_results_icp`, additives views: untouched — flagged experiments must remain in all per-row views.
- **Commands:** Python via `.venv/Scripts/python -m pytest …`, alembic via `.venv/Scripts/alembic`. Frontend via `cd frontend` then `npx vitest run …`, `npx tsc --noEmit`, `npx eslint src --ext .ts,.tsx`. Bash tool syntax (POSIX) for all commands.
- **Test DB:** tests create schema via `Base.metadata.create_all` against `postgresql://experiments_user:password@localhost:5432/experiments_test` — the new column is picked up from the model automatically; no migration needed for tests. The **dev** DB (`experiments`) is where the alembic round-trip is exercised.
- **Servers:** never start/stop uvicorn or Vite (project rule). No `console.log`, no hardcoded hex (use existing `Badge` component / tokens), no new npm or pip packages.
- **Docs sync:** write docs under `docs/` normally; a PostToolUse hook syncs to `docs/project_context/` — never write there directly.
- **No product re-decisions:** locked decisions from issue #70 apply. UI placement decided for this plan: toggle + badge on the experiment detail page (shown only for experiments that are part of a replicate set), plus "(outlier)" annotation in GroupedResultsView. Do not add outlier UI to the experiments list page (out of scope).

---

### Task 1: DB layer — `is_outlier` column, migration, rollup view filter

**Files:**
- Modify: `database/models/experiments.py` (lines 1, 24–25 area)
- Modify: `database/event_listeners.py` (rollup view comment block ~512–518 and view SQL ~519–550)
- Create: `alembic/versions/<generated>_add_is_outlier_to_experiments.py`
- Create: `tests/models/test_is_outlier_column.py`
- Modify: `tests/views/test_v_results_scalar_rollup.py` (append new test class)

**Interfaces:**
- Produces: `Experiment.is_outlier` — `Column(Boolean, nullable=False, default=False, server_default=text("false"))`. Later tasks read/write `exp.is_outlier` (Python `bool`).
- Produces: `v_results_scalar_rollup` now excludes rows where the joined experiment has `is_outlier = true` (affects aggregates AND `n_replicates`).

- [ ] **Step 1: Write the failing model tests**

Create `tests/models/test_is_outlier_column.py`:

```python
"""Tests for the Experiment.is_outlier column (issue #70 P4)."""
import datetime
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from database import Base
from database.models import Experiment

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(TEST_DB_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def test_is_outlier_defaults_to_false(db):
    exp = Experiment(
        experiment_id="OUTL_COL_001",
        experiment_number=910001,
        status="ONGOING",
        date=datetime.date(2026, 1, 1),
    )
    db.add(exp)
    db.flush()
    assert exp.is_outlier is False


def test_is_outlier_server_default_false_for_raw_insert(db):
    # Raw insert omitting the column exercises the server_default that
    # backfills pre-existing rows during migration.
    db.execute(text(
        "INSERT INTO experiments (experiment_id, experiment_number) "
        "VALUES ('OUTL_COL_002', 910002)"
    ))
    val = db.execute(text(
        "SELECT is_outlier FROM experiments WHERE experiment_id = 'OUTL_COL_002'"
    )).scalar_one()
    assert val is False


def test_is_outlier_settable_true(db):
    exp = Experiment(
        experiment_id="OUTL_COL_003c",
        experiment_number=910003,
        status="ONGOING",
        date=datetime.date(2026, 1, 1),
        is_outlier=True,
    )
    db.add(exp)
    db.flush()
    assert exp.is_outlier is True
```

- [ ] **Step 2: Run model tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/models/test_is_outlier_column.py -v`
Expected: FAIL / ERROR — `'is_outlier' is an invalid keyword argument for Experiment` and `column "is_outlier" does not exist`.

- [ ] **Step 3: Add the column to the model**

In `database/models/experiments.py`, change line 1 from:

```python
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SQLEnum, Text
```

to:

```python
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SQLEnum, Text, Boolean, text
```

After the `replicate_label` line (line 24), add:

```python
    is_outlier = Column(Boolean, nullable=False, default=False, server_default=text("false"))  # True = bad vial (leak, cracked septum): excluded from v_results_scalar_rollup aggregates incl. n_replicates; per-row views and own pages unaffected
```

- [ ] **Step 4: Run model tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/models/test_is_outlier_column.py -v`
Expected: 3 PASS (test DB schema comes from `Base.metadata.create_all`, so no migration is needed here).

- [ ] **Step 5: Write the failing view tests**

Append to `tests/views/test_v_results_scalar_rollup.py` (uses the file's existing `view_db` fixture and `_make_experiment` / `_make_result` / `_make_scalar` helpers — do not redefine them):

```python
class TestRollupOutlierExclusion:
    def test_flagged_replicate_excluded_from_stats_and_n(self, view_db):
        exp_a = _make_experiment(view_db, "ROLL_OUT_001a", 7)
        exp_b = _make_experiment(view_db, "ROLL_OUT_001b", 8)
        exp_c = _make_experiment(view_db, "ROLL_OUT_001c", 9)
        for exp, nh4 in ((exp_a, 1.0), (exp_b, 2.0), (exp_c, 30.0)):
            er = _make_result(view_db, exp, bucket_days=7.0)
            _make_scalar(view_db, er, gross_nh4=nh4)
        exp_c.is_outlier = True
        view_db.commit()

        row = view_db.execute(
            text("""
                SELECT n_replicates, "mean_gross_ammonium_mM", "median_gross_ammonium_mM", "sd_gross_ammonium_mM"
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_OUT_001' AND time_post_reaction_bucket_days = 7.0
            """)
        ).fetchone()

        assert row is not None
        mapping = row._mapping
        assert mapping["n_replicates"] == 2
        assert mapping["mean_gross_ammonium_mM"] == pytest.approx(1.5)
        assert mapping["median_gross_ammonium_mM"] == pytest.approx(1.5)
        assert mapping["sd_gross_ammonium_mM"] == pytest.approx(0.70710678, abs=1e-6)

    def test_flagged_replicate_remains_in_per_row_view(self, view_db):
        exp_a = _make_experiment(view_db, "ROLL_OUT_002a", 10)
        exp_b = _make_experiment(view_db, "ROLL_OUT_002b", 11)
        for exp, nh4 in ((exp_a, 1.0), (exp_b, 50.0)):
            er = _make_result(view_db, exp, bucket_days=3.0)
            _make_scalar(view_db, er, gross_nh4=nh4)
        exp_b.is_outlier = True
        view_db.commit()

        rows = view_db.execute(
            text("""
                SELECT experiment_id FROM v_results_scalar
                WHERE experiment_id IN ('ROLL_OUT_002a', 'ROLL_OUT_002b')
            """)
        ).fetchall()
        assert {r._mapping["experiment_id"] for r in rows} == {"ROLL_OUT_002a", "ROLL_OUT_002b"}

    def test_group_with_all_members_flagged_has_no_rollup_row(self, view_db):
        exp_a = _make_experiment(view_db, "ROLL_OUT_003a", 12)
        exp_b = _make_experiment(view_db, "ROLL_OUT_003b", 13)
        for exp in (exp_a, exp_b):
            er = _make_result(view_db, exp, bucket_days=7.0)
            _make_scalar(view_db, er, gross_nh4=2.0)
            exp.is_outlier = True
        view_db.commit()

        rows = view_db.execute(
            text("SELECT 1 FROM v_results_scalar_rollup WHERE base_experiment_id = 'ROLL_OUT_003'")
        ).fetchall()
        assert rows == []
```

- [ ] **Step 6: Run view tests to verify the exclusion tests fail**

Run: `.venv/Scripts/python -m pytest tests/views/test_v_results_scalar_rollup.py -v`
Expected: the 3 pre-existing tests PASS; `test_flagged_replicate_excluded_from_stats_and_n` FAILS (`n_replicates == 3`, mean 11.0) and `test_group_with_all_members_flagged_has_no_rollup_row` FAILS (1 row returned). `test_flagged_replicate_remains_in_per_row_view` may already pass — that is fine; it pins the non-regression.

- [ ] **Step 7: Add the filter to the rollup view**

In `database/event_listeners.py`, update the `v_results_scalar_rollup` comment block (currently ~lines 512–518). Replace:

```python
    # ------------------------------------------------------------------
    # v_results_scalar_rollup
    # One row per (base_experiment_id, timepoint bucket). Cross-replicate
    # mean/median/std for a replicate set (or a single non-replicate
    # experiment, which yields n_replicates=1 and NULL std). No outlier
    # filter and no ICP aggregation in P1 (see issue #69 P4).
    # ------------------------------------------------------------------
```

with:

```python
    # ------------------------------------------------------------------
    # v_results_scalar_rollup
    # One row per (base_experiment_id, timepoint bucket). Cross-replicate
    # mean/median/std for a replicate set (or a single non-replicate
    # experiment, which yields n_replicates=1 and NULL std). Experiments
    # flagged is_outlier are excluded from all aggregates including
    # n_replicates (issue #70 P4) but stay in every per-row view.
    # No ICP aggregation (permanently out of scope).
    # ------------------------------------------------------------------
```

In the view SQL immediately below, change:

```sql
        WHERE er.is_primary_timepoint_result = TRUE
        GROUP BY COALESCE(e.base_experiment_id, e.experiment_id),
                 er.time_post_reaction_bucket_days
```

to:

```sql
        WHERE er.is_primary_timepoint_result = TRUE
          AND NOT COALESCE(e.is_outlier, false)
        GROUP BY COALESCE(e.base_experiment_id, e.experiment_id),
                 er.time_post_reaction_bucket_days
```

(Only this one view. Nothing else in `_VIEWS` changes.)

- [ ] **Step 8: Run view tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/views/test_v_results_scalar_rollup.py tests/views/ -v`
Expected: all PASS (the `view_db` fixture recreates views from `_VIEWS`, so the new SQL is exercised directly).

- [ ] **Step 9: Create the migration**

Verify head, then autogenerate:

```bash
.venv/Scripts/alembic heads          # expect: fe48608cabb7 (head)
.venv/Scripts/alembic revision --autogenerate -m "add is_outlier to experiments"
```

Review the generated file in `alembic/versions/`. Autogenerate will produce only the `add_column`/`drop_column` pair (views are not in metadata; ignore/delete any unrelated drift ops — there should be none). Then **edit it** so the rollup view is recreated in both directions (the view must be dropped before the column can be dropped on downgrade, and Power BI needs a working view at every revision). Final file content (keep the generated revision id and the generated `down_revision = 'fe48608cabb7'`):

```python
"""add is_outlier to experiments

Revision ID: <keep generated id>
Revises: fe48608cabb7
Create Date: <keep generated>

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '<keep generated id>'
down_revision: Union[str, None] = 'fe48608cabb7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ROLLUP_COLUMNS_SQL = """
        SELECT
            COALESCE(e.base_experiment_id, e.experiment_id)              AS base_experiment_id,
            er.time_post_reaction_bucket_days,
            COUNT(sr.result_id)                                          AS n_replicates,
            AVG(sr."gross_ammonium_concentration_mM")                   AS "mean_gross_ammonium_mM",
            percentile_cont(0.5) WITHIN GROUP (
                ORDER BY sr."gross_ammonium_concentration_mM")          AS "median_gross_ammonium_mM",
            stddev_samp(sr."gross_ammonium_concentration_mM")           AS "sd_gross_ammonium_mM",
            AVG(GREATEST(0, sr."gross_ammonium_concentration_mM" - sr."background_ammonium_concentration_mM"))
                                                                        AS "mean_net_ammonium_mM",
            stddev_samp(GREATEST(0, sr."gross_ammonium_concentration_mM" - sr."background_ammonium_concentration_mM"))
                                                                        AS "sd_net_ammonium_mM",
            AVG(sr.h2_micromoles)                                       AS mean_h2_micromoles,
            stddev_samp(sr.h2_micromoles)                               AS sd_h2_micromoles,
            AVG(sr.h2_grams_per_ton_yield)                              AS mean_h2_grams_per_ton,
            stddev_samp(sr.h2_grams_per_ton_yield)                      AS sd_h2_grams_per_ton,
            AVG(sr.ferrous_iron_yield_h2_pct)                           AS mean_fe_yield_h2_pct,
            stddev_samp(sr.ferrous_iron_yield_h2_pct)                   AS sd_fe_yield_h2_pct,
            AVG(sr.ferrous_iron_yield_nh3_pct)                          AS mean_fe_yield_nh3_pct,
            stddev_samp(sr.ferrous_iron_yield_nh3_pct)                  AS sd_fe_yield_nh3_pct,
            AVG(sr.grams_per_ton_yield)                                 AS mean_grams_per_ton_yield,
            stddev_samp(sr.grams_per_ton_yield)                         AS sd_grams_per_ton_yield,
            AVG(sr.final_ph)                                            AS mean_final_ph
        FROM experimental_results er
        JOIN experiments e         ON e.id  = er.experiment_fk
        LEFT JOIN scalar_results sr ON sr.result_id = er.id
"""

# P4 definition: outlier-flagged experiments excluded from all aggregates.
ROLLUP_VIEW_NEW = f"""
    CREATE VIEW v_results_scalar_rollup AS
    {_ROLLUP_COLUMNS_SQL}
        WHERE er.is_primary_timepoint_result = TRUE
          AND NOT COALESCE(e.is_outlier, false)
        GROUP BY COALESCE(e.base_experiment_id, e.experiment_id),
                 er.time_post_reaction_bucket_days
"""

# Pre-P4 definition (no outlier filter) — restored on downgrade so the view
# keeps working after the column is dropped.
ROLLUP_VIEW_OLD = f"""
    CREATE VIEW v_results_scalar_rollup AS
    {_ROLLUP_COLUMNS_SQL}
        WHERE er.is_primary_timepoint_result = TRUE
        GROUP BY COALESCE(e.base_experiment_id, e.experiment_id),
                 er.time_post_reaction_bucket_days
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'experiments',
        sa.Column('is_outlier', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.execute("DROP VIEW IF EXISTS v_results_scalar_rollup CASCADE")
    op.execute(ROLLUP_VIEW_NEW)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP VIEW IF EXISTS v_results_scalar_rollup CASCADE")
    op.execute(ROLLUP_VIEW_OLD)
    op.drop_column('experiments', 'is_outlier')
```

- [ ] **Step 10: Round-trip the migration against the dev DB**

```bash
.venv/Scripts/alembic upgrade head
.venv/Scripts/alembic downgrade -1
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -c "import database.event_listeners; print('views ok')"
```

Expected: all four commands exit 0; last prints `views ok` with no `Failed to create view` / `Reporting view creation failed` log lines. If the dev DB is unreachable, STOP and report — do not fake this verification.

- [ ] **Step 11: Run the wider regression net**

Run: `.venv/Scripts/python -m pytest tests/models/ tests/views/ tests/test_replicate_lineage.py -q`
Expected: all pass (3 known pre-existing failures live only in `tests/test_pg_backup_restore.py`, which is not in this selection).

- [ ] **Step 12: Commit**

```bash
git add database/models/experiments.py database/event_listeners.py alembic/versions/ tests/models/test_is_outlier_column.py tests/views/test_v_results_scalar_rollup.py
git commit -m "[#70] Add is_outlier column and rollup filter

- Additive Experiment.is_outlier (bool, default false), migration round-trips
- v_results_scalar_rollup excludes flagged experiments incl. n_replicates
- Tests added: yes
- Docs updated: no (Task 4)"
```

---

### Task 2: API layer — expose and audit the flag

**Files:**
- Modify: `backend/api/schemas/experiments.py` (ExperimentUpdate ~line 19, ExperimentListItem ~line 48, ExperimentResponse ~line 84, ReplicateGroupMember ~line 118)
- Modify: `backend/api/routers/experiments.py` (`update_experiment`, ~lines 805–825)
- Modify: `tests/api/test_experiments.py` (append new class)
- Modify: `tests/api/test_experiment_rollup.py` (append tests)

**Interfaces:**
- Consumes: `Experiment.is_outlier` from Task 1.
- Produces: `PATCH /api/experiments/{experiment_id}` accepts `{"is_outlier": true|false}`; `ExperimentResponse`, `ExperimentListItem`, `ReplicateGroupMember` all carry `is_outlier: bool`. Task 3's frontend relies on exactly these JSON field names.

Notes for the implementer:
- The PATCH router applies unknown-to-you fields via its generic loop (`for field, value in data.items(): setattr(exp, field, value)`), so adding `is_outlier` to `ExperimentUpdate` makes the write work with no loop change — you only add the audit-log block.
- `_build_list_item` copies every `Experiment.__table__` column into the list payload, so `ExperimentListItem.is_outlier` gets populated with no router change.
- `RollupTimepointResponse` needs NO change — the view's columns are unchanged; only its row filter changed.

- [ ] **Step 1: Write the failing API tests**

Append to `tests/api/test_experiments.py` (follow the file's existing fixture usage — `client`, `db_session`; import style at top of file already includes `Experiment`; add `ModificationsLog` and `select` imports if not present):

```python
from sqlalchemy import select as sa_select
from database.models import ModificationsLog


class TestOutlierFlagPatch:
    def _mk(self, db_session, exp_id, number):
        from database.models.enums import ExperimentStatus
        exp = Experiment(experiment_id=exp_id, experiment_number=number,
                         status=ExperimentStatus.ONGOING)
        db_session.add(exp)
        db_session.commit()
        return exp

    def test_patch_sets_and_clears_is_outlier(self, client, db_session):
        self._mk(db_session, "OUTL_API_001a", 920001)
        resp = client.patch("/api/experiments/OUTL_API_001a", json={"is_outlier": True})
        assert resp.status_code == 200
        assert resp.json()["is_outlier"] is True

        resp = client.patch("/api/experiments/OUTL_API_001a", json={"is_outlier": False})
        assert resp.status_code == 200
        assert resp.json()["is_outlier"] is False

    def test_get_detail_includes_is_outlier(self, client, db_session):
        self._mk(db_session, "OUTL_API_002a", 920002)
        client.patch("/api/experiments/OUTL_API_002a", json={"is_outlier": True})
        data = client.get("/api/experiments/OUTL_API_002a").json()
        assert data["is_outlier"] is True

    def test_patch_is_outlier_writes_modifications_log(self, client, db_session):
        exp = self._mk(db_session, "OUTL_API_003a", 920003)
        client.patch("/api/experiments/OUTL_API_003a", json={"is_outlier": True})
        db_session.expire_all()
        logs = db_session.execute(
            sa_select(ModificationsLog).where(ModificationsLog.experiment_fk == exp.id)
        ).scalars().all()
        assert any(
            l.new_values == {"is_outlier": True} and l.old_values == {"is_outlier": False}
            for l in logs
        )

    def test_list_items_include_is_outlier(self, client, db_session):
        self._mk(db_session, "OUTL_API_004a", 920004)
        client.patch("/api/experiments/OUTL_API_004a", json={"is_outlier": True})
        data = client.get("/api/experiments", params={"search": "OUTL_API_004a"}).json()
        assert data["items"][0]["is_outlier"] is True
```

Append to `tests/api/test_experiment_rollup.py` (inside `TestRollupEndpoint` and `TestReplicateGroupEndpoint` respectively, reusing that file's `_make_experiment` / `_add_primary_scalar` helpers and `reporting_views` fixture):

```python
    def test_rollup_excludes_outlier_flagged_member(self, client, db_session, reporting_views):
        _make_experiment(db_session, "RUP_003", 9765)
        members = []
        for i, letter in enumerate("abc"):
            member = _make_experiment(db_session, f"RUP_003{letter}", 9766 + i)
            _add_primary_scalar(db_session, member, 7.0, float(i + 1))  # 1, 2, 3
            members.append(member)
        members[2].is_outlier = True
        db_session.commit()
        (row,) = client.get("/api/experiments/RUP_003a/rollup").json()
        assert row["n_replicates"] == 2
        assert row["mean_gross_ammonium_mM"] == pytest.approx(1.5)
```

```python
    def test_replicate_group_exposes_is_outlier(self, client, db_session):
        _make_experiment(db_session, "RGRP_OUT_001", 9795)
        flagged = _make_experiment(db_session, "RGRP_OUT_001a", 9796)
        flagged.is_outlier = True
        db_session.commit()
        data = client.get("/api/experiments/RGRP_OUT_001/replicate-group").json()
        assert data["parent"]["is_outlier"] is False
        assert data["members"][0]["is_outlier"] is True
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/api/test_experiments.py -k Outlier -v && .venv/Scripts/python -m pytest tests/api/test_experiment_rollup.py -v`
Expected: the new tests FAIL — `is_outlier` KeyError in responses (Pydantic drops unknown fields) and/or the PATCH is a silent no-op (`ExperimentUpdate` rejects the unknown field → response lacks `is_outlier`). Pre-existing rollup tests PASS.

- [ ] **Step 3: Add the schema fields**

In `backend/api/schemas/experiments.py`:

`ExperimentUpdate` — add after `status`:

```python
    is_outlier: Optional[bool] = None
```

`ExperimentListItem` — add after `replicate_label` (~line 48):

```python
    is_outlier: bool = False
```

`ExperimentResponse` — add after `replicate_label` (~line 84):

```python
    is_outlier: bool = False
```

`ReplicateGroupMember` — add after `status` (~line 119):

```python
    is_outlier: bool = False
```

- [ ] **Step 4: Add the ModificationsLog audit block to the PATCH router**

In `backend/api/routers/experiments.py::update_experiment`, directly after `old_date = exp.date  # capture before mutation` (~line 808), add:

```python
    old_is_outlier = exp.is_outlier  # capture before mutation
```

Directly after the existing `if "date" in data:` ModificationsLog block (ends ~line 823 with the `log.info("experiment_date_updated", ...)` line), add:

```python
    if "is_outlier" in data:
        db.add(ModificationsLog(
            experiment_id=exp.experiment_id,
            experiment_fk=exp.id,
            modified_by=current_user.uid,
            modification_type="update",
            modified_table="experiments",
            old_values={"is_outlier": old_is_outlier},
            new_values={"is_outlier": data["is_outlier"]},
        ))
        log.info("experiment_outlier_updated", experiment_id=exp.experiment_id,
                 is_outlier=data["is_outlier"], user=current_user.uid)
```

(No other router change: the generic setattr loop already writes the column, and `_build_list_item` already copies it.)

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/api/test_experiments.py tests/api/test_experiment_rollup.py -v`
Expected: ALL PASS (new and pre-existing).

- [ ] **Step 6: Run the API + schema regression net**

Run: `.venv/Scripts/python -m pytest tests/api/ tests/services/ -q`
Expected: all pass, 0 new failures.

- [ ] **Step 7: Commit**

```bash
git add backend/api/schemas/experiments.py backend/api/routers/experiments.py tests/api/test_experiments.py tests/api/test_experiment_rollup.py
git commit -m "[#70] Expose is_outlier through experiments API

- PATCH accepts is_outlier with ModificationsLog audit entry
- Response/list/replicate-group schemas carry the flag
- Tests added: yes
- Docs updated: no (Task 4)"
```

---

### Task 3: Frontend — outlier toggle, badge, grouped-view annotation

**Files:**
- Modify: `frontend/src/api/experiments.ts` (interfaces + patch payload)
- Modify: `frontend/src/pages/ExperimentDetail/index.tsx` (badge + toggle + replicate-group query)
- Modify: `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx` (member "(outlier)" annotation)
- Modify: `frontend/src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx` (fixtures + new test)
- Create: `frontend/src/pages/ExperimentDetail/__tests__/OutlierToggle.test.tsx`

**Interfaces:**
- Consumes: `is_outlier: boolean` on `GET /api/experiments/{id}` (detail), list items, and replicate-group members; `PATCH /api/experiments/{id}` body `{ is_outlier: boolean }` — exactly as produced by Task 2.
- Produces: no downstream consumers.

UI decisions (locked for this task): toggle button lives in the detail page "Quick actions" row and shows ONLY when the experiment is part of a replicate set (`replicate_label !== null` OR its replicate group has ≥1 lettered member — covers the group parent, which is itself vial 0). Badge (`Badge variant="warning"`, already exported from `@/components/ui`) renders next to the StatusBadge when flagged. GroupedResultsView keeps charting flagged members (their individual data stays visible) but annotates their name/link with `(outlier)`.

- [ ] **Step 1: Update the API types**

In `frontend/src/api/experiments.ts`:

`ExperimentListItem` — after `replicate_label: string | null`:

```typescript
  is_outlier: boolean
```

`ExperimentDetail` — after `replicate_label: string | null`:

```typescript
  is_outlier: boolean
```

`ReplicateGroupMember` — after `status: ExperimentStatus | null`:

```typescript
  is_outlier: boolean
```

`CreatedReplicate` — after `replicate_label: string | null`:

```typescript
  is_outlier: boolean
```

`experimentsApi.patch` payload type — add:

```typescript
      is_outlier?: boolean
```

- [ ] **Step 2: Write the failing GroupedResultsView test**

In `frontend/src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx`, first add `is_outlier: false` to the existing `parent` and `SERUM_001a` mock members and `is_outlier: true` to `SERUM_001b` in the `beforeEach` `getReplicateGroup` mock (required — the interface field is non-optional, `tsc` fails otherwise). Then append:

```typescript
  it('annotates outlier members in drill-in links', async () => {
    render(<GroupedResultsView experimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByRole('link', { name: /SERUM_001b.*outlier/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'SERUM_001a' })).toBeInTheDocument()
  })
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx`
Expected: new test FAILS (no `(outlier)` text); pre-existing 3 tests PASS.

- [ ] **Step 4: Annotate outliers in GroupedResultsView**

In `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx`, change the drill-in links block:

```tsx
          {seriesEntities.map((m) => (
            <Link
              key={m.id}
              to={`/experiments/${m.experiment_id}`}
              className="font-mono-data text-red-400 hover:text-red-300"
            >
              {m.experiment_id}
            </Link>
          ))}
```

to:

```tsx
          {seriesEntities.map((m) => (
            <Link
              key={m.id}
              to={`/experiments/${m.experiment_id}`}
              className={`font-mono-data ${m.is_outlier ? 'text-ink-muted line-through hover:text-ink-secondary' : 'text-red-400 hover:text-red-300'}`}
            >
              {m.experiment_id}
              {m.is_outlier ? ' (outlier)' : ''}
            </Link>
          ))}
```

and the individual `Line` name from:

```tsx
                  name={m.replicate_label ? `replicate ${m.replicate_label}` : 'replicate 0'}
```

to:

```tsx
                  name={`${m.replicate_label ? `replicate ${m.replicate_label}` : 'replicate 0'}${m.is_outlier ? ' (outlier)' : ''}`}
```

- [ ] **Step 5: Run GroupedResultsView tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx`
Expected: all PASS.

- [ ] **Step 6: Write the failing detail-page toggle test**

Create `frontend/src/pages/ExperimentDetail/__tests__/OutlierToggle.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    get: vi.fn(),
    patch: vi.fn(),
    getReplicateGroup: vi.fn(),
    getResults: vi.fn(),
    getRollup: vi.fn(),
  },
}))
vi.mock('@/api/conditions', () => ({
  conditionsApi: { getByExperiment: vi.fn().mockRejectedValue(new Error('none')) },
}))

import { ExperimentDetailPage } from '../index'
import { experimentsApi } from '@/api/experiments'
import type { ExperimentDetail } from '@/api/experiments'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
})

function renderPage(experimentId: string) {
  return render(
    <MemoryRouter initialEntries={[`/experiments/${experimentId}`]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/experiments/:id" element={<ExperimentDetailPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

const BASE_DETAIL: ExperimentDetail = {
  id: 2,
  experiment_id: 'SERUM_001a',
  experiment_number: 101,
  status: 'ONGOING',
  researcher: null,
  date: null,
  sample_id: null,
  base_experiment_id: 'SERUM_001',
  parent_experiment_fk: 1,
  replicate_label: 'a',
  is_outlier: false,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: null,
  conditions: null,
  notes: [],
  modifications: [],
}

beforeEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
  vi.mocked(experimentsApi.get).mockResolvedValue(BASE_DETAIL)
  vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
    base_experiment_id: 'SERUM_001',
    parent: { id: 1, experiment_id: 'SERUM_001', replicate_label: null, status: 'ONGOING', is_outlier: false },
    members: [{ id: 2, experiment_id: 'SERUM_001a', replicate_label: 'a', status: 'ONGOING', is_outlier: false }],
  })
  vi.mocked(experimentsApi.patch).mockResolvedValue({ ...BASE_DETAIL, is_outlier: true })
})

describe('outlier toggle', () => {
  it('shows Mark as outlier for a replicate member and patches on click', async () => {
    const user = userEvent.setup()
    renderPage('SERUM_001a')
    const btn = await screen.findByRole('button', { name: /mark as outlier/i })
    await user.click(btn)
    await waitFor(() =>
      expect(experimentsApi.patch).toHaveBeenCalledWith('SERUM_001a', { is_outlier: true }),
    )
  })

  it('shows badge and Include in rollup when flagged', async () => {
    vi.mocked(experimentsApi.get).mockResolvedValue({ ...BASE_DETAIL, is_outlier: true })
    renderPage('SERUM_001a')
    expect(await screen.findByRole('button', { name: /include in rollup/i })).toBeInTheDocument()
    expect(screen.getByText(/excluded from group stats/i)).toBeInTheDocument()
  })

  it('hides the toggle for a standalone experiment', async () => {
    vi.mocked(experimentsApi.get).mockResolvedValue({
      ...BASE_DETAIL, experiment_id: 'SERUM_099', base_experiment_id: null,
      parent_experiment_fk: null, replicate_label: null,
    })
    vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
      base_experiment_id: 'SERUM_099',
      parent: { id: 9, experiment_id: 'SERUM_099', replicate_label: null, status: 'ONGOING', is_outlier: false },
      members: [],
    })
    renderPage('SERUM_099')
    await screen.findByRole('heading', { name: 'SERUM_099' })
    expect(screen.queryByRole('button', { name: /mark as outlier/i })).not.toBeInTheDocument()
  })
})
```

Adjust mock shape only if the module under test imports something not stubbed (add further `vi.fn()` members to the mock as vitest errors dictate — do not weaken the assertions). Two known adaptation points: `useExperimentIdValidation` may call `experimentsApi.checkExists` (add `checkExists: vi.fn().mockResolvedValue({ exists: false })` if needed), and if `useToast` requires a provider, wrap the rendered tree in the toast provider exported from `@/components/ui` — copy the pattern from an existing page test (e.g. `frontend/src/pages/__tests__/ExperimentList.test.tsx`).

- [ ] **Step 7: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/pages/ExperimentDetail/__tests__/OutlierToggle.test.tsx`
Expected: FAIL — no button matching /mark as outlier/i.

- [ ] **Step 8: Implement the toggle + badge on the detail page**

In `frontend/src/pages/ExperimentDetail/index.tsx`:

Import `Badge` (extend the existing UI import):

```tsx
import { StatusBadge, Badge, Button, Input, PageSpinner, useToast } from '@/components/ui'
```

After the `conditions` useQuery block, add:

```tsx
  const { data: replicateGroup } = useQuery({
    queryKey: ['replicate-group', id],
    queryFn: () => experimentsApi.getReplicateGroup(id!),
    enabled: Boolean(id),
  })
```

After `sampleMutation`, add:

```tsx
  const outlierMutation = useMutation({
    mutationFn: (isOutlier: boolean) => experimentsApi.patch(id!, { is_outlier: isOutlier }),
    onSuccess: (_updated, isOutlier) => {
      queryClient.invalidateQueries({ queryKey: ['experiment'] })
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
      queryClient.invalidateQueries({ queryKey: ['rollup'] })
      queryClient.invalidateQueries({ queryKey: ['replicate-group'] })
      success(isOutlier ? 'Marked as outlier — excluded from group stats' : 'Outlier flag removed')
    },
    onError: (err: unknown) => {
      toastError('Update failed', String(err))
    },
  })
```

After the `if (error || !experiment)` guard, add:

```tsx
  const inReplicateSet =
    experiment.replicate_label !== null || (replicateGroup?.members.length ?? 0) > 0
```

Next to the StatusBadge (directly after `<StatusBadge status={experiment.status} />`):

```tsx
            {experiment.is_outlier && (
              <Badge variant="warning">Outlier — excluded from group stats</Badge>
            )}
```

In the Quick actions row (after the Create Replicates button block, inside the same `flex gap-2` div):

```tsx
        {inReplicateSet && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => outlierMutation.mutate(!experiment.is_outlier)}
            disabled={outlierMutation.isPending}
          >
            {experiment.is_outlier ? 'Include in rollup' : 'Mark as outlier'}
          </Button>
        )}
```

- [ ] **Step 9: Run the frontend verification battery**

```bash
cd frontend
npx vitest run
npx tsc --noEmit
npx eslint src --ext .ts,.tsx
```

Expected: all vitest suites pass (fix any fixture that now misses `is_outlier` — required by the type change; likely candidates: `frontend/src/api/__tests__/experiments.replicates.test.ts`, `frontend/src/components/experiments/CreateReplicatesModal.test.tsx`, `frontend/src/pages/__tests__/ExperimentList.test.tsx`); tsc and eslint zero errors/warnings.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/api/experiments.ts frontend/src/pages/ExperimentDetail/index.tsx frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx frontend/src/pages/ExperimentDetail/__tests__/ frontend/src/api/__tests__/ frontend/src/components/experiments/ frontend/src/pages/__tests__/
git commit -m "[#70] Add outlier toggle to experiment UI

- Detail-page toggle + warning badge for replicate-set members
- GroupedResultsView annotates flagged members as (outlier)
- Tests added: yes
- Docs updated: no (Task 4)"
```

(Only add the test files that actually changed; drop untouched paths from `git add`.)

---

### Task 4: Docs + full verification

**Files:**
- Modify: `.claude/rules/MODELS.md` (Experiment fields + `v_results_scalar_rollup` section)
- Modify: `docs/api/API_REFERENCE.md` (PATCH body + response fields + replicate-group member fields)
- Modify: `docs/user_guide/REPLICATES.md` (new "Flagging an outlier" section)

**Interfaces:**
- Consumes: everything shipped in Tasks 1–3. No code changes in this task.

- [ ] **Step 1: Update MODELS.md**

In `.claude/rules/MODELS.md`, `### Experiment` → **Key Fields**, add after the `researcher, date` bullet:

```markdown
  - `is_outlier` (Boolean, non-null, default `false`): flags a bad vial (leak, cracked septum). Flagged experiments are excluded from `v_results_scalar_rollup` aggregates **including `n_replicates`**, but remain fully visible in all per-row views (`v_results_scalar`, `v_results_h2`, `v_results_icp`, `v_primary_experiment_results`) and on their own pages.
```

In the `### v_results_scalar_rollup` section, replace the scope line:

```markdown
- **Scope:** gross/net ammonium, H2 (micromoles, grams/ton), ferrous iron yield (H2% and NH3%), grams/ton yield, final pH. No outlier filter (P4) and no ICP element aggregation (permanently out of scope).
```

with:

```markdown
- **Scope:** gross/net ammonium, H2 (micromoles, grams/ton), ferrous iron yield (H2% and NH3%), grams/ton yield, final pH. No ICP element aggregation (permanently out of scope).
- **Outlier filter (P4):** rows from experiments with `is_outlier = true` are excluded from all aggregates including `n_replicates` (`WHERE … AND NOT COALESCE(e.is_outlier, false)`). Flagged experiments stay present in every per-row view.
```

- [ ] **Step 2: Update API_REFERENCE.md**

In `docs/api/API_REFERENCE.md`, locate the `PATCH /api/experiments/{experiment_id}` entry (grep for `PATCH /api/experiments`) and add `is_outlier` (optional boolean; writing it appends a ModificationsLog audit entry) to its request body field list. Add `is_outlier: bool` to the documented experiment response/list-item fields and to the replicate-group member fields where those endpoints are documented (grep `replicate-group` and `rollup`). Note on the rollup endpoint that flagged experiments are excluded from all statistics including `n_replicates`.

- [ ] **Step 3: Update the user guide**

In `docs/user_guide/REPLICATES.md`, append a section:

```markdown
## Flagging an outlier

If one vial in a replicate set goes bad (leak, cracked septum, contamination), you can drop it from the group statistics without deleting any data:

1. Open the replicate's experiment page (e.g. `SERUM_001c`).
2. Click **Mark as outlier** in the quick-actions row. An **Outlier — excluded from group stats** badge appears next to the status.
3. The grouped results view and the Power BI rollup (`v_results_scalar_rollup`) immediately recompute mean/median/std **and `n`** without that replicate. The flagged replicate is annotated "(outlier)" in the grouped view.
4. All of the replicate's own data stays intact and visible on its page and in every per-row reporting view.
5. To undo, click **Include in rollup** on the same page. Every flag change is recorded in the experiment's Entry Logs.

The button appears only on experiments that belong to a replicate set (lettered members and the group parent, which is vial 0).
```

- [ ] **Step 4: Full verification battery**

```bash
.venv/Scripts/python -m pytest tests/ -q
cd frontend && npx vitest run && npx tsc --noEmit && npx eslint src --ext .ts,.tsx && npm run build
cd .. && .venv/Scripts/alembic downgrade -1 && .venv/Scripts/alembic upgrade head
.venv/Scripts/python -c "import database.event_listeners; print('views ok')"
```

Expected: backend suite green except the 3 known pre-existing `tests/test_pg_backup_restore.py` failures (local pg_dump toolchain gap — confirm they are the ONLY failures); vitest/tsc/eslint/build clean; migration round-trips; views recreate (`views ok`, no error logs).

- [ ] **Step 5: Commit**

```bash
git add .claude/rules/MODELS.md docs/api/API_REFERENCE.md docs/user_guide/REPLICATES.md docs/project_context/
git commit -m "[#70] Document outlier flag

- MODELS.md, API_REFERENCE.md, REPLICATES.md user guide
- Tests added: no (docs only)
- Docs updated: yes"
```

(`docs/project_context/` copies are produced by the sync hook — include them in the commit if the hook updated them.)

---

## Acceptance mapping (issue #70 P4)

| Acceptance criterion | Where proven |
|---|---|
| Additive `is_outlier` boolean on Experiment only, migration round-trips | Task 1 Steps 3, 9, 10; re-proven Task 4 Step 4 |
| `WHERE NOT COALESCE(e.is_outlier, false)` in `v_results_scalar_rollup`; excluded from mean/median/std AND `n_replicates` | Task 1 Steps 5–8 (view tests), Task 2 rollup endpoint test |
| Flagged replicate fully visible on its own pages / per-row views | Task 1 `test_flagged_replicate_remains_in_per_row_view`; Task 3 keeps individual series charted + detail page unchanged apart from badge |
| Flag exposed in replicate/experiment UI | Task 3 (toggle, badge, grouped-view annotation + tests) |
| Full suite green | Task 4 Step 4 |
