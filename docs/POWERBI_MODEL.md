# Power BI Model — Reporting Views

All views are defined in `database/event_listeners.py` and recreated at application startup.
They are **not** managed by Alembic migrations. Changes to view SQL take effect on the next
application restart.

Views are all in the `public` schema (PostgreSQL default). Connect Power BI directly to the
PostgreSQL database on the lab PC and import these views as tables.

---

## Experiment Views

| View | Key columns |
|---|---|
| `public.v_experiments` | `experiment_id`, `experiment_number`, `status`, `researcher`, `date`, `sample_id`, `base_experiment_id`, `reactor_number`, `rock_mass_g`, `water_volume_mL`, `initial_ph`, `experiment_type`, `feedstock`, `description` |
| `public.v_experiment_conditions` | `experiment_id`, `experiment_type`, `temperature_c`, `particle_size`, `initial_ph`, `rock_mass_g`, `water_volume_mL`, `water_to_rock_ratio`, `reactor_number`, `feedstock`, `stir_speed_rpm`, `room_temp_pressure_psi`, `rxn_temp_pressure_psi`, `co2_partial_pressure_MPa`, `confining_pressure`, `pore_pressure`, `flow_rate`, `initial_conductivity_mS_cm`, `initial_nitrate_concentration`, `initial_dissolved_oxygen`, `initial_alkalinity`, `core_height_cm`, `core_width_cm`, `core_volume_cm3`, `total_ferrous_iron_g`, `total_ferrous_iron` |
| `public.v_chemical_additives` | `experiment_id`, `compound_name`, `formula`, `amount`, `unit`, `addition_order`, `addition_method`, `purity`, `mass_in_grams`, `moles_added`, `final_concentration`, `concentration_units`, `elemental_metal_mass`, `catalyst_percentage`, `catalyst_ppm` |
| `public.v_experiment_additives_summary` | `experiment_id`, `additives_summary` |
| `public.v_experiment_additive_names_summary` | `experiment_id`, `additive_names` |
| `public.v_dim_timepoints` | `result_id`, `experiment_id`, `time_post_reaction_days`, `time_post_reaction_bucket_days`, `cumulative_time_post_reaction_days`, `brine_modification_description` |
| `public.v_experiment_xrd` | `experiment_id`, `time_post_reaction_days`, `mineral_name`, `amount_pct`, `rwp`, `measurement_date` |

---

## Result Views

| View | Key columns |
|---|---|
| `public.v_results_scalar` | `result_id`, `experiment_id`, `experiment_fk`, `sampling_description`, `time_post_reaction_days`, `time_post_reaction_bucket_days`, `cumulative_time_post_reaction_days`, `gross_ammonium_concentration_mM`, `background_ammonium_concentration_mM`, `net_ammonium_concentration`, `grams_per_ton_yield`, `final_ph`, `final_nitrate_concentration_mM`, `ferrous_iron_yield`, `ferrous_iron_yield_h2_pct`, `cumulative_ferrous_iron_yield_h2_pct`, `ferrous_iron_yield_nh3_pct`, `final_dissolved_oxygen_mg_L`, `final_conductivity_mS_cm`, `final_alkalinity_mg_L`, `co2_partial_pressure_MPa`, `sampling_volume_mL`, `ammonium_quant_method`, `background_experiment_fk`, `scalar_measurement_date`, `nmr_run_date` |
| `public.v_results_h2` | `result_id`, `experiment_id`, `experiment_fk`, `time_post_reaction_days`, `time_post_reaction_bucket_days`, `h2_concentration`, `h2_concentration_unit`, `gas_sampling_volume_ml`, `gas_sampling_pressure_MPa`, `h2_micromoles`, `h2_mass_ug`, `h2_grams_per_ton_yield`, `gc_run_date` |
| `public.v_results_icp` | `result_id`, `experiment_id`, `experiment_fk`, `time_post_reaction_days`, `time_post_reaction_bucket_days`, `icp_dilution_factor`, `icp_instrument_used`, `icp_raw_label`, `icp_sample_date`, `icp_run_date`, `fe_ppm` … `v_ppm` (36 element columns) |
| `public.v_results_scalar_rollup` | `base_experiment_id`, `time_post_reaction_bucket_days`, `n_vials`, `n_replicate_letters`, `n_values`, `mean_gross_ammonium_mM`, `median_gross_ammonium_mM`, `sd_gross_ammonium_mM`, `mean_net_ammonium_mM`, `sd_net_ammonium_mM`, `mean_h2_ppm`, `sd_h2_ppm`, `mean_h2_micromoles`, `sd_h2_micromoles`, `mean_h2_grams_per_ton`, `sd_h2_grams_per_ton`, `mean_fe_yield_h2_pct`, `sd_fe_yield_h2_pct`, `mean_fe_yield_nh3_pct`, `sd_fe_yield_nh3_pct`, `mean_grams_per_ton_yield`, `sd_grams_per_ton_yield`, `mean_final_ph` |

---

## Replicate & Timepoint Handling

`v_results_scalar_rollup` is the **cross-replicate statistics** view — one row per `(base_experiment_id, time_post_reaction_bucket_days)`, giving mean/median/sample-std across a replicate set. Use it for any visual showing "mean ± std across replicates" rather than aggregating `v_results_scalar` in a Power BI measure.

- **Grouping key:** `COALESCE(e.base_experiment_id, e.experiment_id)` — the same key used by `v_experiment_additives_summary`. A replicate letter (`a`, `b`, `c`) is a distinct scientific unit; a sequential suffix (`-2`, `-3`) on a base ID or a letter is a re-run of that same unit, not a new replicate.
- **The three counts (revised 2026-08-01).** The view used to carry a single `n_replicates`, which counted scalar *rows* — it read 0 for ICP-only timepoints and over-counted whenever one vial held more than one primary row. It is replaced by three unambiguous columns:

  | Column | Meaning | Use it for |
  |---|---|---|
  | `n_vials` | distinct experiments contributing a scalar value | the "n =" on a mean ± SD visual |
  | `n_replicate_letters` | distinct replicate letters; **0 when the group is unlettered** | deciding whether a group is a true replicate set |
  | `n_values` | rows actually behind the mean/SD | spotting double-counted timepoints |

  **`n_replicate_letters` is what settles the lettered-vs-sequential question** that used to require case-by-case checking: `0` means the group is sequential re-runs sharing a base ID, not a lettered replicate set. Only call a group's statistics "replicate statistics" when `n_replicate_letters >= 2`. As of the 2026-08-01 production data, **1063 of 1077 rollup groups are unlettered** — so this is the common case, not the exception.

  **`n_values > n_vials` means a vial contributed more than one row to that bucket** — currently true for 115 groups, all a consequence of the NULL-bucket duplicates described below. Treat those groups' statistics as provisional.
- **Scalar only.** The join to `scalar_results` is INNER: a timepoint with only ICP data produces **no row here at all**. Use `v_results_icp` for those.
- **Outlier handling:** rows from experiments flagged `is_outlier = true` are excluded from every aggregate in this view, including the counts. `is_outlier` and `replicate_label` are **not exposed in any Power BI view** — there is no way to filter or slice on them directly from the model; the rollup view's exclusion happens upstream in SQL.
- **Group parent inclusion:** the group parent ("replicate 0," no letter suffix) shares the grouping key with its lettered siblings and is included in the mean/median/std unless flagged `is_outlier` — there's no separate opt-out for a parent run.
- **Timepoint tokens:** a trailing `-t<days>` token on an experiment ID (e.g. `SERUM_001a-t7`) encodes a destructively-sampled vial's day. The token is stripped before grouping, so `SERUM_001a-t7` still rolls up under base `SERUM_001`.
- **NULL timepoint buckets:** 807 of 1959 primary result rows (41%, all created 2026-02 or earlier) have `time_post_reaction_bucket_days = NULL`. They collapse into **one NULL bucket per group** that averages every timepoint together. Filter `time_post_reaction_bucket_days IS NOT NULL` on any time-series visual, or the NULL bucket will plot as a spurious point. See `docs/issues/issue-rollup-replicate-count-and-null-timepoint-buckets.md`.

> ### ⚠️ Experiments with no results vanish from result-driven visuals
>
> **292 of 1009 experiments currently have no `experimental_results` rows at all** (queued, ongoing, or never sampled). `v_experiments` exposes all 1009, but `v_dim_timepoints`, `v_results_scalar`, `v_results_h2`, `v_results_icp` and `v_results_scalar_rollup` only contain the 717 that have results — and `v_results_scalar_rollup` covers only the subset with *scalar* data.
>
> A visual built on any results view therefore **silently omits those 292 experiments**. This is the usual cause of "I can see every experiment in the app but not in Power BI."
>
> **To list all experiments, build the visual on `v_experiments`** and let the results tables join in as a LEFT relationship, so experiments with no results still render (with blank measures).
- **`v_results_scalar` cumulative column caveat:** `cumulative_ferrous_iron_yield_h2_pct` in `v_results_scalar` partitions by individual `experiment_id`, **not** by the base/group key — replicate siblings accumulate independently and never sum across each other. A single-timepoint `-t` vial's cumulative value equals just that one row. Do not use this column to build a group-level cumulative-yield chart; aggregate at the `v_results_scalar_rollup` grain instead.
- **Join key:** `v_results_scalar_rollup` joins to `v_experiments` on `base_experiment_id = experiment_id` (for a bare base row) or via a calculated column matching `COALESCE(base_experiment_id, experiment_id)` on the experiments side, since `v_experiments` does not itself expose a pre-computed group key column.

---

## Sample Views

| View | Key columns |
|---|---|
| `public.v_sample_info` | `sample_id`, `rock_classification`, `state`, `country`, `locality`, `latitude`, `longitude`, `description`, `characterized` |
| `public.v_sample_characterization` | `sample_id`, `external_analysis_id`, `analysis_type`, `analysis_date`, `laboratory`, `analyst`, `description`, `magnetic_susceptibility`, `pxrf_reading_no` |
| `public.v_pxrf_characterization` | `sample_id`, `pxrf_reading_no`, `analysis_date`, `fe_ppm`, `mg_ppm`, `ni_ppm`, `cu_ppm`, `si_ppm`, `co_ppm`, `mo_ppm`, `al_ppm`, `ca_ppm`, `k_ppm`, `au_ppm`, `zn_ppm` |
| `public.v_sample_elemental_comp` | `sample_id`, `external_analysis_id`, `analysis_date`, `laboratory`, `analyst`, `FeO`, `SiO2`, `Al2O3`, `Fe2O3`, `MnO`, `MgO`, `CaO`, … (66 analyte columns) |
| `public.v_sample_xrd` | `sample_id`, `mineral_name`, `amount_pct`, `analysis_date`, `laboratory`, `analyst` |

---

## Relationships

```
v_experiments (experiment_id)    1 ──── 1 v_experiment_conditions (experiment_id)
v_experiments (experiment_id)    1 ──── * v_chemical_additives (experiment_id)
v_experiments (experiment_id)    1 ──── 1 v_experiment_additives_summary (experiment_id)
v_experiments (experiment_id)    1 ──── 1 v_experiment_additive_names_summary (experiment_id)
v_experiments (experiment_id)    1 ──── * v_experiment_xrd (experiment_id)
v_experiments (experiment_id)    1 ──── * v_dim_timepoints (experiment_id)

v_dim_timepoints (result_id)    1 ──── 1 v_results_scalar (result_id)
v_dim_timepoints (result_id)    1 ──── 1 v_results_h2 (result_id)
v_dim_timepoints (result_id)    1 ──── 1 v_results_icp (result_id)

v_experiments (base_experiment_id or experiment_id)  * ──── 1 v_results_scalar_rollup (base_experiment_id, time_post_reaction_bucket_days)

v_sample_info (sample_id)       1 ──── * v_experiments (sample_id)
v_sample_info (sample_id)       1 ──── * v_sample_characterization (sample_id)
v_sample_info (sample_id)       1 ──── * v_pxrf_characterization (sample_id)
v_sample_info (sample_id)       1 ──── * v_sample_elemental_comp (sample_id)
v_sample_info (sample_id)       1 ──── * v_sample_xrd (sample_id)
```

---

## Field Visibility Guide

When configuring the PowerBI model, hide duplicate join keys in child tables so report
authors can only select them from the authoritative dimension. This prevents the
cross-filtering trap described in [issue #17](https://github.com/mathew-h/experiment-tracking-sandbox/issues/17).

### `v_dim_timepoints`

| Field | Visible? | Reason |
|-------|----------|--------|
| `time_post_reaction_days` | Yes | Authoritative source for time axis |
| `time_post_reaction_bucket_days` | Yes | Authoritative source for bucketed time axis |
| `cumulative_time_post_reaction_days` | Yes | Authoritative source for cumulative time |
| `brine_modification_description` | Yes | Documents brine changes between timepoints |
| `experiment_id` | **Hide** | Users get `experiment_id` from `v_experiments` |
| `result_id` | **Hide** | Join key only |

### `v_results_scalar`

| Field | Action |
|-------|--------|
| `experiment_id` | **Hide** (already hidden today) |
| `experiment_fk` | **Hide** |
| `time_post_reaction_days` | **Hide** — use `v_dim_timepoints` |
| `time_post_reaction_bucket_days` | **Hide** — use `v_dim_timepoints` |
| `cumulative_time_post_reaction_days` | **Hide** — use `v_dim_timepoints` |

### `v_results_h2`

| Field | Action |
|-------|--------|
| `experiment_id` | **Hide** (already hidden today) |
| `experiment_fk` | **Hide** |
| `time_post_reaction_days` | **Hide** — use `v_dim_timepoints` |
| `time_post_reaction_bucket_days` | **Hide** — use `v_dim_timepoints` |

### `v_results_icp`

| Field | Action |
|-------|--------|
| `experiment_id` | **Hide** (already hidden today) |
| `experiment_fk` | **Hide** |
| `time_post_reaction_days` | **Hide** — use `v_dim_timepoints` |
| `time_post_reaction_bucket_days` | **Hide** — use `v_dim_timepoints` |

---

## Notes

- `net_ammonium_concentration` in `v_results_scalar` is a computed column: `GREATEST(0, gross - background)` in mM. It is always ≥ 0 — use it instead of computing the difference in Power BI measures.
- `v_experiment_xrd` covers Aeris time-series XRD data (`experiment_fk IS NOT NULL`).
- `v_sample_xrd` covers sample characterisation XRD (Mode A + ActLabs reports), where
  `time_post_reaction_days IS NULL` and the phase is linked to a sample rather than an experiment.
- All ICP element columns in `v_results_icp` use `_ppm` suffix to avoid name collisions in
  Power BI when joining with `v_sample_elemental_comp` (which uses oxide symbols). The 36
  element columns are: `fe`, `si`, `mg`, `ca`, `ni`, `cu`, `mo`, `zn`, `mn`, `cr`, `co`,
  `al`, `sr`, `y`, `nb`, `sb`, `cs`, `ba`, `nd`, `gd`, `pt`, `rh`, `ir`, `pd`, `ru`, `os`,
  `tl`, `ag`, `ce`, `k`, `la`, `na`, `pb`, `sc`, `th`, `v` (each suffixed `_ppm`).
- `v_experiment_additives_summary` and `v_experiment_additive_names_summary` are convenience views; `v_chemical_additives` is the normalised long-format alternative for per-additive analysis. Use `additive_names` (names only, alphabetical) for slicers and text labels; use `additives_summary` (name + amount + unit) for display columns where quantities matter. `additive_names` is NULL for experiments with no additives — use `COALESCE(additive_names, '')` in Power BI if a blank string is preferred.
- `v_experiment_xrd` retains its own `time_post_reaction_days` and connects directly to
  `v_experiments` via `experiment_id` — it is intentionally **not** routed through
  `v_dim_timepoints`. XRD measurements follow a different schedule than scalar/H2/ICP
  results and may not align with primary result timepoints.
- `v_results_scalar_rollup` has no ICP aggregation (permanently out of scope) and no
  `result_id` — it is keyed on `base_experiment_id` + `time_post_reaction_bucket_days`,
  not on an individual result row, so it cannot be joined 1:1 into `v_dim_timepoints`.
  See "Replicate & Timepoint Handling" above for grouping and outlier semantics.

---

## Status Values

The `status` column in experiment views uses the `ExperimentStatus` enum. Valid values:

| Value | Meaning |
|-------|---------|
| `ONGOING` | Experiment is actively running |
| `COMPLETED` | Experiment has finished |
| `CANCELLED` | Experiment was cancelled |
| `QUEUED` | Experiment is registered and configured but not yet started (added 2026-04-06, issue #33) |

**Power BI note:** Existing measures that filter on `status = "ONGOING"` for active experiment counts will continue to work correctly — `QUEUED` is a distinct value and will not inflate active counts. Update any visuals that show a status legend or slicer to include `QUEUED` with an amber color (`#f59e0b`).
