# Issue #83 — Replicate Rollup Bucket Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make hand-entered results (`POST /api/results`, the Add Results modal) populate `time_post_reaction_bucket_days` so the replicate-group rollup aggregates per day; backfill existing null-bucket rows; add the two missing H₂ columns to the Grouped summary table; document the (intended) parent-inclusion behavior.

**Architecture:** `POST /api/results` reuses the existing `normalize_timepoint()` helper (the same one every bulk/merge path uses) to set the bucket server-side, and demotes any existing primary row in the same bucket ("newest wins") so the partial unique index `uq_primary_result_per_experiment_bucket` can't reject the insert. A data-only Alembic migration backfills historical null-bucket rows with the same collision handling. The frontend change is two additional mean±sd columns in `GroupedResultsView.tsx`. Defect #3 is documentation-only (confirmed intended); defect #5 (ammonium `0.00 ± 0.00`) is explicitly out of scope.

**Tech Stack:** FastAPI + SQLAlchemy 2.x + Alembic + PostgreSQL (backend); React 18 + TypeScript + TanStack Query + vitest (frontend); pytest against the Postgres test DB.

## Global Constraints

- **Branch:** `fix/issue-83-rollup-bucket-days` (already created off `develop`). All commits use the issue format: `[#83] <imperative, <50 chars, no trailing period>` with `- Tests added: yes/no` / `- Docs updated: yes/no` body lines.
- **Locked components — zero edits:** `backend/services/bulk_uploads/` (all parsers), `database/models/` (no schema change is needed — `time_post_reaction_bucket_days` already exists), `database/event_listeners.py` (the rollup view SQL is correct; the bug is upstream), enums, Firebase auth. Never delete or rewrite existing files in `alembic/versions/`.
- **Out of scope (per the issue):** defect #5 (`mean_net_ammonium_mM` `0.00 ± 0.00` via `GREATEST` NULL semantics), a `PATCH` endpoint for `ExperimentalResults`, the browser-console 401 note.
- **Servers:** never start, stop, or restart uvicorn (port 8000) or the Vite dev server. Tests only.
- **Backend commands (Windows venv):** run pytest as `.venv/Scripts/python -m pytest <path> -v` from the project root. Alembic as `.venv/Scripts/alembic ...`.
- **Frontend commands:** from `frontend/`: `npx vitest run <path>`, `npx tsc --noEmit`, `npx eslint src --ext .ts,.tsx`. Do NOT touch `package.json`/`package-lock.json` — no new dependencies are needed.
- **Docs sync hook:** a PostToolUse hook auto-copies any file written under `docs/` (except `docs/working/`, `docs/superpowers/`, `docs/project_context/`) into `docs/project_context/`. Never write to `docs/project_context/` directly; DO `git add` the hook-generated copies when committing doc changes.
- **Style:** `structlog` only (never `print`), flake8-clean on touched backend files (`.venv/Scripts/python -m flake8 <files>`), ESLint/Prettier zero new warnings, no `console.log`.
- **Known pre-existing test failures (not yours):** 3 failures in `tests/test_pg_backup_restore.py` (local pg_dump toolchain gap) and 5 pre-existing eslint errors in files this branch doesn't touch. Do not fix or worry about these.

## Background every implementer needs

- `experimental_results.time_post_reaction_bucket_days` (Float, nullable) is the grouping column for `v_results_scalar_rollup` (one row per `(COALESCE(base_experiment_id, experiment_id), bucket)`, primary rows only, outliers excluded). Bulk-upload/merge paths set it via `normalize_timepoint()` (`backend/services/result_merge_utils.py:14` — `round(float(x), 4)`); `POST /api/results` (`backend/api/routers/results.py:75-104`) never sets it, so every hand-entered row lands in a single `bucket=NULL` rollup row.
- **The partial unique index trap:** `uq_primary_result_per_experiment_bucket` is UNIQUE on `(experiment_fk, time_post_reaction_bucket_days) WHERE is_primary_timepoint_result = true` (`database/models/results.py:10-18`). Postgres treats NULL buckets as distinct, so duplicate same-day hand entries never conflicted before. Once buckets are populated — by the endpoint fix or the backfill — a second primary row in the same bucket violates the index. Both Task 1 and Task 2 must demote the loser primary first.
- The Add Results modal chains `POST /api/results` → `POST /api/results/scalar` (`frontend/src/pages/ExperimentDetail/AddResultsModal.tsx:106-128`). No frontend change is needed for the bucket fix itself.

---

### Task 1: `create_result` sets the bucket and resolves primary collisions

**Files:**
- Modify: `backend/api/routers/results.py:1-16` (imports) and `:75-104` (`create_result`)
- Test: `tests/api/test_results.py` (append), `tests/api/test_experiment_rollup.py` (append)

**Interfaces:**
- Consumes: `normalize_timepoint(Optional[float]) -> Optional[float]` and `apply_id_timepoint(id_timepoint_days, time_post_reaction)` from `backend/services/result_merge_utils.py` (both already exist).
- Produces: `POST /api/results` responses now always have `time_post_reaction_bucket_days == round(resolved_days, 4)` (or `null` when the resolved time is `null`). Any client-supplied bucket value is ignored. When the new row is primary and an existing primary row occupies the same bucket for the same experiment, the existing row is demoted (`is_primary_timepoint_result = False`) — newest wins. Tasks 2–4 rely on exactly this behavior.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_results.py` (uses the existing `_seed` helper and `client`/`db_session` fixtures in that file):

```python
# ── Issue #83: POST /api/results must set time_post_reaction_bucket_days ────


def test_create_result_sets_bucket_from_days(client, db_session):
    """The server derives the bucket from the resolved time (round to 4 dp)."""
    exp, _ = _seed(db_session)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "Day 7",
        "time_post_reaction_days": 7.0,
    })
    assert resp.status_code == 201
    assert resp.json()["time_post_reaction_bucket_days"] == pytest.approx(7.0)


def test_create_result_bucket_rounds_to_4_decimals(client, db_session):
    exp, _ = _seed(db_session)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "odd time",
        "time_post_reaction_days": 7.123456,
    })
    assert resp.status_code == 201
    assert resp.json()["time_post_reaction_bucket_days"] == pytest.approx(7.1235)


def test_create_result_overrides_client_supplied_bucket(client, db_session):
    """The server owns the bucket; a client-sent value must be ignored."""
    exp, _ = _seed(db_session)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "lying client",
        "time_post_reaction_days": 7.0,
        "time_post_reaction_bucket_days": 99.0,
    })
    assert resp.status_code == 201
    assert resp.json()["time_post_reaction_bucket_days"] == pytest.approx(7.0)


def test_create_result_null_days_null_bucket(client, db_session):
    """No time and no ID token → bucket stays null (pre-#83 behavior)."""
    exp, _ = _seed(db_session)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "no time yet",
        "is_primary_timepoint_result": False,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["time_post_reaction_days"] is None
    assert body["time_post_reaction_bucket_days"] is None


def test_create_result_bucket_from_id_timepoint_token(client, db_session):
    """A '-t<days>' ID fills a blank time AND the bucket (issues #81 + #83)."""
    exp = Experiment(experiment_id="RES_T_001-t7", experiment_number=6002,
                     status=ExperimentStatus.ONGOING)
    db_session.add(exp)
    db_session.commit()
    assert exp.id_timepoint_days == 7.0  # sanity: lineage listener parsed the token
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "token vial",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["time_post_reaction_days"] == pytest.approx(7.0)
    assert body["time_post_reaction_bucket_days"] == pytest.approx(7.0)


def test_create_result_same_day_newest_wins(client, db_session):
    """A second primary entry at the same day demotes the first instead of 500ing
    on uq_primary_result_per_experiment_bucket."""
    exp, first = _seed(db_session)  # first: day 0.0, bucket 0.0, primary
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "corrected day-0 entry",
        "time_post_reaction_days": 0.0,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["is_primary_timepoint_result"] is True
    db_session.expire_all()
    old = db_session.get(ExperimentalResults, first.id)
    assert old.is_primary_timepoint_result is False


def test_create_result_nonprimary_leaves_existing_primary(client, db_session):
    exp, first = _seed(db_session)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "extra vial draw",
        "time_post_reaction_days": 0.0,
        "is_primary_timepoint_result": False,
    })
    assert resp.status_code == 201
    db_session.expire_all()
    old = db_session.get(ExperimentalResults, first.id)
    assert old.is_primary_timepoint_result is True
```

Append to `tests/api/test_experiment_rollup.py` (uses that file's existing `reporting_views` fixture and `_make_experiment` helper — this is the end-to-end reproduction of defects #1/#2 from the issue):

```python
class TestRollupFromHandEnteredResults:
    """Issue #83: results created via POST /api/results (the Add Results modal
    path) must land in per-day rollup buckets, not one bucket=null row."""

    def _post_result_with_scalar(self, client, experiment_pk, day, gross_nh4):
        resp = client.post("/api/results", json={
            "experiment_fk": experiment_pk,
            "description": f"day {day}",
            "time_post_reaction_days": day,
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["time_post_reaction_bucket_days"] == pytest.approx(day)
        resp = client.post("/api/results/scalar", json={
            "result_id": body["id"],
            "gross_ammonium_concentration_mM": gross_nh4,
        })
        assert resp.status_code == 201

    def test_hand_entered_results_roll_up_per_day(self, client, db_session, reporting_views):
        _make_experiment(db_session, "RUP_083", 9800)
        a = _make_experiment(db_session, "RUP_083a", 9801)
        b = _make_experiment(db_session, "RUP_083b", 9802)
        db_session.commit()
        # day 7 on both replicates, day 14 on replicate a only — all via the API
        self._post_result_with_scalar(client, a.id, 7.0, 1.0)
        self._post_result_with_scalar(client, b.id, 7.0, 3.0)
        self._post_result_with_scalar(client, a.id, 14.0, 5.0)
        rows = client.get("/api/experiments/RUP_083a/rollup").json()
        assert [r["time_post_reaction_bucket_days"] for r in rows] == [7.0, 14.0]
        day7, day14 = rows
        assert day7["n_replicates"] == 2
        assert day7["mean_gross_ammonium_mM"] == pytest.approx(2.0)
        assert day14["n_replicates"] == 1
        assert day14["mean_gross_ammonium_mM"] == pytest.approx(5.0)
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/api/test_results.py tests/api/test_experiment_rollup.py -v -k "bucket or newest or nonprimary or hand_entered or null_days"`
Expected: the new tests FAIL — bucket assertions get `None` back (and `newest_wins` may 500). Pre-existing tests in both files still PASS.

- [ ] **Step 3: Implement the fix**

In `backend/api/routers/results.py`, change the two import lines:

```python
from sqlalchemy import select, update
```

```python
from backend.services.result_merge_utils import apply_id_timepoint, normalize_timepoint
```

Replace the body of `create_result` (keep the decorator and signature as-is) with:

```python
    """Create a new result timepoint for an experiment."""
    # Validate that experiment_fk references experiments.id (integer PK).
    # The frontend must never pass the string experiment_id in this field.
    exp = db.get(Experiment, payload.experiment_fk)
    if exp is None:
        raise HTTPException(
            status_code=404,
            detail=f"Experiment with id={payload.experiment_fk} not found. "
                   "Pass experiments.id (integer PK), not the string experiment_id.",
        )
    data = payload.model_dump()
    try:
        # Issue #81: '-t<days>' in the experiment ID is canonical for the timepoint.
        data["time_post_reaction_days"] = apply_id_timepoint(
            exp.id_timepoint_days, data.get("time_post_reaction_days"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    # Issue #83: the server owns the bucket — mirror the resolved time and
    # ignore any client-supplied value, so hand-entered rows land in
    # v_results_scalar_rollup's per-day buckets like bulk-uploaded ones.
    bucket = normalize_timepoint(data["time_post_reaction_days"])
    data["time_post_reaction_bucket_days"] = bucket
    if bucket is not None and data["is_primary_timepoint_result"]:
        # Newest wins: demote any existing primary row in this bucket so
        # uq_primary_result_per_experiment_bucket cannot reject the insert.
        db.execute(
            update(ExperimentalResults)
            .where(
                ExperimentalResults.experiment_fk == exp.id,
                ExperimentalResults.time_post_reaction_bucket_days == bucket,
                ExperimentalResults.is_primary_timepoint_result.is_(True),
            )
            .values(is_primary_timepoint_result=False)
        )
    result = ExperimentalResults(**data)
    db.add(result)
    db.commit()
    db.refresh(result)
    log.info("result_created", experiment_fk=result.experiment_fk, result_id=result.id)
    return ResultResponse.model_validate(result)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/api/test_results.py tests/api/test_experiment_rollup.py -v`
Expected: ALL tests in both files PASS (old and new).

- [ ] **Step 5: Lint and commit**

Run: `.venv/Scripts/python -m flake8 backend/api/routers/results.py tests/api/test_results.py tests/api/test_experiment_rollup.py`
Expected: clean (no output).

```bash
git add backend/api/routers/results.py tests/api/test_results.py tests/api/test_experiment_rollup.py
git commit -m "[#83] Set timepoint bucket in POST /api/results

- Bucket mirrors resolved time via normalize_timepoint (server-owned)
- Newest-wins demotion avoids partial-unique-index 500s
- Tests added: yes
- Docs updated: no"
```

---

### Task 2: Alembic data migration — backfill historical null buckets

**Files:**
- Create: `alembic/versions/<generated-hash>_backfill_result_timepoint_buckets.py` (via `alembic revision`, NOT `--autogenerate` — this is data-only, no schema change)
- Test: `tests/test_backfill_bucket_migration.py` (new)

**Interfaces:**
- Consumes: nothing from other tasks (independent of Task 1, but the pair together closes defect #1 for old + new data).
- Produces: module-level SQL constants `DEMOTE_COLLIDING_PRIMARIES_SQL` and `BACKFILL_BUCKETS_SQL` inside the migration file (the test loads the file by glob and executes them). `upgrade()` runs them in that order; `downgrade()` is an intentional no-op (precedent: `alembic/versions/458f344f73d8_clamp_negative_icp_ppm_to_zero.py`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_backfill_bucket_migration.py`:

```python
"""Issue #83: data-migration logic that backfills time_post_reaction_bucket_days.

Loads the migration module from its file (alembic version filenames are not
importable) and executes its SQL constants against the test session, so the
demotion ranking and the backfill are pinned without running alembic itself.
"""
import importlib.util
from pathlib import Path

from sqlalchemy import text

from database.models.experiments import Experiment
from database.models.results import ExperimentalResults, ScalarResults, ICPResults
from database.models.enums import ExperimentStatus


def _load_migration_module():
    matches = list(Path("alembic/versions").glob("*_backfill_result_timepoint_buckets.py"))
    assert len(matches) == 1, f"expected exactly one backfill migration, got {matches}"
    spec = importlib.util.spec_from_file_location("backfill_buckets_migration", matches[0])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_backfill(db):
    mod = _load_migration_module()
    db.execute(text(mod.DEMOTE_COLLIDING_PRIMARIES_SQL))
    db.execute(text(mod.BACKFILL_BUCKETS_SQL))
    db.flush()


def _make_experiment(db, experiment_id, number):
    exp = Experiment(experiment_id=experiment_id, experiment_number=number,
                     status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _add_result(db, exp, days, bucket, primary, with_scalar=False, with_icp=False):
    row = ExperimentalResults(
        experiment_fk=exp.id, description=f"t={days}",
        time_post_reaction_days=days, time_post_reaction_bucket_days=bucket,
        is_primary_timepoint_result=primary,
    )
    db.add(row)
    db.flush()
    if with_scalar:
        db.add(ScalarResults(result_id=row.id, gross_ammonium_concentration_mM=1.0))
    if with_icp:
        db.add(ICPResults(result_id=row.id, fe=1.0))
    db.flush()
    return row


def test_backfill_fills_null_bucket_from_days(db_session):
    exp = _make_experiment(db_session, "BF_001", 9810)
    row = _add_result(db_session, exp, days=7.123456, bucket=None, primary=True)
    _run_backfill(db_session)
    db_session.expire_all()
    assert db_session.get(ExperimentalResults, row.id).time_post_reaction_bucket_days == 7.1235


def test_backfill_leaves_null_days_and_existing_buckets_alone(db_session):
    exp = _make_experiment(db_session, "BF_002", 9811)
    no_days = _add_result(db_session, exp, days=None, bucket=None, primary=True)
    bulk = _add_result(db_session, exp, days=3.0, bucket=3.0, primary=True)
    _run_backfill(db_session)
    db_session.expire_all()
    assert db_session.get(ExperimentalResults, no_days.id).time_post_reaction_bucket_days is None
    assert db_session.get(ExperimentalResults, bulk.id).time_post_reaction_bucket_days == 3.0


def test_backfill_demotes_dataless_row_when_bulk_row_exists(db_session):
    """Hand row (scalar only, null bucket) colliding with a bulk row that has
    scalar+icp and a real bucket: the bulk row keeps primary (data-first rank,
    mirroring result_merge_utils._rank_primary_candidate)."""
    exp = _make_experiment(db_session, "BF_003", 9812)
    hand = _add_result(db_session, exp, days=7.0, bucket=None, primary=True, with_scalar=True)
    bulk = _add_result(db_session, exp, days=7.0, bucket=7.0, primary=True,
                       with_scalar=True, with_icp=True)
    _run_backfill(db_session)
    db_session.expire_all()
    hand_row = db_session.get(ExperimentalResults, hand.id)
    bulk_row = db_session.get(ExperimentalResults, bulk.id)
    assert bulk_row.is_primary_timepoint_result is True
    assert hand_row.is_primary_timepoint_result is False
    assert hand_row.time_post_reaction_bucket_days == 7.0  # still backfilled


def test_backfill_same_rank_ties_break_to_newest(db_session):
    """Two hand-entered rows, same day, both scalar-only: highest id wins."""
    exp = _make_experiment(db_session, "BF_004", 9813)
    older = _add_result(db_session, exp, days=7.0, bucket=None, primary=True, with_scalar=True)
    newer = _add_result(db_session, exp, days=7.0, bucket=None, primary=True, with_scalar=True)
    _run_backfill(db_session)
    db_session.expire_all()
    assert db_session.get(ExperimentalResults, newer.id).is_primary_timepoint_result is True
    assert db_session.get(ExperimentalResults, older.id).is_primary_timepoint_result is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_backfill_bucket_migration.py -v`
Expected: all 4 tests FAIL in `_load_migration_module` with the "expected exactly one backfill migration" assertion (the file doesn't exist yet).

- [ ] **Step 3: Create the migration**

Run: `.venv/Scripts/alembic revision -m "backfill result timepoint buckets"`
This generates `alembic/versions/<hash>_backfill_result_timepoint_buckets.py` with the correct `down_revision` chained to the current head. Replace its body below the revision-identifier block with:

```python
# Issue #83: POST /api/results (the Add Results modal) never set
# time_post_reaction_bucket_days, so every hand-entered result row has a NULL
# bucket and v_results_scalar_rollup lumps a group's whole history into one
# bucket=NULL row. This migration backfills the bucket from
# time_post_reaction_days, rounded to 4 decimals — the same normalization as
# backend/services/result_merge_utils.normalize_timepoint (Postgres ROUND
# half-up vs Python banker's rounding differs only at the 5th decimal, which
# never occurs in real day values).
#
# Because uq_primary_result_per_experiment_bucket is UNIQUE on
# (experiment_fk, time_post_reaction_bucket_days) WHERE is_primary_timepoint_result,
# and NULL buckets never conflicted, some experiments may hold several primary
# rows that land in the same bucket after backfill. Those are demoted first,
# keeping the best-ranked row primary: rows with scalar+icp data beat rows
# with either, which beat dataless rows; ties break to the highest id —
# mirroring result_merge_utils._rank_primary_candidate.

DEMOTE_COLLIDING_PRIMARIES_SQL = """
    WITH eff AS (
        SELECT er.id,
               er.experiment_fk,
               COALESCE(er.time_post_reaction_bucket_days,
                        ROUND(er.time_post_reaction_days::numeric, 4)::float8)
                   AS eff_bucket,
               (sr.id IS NOT NULL)  AS has_scalar,
               (icp.id IS NOT NULL) AS has_icp
        FROM experimental_results er
        LEFT JOIN scalar_results sr  ON sr.result_id  = er.id
        LEFT JOIN icp_results   icp ON icp.result_id = er.id
        WHERE er.is_primary_timepoint_result = TRUE
          AND er.time_post_reaction_days IS NOT NULL
    ),
    ranked AS (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY experiment_fk, eff_bucket
                   ORDER BY CASE
                                WHEN has_scalar AND has_icp THEN 0
                                WHEN has_scalar OR  has_icp THEN 1
                                ELSE 2
                            END,
                            id DESC
               ) AS rn
        FROM eff
    )
    UPDATE experimental_results
    SET is_primary_timepoint_result = FALSE
    WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
"""

BACKFILL_BUCKETS_SQL = """
    UPDATE experimental_results
    SET time_post_reaction_bucket_days =
        ROUND(time_post_reaction_days::numeric, 4)::float8
    WHERE time_post_reaction_bucket_days IS NULL
      AND time_post_reaction_days IS NOT NULL
"""


def upgrade() -> None:
    """Backfill NULL timepoint buckets; demote colliding primaries first."""
    op.execute(DEMOTE_COLLIDING_PRIMARIES_SQL)
    op.execute(BACKFILL_BUCKETS_SQL)


def downgrade() -> None:
    # Which buckets were NULL (and which rows were demoted) is not recoverable
    # after the fact. Downgrade is intentionally a no-op, matching
    # 458f344f73d8_clamp_negative_icp_ppm_to_zero.
    pass
```

Keep the generated header (docstring, `revision`, `down_revision`, imports) exactly as alembic produced it; if the generated file imports `sqlalchemy as sa` unused, delete that import so flake8 stays clean.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_backfill_bucket_migration.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Verify the migration round-trips against the dev DB**

Run: `.venv/Scripts/alembic upgrade head`
Expected: runs the backfill without error (this fixes the `HPHT_901*` test-family rows and any real hand-entered data in the dev DB).
Run: `.venv/Scripts/alembic downgrade -1`
Expected: clean no-op.
Run: `.venv/Scripts/alembic upgrade head`
Expected: clean (both UPDATEs are idempotent — the second run finds no NULL-bucket rows with days set).

- [ ] **Step 6: Lint and commit**

Run: `.venv/Scripts/python -m flake8 alembic/versions/*_backfill_result_timepoint_buckets.py tests/test_backfill_bucket_migration.py`
Expected: clean.

```bash
git add alembic/versions/*_backfill_result_timepoint_buckets.py tests/test_backfill_bucket_migration.py
git commit -m "[#83] Backfill result timepoint buckets

- Data-only migration; demotes colliding primaries data-first, then id DESC
- Downgrade is an intentional no-op (matches ICP clamp precedent)
- Tests added: yes
- Docs updated: no"
```

---

### Task 3: Grouped summary table — add H₂ (g/t) and Fe²⁺ → H₂ (%) columns

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx:185-232` (the `<Table>` block)
- Test: `frontend/src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx`

**Interfaces:**
- Consumes: `RollupTimepoint` fields `mean_h2_grams_per_ton` / `sd_h2_grams_per_ton` / `mean_fe_yield_h2_pct` / `sd_fe_yield_h2_pct` (already present in `frontend/src/api/experiments.ts` and returned by the API — no API-layer change).
- Produces: the rollup table shows 10 columns; header order becomes `Time (d) | n | Gross NH₄ (mM) | Net NH₄ (mM) | NH₄ (g/t) | H₂ (µmol) | H₂ (g/t) | Fe²⁺ → H₂ (%) | Fe²⁺ → NH₃ (%) | pH`.

- [ ] **Step 1: Write the failing test**

In `frontend/src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx`, first update the `ROLLUP` fixture's four H₂-related nulls so the new columns have values to render:

```tsx
    mean_h2_micromoles: null, sd_h2_micromoles: null,
    mean_h2_grams_per_ton: 12.3, sd_h2_grams_per_ton: 2.5,
    mean_fe_yield_h2_pct: 1.23, sd_fe_yield_h2_pct: 0.45,
```

(`mean_h2_micromoles` stays `null` — its existing column renders `—`, untouched.)

Then append this test inside the `describe` block. NOTE: the header strings also appear as `<option>` labels in the Metric dropdown, so query by `columnheader` role, not `getByText`:

```tsx
  it('shows H₂ (g/t) and Fe²⁺ → H₂ (%) mean ± sd columns (issue #83)', async () => {
    render(<GroupedResultsView experimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByRole('columnheader', { name: 'H₂ (g/t)' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Fe²⁺ → H₂ (%)' })).toBeInTheDocument()
    expect(screen.getByText('12.3 ± 2.5')).toBeInTheDocument()
    expect(screen.getByText('1.23 ± 0.45')).toBeInTheDocument()
  })
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`): `npx vitest run src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx`
Expected: the new test FAILS on the `columnheader` assertions; the 4 existing tests still PASS.

- [ ] **Step 3: Add the two columns**

In `GroupedResultsView.tsx`, in the `<TableHead>` row, insert after `<Th>H₂ (µmol)</Th>` and before `<Th>Fe²⁺ → NH₃ (%)</Th>`:

```tsx
            <Th>H₂ (g/t)</Th>
            <Th>Fe²⁺ → H₂ (%)</Th>
```

In the `<TableBody>` row, insert after the `mean_h2_micromoles` `<Td>` and before the `mean_fe_yield_nh3_pct` `<Td>` (formatting mirrors the existing columns — g/t values at 1 decimal like `NH₄ (g/t)`, percentages at 2 decimals like `Fe²⁺ → NH₃ (%)`):

```tsx
              <Td className="font-mono-data">
                {r.mean_h2_grams_per_ton == null
                  ? '—'
                  : `${fmt(r.mean_h2_grams_per_ton, 1)} ± ${fmt(r.sd_h2_grams_per_ton ?? 0, 1)}`}
              </Td>
              <Td className="font-mono-data">
                {r.mean_fe_yield_h2_pct == null
                  ? '—'
                  : `${fmt(r.mean_fe_yield_h2_pct)} ± ${fmt(r.sd_fe_yield_h2_pct ?? 0)}`}
              </Td>
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `frontend/`): `npx vitest run src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx`
Expected: all 5 PASS.

- [ ] **Step 5: Type-check, lint, commit**

Run (from `frontend/`): `npx tsc --noEmit` — expected clean.
Run (from `frontend/`): `npx eslint src --ext .ts,.tsx` — expected: only the 5 known pre-existing errors in files this task didn't touch.

```bash
git add frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx frontend/src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx
git commit -m "[#83] Add H2 columns to grouped rollup table

- H2 (g/t) and Fe2+ -> H2 (%) mean±sd, matching the chart metric list
- Tests added: yes
- Docs updated: no"
```

---

### Task 4: Documentation — parent inclusion (#3), bucket behavior, stale-caveat reversal

**Files:**
- Modify: `.claude/rules/MODELS.md` (the `v_results_scalar_rollup` section)
- Modify: `docs/api/API_REFERENCE.md` (the `GET .../rollup` section near line 76 and the `POST /api/results` `id_timepoint_days` section near line 214)
- Modify: `docs/user_guide/REPLICATES.md` (the "How the rollup reads it" caveat around lines 141–157, plus a new parent-inclusion note)
- Modify: `docs/working/issue-log.md` (append the completion entry — LAST, after the whole-branch verification below)
- Also commit: the untracked `docs/issue-replicate-group-h2-calc-testing-findings.md` and its `docs/project_context/` copy (the investigation artifact this issue is built on). Leave the untracked `EXPERIMENT_ID_NAMING.md` files alone — unrelated to this issue.

**Interfaces:**
- Consumes: the shipped behavior from Tasks 1–3 (server-set bucket, newest-wins demotion, backfill, new table columns).
- Produces: docs only. The PostToolUse hook auto-copies each edited `docs/` file into `docs/project_context/` — `git add` those copies too. `.claude/rules/MODELS.md` is NOT under `docs/` so it has no synced copy.

- [ ] **Step 1: Update `.claude/rules/MODELS.md`**

In the `### v_results_scalar_rollup` section, append two bullets after the existing **Note:** bullet about sequential derivations:

```markdown
- **Parent inclusion (issue #83 — confirmed intended):** the group parent ("replicate 0") shares the grouping key with its lettered replicates (`COALESCE(base_experiment_id, experiment_id)` resolves to the same base for both), so a parent that has its own results is counted in the group mean/median/std exactly like a lettered member. To exclude a parent whose run should not count as a replicate, flag it `is_outlier` — there is deliberately no separate parent opt-out.
- **Hand-entered rows (issue #83):** `POST /api/results` (the Add Results modal) sets `time_post_reaction_bucket_days` from the resolved time via `normalize_timepoint`, and a data migration backfilled all pre-existing NULL-bucket rows — so UI-entered results aggregate per day here just like bulk-uploaded ones. When a new primary entry lands in a bucket that already has a primary row, the newest entry wins and the older row is demoted to non-primary.
```

- [ ] **Step 2: Update `docs/api/API_REFERENCE.md`**

(a) In the `### GET /api/experiments/{experiment_id}/rollup` section, after the response-fields paragraph, add:

```markdown
**Parent inclusion (intended):** the bare group parent's own primary results share the
grouping key with its lettered replicates, so they are averaged into the group stats
like any member. Flag the parent `is_outlier` to exclude it. There is no separate
parent opt-out.
```

(b) Next to the existing `### POST /api/results and POST /api/results/scalar — id_timepoint_days (issue #81)` section, add a sibling subsection:

```markdown
### POST /api/results — timepoint bucketing (issue #83)

- The server sets `time_post_reaction_bucket_days` to the resolved
  `time_post_reaction_days` rounded to 4 decimals (`normalize_timepoint`). Any
  client-supplied `time_post_reaction_bucket_days` is ignored — the field is
  accepted for backward compatibility but always overwritten.
- A `null` resolved time (no `time_post_reaction_days` and no `-t<days>` ID token)
  leaves the bucket `null`; such rows do not appear in `v_results_scalar_rollup`
  buckets.
- **Newest wins:** if the new row is primary (`is_primary_timepoint_result`, default
  `true`) and another primary row already occupies the same bucket for the same
  experiment, the older row is demoted to non-primary. Non-primary inserts leave the
  existing primary untouched.
- Historical rows created before this fix were backfilled by the
  `backfill result timepoint buckets` migration using the same rounding and a
  data-first demotion rule (rows with scalar+ICP outrank rows with either, which
  outrank dataless rows; ties go to the newest row).
```

(c) In the rollup response-fields paragraph (line ~87), no field changes are needed — leave the 19-field list as is.

- [ ] **Step 3: Update `docs/user_guide/REPLICATES.md`**

(a) Replace the stale caveat paragraph (currently at lines ~151–157, beginning `**Caveat — Add Results modal does not bucket.**`) with:

```markdown
Results entered via the Add Results modal (`POST /api/results`) set
`time_post_reaction_bucket_days` automatically from the entered (or ID-encoded) time,
so they land in that day's rollup bucket just like bulk-uploaded rows (fixed in issue
#83; rows entered before the fix were backfilled). If you enter the same day twice for
the same experiment, the newest entry becomes that day's primary row and the older one
is kept but excluded from the rollup.
```

(b) In the section describing the rollup/grouped view (near "How the rollup reads it"), add a short subsection:

```markdown
### The group parent counts toward the stats

The bare parent ID ("replicate 0") is part of its own replicate group: if the parent
has results of its own, they are averaged into the group mean ± sd alongside the
lettered replicates. This is intentional — a parent with data is treated as a group
member. If the parent's run should not count (for example, it was a scouting run under
different handling), flag the parent **Mark as outlier** on its experiment page; the
rollup then excludes it, exactly like an outlier replicate.
```

- [ ] **Step 4: Whole-branch verification**

Run: `.venv/Scripts/python -m pytest tests/ -x -q --ignore=tests/test_pg_backup_restore.py`
Expected: all pass (the ignored file has 3 known pre-existing local-toolchain failures).
Run (from `frontend/`): `npx vitest run` — expected all pass.
Run (from `frontend/`): `npx tsc --noEmit` — expected clean.
Run: `git diff develop --stat` — confirm zero edits to `backend/services/bulk_uploads/`, `database/models/`, `database/event_listeners.py`, and no `frontend/package*.json` changes.

- [ ] **Step 5: Append the issue-log entry**

Append to `docs/working/issue-log.md` (follow the file's established format) an entry titled `## <today's date> | issue #83 — Replicate rollup: bucket hand-entered results, backfill, H₂ table columns` summarizing: files changed per task, the newest-wins demotion decision, the backfill migration + no-op downgrade, defect #3 resolved as docs-only, defect #5 deferred, and the final test totals from Step 4.

- [ ] **Step 6: Commit**

```bash
git add .claude/rules/MODELS.md docs/api/API_REFERENCE.md docs/user_guide/REPLICATES.md docs/working/issue-log.md docs/issue-replicate-group-h2-calc-testing-findings.md docs/project_context/
git commit -m "[#83] Document rollup bucketing and parent inclusion

- Parent-in-aggregate confirmed intended (defect 3, docs-only)
- Reverses the stale issue-81 'modal does not bucket' caveat
- Commits the issue-83 testing-findings doc
- Tests added: no
- Docs updated: yes"
```

---

## Self-Review Notes

- **Spec coverage:** defect #1 → Task 1 (+ Task 2 for historical rows); defect #2 → Task 1's `TestRollupFromHandEnteredResults` end-to-end test; defect #3 → Task 4 (docs-only, per the issue's own triage); defect #4 → Task 3; defect #5 → explicitly out of scope (Global Constraints).
- **Design decisions locked here:** (1) server always overwrites a client-supplied bucket; (2) primary collisions resolve newest-wins at the endpoint (matches `v_primary_experiment_results`' `id DESC` tie-break and modal UX) but data-first in the backfill (an existing bulk row with full data should not lose primary to an empty hand row); (3) backfill ships as an Alembic data migration (runs automatically on the lab PC's nightly `alembic upgrade head`) with a no-op downgrade, following the `458f344f73d8` clamp precedent.
- **Type consistency:** `normalize_timepoint` / `apply_id_timepoint` names and signatures match `backend/services/result_merge_utils.py`; `RollupTimepoint` field names match `backend/api/schemas/results.py::RollupTimepointResponse` and the view aliases; SQL constants' names match between Task 2's migration body and its test.
