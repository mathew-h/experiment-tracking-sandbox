# Core Flood Schema and Views (#132) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store per-sample core flood flow and inlet/outlet pressure (four columns on `experimental_results`), a core's pore volume (`experimental_conditions.pore_volume_mL`) and the physical sample tube (`experimental_results.sample_tube_number`), and compute cross-sample run values in a new Power BI view `v_core_flood_samples`.

**Architecture:** One purely additive Alembic revision adds five columns to `experimental_results` and one to `experimental_conditions`, and recreates three views. There is no separate core flood table (Mat, 2026-11-03, revising the spec's `core_flood_results`): four fields don't justify a 1:1 child table. Inlet/outlet pressure are stored now so permeability can be computed later (nothing computes it in this issue); pore pressure stays on conditions (`pore_pressure`) and is not a result column. Models and `database/event_listeners.py::_VIEWS` carry the same view SQL, and tests pin the migration's SQL to the startup SQL. Cross-sample values are SQL window functions in the view, not calculation-engine fields. `pore_volume_mL` follows the existing conditions-column pattern (`serum_vial_size_mL`, plan `2026-10-19-serum-vial-size.md`) through the API, the template and the UI. The bulk parser reflects conditions columns, so it is not edited.

**Tech Stack:** SQLAlchemy 2 / Alembic / PostgreSQL, FastAPI + Pydantic 2, React 18 + TypeScript + Vitest.

**Spec:** `Claude outputs/issue-core-flood-schema-and-views.md` (GitHub #132). Parent: `Claude outputs/issue-core-flood-run-page.md` (#131). Task 5 copies both into `docs/issues/`.

**Branch:** `feat/core-flood-schema` (cut from `develop` at `877fe8b`). Mode: **issue**. Commit prefix: `[#132]`. PR: `gh pr create --base develop`. The PR description must cite Mat's 2026-11-03 sign-off on the locked-model changes (additive columns on `ExperimentalResults` and `ExperimentalConditions`).

## Global Constraints

- New Alembic revision ID **`f3b7c2a9d4e1`**, `down_revision = "e9a4c1f7b3d2"` (single head on 2026-11-03). File: `alembic/versions/f3b7c2a9d4e1_core_flood_columns_and_view.py`.
- Purely additive: add `experimental_results.sample_tube_number` (Integer, nullable), `flow_rate_mL_min`, `nitrogen_flow_rate_mL_min`, `inlet_pressure_psi`, `outlet_pressure_psi` on `experimental_results` (Float, nullable), and `experimental_conditions.pore_volume_mL` (Float, nullable). No defaults, no backfill, no DB `CHECK`. Like `serum_vial_size_mL`, the conditions-sheet loop has no per-row SAVEPOINT.
- Mixed-case columns must be double-quoted in raw SQL: `ec."pore_volume_mL"`, `er."flow_rate_mL_min"`, `er."nitrogen_flow_rate_mL_min"`, `sr."sampling_volume_mL"`, `sr."gas_sampling_pressure_MPa"`, `sr."final_conductivity_mS_cm"`.
- `flow_rate_mL_min` is the rate over the interval **ending** at that sample, and `0` means a hold.
- `conditions.flow_rate` stays in place; only its comment changes, to say it is deprecated in favor of `experimental_results.flow_rate_mL_min`.
- No change under `backend/services/calculations/`, `backend/services/bulk_uploads/`, `database/models/enums.py`, or any **existing** file in `alembic/versions/`. Per-sample H2 stays in `scalar_calcs.py`.
- `pore_volume_mL` validation: `Optional[float] = Field(default=None, gt=0)` on Create and Update, so `0` and `-1` return 422.
- Python tests: `.venv/Scripts/pytest` from the repo root. Never run two pytest processes at once. After adding model columns, reset `experiments_test` (`DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO experiments_user;`), because `create_all` does not alter existing tables.
- Out of scope (sub-issues 2–4): no API writing the flow fields or `sample_tube_number`, no Master Results parser edit, and no run page.
- `frontend/package.json` / `package-lock.json` do not change.
- Edit `docs/**` with the Write/Edit tools so the project_context hook fires. Never write into `docs/project_context/` directly.

## Review Focus

1. **Two samples on the same cumulative day** (re-entered sample, or segment boundary). `interval_days` = 0, so `h2_grams_per_ton_per_day` must be NULL, not a division error. Owner: Task 2, `test_zero_interval_gives_null_rate`.
2. **A sample with no liquid volume** (gas-only, `sampling_volume_mL` NULL), or a segment with NULL or 0 `pore_volume_mL`. The cumulative volume carries forward as if 0 was added, and `cumulative_pore_volumes` is NULL on rows with no usable pore volume, again without an error. Owner: Task 2, `test_null_volume_and_missing_pore_volume`.
3. **Rows that are not core flood primary samples.** A non-primary result row, or a Serum experiment that shares a base ID, must not appear in the view or shift a run's sums. Owner: Task 2, `test_excludes_non_primary_and_non_core_flood`.
4. **Downgrade after the API has started on the new code.** The views then depend on the new columns. Downgrade must drop `v_core_flood_samples` and restore the old `v_dim_timepoints` and `v_experiment_conditions` before dropping the columns. Owner: Task 2 rehearsal, which imports `database.event_listeners` before `downgrade -1`.
5. **Zero entered for pore volume in the New Experiment wizard.** The experiment is created first and the conditions POST then fails with 422, which leaves an experiment without conditions. Step 2 must block Next, the same way an invalid vial size does. Owner: Task 4, Step2 test.

Known and accepted: `CF_020_5_Brine` parses to base `CF_020_5`, so it forms its own one-row run rather than counting as a variant. Renaming it during the run-page cleanup fixes this; the view does not special-case it.

---

## File Map

| File | Change | Task |
|---|---|---|
| `database/models/results.py` | + five `ExperimentalResults` columns | 1 |
| `database/models/conditions.py` | + `pore_volume_mL`; `flow_rate` comment | 1 |
| `alembic/versions/f3b7c2a9d4e1_core_flood_columns_and_view.py` | **new** | 1, 2 |
| `database/event_listeners.py` | `v_dim_timepoints` + tube; `v_experiment_conditions` + pore volume; + `v_core_flood_samples` | 1, 2 |
| `tests/models/test_core_flood_schema.py` | **new**: columns, chain, SQL parity | 1, 2 |
| `tests/api/test_core_flood_view.py` | **new**: view values | 2 |
| `backend/api/schemas/conditions.py` | + `pore_volume_mL` on Create/Update/Response | 3 |
| `tests/api/test_conditions.py` | + accept/reject tests | 3 |
| `backend/api/routers/bulk_uploads.py` | template header + example cell + instruction row | 3 |
| `tests/api/test_bulk_uploads.py` | + header test | 3 |
| `frontend/src/api/conditions.ts`, `pages/NewExperiment/{fieldVisibility.ts,Step2Conditions.tsx,index.tsx}`, `pages/ExperimentDetail/ConditionsTab.tsx` + their `__tests__` | UI | 4 |
| `.claude/rules/MODELS.md`, `docs/CALCULATIONS.md`, `docs/POWERBI_MODEL.md`, `docs/api/API_REFERENCE.md`, `docs/upload_templates/new_experiments.md`, `docs/issues/issue-core-flood-*.md`, `docs/issues/issue-master-upload-tube-number.md`, `docs/working/issue-log.md` | docs | 5 |

---

### Task 1: Model columns and the two extended views

**Files:**
- Modify: `database/models/results.py` (after `is_primary_timepoint_result`, line ~32), `database/models/conditions.py:56,71`
- Create: `alembic/versions/f3b7c2a9d4e1_core_flood_columns_and_view.py`
- Modify: `database/event_listeners.py` (`v_dim_timepoints` ~line 471, `v_experiment_conditions` ~line 151)
- Test: `tests/models/test_core_flood_schema.py` (new)

**Interfaces:**
- Produces: `ExperimentalResults.sample_tube_number`, `.flow_rate_mL_min`, `.nitrogen_flow_rate_mL_min`, `.inlet_pressure_psi`, `.outlet_pressure_psi`; `ExperimentalConditions.pore_volume_mL`. Migration module constants `_V_DIM_OLD`, `_V_DIM_NEW`, `_V_CONDITIONS_OLD`, `_V_CONDITIONS_NEW` and helper `_recreate(name, sql)` (copied from `e9a4c1f7b3d2`). Task 2 adds to this same migration.

- [ ] **Step 1: Write the failing tests** in `tests/models/test_core_flood_schema.py`, modeled on `tests/models/test_serum_vial_size_column.py` (same `_script_dir`, `_migration_module`, `_norm` helpers; `REVISION="f3b7c2a9d4e1"`, `PARENT="e9a4c1f7b3d2"`):
  - `test_new_columns_nullable`: `ExperimentalResults.__table__.c.sample_tube_number` is a nullable `Integer`; `flow_rate_mL_min`, `nitrogen_flow_rate_mL_min`, `inlet_pressure_psi` and `outlet_pressure_psi` are nullable `Float`, and `pore_pressure_psi` is NOT a column; and `ExperimentalConditions.__table__.c["pore_volume_mL"]` is a nullable `Float`; neither has a default or server default.
  - `test_single_head` (`len(heads) == 1`) and `test_revision_parent`.
  - `test_dim_and_conditions_views_match_startup`: `_norm(mod._V_DIM_NEW) == _norm(dict(_VIEWS)["v_dim_timepoints"])`, and the same for conditions.
  - `test_old_views_are_new_minus_column`: `_V_DIM_NEW` with `er.sample_tube_number,` removed equals `_V_DIM_OLD`, and `_V_CONDITIONS_NEW` with `ec."pore_volume_mL",` removed equals `_V_CONDITIONS_OLD`.

- [ ] **Step 2: Run and confirm failure**

Run: `.venv/Scripts/pytest tests/models/test_core_flood_schema.py -v`
Expected: FAIL with `KeyError` on the columns. `test_single_head` already passes.

- [ ] **Step 3: Models.** On `ExperimentalResults`, add `sample_tube_number = Column(Integer, nullable=True)` (comment: the physical centrifuge tube number, reused across dates, any experiment type) and the four `Float` flow/pressure columns, under a short comment block: Core Flood only, NULL elsewhere; `flow_rate_mL_min` is the rate over the interval ending at this sample and 0 means a hold; inlet/outlet pressure are stored for a future permeability calculation; pore pressure is `experimental_conditions.pore_pressure`. Add `pore_volume_mL = Column(Float, nullable=True)` after `core_volume_cm3` (comment: the core's pore volume in mL, entered by the researcher; denominator of `v_core_flood_samples.cumulative_pore_volumes`). Change the `flow_rate` comment to `# DEPRECATED: per-sample flow lives in experimental_results.flow_rate_mL_min (issue #132); kept, not backfilled`.

- [ ] **Step 4: Startup views.** In `_VIEWS`, add `er.sample_tube_number,` after `er.cumulative_time_post_reaction_days,` in `v_dim_timepoints`, and add `ec."pore_volume_mL",` after `ec.core_volume_cm3,` in `v_experiment_conditions`.

- [ ] **Step 5: Migration** (first part). Write the docstring in the style of `e9a4c1f7b3d2`'s: additive, no backfill, no CHECK, and why the downgrade order matters. `_V_CONDITIONS_OLD` is a copy of `e9a4c1f7b3d2._V_CONDITIONS_NEW`. `_V_DIM_OLD` is the current startup `v_dim_timepoints` text before Step 4. `upgrade()` runs the six `op.add_column` calls, then `_recreate` on both views. `downgrade()` must run in this order: `_recreate` both views with their `_OLD` SQL, then the six `op.drop_column` calls.

- [ ] **Step 6: Reset `experiments_test` and run the tests**

Run: `.venv/Scripts/pytest tests/models/test_core_flood_schema.py tests/views/ -v`
Expected: PASS. Existing `tests/views/` still pass.

- [ ] **Step 7: Commit**

```bash
git add database/models/ database/event_listeners.py alembic/versions/f3b7c2a9d4e1_core_flood_columns_and_view.py tests/models/test_core_flood_schema.py
git commit -F <scratchpad msg>   # "[#132] Add core flood and tube result columns"
```

---

### Task 2: `v_core_flood_samples` view

**Files:**
- Modify: `database/event_listeners.py` (append to `_VIEWS`, after `v_notes`), `alembic/versions/f3b7c2a9d4e1_core_flood_columns_and_view.py`, `tests/models/test_core_flood_schema.py`
- Create: `tests/api/test_core_flood_view.py`

**Interfaces:**
- Consumes: Task 1's models and migration constants.
- Produces: view `v_core_flood_samples`, with one row per primary timepoint of an experiment whose `ec.experiment_type = 'Core Flood'`. Its columns, which sub-issue 2's API and the run page will read, are:
  `result_id, experiment_id, experiment_fk, run_base_id, is_variant, time_post_reaction_days, cumulative_time_post_reaction_days, sample_date` (= `sr.measurement_date`)`, gc_run_date, sample_tube_number, "flow_rate_mL_min", "nitrogen_flow_rate_mL_min", inlet_pressure_psi, outlet_pressure_psi, "sampling_volume_mL", h2_concentration, gas_sampling_volume_ml, "gas_sampling_pressure_MPa", h2_micromoles, h2_mass_ug, h2_grams_per_ton_yield, final_ph, "final_conductivity_mS_cm", "pore_volume_mL", interval_days, "cumulative_liquid_volume_mL", cumulative_pore_volumes, cumulative_h2_grams_per_ton, h2_grams_per_ton_per_day, is_hold_interval`.
  Migration constant `_V_CORE_FLOOD_SAMPLES`.

- [ ] **Step 1: Write the failing view tests** in `tests/api/test_core_flood_view.py`. Use the `reporting_views` fixture pattern from `tests/api/test_experiment_rollup.py:14-23` on `db_session`. Helpers: `_cf_experiment(db, exp_id, number, pore_volume_mL=20.0, experiment_type="Core Flood")` (conditions attached as in the rollup helper), and `_sample(db, exp, cum_days, volume_mL, h2_gpt, flow=None, primary=True)`. `_sample` writes `ExperimentalResults(cumulative_time_post_reaction_days=cum_days, time_post_reaction_days=cum_days, time_post_reaction_bucket_days=cum_days, is_primary_timepoint_result=primary, flow_rate_mL_min=flow)` and a `ScalarResults` with `sampling_volume_mL` and `h2_grams_per_ton_yield` set directly. No listener recalculates `ScalarResults`, so the stored values hold. Query `SELECT ... FROM v_core_flood_samples WHERE run_base_id = :b ORDER BY cumulative_time_post_reaction_days, result_id`, and compare floats with `pytest.approx`.
  - `test_spec_three_sample_run`: `CFV_001` (1 sample, day 1, 10 mL, 0.1) and `CFV_001-2` (days 5 and 8; 0 mL then 30 mL; 0.4 then 0.3), all with pore volume 20. Assert `interval_days == [1, 4, 3]`, `cumulative_liquid_volume_mL == [10, 10, 40]`, `cumulative_pore_volumes == [0.5, 0.5, 2.0]`, `cumulative_h2_grams_per_ton == [0.1, 0.5, 0.8]`, `h2_grams_per_ton_per_day == [0.1, 0.1, 0.1]`, and `is_variant` all false.
  - `test_variant_is_flagged_and_excluded`: the same run plus `CFV_001-2_Bypass` (parent `CFV_001-2`, set by the lineage listener) with one sample at day 6, 50 mL, H2 9.9. The Bypass row has `is_variant is True`, with every derived column (`interval_days` through `is_hold_interval`) `None`. The three segment rows keep exactly the values from the previous test.
  - `test_hold_interval`: flows `0.1, 0, None` give `is_hold_interval == [False, True, None]`.
  - `test_zero_interval_gives_null_rate`: two samples at day 3 give `interval_days[1] == 0` and `h2_grams_per_ton_per_day[1] is None`.
  - `test_null_volume_and_missing_pore_volume`: a segment with `pore_volume_mL=None` and a sample with `volume_mL=None`. The cumulative volume carries forward unchanged across the NULL sample, and that segment's rows have `cumulative_pore_volumes is None`.
  - `test_excludes_non_primary_and_non_core_flood`: a non-primary sample on `CFV_003` and a `CFV_003-2` with `experiment_type="Serum"` are both absent from the view. The run's `cumulative_liquid_volume_mL` counts only the primary Core Flood sample.
  - Add to `tests/models/test_core_flood_schema.py`: `test_core_flood_view_matches_startup`, comparing `_norm(mod._V_CORE_FLOOD_SAMPLES)` with `_norm(dict(_VIEWS)["v_core_flood_samples"])`.

- [ ] **Step 2: Run and confirm failure**

Run: `.venv/Scripts/pytest tests/api/test_core_flood_view.py tests/models/test_core_flood_schema.py -v`
Expected: FAIL with `relation "v_core_flood_samples" does not exist` and `KeyError`.

- [ ] **Step 3: Write the view.** Precede it with a comment block in the `_VIEWS` style that states the interval-ending flow rule and the H2 basis (each sample's H2 is only what was collected since the previous sample, which is why the sums are valid). Structure:

```sql
CREATE VIEW v_core_flood_samples AS
WITH s AS (
    SELECT er.id AS result_id, e.experiment_id, er.experiment_fk,
           e.base_experiment_id AS run_base_id,
           COALESCE(p.experiment_id IS NOT NULL
                    AND left(e.experiment_id, length(p.experiment_id) + 1) = p.experiment_id || '_',
                    false) AS is_variant,
           ... pass-through columns ...
    FROM experimental_results er
    JOIN experiments e               ON e.id = er.experiment_fk
    LEFT JOIN experiments p          ON p.id = e.parent_experiment_fk
    JOIN experimental_conditions ec  ON ec.experiment_fk = e.id
    LEFT JOIN scalar_results sr      ON sr.result_id = er.id
    WHERE er.is_primary_timepoint_result = TRUE AND ec.experiment_type = 'Core Flood'
), w AS (
    SELECT s.*, <interval_days, cumulative volume, cumulative H2 as spec table, OVER win>
    FROM s
    WINDOW win AS (PARTITION BY run_base_id, is_variant
                   ORDER BY cumulative_time_post_reaction_days, result_id
                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
)
SELECT <pass-through>, CASE WHEN is_variant THEN NULL ELSE <derived> END AS <each derived column>
FROM w
```

  `cumulative_pore_volumes` and `h2_grams_per_ton_per_day` divide the outer-level values with `NULLIF(..., 0)`. `is_hold_interval` is `"flow_rate_mL_min" = 0`.

- [ ] **Step 4: Migration** (second part). Add `_V_CORE_FLOOD_SAMPLES`. At the end of `upgrade()`, call `_recreate("v_core_flood_samples", ...)`. At the start of `downgrade()`, before the two `_OLD` recreates, run `op.execute("DROP VIEW IF EXISTS v_core_flood_samples CASCADE")`.

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/pytest tests/api/test_core_flood_view.py tests/models/test_core_flood_schema.py -v`
Expected: PASS.

- [ ] **Step 6: Rehearse the migration on `experiments_test`.** Follow memory `migration-rehearsal-on-experiments-test`; write a scratchpad script with `set -o pipefail` semantics in mind. Steps: `create_all`, then drop the six new columns to simulate `e9a4c1f7b3d2`, then `alembic stamp e9a4c1f7b3d2`, then `alembic upgrade head`. Import `database.event_listeners` with `DATABASE_URL` pointed at the test DB, to simulate API start. Then `alembic downgrade -1`, assert the six columns and `v_core_flood_samples` are gone and that `v_dim_timepoints` / `v_experiment_conditions` exist, then `upgrade head` again and confirm `alembic heads` lists one head. Clean up by dropping all views, `alembic_version` and the tables.
Expected: every step exits 0, and the final `alembic heads` prints `f3b7c2a9d4e1 (head)`.

- [ ] **Step 7: Commit**: `[#132] Add v_core_flood_samples view`.

---

### Task 3: `pore_volume_mL` on the conditions API and the template

**Files:**
- Modify: `backend/api/schemas/conditions.py:21,48,79`, `backend/api/routers/bulk_uploads.py:~964-974,~1022`
- Test: `tests/api/test_conditions.py`, `tests/api/test_bulk_uploads.py`

**Interfaces:**
- Consumes: `ExperimentalConditions.pore_volume_mL` (Task 1).
- Produces: `pore_volume_mL: Optional[float]` in conditions request and response JSON (Task 4's TS type mirrors it).

- [ ] **Step 1: Write the failing tests.** Copy the serum-vial tests in `tests/api/test_conditions.py` (from commit `b298c94`) as models:
  - `test_post_conditions_accepts_pore_volume`: POST with `pore_volume_mL=125.5`, then GET by experiment returns `125.5`.
  - `test_patch_conditions_pore_volume`: PATCH `{"pore_volume_mL": 80.0}` returns 200 with the value.
  - `test_patch_conditions_rejects_nonpositive_pore_volume`, parametrized over `[0, -1]`: returns 422, and a follow-up GET shows the value unchanged.
  - In `tests/api/test_bulk_uploads.py`, `test_new_experiments_template_has_pore_volume`: the conditions sheet's last header is `pore_volume_mL`, the HPHT example cell under it is empty, and the INSTRUCTIONS sheet has a `pore_volume_mL` row.

- [ ] **Step 2: Run and confirm failure**

Run: `.venv/Scripts/pytest tests/api/test_conditions.py tests/api/test_bulk_uploads.py -k "pore_volume" -v`
Expected: FAIL (the field is dropped and PATCH returns 200).

- [ ] **Step 3: Implement.** Add `pore_volume_mL: Optional[float] = Field(default=None, gt=0)` to Create and Update, and `Optional[float] = None` to Response. In the template, append the header `"pore_volume_mL"` after `"initial_alkalinity"`, append `None` to `example_row`, and add the instruction `("pore_volume_mL", "Core Flood only. Pore volume of the core in mL (> 0). Pore volumes flushed = cumulative liquid sample volume / this value. Leave blank for other types.")` after the `serum_vial_size_mL` instruction.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/pytest tests/api/test_conditions.py tests/api/test_bulk_uploads.py tests/services/bulk_uploads/test_new_experiments.py -v`
Expected: PASS, with existing tests unchanged.

- [ ] **Step 5: Commit**: `[#132] Accept pore_volume_mL on conditions API`.

---

### Task 4: Pore volume in the wizard and on the Conditions tab

**Files:**
- Modify: `frontend/src/api/conditions.ts`, `frontend/src/pages/NewExperiment/fieldVisibility.ts`, `Step2Conditions.tsx`, `index.tsx`, `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx`
- Test: `frontend/src/pages/NewExperiment/__tests__/Step2Conditions.test.tsx`, `frontend/src/pages/ExperimentDetail/__tests__/ConditionsTab.buttons.test.tsx`

**Interfaces:**
- Consumes: the API field `pore_volume_mL` (Task 3).

- [ ] **Step 1: Write the failing tests**
  - Step2: with `experimentType="Core Flood"`, a `Pore Volume` input is present, and it is absent for `Serum`. Entering `0` shows "Must be greater than 0" and disables Next. Entering `25` enables Next. A hidden stale `0` (type switched to HPHT) does not block Next.
  - ConditionsTab: with `conditions.pore_volume_mL = 42`, a read-only row labeled "Pore Volume" shows `42` with unit `mL`, and the edit modal's "Pore Volume (mL)" input is seeded with `42`.

- [ ] **Step 2: Run and confirm failure**

Run: `cd frontend && npx vitest run src/pages/NewExperiment/__tests__/Step2Conditions.test.tsx src/pages/ExperimentDetail/__tests__/ConditionsTab.buttons.test.tsx`
Expected: FAIL (no such label).

- [ ] **Step 3: Implement.**
  - Add `pore_volume_mL?: number` to `ConditionsPayload`.
  - Add `'pore_volume_mL'` to the `ConditionField` union and to the `'Core Flood'` set only.
  - In Step2: add `pore_volume_mL: string` to the data type and a `field('Pore Volume', 'pore_volume_mL', ..., 'mL')` after Core Width. Compute an error (`Must be greater than 0` when the value is visible, non-blank, and `!(Number(v) > 0)`) and block Next the same way `vialError` does.
  - In `index.tsx`: default `''`, copy-from `numToStr(conditions.pore_volume_mL)`, payload `toFloat(step2.pore_volume_mL)` only when it is visible for the type.
  - In ConditionsTab: add `<Row label="Pore Volume" value={conditions.pore_volume_mL} unit="mL" />` after Core Width, a modal `Input` "Pore Volume (mL)" with `min={0}` after Core Width, and a seed of `pore_volume_mL: conditions?.pore_volume_mL ?? undefined`.

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: all pass, with no type errors.

- [ ] **Step 5: Commit**: `[#132] Add pore volume to wizard and Conditions tab`.

---

### Task 5: Docs and full verification

**Files:** see File Map, Task 5 row.

- [ ] **Step 1: Copy the specs.** Copy `Claude outputs/issue-core-flood-*.md` and `issue-master-upload-tube-number.md` verbatim into `docs/issues/` with the Write tool. The parent issue's cross-references name these files.
- [ ] **Step 2: `docs/CALCULATIONS.md`.** Add a new section, "Core flood run values (`v_core_flood_samples`)", after the Scalar section. It contains the spec's derived-column table, the interval-ending flow rule (0 = hold), variant exclusion and the `is_variant` rule, the volume basis (`sampling_volume_mL` / `pore_volume_mL`), and the H2 basis sentence. State that these are view columns, not calculation-engine fields.
- [ ] **Step 3: `docs/POWERBI_MODEL.md`.** Add a `v_core_flood_samples` row and section (key `result_id`, joining 1–1 to `v_dim_timepoints`; `run_base_id` is the run). Also add `sample_tube_number` to `v_dim_timepoints` and `pore_volume_mL` to `v_experiment_conditions`.
- [ ] **Step 4: `.claude/rules/MODELS.md`.** Add `sample_tube_number` and the four flow/pressure columns under `ExperimentalResults` (inlet/outlet kept for future permeability) (noting the no-separate-table decision), `pore_volume_mL` and the deprecated `flow_rate` under `ExperimentalConditions`, and a `v_core_flood_samples` entry under Reporting Views. Also cover `docs/api/API_REFERENCE.md` (conditions field) and `docs/upload_templates/new_experiments.md` (new column), plus a `docs/working/issue-log.md` entry.
- [ ] **Step 5: Full suite**

Run: `.venv/Scripts/pytest tests/services/ tests/regression/ tests/api/ tests/models/ tests/views/ -v`
Expected: PASS. If anything fails, compare against `develop` before treating it as a regression (memory `pg-backup-restore-test-order-fragility`).

- [ ] **Step 6:** Run `git status` and confirm the matching `docs/project_context/` copies changed. Commit `[#132] Document core flood schema and view` with `Docs updated: yes`. Then `/complete-task`, and open the PR with `--base develop` citing the 2026-11-03 sign-off.
