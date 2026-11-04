---
paths:
  - "database/event_listeners.py"
  - "alembic/**"
  - "tests/views/**"
  - "tests/api/test_core_flood_view.py"
  - "tests/api/test_experiment_rollup.py"
---

# Reporting Views (Power BI)

> Part of the schema reference split out of `.claude/rules/MODELS.md` (the index). Field lists live in the model files; this file keeps what the code cannot tell you.

SQL views are created at application startup so Power BI (and other reporting tools) can query flattened, one-row-per-primary-result datasets. View creation runs in `database/event_listeners.py` on engine connect: views are dropped and recreated so their definitions stay in sync with the current schema.

### `v_experiments` — `description` (issue #118 PR3)

`description` is the note typed `'description'` (`WHERE n.note_type = 'description'`, at most one per experiment by the partial unique index). It replaced `ORDER BY n.created_at ASC LIMIT 1`, which was **wrong, not merely different**: `created_at` is the transaction timestamp, so every note a bulk upload inserted in one transaction shared it and the `LIMIT 1` was arbitrary. Recreated by Alembic `c4d8f1a2b6e7` and on API startup.

### `v_dim_timepoints` — `modification_note` (issue #118 PR3)

`brine_modification_description` was replaced by `modification_note`: the result's `'modification'` notes, `'; '`-joined in id order when more than one exists (an upload's mirror and a hand-written one can coexist under different `created_by`). NULL when none.

### `v_results_scalar` — `sampling_description` dropped (issue #118 PR3)

The legacy `experimental_results.description` column is no longer exposed anywhere; its researcher-written content lives in `v_notes` as `observation` rows scoped to the result. The column itself was dropped by PR-D (2026-10-14).

### `v_dim_timepoints` — `sample_tube_number`, `v_experiment_conditions` — `pore_volume_mL` (issue #132)

`v_dim_timepoints` gained `sample_tube_number` and `v_experiment_conditions` gained `pore_volume_mL`. Both are additive; Alembic `f3b7c2a9d4e1` recreates them with the new columns and its downgrade restores the old definitions.

### `v_core_flood_samples` (issue #132)

One row per **primary timepoint of a Core Flood experiment** (`er.is_primary_timepoint_result` and `experiment_type` read as Core Flood the way `database/reactor_slot.py::_SERIES_BY_TYPE` reads it: lowercased, whitespace collapsed, in `core flood` / `coreflood` / `cf` — production stores CF-014 as `CF`; keep the SQL in sync with that dict), with cross-sample run values. Key: `result_id` (1–1 with `v_dim_timepoints`). Created by `database/event_listeners.py` and Alembic `f3b7c2a9d4e1`; dropped first on downgrade. Reads `experimental_results`, `experiments` (plus its parent), `experimental_conditions` and `scalar_results` (LEFT JOIN, so a timepoint with no scalar row still appears).

- **Run:** `run_base_id = experiments.base_experiment_id`. A run is one base ID split across sequential segments (`CF_020`, `CF_020-2`, ...). Window: `PARTITION BY run_base_id, is_variant ORDER BY cumulative_time_post_reaction_days, result_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`.
- **Variants:** `is_variant` = the experiment has a parent **and** its ID starts with `<parent experiment_id>_` (a `_Text` blank or bypass such as `CF_020-5_Bypass1`; against the 2026-10-26 backup it flags exactly the 8 known variants and no sequential segment). Variants keep their raw columns, sit in their own partition, and have every derived column NULL, so they never shift a segment's sums. **Known and accepted:** `CF_020_5_Brine` parses to base `CF_020_5` (underscore typo), so it forms its own one-row run instead of a variant (the run page's rename fixes it); an orphaned variant (parent link cleared) counts as a segment.
- **Two-root runs (known, not fixed):** CF_026 and CF_027 each have a bare root and a `-1` root holding their own samples; the view merges them by `base_experiment_id` and interleaves them by cumulative time, so an interval or rate can be measured against the other root's sample. Cleanup is tracked in the parent issue (#131).
- **Derived columns** (full formulas and bases in `docs/CALCULATIONS.md`, "Core flood run values"): `interval_days = cumulative_time − COALESCE(LAG(cumulative_time), 0)`; `cumulative_liquid_volume_mL = SUM(COALESCE(sampling_volume_mL, 0))`; `cumulative_pore_volumes = cumulative_liquid_volume_mL / NULLIF(pore_volume_mL, 0)`; `cumulative_h2_grams_per_ton = SUM(COALESCE(h2_grams_per_ton_yield, 0))`; `h2_grams_per_ton_per_day = h2_grams_per_ton_yield / NULLIF(interval_days, 0)`; `is_hold_interval = (flow_rate_mL_min = 0)` (NULL when flow is NULL).
- **H2 basis (Mat, 2026-11-03):** each sample's H2 is only what was collected since the previous sample, so per-sample H2 g/t sums to cumulative H2 and divides by interval days to a rate.
- **View columns, not calculation-engine fields.** Nothing is registered in the calculation registry or stored; per-sample H2 is still computed by `recalculate_scalar`.
- **Assumes one `experimental_conditions` row per experiment** (`uq_conditions_experiment_fk`); a duplicate would duplicate rows here.

### `v_notes` (issue #118 PR3)

One row per experiment note — Power BI's entry point for this domain. Columns: `note_id`, `experiment_id`, `result_id` (NULL for experiment-level notes), `note_type` (enum as text: `description` / `modification` / `observation` / `result_note`), `note_text`, `created_at`, `created_by`, `needs_review`. Join `experiment_id` to `v_experiments`, `result_id` to `v_dim_timepoints` / `v_results_*`. `WHERE needs_review` is the review queue left by the 020 backfill.

### `v_experiment_additives_summary`

One row per experiment: concatenated chemical additives for reporting.

- **Purpose:** Power BI and reports can show “additives” as a single text column (e.g. “Mg(OH)₂ 5 g; Magnetite 1 g”) without joining through conditions and compounds.
- **Definition:** `chemical_additives` → `experimental_conditions` → `experiments`, joined to `compounds`; `GROUP BY e.experiment_id` with `GROUP_CONCAT(c.name || ' ' || amount || ' ' || unit, '; ')` as `additives_summary`.
- **Key column:** `experiment_id`, `additives_summary`.

### `v_experiment_additive_names_summary`

One row per experiment: compound names only, comma-separated and alphabetically sorted.

- **Purpose:** Power BI slicers and text-label columns that need only the additive names (not amounts/units). Avoids fragile string-parsing of `additives_summary` from `v_experiment_additives_summary`.
- **Definition:** `experiments` LEFT JOIN `experimental_conditions` → LEFT JOIN `chemical_additives` → LEFT JOIN `compounds`; `STRING_AGG(c.name, ', ' ORDER BY c.name)` grouped by `e.experiment_id`. `LEFT JOIN` chain ensures experiments with no additives still appear.
- **Key columns:** `experiment_id`, `additive_names` (NULL when experiment has no additives).

### `v_primary_experiment_results`

> **Not a live view.** `database/event_listeners.py` only drops it (`DROP VIEW IF EXISTS v_primary_experiment_results CASCADE`); its old definition is in git history. Use `v_dim_timepoints` / `v_results_*` / `v_notes`.

**Note on `v_results_scalar`:** its `cumulative_ferrous_iron_yield_h2_pct` running-sum window partitions by `e.experiment_id` (per-vial), not by `COALESCE(base_experiment_id, experiment_id)` — replicate siblings (e.g. `SERUM_001a/b/c`) each accumulate independently and do not sum across each other. A digit-suffixed derivation (e.g. `HPHT_001-2`) also no longer shares its running sum with its root; each `experiment_id` gets its own partition. **`-t<days>` caveat:** a single-timepoint `-t` vial (e.g. `SERUM_001a-t7`) has exactly one result row, so its per-experiment cumulative equals that one row — it never accumulates across sibling timepoints of the same base. Read time courses across `-t` vials at the base/rollup grain (`v_results_scalar_rollup`, grouped by `COALESCE(base_experiment_id, experiment_id)`), not from an individual `-t` vial's own cumulative column.

### `v_results_scalar_rollup`

One row per `(base_experiment_id, time_post_reaction_bucket_days)`: cross-replicate mean/median/std for a replicate set (or `n_vials = 1` with `NULL` std for a single non-replicate experiment).

- **Purpose:** Power BI dashboards can show replicate-set statistics (e.g. mean +/- std NH₄⁺ across `SERUM_001a/b/c`) without an application-layer aggregation step.
- **Grouping key:** `COALESCE(e.base_experiment_id, e.experiment_id)`, matching the existing pattern in `v_results_scalar` and `v_experiment_additives_summary`.
- **Statistics:** `stddev_samp` (n-1); returns `NULL` for `n_vials = 1`. Median via `percentile_cont(0.5) WITHIN GROUP`.
- **Scope:** gross/net ammonium, H2 (ppm, micromoles, grams/ton), ferrous iron yield (H2% and NH3%), grams/ton yield, final pH. No ICP element aggregation (permanently out of scope). H2 ppm (`mean_h2_ppm`/`sd_h2_ppm`, issue #90) averages `scalar_results.h2_concentration`, which is meaningful only because the unit is the invariant ppm (vol/vol) documented on `ScalarResults`.
- **Outlier filter (P4):** rows from experiments with `is_outlier = true` are excluded from all aggregates including `n_vials` (`WHERE … AND NOT COALESCE(e.is_outlier, false)`). Flagged experiments stay present in every per-row view.
- **Counts (revised 2026-08-01):** the former single `n_replicates` column was `COUNT(sr.result_id)` over a LEFT JOIN — it counted scalar *rows*, read 0 for ICP-only timepoints (335 phantom groups in production) and over-counted a vial holding several primary rows; it was wrong in 457 of 1412 groups. Replaced by `n_vials` (distinct experiments), `n_replicate_letters` (distinct letters, 0 when unlettered) and `n_values` (rows behind the stats). The join to `scalar_results` is now **INNER**, so an ICP-only timepoint produces no row here at all. `n_replicate_letters >= 2` is the test for "this really is a lettered replicate set" — 1063 of 1077 production groups are unlettered. See `docs/issues/issue-rollup-replicate-count-and-null-timepoint-buckets.md`.
- **Note:** the grouping key (`COALESCE(base_experiment_id, experiment_id)`) does not distinguish letter-suffixed replicates from ordinary sequential derivations — a base experiment with sequential re-runs (e.g. `HPHT_001`, `HPHT_001-2`) but no lettered replicates will still produce `n_vials >= 2` here, since both share `base_experiment_id`. **`n_replicate_letters` now answers this directly** (0 = unlettered sequential set), so it no longer needs checking case-by-case: only treat these stats as "replicate statistics" when `n_replicate_letters >= 2`.
- **Parent inclusion (issue #83 — confirmed intended):** the group parent ("replicate 0") shares the grouping key with its lettered replicates (`COALESCE(base_experiment_id, experiment_id)` resolves to the same base for both), so a parent that has its own results is counted in the group mean/median/std exactly like a lettered member. To exclude a parent whose run should not count as a replicate, flag it `is_outlier` — there is deliberately no separate parent opt-out.
- **Hand-entered rows (issue #83):** `POST /api/results` (the Add Results modal) sets `time_post_reaction_bucket_days` from the resolved time via `normalize_timepoint`, so UI-entered results aggregate per day here just like bulk-uploaded ones. When a new primary entry lands in a bucket that already has a primary row, the newest entry wins and the older row is demoted to non-primary.
- **NULL buckets are NOT all backfilled (corrected 2026-08-01).** This section previously claimed a data migration had backfilled every pre-existing NULL-bucket row. That is **false against production**: 807 of 1959 primary rows (41%) still have `time_post_reaction_bucket_days IS NULL`, all created 2026-02 or earlier. The write path was fixed — zero NULL-bucket primary rows have been created since 2026-03 — but the historical rows were never corrected. They collapse into one `(base, NULL)` group per set, averaging every timepoint together.
  - **The partial unique index is inert on them.** `uq_primary_result_per_experiment_bucket` is `UNIQUE (experiment_fk, time_post_reaction_bucket_days) WHERE is_primary_timepoint_result`, and Postgres treats NULLs as distinct by default — so it never fires on a NULL bucket. Result: 198 `(experiment, NULL)` pairs hold duplicate primary rows (397 excess), while **zero** duplicates exist on any real bucket. Tightening it needs `NULLS NOT DISTINCT` (PG15+) and is blocked on cleaning those duplicates first.
  - Full analysis, backfill sources and proposed fixes: `docs/issues/issue-rollup-replicate-count-and-null-timepoint-buckets.md`.
- **Letter vs vial (issue #98):** this view's `n_vials` counts experiment
  ROWS in the bucket, so a 2-letter × 2-timepoint set yields
  `n_vials = 2` per day bucket (one vial per letter contributes to each
  bucket) — which happens to match the letter count. The group page's
  individual-replicate overlay draws one series per letter and excludes
  `is_outlier` vials, so the overlay and this view's mean agree on membership.
  A *letterless* `-t` vial (`SERUM_001-t7`) is counted here **and** appears in
  the group page's members table as of issue #101 — the two agree. Such a set
  has `n_replicate_letters = 0` and one vial per bucket, so every `sd_*` is
  NULL; the group page renders the mean alone (no error bars, no "± 0.0") and
  draws no individual overlay series, because with one value per bucket the
  series would be the mean line redrawn on itself.

**Where views are created:** `database/event_listeners.py` runs `DROP VIEW IF EXISTS` then `CREATE VIEW` for each view in a `try` block on module import (using the shared `engine`). Failures are ignored so startup is not blocked if the DB is unavailable; views are also recreated in Alembic migrations when dependent tables change (e.g. new ICP columns), so the canonical definitions stay aligned with the schema documented here.
