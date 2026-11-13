---
paths:
  - "database/models/conditions.py"
  - "database/models/chemicals.py"
  - "database/reactor_slot.py"
  - "backend/services/denormalized_ids.py"
  - "backend/services/calculations/**"
  - "backend/services/bulk_uploads/new_experiments.py"
  - "backend/services/bulk_uploads/experiment_status.py"
  - "backend/api/routers/conditions.py"
  - "backend/api/routers/dashboard.py"
  - "tests/**/*condition*"
  - "tests/**/*reactor*"
  - "tests/**/*dashboard*"
  - "tests/**/*denormalized*"
---

# Experimental Conditions

> Part of the schema reference split out of `.claude/rules/MODELS.md` (the index). Field lists live in the model files; this file keeps what the code cannot tell you.

Defined in `database/models/conditions.py` and `database/models/chemicals.py`.

### `ExperimentalConditions`
Defines the parameters and setup for an experiment.
- **Key Fields**:
  - `serum_vial_size_mL` (Integer, nullable; added 2026-10-19, Alembic `e9a4c1f7b3d2`): the **nominal** serum vial size in whole mL (20, 60, 120, 160, ...). **Tracking only** — no calculation reads it. **Not the true total vial volume:** a "120 mL" vial holds noticeably more when filled to the brim, so a future headspace calc (total volume − liquid volume) needs a lookup by nominal size or a measured column, not this value. "Serum only" is enforced in the UI only (wizard Step 2 shows it for Serum; the Conditions edit modal shows it for Serum or when a value is already stored); the API and the new-experiments bulk upload accept it on any type. Positive-integer validation lives in `ConditionsCreate`/`ConditionsUpdate` (`gt=0, le=10_000` via `SERUM_VIAL_SIZE_MAX_ML`, 422 for `0`, `-1`, `120.5`, `10001`; the cap exists because the column is int4 and an overflow would 500 at flush) and the UI — there is deliberately **no DB `CHECK`**, because the conditions-sheet loop in `new_experiments.py` has no per-row SAVEPOINT and a constraint violation would break every remaining row. The bulk parser applies no validation to it (as it applies none to `reactor_number`; the API's `reactor_number` type check is separate). Raw SQL must quote it: `ec."serum_vial_size_mL"`. Exposed in `v_experiment_conditions` (not `v_experiments`). Existing rows are NULL; no backfill.
  - `pore_volume_mL` (Float, nullable; added 2026-11-03, Alembic `f3b7c2a9d4e1`, issue #132): the core's **pore volume in mL**, entered by the researcher (Core Flood). Tracking input only — no calculation-engine field reads it; `v_core_flood_samples` divides cumulative liquid volume by it to give pore volumes flushed (NULL or 0 gives NULL, never an error). Each segment holds its own value; a new segment inherits it through parent auto-copy. "Core Flood only" is enforced in the UI only (wizard Step 2 and the Conditions tab); the API and the new-experiments bulk upload accept it on any type. Positive-value validation (`gt=0`, 422 for `0`, `-1`) lives in `ConditionsCreate`/`ConditionsUpdate` and the wizard; there is deliberately **no DB `CHECK`**, for the same per-row-SAVEPOINT reason as `serum_vial_size_mL`, and the bulk parser applies no validation to it. Raw SQL must quote it: `ec."pore_volume_mL"`. Exposed in `v_experiment_conditions` and `v_core_flood_samples`. Existing rows are NULL; no backfill. Last column of the new-experiments template conditions sheet.
  - `flow_rate` (Float): **DEPRECATED** in favor of `experimental_results.flow_rate_mL_min` (per sample). Kept in place and not backfilled; set on 16 experiments older than CF_016; the frontend never shows it. Still exposed in `v_experiment_conditions`.
  - `reactor_series` (String(4), nullable; added 2026-11-07, Alembic `c6d2f8a4e1b9`, issue #147): which vessel series `reactor_number` counts in. **`NULL` = the type's default series** (`R` for HPHT, `CF` for Core Flood); `'P'` = the Parr HPHT vessels `P01`–`P06`. `CHECK ck_conditions_reactor_series` allows only NULL or `'P'`, so a new series is a one-line migration widening it (plus `ALLOWED_REACTOR_SERIES` in `database/reactor_slot.py`). `'P'` is **HPHT only**: the conditions API returns 422 on any other type (`reactor_series_error`), and `derive_reactor_slot` returns None for it, so a stray `'P'` on a Core Flood holds no slot rather than borrowing CF's. The API trims and upper-cases it. The new-experiments bulk parser validates the `reactor_number` / `reactor_series` cells **before** writing the row (`_resolve_reactor_cells`), because the conditions loop has no per-row SAVEPOINT and a CHECK violation at flush would break every remaining row. Exposed in `v_experiment_conditions` with `reactor_slot`, right after `reactor_number`. No backfill: existing rows are NULL and keep their `R`/`CF` slot.
  - `reactor_slot` (String(8), nullable, indexed): canonical physical slot label — `R01`–`R16` / `P01`–`P06` (HPHT vessels) or `CF01`–`CF03` (Core Flood rigs). **`NULL` means the experiment holds no physical slot**: a non-occupancy `experiment_type` (Serum / Autoclave / Other), a missing `reactor_number`, `reactor_number <= 0`, or a `reactor_series` that isn't valid for the type.
    - **Derived — never set it by hand.** `database/reactor_slot.py::derive_reactor_slot` is the only definition of the mapping; the `before_insert`/`before_update` listener `set_reactor_slot` in `database/event_listeners.py` writes it on every ORM write. A direct assignment is overwritten on the next flush.
    - **This is the key for every occupancy comparison** (issue #97). `reactor_number` alone conflates `R01` with `CF01` — two different vessels sharing the number 1 — which let a Core Flood going ONGOING silently set a running HPHT to COMPLETED. Sites now keyed on it: `experiment_status.py` (both occupant queries and the same-file conflict map), `new_experiments.py` (both occupancy call sites), `PATCH /api/experiments/{id}/status`, `dashboard.py` (reactor cards and `/reactor-status`).
    - **Pre-flush caveat:** the listener runs *during* flush, so code that has just assigned a new `reactor_number` (or `reactor_series`) must call `derive_reactor_slot(number, type, series)` rather than read `.reactor_slot`. Production `SessionLocal` sets `autoflush=False`. Every call site passes the series as of issue #147; forgetting it silently maps a Parr run onto the R slot with the same number.
    - **Bulk-update caveat:** the listener does NOT fire for a bulk `Query.update()` / Core `UPDATE`, which compiles to SQL without per-row mapper events. `database/data_migrations/swap_reactor_4_7_015.py:96-109` is the existing precedent for that idiom (it predates this column, and the Task 2 backfill left the DB self-consistent). Any future script changing `reactor_number` or `experiment_type` that way must either avoid `Query.update()` for those columns or recompute `reactor_slot` explicitly in the same script. Every other write path in the codebase loads an ORM instance and mutates attributes, which does fire the listener.
    - `reactor_number` is retained unchanged — Power BI views, `database/data_migrations/swap_reactor_4_7_015.py` and the `GET /api/experiments?reactor_number=` filter all read it.
    - **Still not enforced:** nothing prevents two ONGOING experiments sharing a `reactor_slot`. The one-ONGOING-per-slot trigger and `CHECK (reactor_number > 0)` are tracked in `docs/issues/issue-reactor-occupancy-uniqueness-trigger.md`, blocked on the cleanup in `docs/issues/audit-2026-07-28-results-and-cleanup.md`. Until then the `seen_labels` dedup at `dashboard.py:126-140` means a double-booked slot renders as one card, so the *grid* does not show the contention — but `_occupancy()` (`dashboard.py:48-64`) counts that same deduped `reactor_cards` list, so `ongoing` equals the number of distinct occupied slots and `summary.reactors.empty` is **correct**, not one too high. This is why the dedup must stay until the uniqueness constraint lands: removing it would make `ongoing` count experiments against a slot total instead of distinct slots, driving `empty` negative on real double-booked data.
- **Derived Fields**:
  - `water_to_rock_ratio` (hybrid/property: `formatted_additives` from chemical_additives).
  - `total_ferrous_iron_g` (Float, nullable): mass of ferrous iron (Fe²⁺) in grams, derived from rock characterization FeO wt% × `FE_IN_FEO_FRACTION` × `rock_mass_g`; see `docs/CALCULATIONS.md` for full formula. **Stored, so it is only correct if `recalculate()` ran after the row's last mutation** — and `calculate_ferrous_iron_yield_h2` returns NULL whenever it is NULL, taking `ferrous_iron_yield_h2_pct` and `ferrous_iron_yield_nh3_pct` down with it. The New Experiments bulk upload did not recalculate conditions until 2026-08-10, so 845 of 1125 production conditions rows held NULL and 157 scalar rows had no Fe²⁺ %H₂ despite a computed `h2_micromoles`. **Production has not been backfilled yet** — that runs post-deploy per the runbook in the issue doc; only the dev DB is done. Two passes are needed, not one: `database/data_migrations/backfill_total_ferrous_iron_017.py` filters on `total_ferrous_iron_g IS NULL`, so it cannot reach the ~15 stale scalar rows whose conditions row already held a value — those need `recalculate_all_registry_012.py::_backfill_scalars`. And 845 is not the recoverable count: 77+ rows stay NULL for want of FeO data on the sample and only resolve when rock characterization is uploaded. A NULL `water_to_rock_ratio` on a row with positive rock mass and water volume is the diagnostic for "recalculate never ran here". See `docs/issues/issue-bulk-upload-never-recalculates-conditions.md`.
- **Note**: Legacy fields like `catalyst`, `buffer_system`, `surfactant` are deprecated in favor of `ChemicalAdditive`.
- **Identity (issue #109 follow-up):** `experiment_fk` is the **only** authoritative
  link to `Experiment`; the `experiment_id` string on this table is a denormalized
  copy. Both rename paths keep it in sync as of 2026-08-05: `PATCH /api/experiments/{id}`
  and the bulk parser (`backend/services/bulk_uploads/new_experiments.py`) both
  call `backend/services/denormalized_ids.py::sync_denormalized_experiment_id`,
  which is the **single definition** of the five-table fan-out
  (`experimental_conditions`, `experiment_notes`, `modifications_log`,
  `external_analyses`, `xrd_phases`). Add a sixth table there, not at a call site.
  `xrd_phases` rows whose new `(experiment_id, time_post_reaction_days,
  mineral_name)` slot is already taken are **left stale and reported** rather
  than renamed — renaming into an occupied `uq_xrd_phase_experiment_time_mineral`
  slot would abort the whole rename with an `IntegrityError`.
  187 of 1013 rows were stale as of 2026-08-05 from the pre-fix bulk path and
  are corrected only by running
  `database/data_migrations/dedupe_conditions_and_backfill_ids_018.py`.
  Never resolve a conditions row by this string — resolve through `experiment_fk`.
  - `UNIQUE (experiment_fk)` (`uq_conditions_experiment_fk`, Alembic revision
    `00063a5dd6a8`) enforces the 1:1 with `Experiment` that `_build_list_item`,
    `serialize_experiment_snapshot`, `v_experiments` and `v_experiment_conditions`
    all assume. Before it, one duplicate row 500'd the experiments list
    (`MultipleResultsFound`), duplicated the Power BI dimension key in the two
    views above, and made the owning experiment undeletable through either delete
    path. The migration's `upgrade()` refuses with a `RuntimeError` (listing the
    offending `experiment_fk`s) if any duplicate remains — the dedupe script above
    must be run with `--apply` first.
  - `POST /api/conditions` returns **409** when a row already exists for the
    submitted `experiment_fk`, with the existing row's id in the `detail` text.
  - `GET /api/conditions/by-experiment/{experiment_id}`, `_build_list_item`, and
    `serialize_experiment_snapshot` all select the **lowest-id** row rather than
    `scalar_one_or_none()`/`.one()`, so a database that predates the constraint
    degrades to "pick one row" instead of 500ing.
  - Full incident record, the production measurements, and the deploy sequence:
    `docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md`.
