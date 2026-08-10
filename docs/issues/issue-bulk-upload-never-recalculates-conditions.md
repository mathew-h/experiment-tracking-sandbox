# New Experiments bulk upload never recalculated conditions derived fields

**Found:** 2026-08-10, investigating a missing Fe²⁺ %H₂ on `SERUM_Catalyst_001a-t3`.
**Status:** code fixed (`fix/bulk-upload-conditions-recalc`); data backfill see below.

## Symptom

`SERUM_Catalyst_001a-t3` had a complete H2 chain and no iron conversion:

```
h2_concentration = 353.88 ppm   gas_sampling_volume_ml = 30   gas_sampling_pressure_MPa = 0.101353
h2_micromoles    = 0.4415       h2_grams_per_ton_yield  = 0.8899
ferrous_iron_yield_h2_pct = NULL
```

Reported as a direct-injection problem, because the affected vials were all DI runs.

## Root cause

`water_to_rock_ratio` and `total_ferrous_iron_g` are stored derived fields written by
`recalculate_conditions()`. Every write path called `recalculate()` after mutating a
conditions row — `backend/api/routers/conditions.py:103` and `:125`,
`backend/api/routers/experiments.py:1329`, `database/lineage_utils.py:603` — except
`backend/services/bulk_uploads/new_experiments.py`, which creates or modifies
conditions rows in three places and only recalculated `ChemicalAdditive`.

`calculate_ferrous_iron_yield_h2` (`backend/services/calculations/scalar_calcs.py:24`)
returns None when `total_ferrous_iron_g` is None, so every scalar result under a
bulk-created experiment lost both Fe²⁺ yield percentages.

The tell was `water_to_rock_ratio` being NULL on the same row, with
`rock_mass_g = 1` and `water_volume_mL = 20`. Two computable derived fields both
empty means `recalculate()` never ran, not that an input was missing.

## Not a DI problem

`SERUM_Cation_001a-t5` is a DI row with the same 30 mL / 14.7 psi geometry and the
same sample `20250616_7`, and it *has* `ferrous_iron_yield_h2_pct = 0.0159%` — its
conditions row was recalculated by a later elemental upload via
`recalculate_conditions_for_samples`. The SERUM_Catalyst_001 vials were created
2026-07-24, after the last FeO upload for that sample, so nothing ever touched them.
The DI correlation is that the DI-era runs were all bulk-created.

## Production measurements (backup 2026-08-10 01:00)

Of 577 scalar rows with a computed `h2_micromoles`, 249 had no Fe²⁺ %H₂:

| Cause | Rows |
|---|---|
| `total_ferrous_iron_g` NULL, sample has FeO on record | 157 (144 experiments) |
| `total_ferrous_iron_g` NULL, sample has no FeO on record | 77 |
| `total_ferrous_iron_g` populated, scalar row stale | 15 |

845 of 1125 conditions rows had `total_ferrous_iron_g` NULL; 185 of those had **both**
derived fields NULL with positive rock mass and water volume.

## Fix

`_recalculate_touched_conditions(db, conditions_ids)` in `new_experiments.py` records
the primary key of every conditions row the upload touches — at all three write sites
— and recalculates them in one pass before returning, after every sheet has finished
mutating them. Keyed on primary keys for two plain reasons: a set of ints deduplicates
a row reached by more than one sheet (the conditions and additives sheets resolve the
same row for the same experiment), so it is recalculated once from its final state; and
an int is the cheapest handle to carry through the parse. Nothing in the uploader can
invalidate a recorded id — `db.expire_all()` runs *before* all three record sites, and
the additives site's `db.add` sits outside that loop's savepoint — so the helper's
"row no longer resolves" skip is defensive only, not reachable through the uploader
today. Each row is recalculated inside its own `db.begin_nested()` SAVEPOINT (the
idiom already used elsewhere in this file), so a failing row rolls back only itself and
neither poisons the next row's `db.get()` with `PendingRollbackError` nor leaves
half-applied mutations for the caller to commit.

The recalculated-row count is appended to the parser's `info_messages`, but
`backend/api/routers/bulk_uploads.py:180` discards that value (`_info`) and nothing in
`backend/api` or `frontend/src` reads it — **so the recalculation is not surfaced in the
UI today.** Known gap, deliberately not fixed here: wiring it through needs a new
response field and frontend rendering. Failures are surfaced, since they go into
`warnings`, which the bulk-upload panel renders.

## Forward-only at the additives path

The fix repairs a legacy NULL row only where the upload actually *mutates* that row.
The conditions sheet does (a pre-existing row being overwritten is recorded), but the
additives path records a conditions row **only when it creates one** — correctly, since
on that path a pre-existing row is never mutated and there would be nothing to
recalculate. The consequence is that an additives-only upload against an experiment
that already has a conditions row will **not** heal one of the legacy NULL rows. Only
the backfill below does that. Do not read this fix as "the uploader repairs whatever it
touches".

## Acceptance criteria

- [x] A conditions-sheet row gets both derived fields computed by the upload. (`test_conditions_sheet_path_recalculates`)
- [x] An `overwrite=TRUE` row that changes `rock_mass_g` recomputes both fields rather than keeping the stale values. (`test_conditions_sheet_overwrite_of_existing_row_recalculates`)
- [x] A parent auto-copy row (no conditions sheet entry) gets its own derived fields. (`test_parent_autocopy_path_recalculates`)
- [x] An experiment reaching conditions creation only via the additives sheet is recalculated. (`test_additives_only_path_recalculates`)
- [x] A bulk-created vial with a DI H2 reading ends up with a non-NULL `ferrous_iron_yield_h2_pct`. (`test_bulk_created_experiment_gets_fe_yield_h2_on_scalar_result`)
- [x] An `overwrite=TRUE` conditions row repairs the **stored** yield on a scalar row that already existed, via the `recalculate_conditions` → `recalculate_scalar` cascade. (`test_overwrite_repairs_stored_yield_on_pre_existing_scalar_row`)
- [ ] The 157 recoverable production rows have Fe²⁺ %H₂ after the backfill. **Not met — only the dev DB has been backfilled**; production runs the runbook below post-deploy.
- [~] The 77 rows whose sample has no FeO on record cannot be fixed here — they need rock characterization uploaded first, which then triggers `recalculate_conditions_for_samples` automatically.

## Backfill

**Dev DB only so far. Production has not been backfilled** — that happens post-deploy,
via the lab PC runbook at the end of this section.

Dev DB, 2026-08-10:

| Measure | Before | After |
|---|---|---|
| conditions rows with `total_ferrous_iron_g` NULL | 732 | 454 |
| conditions rows with both derived fields NULL and inputs present | 137 | 0 |
| scalar rows with `h2_micromoles` but no Fe²⁺ %H₂ | 158 | 87 |

`backfill_total_ferrous_iron_017.py` updated 278 conditions rows and cascaded to
211 scalar rows; `recalculate_all_registry_012.py::_backfill_scalars` then
recalculated 1465 scalar rows (its full run, not a targeted subset), catching the
ones whose conditions already had a value. Both passes reported `Errors: 0` /
`err=0` on both the dry run and the apply. Reporting-layer check afterwards:
`v_results_scalar_rollup` had 301 of 1076 rows with a non-null `mean_fe_yield_h2_pct`
and `v_results_scalar` had 352 of 1953 rows with a non-null
`ferrous_iron_yield_h2_pct`.

The 87 scalar rows still missing `ferrous_iron_yield_h2_pct` are the rows whose
sample has no FeO on record (see "Not a DI problem" / acceptance criteria above) —
this backfill cannot reach them; they resolve once rock characterization data is
uploaded for those samples.

No view recreation is needed for this backfill — views cache no data and no schema
changed. (`database/event_listeners.py` drops and recreates them at import time anyway;
the `create_reporting_views()` function named in `.claude/rules/schema-checklist.md:88`
does not exist.)

### Lab PC runbook

Run **after** deploying this branch, from the repo root on the lab PC, in this order:

1. `.venv/Scripts/python database/data_migrations/backfill_total_ferrous_iron_017.py --dry-run` — confirm `Errors: 0`
2. `.venv/Scripts/python database/data_migrations/backfill_total_ferrous_iron_017.py`
3. `.venv/Scripts/python -c "from database import SessionLocal; from database.data_migrations.recalculate_all_registry_012 import _backfill_scalars; db = SessionLocal(); _backfill_scalars(db, dry_run=False); db.close()"`
4. Refresh the Power BI dataset.

Step 3 commits per chunk, so an interruption leaves the chunks it finished already
committed — re-running it is safe and idempotent (`recalculate` is a pure recomputation
from current inputs).

The rows whose sample has no FeO on record stay NULL. They resolve on their own
once that rock's elemental data is uploaded — `recalculate_conditions_for_samples`
fires on every elemental upload and covers experiments created before the rock data
arrived.
