# Core Flood API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Four endpoints under `/api/core-floods` — list runs, read a run, create a sample, edit a sample — so the run page (#131 sub-issue 3) can load and write core flood data.

**Architecture:** A run is every Core Flood experiment sharing a `base_experiment_id`. Read endpoints take segment metadata from the ORM and every per-sample and cross-sample value from the `v_core_flood_samples` view (never recomputed in Python), so the app and Power BI share one definition. Writes go through one service module that owns the transaction: timepoint row (shared bucket helper extracted from `POST /api/results`), core flood/tube columns on that row, `ScalarResults`, `recalculate`, `update_cumulative_times_for_chain`, `ModificationsLog`.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2.x, PostgreSQL, pytest + TestClient, structlog.

**Spec:** `docs/issues/issue-core-flood-api.md` (parent: `docs/issues/issue-core-flood-run-page.md`).

## Global Constraints

- Branch `feat/core-flood-api`; commits `[#133] <imperative, <50 chars, no period>` with `- Tests added: yes/no` / `- Docs updated: yes/no` and the `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` trailer; PR `--base develop`.
- **No schema, model, migration or bulk-parser change.** `database/models/` is locked. If a task seems to need one, stop and ask.
- There is no `core_flood_results` table. "Core flood row" in the spec = the columns `sample_tube_number`, `flow_rate_mL_min`, `nitrogen_flow_rate_mL_min`, `inlet_pressure_psi`, `outlet_pressure_psi` on `experimental_results`. Pore pressure is `experimental_conditions.pore_pressure`, not a sample field.
- Core Flood type test: `database/reactor_slot.py::series_prefix(conditions.experiment_type) == "CF"`, the same rule as the view (`core flood` / `coreflood` / `cf`, case/whitespace-insensitive). Never compare against the literal `"Core Flood"`.
- Run values (`interval_days`, `cumulative_liquid_volume_mL`, `cumulative_pore_volumes`, `cumulative_h2_grams_per_ton`, `h2_grams_per_ton_per_day`, `is_hold_interval`, `is_variant`) are read from `v_core_flood_samples`. Do not recompute them.
- Per-sample H2 comes only from `recalculate(scalar, db)` (`backend/services/calculations/registry.py`; requires `import backend.services.calculations` for registration).
- `ModificationsLog.modified_by = current_user.email` (the spec says email; older routers use uid, so don't copy them on this point).
- Tests: `.venv/Scripts/pytest ...`. Never run two pytest processes at the same time (shared `experiments_test` DB).
- The bare `Experiment.date` and `ScalarResults.measurement_date` / `gc_run_date` are `DateTime(timezone=True)`. Request bodies use `datetime`, and Pydantic v2 accepts `"2026-11-03"`. Treat a naive value as UTC before subtracting.

## Review Focus

1. **Sample date before the experiment's start date.** The defaulted day would be negative, so expect 422 with no rows written. Test in Task 3.
2. **Core Flood experiment with no `experimental_conditions` row.** The type can't be read, so expect 422, not 500. Test in Task 3.
3. **Second sample on the same day of the same segment.** Newest wins: the earlier row is demoted to non-primary and drops out of the view. Test in Task 3.
4. **PATCH that clears `h2_concentration` to null.** `h2_micromoles` must clear too, so recalculate runs on a clear, not only on a set. Test in Task 4.
5. **PATCH on a result whose experiment isn't Core Flood → 422, and on a missing result → 404.** Test in Task 4.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `backend/services/result_merge_utils.py` (modify) | New `resolve_primary_timepoint` helper: id-timepoint, bucket, newest-wins demotion. Shared by `POST /api/results` and the core flood create. |
| `backend/api/routers/results.py` (modify, lines 87-121) | `create_result` calls the helper. Behaviour unchanged. |
| `backend/api/schemas/core_floods.py` (create) | Request and response models. |
| `backend/services/core_flood_service.py` (create) | Run membership, warnings, list, run detail, sample create/update, audit rows. The only place with business logic. |
| `backend/api/routers/core_floods.py` (create) | Thin HTTP layer: maps `CoreFloodError` subclasses to 404/422 and commits. |
| `backend/api/main.py` (modify, ~line 67) | `app.include_router(core_floods.router)`. |
| `tests/services/test_timepoint_guard.py` (extend) or `tests/services/test_resolve_primary_timepoint.py` (create) | Helper tests. |
| `tests/api/test_core_floods.py` (create) | Endpoint tests. |
| `docs/api/API_REFERENCE.md`, `docs/working/issue-log.md` | Docs. |

---

### Task 1: Extract the primary-timepoint helper

**Files:**
- Modify: `backend/services/result_merge_utils.py`
- Modify: `backend/api/routers/results.py:87-121`
- Test: `tests/services/test_resolve_primary_timepoint.py` (create)

**Interfaces:**
- Produces: `resolve_primary_timepoint(db: Session, exp: Experiment, time_post_reaction_days: float | None, is_primary: bool = True) -> tuple[float | None, float | None]`, which returns `(resolved_time, bucket)`. It raises `ValueError` (the message from `apply_id_timepoint`) on a conflicting `-t` token. When `bucket is not None and is_primary`, it runs the existing `UPDATE ... SET is_primary_timepoint_result=False` demotion for `(exp.id, bucket)`. It does not insert, flush or commit.

- [ ] **Step 1: Write failing tests** in `tests/services/test_resolve_primary_timepoint.py` (uses the `db_session` fixture from `tests/conftest.py`):
  - `test_returns_time_and_bucket`: an experiment with no `-t` token, `resolve_primary_timepoint(db, exp, 7.0)` gives `(7.0, normalize_timepoint(7.0))`.
  - `test_id_token_fills_blank_time`: experiment `SERUM_RPT_001a-t7` (flush so the lineage listener sets `id_timepoint_days`), `time=None` gives `(7.0, 7.0)`.
  - `test_conflicting_token_raises`: the same experiment with `time=3.0` raises `ValueError`.
  - `test_demotes_existing_primary_in_bucket`: seed a primary result at day 5. After calling with 5.0, the seeded row has `is_primary_timepoint_result is False` (expire it, then reload).
  - `test_non_primary_does_not_demote`: `is_primary=False` leaves the seeded row primary.

- [ ] **Step 2: Run them and confirm they fail.** Run `.venv/Scripts/pytest tests/services/test_resolve_primary_timepoint.py -v`. They should fail with an ImportError for `resolve_primary_timepoint`.

- [ ] **Step 3: Implement the helper.** Move the block at `results.py:94-121` into `resolve_primary_timepoint` without changing it. Keep the issue #81/#83 comments with the code. Then `create_result` becomes: dump the payload → `try: time, bucket = resolve_primary_timepoint(db, exp, data.get("time_post_reaction_days"), data["is_primary_timepoint_result"])` / `except ValueError → 422` → assign both into `data` → insert as before. Remove imports in `results.py` that are no longer used.

- [ ] **Step 4: Run the new tests and the existing results tests.** Run `.venv/Scripts/pytest tests/services/test_resolve_primary_timepoint.py tests/services/test_timepoint_guard.py tests/api/test_results.py -v`. Everything should pass.

- [ ] **Step 5: Commit** with `[#133] Extract primary timepoint helper`.

---

### Task 2: Read endpoints — list runs and read a run

**Files:**
- Create: `backend/api/schemas/core_floods.py`, `backend/services/core_flood_service.py`, `backend/api/routers/core_floods.py`
- Modify: `backend/api/main.py` (register after `additives`)
- Test: `tests/api/test_core_floods.py` (create)

**Interfaces:**
- Produces (schemas, all `ConfigDict(from_attributes=True)` where they wrap ORM rows):
  - `CoreFloodWarning(code: Literal["multiple_roots","multiple_ongoing","missing_pore_volume","missing_description","sample_missing_flow_rate"], experiment_ids: list[str])`
  - `CoreFloodSegment(id: int, experiment_id: str, status: str | None, date: datetime | None, parent_experiment_id: str | None, is_variant: bool, description: str | None, conditions_id: int | None, pore_volume_mL: float | None, rock_mass_g: float | None, reactor_slot: str | None)`. `conditions_id` isn't in the spec but is added because the run page edits pore volume through `PATCH /api/conditions/{id}`.
  - `CoreFloodSample`: one field per `v_core_flood_samples` column, named exactly as the view names them (the column list is in `.claude/rules/MODELS.md` under `v_core_flood_samples`).
  - `CoreFloodRun(base_id: str, segments: list[CoreFloodSegment], samples: list[CoreFloodSample], warnings: list[CoreFloodWarning])`
  - `CoreFloodRunListItem(base_id: str, segment_count: int, ongoing_experiment_ids: list[str], rig: str | None, sample_count: int, first_sample_date: datetime | None, last_sample_date: datetime | None, latest_cumulative_h2_grams_per_ton: float | None, warning_count: int)`
- Produces (service):
  - `class CoreFloodError(Exception)`, with subclasses `CoreFloodNotFound` (→404) and `CoreFloodInvalid` (→422). The router translates these and the service never raises `HTTPException`.
  - `is_core_flood(conditions: ExperimentalConditions | None) -> bool`: `conditions is not None and series_prefix(conditions.experiment_type) == "CF"`.
  - `list_runs(db: Session, scope: Literal["active","all"] = "active", q: str | None = None) -> list[CoreFloodRunListItem]`
  - `get_run(db: Session, base_id: str) -> CoreFloodRun`, which raises `CoreFloodNotFound`.
  - `fetch_samples(db: Session, *, base_ids: list[str] | None = None, result_id: int | None = None) -> list[dict]`. It reads the view `SELECT * FROM v_core_flood_samples` with the filter, ordered `run_base_id, cumulative_time_post_reaction_days NULLS LAST, result_id`. Task 3 reuses it with `result_id`.

**Decisions the implementer can't infer:**
- **Membership:** experiments whose `base_experiment_id` is set, loaded with their conditions (one `select(Experiment, ExperimentalConditions).join(...)` plus a Python filter on `is_core_flood`), grouped by `base_experiment_id`. Use `selectinload` for `parent` and `description_note`. `list_runs` must not issue a query per run: load all Core Flood experiments once, call `fetch_samples` once for every base ID, and group in Python.
- **`is_variant` on segments:** the view's rule, re-expressed in Python as `parent is not None and experiment_id.startswith(parent.experiment_id + "_")`. Segments with no samples aren't in the view, so it can't be read from there. A test pins the Python value against the view's value for a variant with a sample.
- **Warnings (one object per code, only when non-empty, IDs sorted):**
  - `multiple_roots`: non-variant segments with `parent_experiment_fk IS NULL`, when there are more than one.
  - `multiple_ongoing`: segments with status `ONGOING`, when there are more than one.
  - `missing_pore_volume`: non-variant segments with NULL `pore_volume_mL`.
  - `missing_description`: segments with no description.
  - `sample_missing_flow_rate`: experiment IDs (deduplicated) of non-variant view rows with NULL `flow_rate_mL_min`.

  One pure function, `compute_warnings(segments: list[CoreFloodSegment], samples: list[dict]) -> list[CoreFloodWarning]`, is shared by both endpoints. `warning_count = len(warnings)`.
- **List fields:**
  - `rig` is the `reactor_slot` of the latest segment by `(date NULLS FIRST, id)`.
  - `sample_count`, `first_sample_date` and `last_sample_date` are counted over non-variant view rows (`sample_date`).
  - `latest_cumulative_h2_grams_per_ton` is the value from the last non-variant view row in view order.
  - `active` means `ongoing_experiment_ids` is non-empty, and `scope=active` keeps only active runs.
  - `q` is a case-insensitive substring match against `base_id` or any segment `experiment_id`.
  - Sort order: active first, then `last_sample_date` descending with NULLs last, then `base_id`.
- **Run detail:**
  - `segments` are ordered by `(date NULLS LAST, experiment_id)`.
  - `samples` are the view rows for `base_id` in view order, variants included.
  - Return 404 when no Core Flood experiment has that base ID, including when the base exists but isn't Core Flood.
- **Routes:**
  - `GET ""` with `scope: Literal["active","all"] = "active"` and `q: str | None = None`.
  - `GET "/{base_id}"`.
  - Both use `Depends(get_db)` and `Depends(verify_firebase_token)`, the same pattern as `results.py`.

- [ ] **Step 1: Write failing tests** in `tests/api/test_core_floods.py`. Copy the `reporting_views` fixture and the `_cf_experiment`/`_sample` helper shapes from `tests/api/test_core_flood_view.py`, but add `experiment_type`, `status`, `date`, `reactor_number` and `description` parameters. Use run IDs `CFA_*` so they can't collide with the view tests.
  - `test_list_puts_active_runs_first`: run `CFA_001` is COMPLETED with a later last sample, and run `CFA_002` has an ONGOING segment. With `scope=all`, `[i["base_id"] for i in items]` starts `["CFA_002", "CFA_001"]`. With `scope=active`, only `CFA_002` is returned.
  - `test_list_q_filter_narrows`: `q=cfa_002` returns exactly `["CFA_002"]`, and `q=CFA_002-2` (a segment ID) also returns it.
  - `test_list_item_fields`: `segment_count`, `rig == "CF02"`, `sample_count`, and `latest_cumulative_h2_grams_per_ton` equal the view's last `cumulative_h2_grams_per_ton`.
  - `test_list_excludes_non_core_flood`: an HPHT experiment with a base ID doesn't appear, and a type `"CF"` experiment does.
  - `test_run_warnings_cf027_shape`: `CFA_027` (root, ONGOING) and `CFA_027-1` (a second root, because `-1` is a group parent so the listener leaves its parent NULL, also ONGOING) plus `CFA_027-2`. The warnings include `{"code": "multiple_roots", "experiment_ids": ["CFA_027", "CFA_027-1"]}` and a `multiple_ongoing` warning with both IDs.
  - `test_run_missing_field_warnings`: a segment with NULL pore volume, no description, and a sample with NULL flow gives `missing_pore_volume`, `missing_description` and `sample_missing_flow_rate`, each naming that segment.
  - `test_run_samples_come_from_view`: the response's `samples` equal `fetch`-ed view rows for the base (compare `result_id` and `cumulative_h2_grams_per_ton`).
  - `test_segment_is_variant_matches_view`: `CFA_005-2_Bypass1` with a sample, so the segment's `is_variant` equals the view row's `is_variant` (both `True`).
  - `test_run_404_unknown_base` and `test_run_404_non_core_flood_base`.

- [ ] **Step 2: Run them and confirm they fail.** Run `.venv/Scripts/pytest tests/api/test_core_floods.py -v`. They should fail with 404 for every route.

- [ ] **Step 3: Implement the schemas, `list_runs`/`get_run`/`compute_warnings`/`fetch_samples`/`is_core_flood`, the two routes, and the router registration.**

- [ ] **Step 4: Run the tests and confirm they pass.** Run `.venv/Scripts/pytest tests/api/test_core_floods.py -v`.

- [ ] **Step 5: Commit** with `[#133] Add core flood run list and detail`.

---

### Task 3: Create a sample

**Files:**
- Modify: `backend/api/schemas/core_floods.py`, `backend/services/core_flood_service.py`, `backend/api/routers/core_floods.py`
- Test: `tests/api/test_core_floods.py`

**Interfaces:**
- Consumes: `resolve_primary_timepoint` (Task 1), and `is_core_flood`, `fetch_samples`, `CoreFloodSample`, `CoreFloodNotFound`/`CoreFloodInvalid` (Task 2).
- Produces:
  - `CoreFloodSampleCreate`, with `model_config = ConfigDict(extra="forbid")`:
    - `measurement_date: datetime` (required)
    - `time_post_reaction_days: float | None = None`
    - `gc_run_date: datetime | None = None`
    - `sample_tube_number: int | None = Field(None, gt=0)`
    - `sampling_volume_mL`, `h2_concentration`, `gas_sampling_volume_ml`, `gas_sampling_pressure_MPa`: `float | None = Field(None, ge=0)`
    - `final_ph`, `final_conductivity_mS_cm`: `float | None = None`
    - `flow_rate_mL_min: float = Field(..., ge=0)`
    - `nitrogen_flow_rate_mL_min`, `inlet_pressure_psi`, `outlet_pressure_psi`: `float | None = None`
  - Module constants `RESULT_FIELDS = ("sample_tube_number", "flow_rate_mL_min", "nitrogen_flow_rate_mL_min", "inlet_pressure_psi", "outlet_pressure_psi")` and `SCALAR_FIELDS = ("measurement_date", "gc_run_date", "sampling_volume_mL", "h2_concentration", "gas_sampling_volume_ml", "gas_sampling_pressure_MPa", "final_ph", "final_conductivity_mS_cm")`. Task 4 uses them to route each field to its table.
  - `create_sample(db: Session, experiment_id: str, payload: CoreFloodSampleCreate, user_email: str) -> int` returns the new `result_id`. It flushes but does not commit; the router commits and then returns `CoreFloodSample(**fetch_samples(db, result_id=rid)[0])`.
  - `_audit(db, exp, table: str, mod_type: Literal["create","update"], old: dict | None, new: dict, user_email: str) -> None` adds one `ModificationsLog` row. Values pass through a `_jsonable` helper that converts datetimes with `isoformat()`. Task 4 reuses it.
- Route: `POST "/{experiment_id}/samples"`, which returns status 201 and `CoreFloodSample`.

**Order inside `create_sample` (all validation before any write):**
1. Look up the experiment by its string `experiment_id`; if it's missing, raise `CoreFloodNotFound`.
2. Load the conditions row by `experiment_fk` (lowest id). If `not is_core_flood(...)`, raise `CoreFloodInvalid` (422). This covers both a non-Core Flood type and a missing conditions row.
3. Default the day. If `time_post_reaction_days is None`:
   - If `exp.date` is None, raise `CoreFloodInvalid("time_post_reaction_days is required when the experiment has no start date")`.
   - Otherwise set it to `round((measurement_date - exp.date).total_seconds() / 86400, 4)`, with naive values treated as UTC.
   - If the result is `< 0`, raise `CoreFloodInvalid`.
4. Call `resolve_primary_timepoint(db, exp, day, True)`. If it raises `ValueError`, raise `CoreFloodInvalid`.
5. Insert `ExperimentalResults` with the time, the bucket, `is_primary_timepoint_result=True` and the `RESULT_FIELDS`, then flush.
6. Insert `ScalarResults(result_id=..., **SCALAR_FIELDS)` with `gc_run_date` defaulting to `measurement_date`. If `h2_concentration` is not None, also set `h2_concentration_unit="ppm"`. Flush, then call `recalculate(scalar, db)`.
7. Call `update_cumulative_times_for_chain(db, exp.id)`.
8. Write two audit rows, `"experimental_results"` and `"scalar_results"`, each with `mod_type="create"`, `old=None` and `new` set to that table's non-None written fields. Use `experiment_fk=exp.id` and `experiment_id=exp.experiment_id`.

- [ ] **Step 1: Write failing tests.** Every success test uses `reporting_views`. Seed `exp.date = datetime(2026, 10, 1, tzinfo=timezone.utc)`.
  - `test_create_on_derivation_persists_everything`: parent `CFA_100` has a sample at day 10. POST to `CFA_100-2` with `time_post_reaction_days=3`, `flow_rate_mL_min=0.5`, `sample_tube_number=4`, `inlet_pressure_psi=100`, `h2_concentration=1000`, `gas_sampling_volume_ml=5`, and `gas_sampling_pressure_MPa=0.1`. Expect 201. The DB result row then has `flow_rate_mL_min == 0.5`, `sample_tube_number == 4`, `inlet_pressure_psi == 100`, and `cumulative_time_post_reaction_days == 13.0`. The scalar has `h2_micromoles is not None`. The response's `result_id` equals the new row's ID.
  - `test_create_missing_flow_422_no_rows` and `test_create_negative_flow_422_no_rows`: expect 422, and the result count for the experiment is unchanged.
  - `test_create_non_core_flood_422`: an HPHT experiment.
  - `test_create_no_conditions_422` (Review Focus 2).
  - `test_create_defaults_day_and_gc_run_date`: `measurement_date="2026-10-04"` with no day gives `time_post_reaction_days == 3.0`, and the scalar `gc_run_date == measurement_date`.
  - `test_create_no_start_date_without_day_422`: `exp.date=None`.
  - `test_create_date_before_start_422` (Review Focus 1): `measurement_date="2026-09-30"`, and no rows are written.
  - `test_create_same_day_newest_wins` (Review Focus 3): two POSTs at day 2 leave exactly one primary row in that bucket, and the view returns the second `result_id` only.
  - `test_create_writes_audit_rows`: two `ModificationsLog` rows exist with `modified_table` values `{"experimental_results", "scalar_results"}`, `modification_type == "create"`, and `modified_by == "test@addisenergy.com"`.
  - `test_create_unknown_experiment_404`.
  - `test_create_unknown_key_422`.

- [ ] **Step 2: Run them and confirm they fail.** Run `.venv/Scripts/pytest tests/api/test_core_floods.py -k create -v`. They should fail with 405 or 404.

- [ ] **Step 3: Implement the schema, `create_sample`, `_audit`/`_jsonable`, and the route.** The route catches `CoreFloodNotFound` → 404 and `CoreFloodInvalid` → 422 (`detail=str(exc)`), then commits.

- [ ] **Step 4: Run all core flood tests and confirm they pass.** Run `.venv/Scripts/pytest tests/api/test_core_floods.py -v`.

- [ ] **Step 5: Commit** with `[#133] Add core flood sample create`.

---

### Task 4: Edit a sample

**Files:**
- Modify: `backend/api/schemas/core_floods.py`, `backend/services/core_flood_service.py`, `backend/api/routers/core_floods.py`
- Test: `tests/api/test_core_floods.py`

**Interfaces:**
- Consumes: `RESULT_FIELDS`, `SCALAR_FIELDS`, `_audit`, `is_core_flood` and `fetch_samples` (Tasks 2-3).
- Produces:
  - `CoreFloodSampleUpdate`, with `extra="forbid"`. It has the same fields and constraints as `CoreFloodSampleCreate`, all optional. `measurement_date` and `flow_rate_mL_min` become `... | None = None` (`flow_rate_mL_min` keeps `ge=0`). `time_post_reaction_days` is omitted, so sending it returns 422.
  - `update_sample(db: Session, result_id: int, payload: CoreFloodSampleUpdate, user_email: str) -> None`, which raises `CoreFloodNotFound` or `CoreFloodInvalid`.
- Route: `PATCH "/samples/{result_id}"`, which returns `CoreFloodSample`. Register it before `GET "/{base_id}"` to keep the static-segment ordering convention used in `results.py`.

**Behaviour:**
- Look up the result with `db.get(ExperimentalResults, result_id)`; if it's missing, raise `CoreFloodNotFound`. If the experiment isn't Core Flood (`is_core_flood` on its conditions), raise `CoreFloodInvalid`.
- Split `payload.model_dump(exclude_unset=True)` into result fields and scalar fields.
- For each table, compute `changed = {k: v for k, v in new.items() if getattr(row, k) != v}` and `old = {k: getattr(row, k) for k in changed}`.
- If the scalar row is missing and there is at least one scalar field, create it with `ScalarResults(result_id=...)`. Its audit row is `"create"` with `old=None`.
- Set `h2_concentration_unit="ppm"` whenever `h2_concentration` is set to a non-None value.
- If any scalar field changed, or the scalar row was created, call `recalculate(scalar, db)`. This is a superset of the spec's "when any H2 input changes", and it guarantees that clearing H2 also clears the derived fields.
- Write one audit row per table that has a non-empty `changed`, with `mod_type="update"`.
- A no-op request (empty or identical values) writes no rows and no audit, and returns the current sample.
- If no row survives in the view for this result (it's non-primary), return 404 from the route with `detail="Sample is not a primary timepoint"`.

- [ ] **Step 1: Write failing tests.** Seed a sample through the POST endpoint so the scalar exists.
  - `test_patch_conductivity_persists`: `{"final_conductivity_mS_cm": 12.5}` returns 200, and the DB scalar holds 12.5.
  - `test_patch_unknown_key_422` and `test_patch_day_not_editable_422` (`{"time_post_reaction_days": 4}`).
  - `test_patch_audit_changed_fields_only`: PATCH `{"final_ph": 7.1, "flow_rate_mL_min": <the current value>}`. Exactly one new `update` row is written: `modified_table == "scalar_results"`, `old_values == {"final_ph": <old>}`, `new_values == {"final_ph": 7.1}`, and `modified_by == "test@addisenergy.com"`.
  - `test_patch_noop_writes_no_audit`: `{}`, and a payload equal to the current values, both leave the `ModificationsLog` count unchanged.
  - `test_patch_creates_missing_scalar`: a historical result seeded directly with no scalar. PATCH `{"flow_rate_mL_min": 0.2, "final_ph": 7}` sets flow on the result and creates the scalar, writing one `create` audit row and one `update` audit row.
  - `test_patch_h2_change_recalculates`: changing `h2_concentration` changes `h2_micromoles`.
  - `test_patch_clear_h2_clears_micromoles` (Review Focus 4): `{"h2_concentration": None}` makes `h2_micromoles` None.
  - `test_patch_missing_result_404` and `test_patch_non_core_flood_422` (Review Focus 5).

- [ ] **Step 2: Run them and confirm they fail.** Run `.venv/Scripts/pytest tests/api/test_core_floods.py -k patch -v`.

- [ ] **Step 3: Implement `update_sample`, the schema, and the route.**

- [ ] **Step 4: Run all core flood tests and confirm they pass.** Run `.venv/Scripts/pytest tests/api/test_core_floods.py -v`.

- [ ] **Step 5: Commit** with `[#133] Add core flood sample edit`.

---

### Task 5: Docs and full verification

**Files:**
- Modify: `docs/api/API_REFERENCE.md` (new `## Core floods` section before `## Interactive Docs`), `docs/working/issue-log.md` (new `## 2026-11-03 | issue #133 ...` entry in the existing format), `docs/issues/issue-core-flood-api.md` (tick the acceptance boxes that pass).

- [ ] **Step 1: Write the API reference section.** Cover the four routes, the query params, the warning codes and their rules, the create defaults and their 422 cases, the PATCH semantics (`extra="forbid"`, day not editable, missing scalar is created, changed-fields-only audit, a no-op writes nothing), and the fact that `samples` are rows of `v_core_flood_samples`. Also list the run-page cleanup endpoints from the spec, which reuse existing routes. Edit with the Edit tool so the `docs/project_context/` sync hook fires.

- [ ] **Step 2: Run the full verification.** Run `.venv/Scripts/pytest tests/services/ tests/regression/ tests/api/ tests/models/ -q` in one process. Expect 0 failed. The only exception is the 3 known `pg_backup_restore` order failures, if they appear; confirm those against develop before calling them pre-existing.

- [ ] **Step 3: Write the issue-log entry.** Record the files changed, why, the verification counts, and the follow-ups: the run page (sub-issue 3), and `POST /api/results` still not calling `update_cumulative_times_for_chain`, which is out of scope here.

- [ ] **Step 4: Commit** with `[#133] Document core flood API`, including `- Docs updated: yes`.
