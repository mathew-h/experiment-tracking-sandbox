# Audit & Test Plan: Background Ammonium Default (0.2 mM)

> **For agentic workers:** Use `superpowers:executing-plans` to work through
> this task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Branch:** `feat/background-ammonium-default`
**Commit audited:** `1fb7b70`

**Goal:** Verify correctness of all six change layers (model, calc engine, schema,
bulk upload, API endpoint, frontend) and add backend tests for the new endpoint.

---

## File Map

| Action | Path |
|--------|------|
| Audit only | `database/models/results.py` |
| Audit only | `backend/services/calculations/scalar_calcs.py` |
| Audit only | `backend/api/schemas/results.py` |
| Audit only | `backend/services/bulk_uploads/scalar_results.py` |
| Audit only | `backend/api/routers/experiments.py` |
| Audit only | `frontend/src/pages/ExperimentDetail/ResultsTab.tsx` |
| Create | `tests/api/test_background_ammonium.py` |
| Run | pytest on new test file |

---

## Task 1 — Code Audit

Read each changed file and verify the checklist item for it. Record any
finding as a **PASS**, **WARN**, or **FAIL** note inline.

### 1a — `database/models/results.py`

- [ ] `background_ammonium_concentration_mM` column has `default=0.2` (Python ORM default for new objects created without that field set)
- [ ] Column also has `server_default=text("0.2")` (PostgreSQL-level default — covers raw SQL inserts and alembic backfill)
- [ ] `nullable=True` is preserved (value is optional; calcs handle None via fallback)

### 1b — `alembic/versions/a1b2c3d4e5f6_background_ammonium_default_0_2.py`

- [ ] `down_revision` is `'88c99be25944'` (the current head — no skipped links)
- [ ] `upgrade()` calls `op.alter_column` to set `server_default='0.2'`
- [ ] `upgrade()` calls `op.execute` to backfill `WHERE background_ammonium_concentration_mM IS NULL`
- [ ] `downgrade()` removes the server_default (sets it back to `None`)
- [ ] No destructive ops (no DROP COLUMN, no ALTER TYPE, no data loss)

### 1c — `backend/services/calculations/scalar_calcs.py`

- [ ] `calculate_ferrous_iron_yield_nh3`: fallback `else 0.3` → `else 0.2`
- [ ] `recalculate_scalar`: inline fallback `else 0.3` → `else 0.2`
- [ ] Docstring comment updated: `[background defaults to 0.2 mM if None]`
- [ ] No other hardcoded background fallbacks remain (grep for `0.3` in this file)

### 1d — `backend/api/schemas/results.py`

- [ ] `ScalarCreate.background_ammonium_concentration_mM` default is `0.2` not `None`
- [ ] `ScalarUpdate.background_ammonium_concentration_mM` default remains `None` (correct — PATCH must not overwrite existing values silently)
- [ ] `BackgroundAmmoniumUpdate` schema exists with `value: float` and `ge=0.0` validator
- [ ] `BackgroundAmmoniumUpdated` schema exists with `updated: int`

### 1e — `backend/services/bulk_uploads/scalar_results.py`

- [ ] Default insertion appears AFTER the `_overwrite` handling (line ~232) and BEFORE `cleaned_records.append(clean)`
- [ ] Guard is `if 'background_ammonium_concentration_mM' not in clean` — only fills when genuinely absent (does not override an explicit value of `0.0`)
- [ ] Does not interfere with the dry-run path (dry-run reads `cleaned_records` after this point — correct)

### 1f — `backend/api/routers/experiments.py`

- [ ] Route decorator is `@router.patch("/{experiment_id}/background-ammonium")` registered BEFORE `@router.get("/{experiment_id}")` to prevent path shadowing
- [ ] Looks up experiment by string `experiment_id` — 404 if not found
- [ ] Queries `ExperimentalResults.id` values for that experiment, then fetches all `ScalarResults` with `result_id.in_(...)`
- [ ] For each scalar: sets field, calls `db.flush()`, then `recalculate(scalar, db)` — flush before recalculate is required so the registry reads the updated value
- [ ] Single `db.commit()` after the loop (not per-row — atomic)
- [ ] Returns `BackgroundAmmoniumUpdated(updated=len(scalars))`
- [ ] Logs with structlog

### 1g — `frontend/src/pages/ExperimentDetail/ResultsTab.tsx`

- [ ] `DEFAULT_BACKGROUND_NH4 = 0.2` constant defined at module level
- [ ] `useMutation` calls `experimentsApi.setBackgroundAmmonium`
- [ ] `onSuccess` invalidates `['experiment-results', experimentId]` AND `['scalar']` query key
- [ ] Button label shows the constant (`Background NH₄: 0.2 mM`) — not hardcoded string
- [ ] Input has `min="0"` guard
- [ ] Pending state disables the Apply button
- [ ] Error state shown to user on failure
- [ ] No `console.log`

---

## Task 2 — Write Backend Tests

**File:** `tests/api/test_background_ammonium.py`

Tests use the existing `client` and `db_session` fixtures from `tests/api/conftest.py`.

### Setup helpers needed

```python
from database.models.experiments import Experiment
from database.models.conditions import ExperimentalConditions
from database.models.results import ExperimentalResults, ScalarResults
from database.models.enums import ExperimentStatus
import backend.services.calculations  # noqa: F401 — registers calculators


def _make_experiment(db, exp_id="BGNH4_001", number=7001):
    exp = Experiment(experiment_id=exp_id, experiment_number=number, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _make_conditions(db, exp, rock_g=100.0, water_ml=500.0):
    cond = ExperimentalConditions(
        experiment_id=exp.experiment_id,
        experiment_fk=exp.id,
        rock_mass_g=rock_g,
        water_volume_mL=water_ml,
    )
    db.add(cond)
    db.flush()
    return cond


def _make_scalar(db, exp, time_days=7.0, gross_mM=10.0, background_mM=0.2):
    result = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=time_days,
        time_post_reaction_bucket_days=time_days,
        description=f"t={time_days}d",
        is_primary_timepoint_result=True,
    )
    db.add(result)
    db.flush()
    scalar = ScalarResults(
        result_id=result.id,
        gross_ammonium_concentration_mM=gross_mM,
        background_ammonium_concentration_mM=background_mM,
        sampling_volume_mL=100.0,
    )
    db.add(scalar)
    db.flush()
    return scalar
```

### Tests to implement

- [ ] **test_set_background_ammonium_404_unknown_experiment**
  - PATCH `/api/experiments/DOES_NOT_EXIST/background-ammonium` with `{"value": 0.5}`
  - Assert 404

- [ ] **test_set_background_ammonium_no_scalars_returns_zero**
  - Create experiment with no scalar results
  - PATCH with `{"value": 0.5}`
  - Assert 200, `{"updated": 0}`

- [ ] **test_set_background_ammonium_updates_all_scalars**
  - Create experiment + conditions + 3 scalar results (background=0.2)
  - PATCH with `{"value": 0.5}`
  - Assert 200, `{"updated": 3}`
  - Re-fetch all scalars from DB, assert each has `background_ammonium_concentration_mM == 0.5`

- [ ] **test_set_background_ammonium_triggers_recalculation**
  - Create experiment + conditions (rock=100g, water=500mL)
  - Create 1 scalar (gross=10.0 mM, background=0.2, sampling_volume=100mL)
  - Record initial `grams_per_ton_yield`
  - PATCH with `{"value": 5.0}`  (large change to make yield difference obvious)
  - Re-fetch scalar; assert `grams_per_ton_yield` is different from initial value and not None

- [ ] **test_set_background_ammonium_negative_value_rejected**
  - PATCH with `{"value": -0.1}`
  - Assert 422 (Pydantic validation rejects `ge=0.0`)

- [ ] **test_scalar_create_default_background_ammonium**
  - Create an experiment + result entry
  - POST `/api/results/scalar` with payload that omits `background_ammonium_concentration_mM`
  - Assert 201
  - Assert response `background_ammonium_concentration_mM == 0.2`

---

## Task 3 — Run Tests

```bash
cd /c/Users/MathewHearl/Documents/0x_Software/database_sandbox/experiment_tracking_sandbox
python -m pytest tests/api/test_background_ammonium.py -v
```

All 6 tests must pass. If any fail, diagnose and fix before committing.

---

## Task 4 — Commit

```bash
git add tests/api/test_background_ammonium.py
git commit -m "[feat] Add tests for background ammonium default and bulk-apply endpoint

- 6 tests: 404, no-scalars, bulk update, recalc trigger, negative rejection, create default
- Tests added: yes
- Docs updated: no"
```
