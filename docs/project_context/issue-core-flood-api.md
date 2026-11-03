# Core flood API: list runs, read a run, create and edit samples

**Type:** feat
**Area:** `backend/api/routers/core_floods.py`
**Priority:** high
**Related:** issue-core-flood-run-page.md (parent), depends on issue-core-flood-schema-and-views.md

---

## Problem

The run page needs four endpoints: a list of runs, a run with all its segments and samples, and sample create and edit that write the timepoint, scalar, core flood and tube fields together. None exist.

## Impact

Without them the page can't load or write anything, and Power BI and the app would compute run values in different places.

## Fix

New files: `backend/services/core_flood_service.py`, `backend/api/schemas/core_floods.py` and `backend/api/routers/core_floods.py`, with prefix `/api/core-floods`. Register the router in `backend/api/main.py` beside lines 57-59.

**`GET /api/core-floods?scope=active|all&q=`**

- Returns one item per Core Flood `base_experiment_id`:
  - segment count, ONGOING segment IDs, rig (`reactor_slot` of the latest segment)
  - sample count, first and last sample date
  - latest `cumulative_h2_grams_per_ton`
  - a warning count
- `active` means any segment is ONGOING.

**`GET /api/core-floods/{base_id}`**

- `segments`: experiment_id, id, status, date, parent experiment_id, `is_variant`, description note, `pore_volume_mL`, `rock_mass_g`, `reactor_slot`.
- `samples`: rows of `v_core_flood_samples` for the run. Read the view so the app and Power BI share one definition.
- `warnings`, each with a code and the experiment IDs involved:
  - `multiple_roots` (CF_026, CF_027 today)
  - `multiple_ongoing` (CF_027, CF_030 today)
  - `missing_pore_volume`
  - `missing_description`
  - `sample_missing_flow_rate`
- Returns 404 when no Core Flood experiment has that base ID.

**`POST /api/core-floods/{experiment_id}/samples`**

- Returns 422 if the experiment's conditions type isn't Core Flood.
- The body uses model field names; the UI aliases live in the frontend:
  - `measurement_date` (required)
  - `time_post_reaction_days` (optional; default `(measurement_date - experiment.date)` in days, rounded to 4 decimals. `Experiment.date` is nullable (`database/models/experiments.py:20`), so omitting the day on an experiment with no start date returns 422)
  - `gc_run_date` (default `measurement_date`)
  - `sample_tube_number` (`gt=0`)
  - `sampling_volume_mL`, `h2_concentration`, `gas_sampling_volume_ml`, `gas_sampling_pressure_MPa` (all `ge=0`)
  - `final_ph`, `final_conductivity_mS_cm`
  - `flow_rate_mL_min` (required, `ge=0`)
  - `nitrogen_flow_rate_mL_min`, `inlet_pressure_psi`, `outlet_pressure_psi`
- Everything happens in one transaction:
  1. Timepoint row, using the bucket, id-timepoint and newest-wins logic from `backend/api/routers/results.py:87-121`. Extract that block into a shared helper if issue-atomic-result-create.md hasn't already.
  2. Set the flow, pressure and tube fields on the timepoint row, and insert `ScalarResults`.
  3. `recalculate(scalar, db)`.
  4. `update_cumulative_times_for_chain(db, exp.id)` (`backend/services/result_merge_utils.py:233`). `POST /api/results` skips this today, which is how hand-entered rows end up with NULL cumulative time.
  5. One `ModificationsLog` "create" row per table written, with `modified_by=current_user.email`.

**`PATCH /api/core-floods/samples/{result_id}`**

- Every create field is optional except the day, which is not editable. Set `extra="forbid"`.
- Creates the scalar or core flood row if it's missing, so historical samples can be given flow rates.
- Calls `recalculate` when any H2 input changes.
- Writes one `ModificationsLog` row per changed table, with `modified_by` and old and new values for the changed fields only. A no-op PATCH writes nothing.

Cleanup on the run page uses existing endpoints, with no backend change:

- rename: `PATCH /api/experiments/{id}` with `experiment_id` (`backend/api/routers/experiments.py:1267`; lineage is re-derived from the new ID)
- status: `PATCH /api/experiments/{id}/status` (`backend/api/routers/experiments.py:869`)
- description: the notes endpoints
- pore volume: `PATCH /api/conditions/{id}`

## Acceptance criteria

- [x] `tests/api/test_core_floods.py`: the list puts active runs first, and the `q` filter narrows it
- [x] The run endpoint returns the `multiple_roots` and `multiple_ongoing` warnings on a fixture shaped like CF_027
- [x] Creating a sample on a derivation persists the scalar and core flood rows, `h2_micromoles`, and a cumulative time equal to the parent's max day plus the day
- [x] Creating a sample with no `flow_rate_mL_min`, or with a negative value, returns 422, and the experiment's result rows are unchanged
- [x] Create on a non-Core Flood experiment returns 422
- [x] `time_post_reaction_days` defaults from the sample date minus the start date, and `gc_run_date` defaults to the sample date. Omitting the day on an experiment with no start date returns 422
- [x] PATCH of `final_conductivity_mS_cm` persists the value. PATCH with an unknown key returns 422
- [x] PATCH writes `ModificationsLog` rows carrying the caller's email and the changed fields only. A no-op PATCH writes none
- [x] `docs/api/API_REFERENCE.md` has a "Core floods" section
- [x] `.venv/Scripts/pytest tests/services/ tests/regression/ tests/api/ -v` passes

## Notes

This issue uses its own schemas, so it doesn't depend on fixing the gaps in `ScalarUpdate` (issue-scalar-result-edit.md). That issue is still needed for the general Results tab.
