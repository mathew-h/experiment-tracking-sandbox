# Expose H2 concentration (ppm) through the results API and the rollup view

**Labels:** `backend`, `database`, `api`
**Depends on:** nothing
**Blocks:** `H2-first results and rollup UI` (issue 04)

## Problem

`ScalarResults.h2_concentration` is the raw measured H2 value in ppm (vol/vol), and it is the number the team reads off the GC. Everything downstream of it is derived: `h2_micromoles`, `h2_mass_ug`, `h2_grams_per_ton_yield`. But ppm is not currently reachable from either place the UI needs it:

1. `GET /api/experiments/{experiment_id}/results` returns `ResultWithFlagsResponse`, which carries `h2_micromoles` and `h2_grams_per_ton_yield` but not `h2_concentration`. The per-result table would have to fire a second request per row (`resultsApi.getScalar`) just to show ppm, which is what the expanded drawer already does.
2. `v_results_scalar_rollup` aggregates H2 micromoles and grams/ton but has no ppm columns, so the rollup chart and table cannot plot or average ppm.

Both are additive gaps. Nothing needs to be renamed or removed.

## Change

### Part 1: results endpoint

Purely additive, no migration.

- `backend/api/schemas/results.py`, `ResultWithFlagsResponse`: add `h2_concentration: Optional[float] = None` alongside the existing `h2_micromoles` / `h2_grams_per_ton_yield` fields
- `backend/api/routers/experiments.py`, `get_experiment_results` (around line 418): add `h2_concentration=scalar.h2_concentration if scalar else None` to the `ResultWithFlagsResponse(...)` construction
- `frontend/src/api/experiments.ts`, `ResultWithFlags` interface: add `h2_concentration: number | null`

No unit field is needed. `MODELS.md` documents `h2_concentration_unit` as always `'ppm'`, and `ScalarResults` stores H2 exclusively in ppm.

### Part 2: rollup view

- `database/event_listeners.py`, the `v_results_scalar_rollup` entry (around line 521): add two aggregates, placed immediately before the existing `mean_h2_micromoles` so the H2 block stays contiguous:

  ```sql
  AVG(sr.h2_concentration)          AS mean_h2_ppm,
  stddev_samp(sr.h2_concentration)  AS sd_h2_ppm,
  ```

  Everything else about the view is unchanged: same grouping key `COALESCE(e.base_experiment_id, e.experiment_id)`, same `is_primary_timepoint_result = TRUE` filter, same `NOT COALESCE(e.is_outlier, false)` outlier exclusion, same `stddev_samp` (n-1) semantics that return NULL when `n_replicates = 1`.

- New Alembic migration that drops and recreates `v_results_scalar_rollup` with the new columns. Follow the existing view-recreation pattern in `alembic/versions/98b849b9f08b_add_is_outlier_to_experiments.py` and `6bd58ee7bf51_normalized_time_buckets.py`. The migration is additive (view only, no table DDL) and `downgrade()` recreates the prior view definition verbatim.

- `backend/api/schemas/results.py`, `RollupTimepointResponse`: add `mean_h2_ppm: Optional[float] = None` and `sd_h2_ppm: Optional[float] = None`. Field names must match the view's column aliases exactly, per the docstring on that class.

- `frontend/src/api/experiments.ts`, `RollupTimepoint` interface: add `mean_h2_ppm: number | null`, `sd_h2_ppm: number | null`

## Notes

- `AVG` over `h2_concentration` is only meaningful because the unit is invariant. If `h2_concentration_unit` ever becomes genuinely variable, this aggregate silently averages mixed units. Worth a comment in the view SQL next to the new lines pointing at the `MODELS.md` invariant.
- Power BI picks up `mean_h2_ppm` / `sd_h2_ppm` for free once the view is recreated, since it queries the view directly.
- Views are also recreated on engine connect by `database/event_listeners.py`, so a dev database picks the change up on next app start even without running the migration. The migration exists so the lab PC and any Alembic-managed environment stay consistent.

## Acceptance criteria

- [ ] `GET /api/experiments/{id}/results` includes `h2_concentration` on every row, `null` where no scalar record exists
- [ ] `GET /api/experiments/{id}/rollup` and `GET /api/experiments/groups/{base_id}/rollup` include `mean_h2_ppm` and `sd_h2_ppm`
- [ ] `sd_h2_ppm` is `null` when `n_replicates = 1`
- [ ] Outlier-flagged replicates are excluded from `mean_h2_ppm` (consistent with every other aggregate in the view)
- [ ] `alembic upgrade head` then `alembic downgrade -1` runs clean, and the view matches its prior definition after downgrade
- [ ] No existing field renamed or removed; all ammonium aggregates untouched

## Tests

- [ ] Backend: `get_experiment_results` returns `h2_concentration` for a result with a scalar record, and `None` for one without
- [ ] Backend: rollup endpoint returns `mean_h2_ppm` matching the mean of member `h2_concentration` values, and `sd_h2_ppm is None` for a single-member group
- [ ] Backend: a group with one member flagged `is_outlier` excludes that member from `mean_h2_ppm` and from `n_replicates`
- [ ] Migration: `alembic downgrade -1` followed by `alembic upgrade head` leaves the view queryable

## Docs

- [ ] `MODELS.md`, the `v_results_scalar_rollup` section: add `mean_h2_ppm` and `sd_h2_ppm` to the columns list and note them in the Scope line
- [ ] `docs/api/API_REFERENCE.md`: add `h2_concentration` to the results response and the two new fields to the rollup response

## Out of scope

- Adding H2 ppm to `v_primary_experiment_results` (it already exposes `h2_concentration` via the scalar join)
- Any change to the H2 derivation math in `backend/services/calculations/`
- Median or percentile aggregates for ppm
