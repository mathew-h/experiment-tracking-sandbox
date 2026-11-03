# Add per-sample core flood columns, pore_volume_mL, sample_tube_number, and the v_core_flood_samples view

**Type:** feat
**Area:** `database/models/results.py`, `database/event_listeners.py`
**Priority:** high
**Related:** issue-core-flood-run-page.md (parent)

---

## Problem

The schema has nowhere to store:

- flow rate per sample (the only `flow_rate` is per experiment, `database/models/conditions.py:71`)
- a core's pore volume
- the physical sample tube number

Nothing computes values that depend on more than one sample in a run, either.

## Impact

Every flow change requires a new experiment. Pore volumes and cumulative H2 can't be reported. Tube numbers in the tracker (Sampling, ICP List and pH sheets) never reach the database.

## Fix

**Migration.** One Alembic revision, purely additive, with both upgrade and downgrade:

- Add five nullable columns to `experimental_results`:

  | Column | Type |
  |---|---|
  | `sample_tube_number` | Integer, nullable (every experiment type) |
  | `flow_rate_mL_min` | Float, nullable (Core Flood) |
  | `nitrogen_flow_rate_mL_min` | Float, nullable (Core Flood) |
  | `inlet_pressure_psi` | Float, nullable (Core Flood) |
  | `outlet_pressure_psi` | Float, nullable (Core Flood) |

  No separate table (Mat, 2026-11-03, revising the original `core_flood_results` design): four fields don't justify a 1:1 child table, a model and a cascade. NULL outside core floods, like `core_height_cm` on conditions.

  `inlet_pressure_psi` and `outlet_pressure_psi` give the pressure drop that, with `flow_rate_mL_min` and the core geometry, a later permeability (Darcy) calculation needs; nothing computes it yet. Pore pressure is not a result column: it is `experimental_conditions.pore_pressure`.
- Add `experimental_conditions.pore_volume_mL` (Float, nullable).
- **Downgrade order matters.** Drop `v_core_flood_samples` first, then recreate the *old* `v_dim_timepoints` and `v_experiment_conditions` definitions, and only then drop the columns. Use the `_recreate()` pattern in `alembic/versions/c4d8f1a2b6e7_typed_notes_reporting_views.py`. `event_listeners.py` recreates every view when the API is imported, so the new views will depend on the new columns.

**Models.**

- `database/models/results.py`: add the five columns to `ExperimentalResults`.
- `database/models/conditions.py`: add `pore_volume_mL`, and change the `flow_rate` comment (line 71) to say it is deprecated in favor of `experimental_results.flow_rate_mL_min`.
- Update `MODELS.md`.

**Conditions plumbing.** This follows the established conditions-column pattern: the parser reflects conditions columns, so it needs no edit. Changes:

- `pore_volume_mL` on `ConditionsCreate` / `ConditionsUpdate` / `ConditionsResponse` (`backend/api/schemas/conditions.py:11,43,69`) with `Field(gt=0)`
- `frontend/src/api/conditions.ts`
- the Core Flood set in `frontend/src/pages/NewExperiment/fieldVisibility.ts:25-30`
- the Row and Input in `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx`
- the new-experiments template header in `backend/api/routers/bulk_uploads.py::_get_template_bytes`

**Views** (`database/event_listeners.py`, `_VIEWS`):

- Add `sample_tube_number` to `v_dim_timepoints`.
- Add `pore_volume_mL` to `v_experiment_conditions`.
- Add `v_core_flood_samples`, with one row per primary timepoint of a Core Flood experiment. It reads `experimental_results`, `experiments` (plus its parent), `experimental_conditions` and `scalar_results`.
  - `run_base_id` = `e.base_experiment_id`.
  - `is_variant` = the experiment has a parent and `left(e.experiment_id, length(p.experiment_id) + 1) = p.experiment_id || '_'`. Against the backup this flags exactly the 8 variants listed in the parent issue, and no sequential segment.
  - Window `w`: `PARTITION BY run_base_id, is_variant ORDER BY cumulative_time_post_reaction_days, result_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. Every derived column below is NULL on variant rows.

| Column | Definition |
|---|---|
| `interval_days` | `cumulative_time - COALESCE(LAG(cumulative_time) OVER w, 0)` |
| `cumulative_liquid_volume_mL` | `SUM(COALESCE(sampling_volume_mL, 0)) OVER w` |
| `cumulative_pore_volumes` | `cumulative_liquid_volume_mL / NULLIF(pore_volume_mL, 0)` |
| `cumulative_h2_grams_per_ton` | `SUM(COALESCE(h2_grams_per_ton_yield, 0)) OVER w` |
| `h2_grams_per_ton_per_day` | `h2_grams_per_ton_yield / NULLIF(interval_days, 0)` |
| `is_hold_interval` | `flow_rate_mL_min = 0` |

The view also passes through the raw inputs with their per-sample H2 values: sample date, GC run date, tube number, the two flow rates, inlet and outlet pressure, liquid volume, the H2 inputs, H2 µmol, H2 µg, H2 g/t, pH and conductivity.

**Docs.**

- `docs/CALCULATIONS.md`: add a "Core flood run values" section with the table above and the interval-ending flow rule.
- `docs/POWERBI_MODEL.md`: add the new view and columns.

## Acceptance criteria

- [ ] `alembic upgrade head`, then `alembic downgrade -1`, then `upgrade head` runs clean on a database holding all views. `alembic heads` shows one head
- [ ] View test (new `tests/api/test_core_flood_view.py`): a run of three samples at cumulative days 1, 5 and 8, with liquid volumes 10, 0 and 30 mL, pore volume 20 mL and H2 g/t 0.1, 0.4 and 0.3, gives:
  - `interval_days` = 1, 4, 3
  - cumulative volume = 10, 10, 40
  - pore volumes = 0.5, 0.5, 2.0
  - cumulative H2 = 0.1, 0.5, 0.8
  - g/t/day = 0.1, 0.1, 0.1
- [ ] A `_Bypass` child of a segment appears with `is_variant = true`, NULL derived columns, and no effect on the segments' sums
- [ ] Conditions PATCH accepts `pore_volume_mL` and rejects 0 with a 422
- [ ] `.venv/Scripts/pytest tests/services/ tests/regression/ tests/api/ -v` passes

## Notes

- The view uses each segment's own `pore_volume_mL`. New segments inherit it through parent auto-copy, and the run page (issue-core-flood-frontend.md) fills it in for older segments.
- The view assumes one conditions row per experiment (see `database/data_migrations/dedupe_conditions_and_backfill_ids_018.py`).
- No calculation-engine registration is needed. The new per-row fields are inputs only, and per-sample H2 is still computed by `recalculate_scalar` (`backend/services/calculations/scalar_calcs.py:64`).
- `cumulative_h2_grams_per_ton` and `h2_grams_per_ton_per_day` rely on each sample's H2 being only what was collected since the previous sample (confirmed by Mat, 2026-11-03). State this basis in the `docs/CALCULATIONS.md` entry.
