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
| `public.v_experiment_conditions` | `experiment_id`, `experiment_type`, `temperature_c`, `particle_size`, `initial_ph`, `rock_mass_g`, `water_volume_mL`, `water_to_rock_ratio`, `reactor_number`, `feedstock`, `stir_speed_rpm`, `room_temp_pressure_psi`, `rxn_temp_pressure_psi`, `co2_partial_pressure_MPa`, `confining_pressure`, `pore_pressure`, `flow_rate`, `initial_conductivity_mS_cm`, `initial_nitrate_concentration`, `initial_dissolved_oxygen`, `initial_alkalinity`, `core_height_cm`, `core_width_cm`, `core_volume_cm3`, `total_ferrous_iron_g` |
| `public.v_chemical_additives` | `experiment_id`, `compound_name`, `formula`, `amount`, `unit`, `addition_order`, `addition_method`, `purity`, `mass_in_grams`, `moles_added`, `final_concentration`, `concentration_units`, `elemental_metal_mass`, `catalyst_percentage`, `catalyst_ppm` |
| `public.v_experiment_additives_summary` | `experiment_id`, `additives_summary` |
| `public.v_experiment_xrd` | `experiment_id`, `time_post_reaction_days`, `mineral_name`, `amount_pct`, `rwp`, `measurement_date` |

---

## Result Views

| View | Key columns |
|---|---|
| `public.v_results_scalar` | `result_id`, `experiment_id`, `experiment_fk`, `time_post_reaction_days`, `time_post_reaction_bucket_days`, `cumulative_time_post_reaction_days`, `gross_ammonium_concentration_mM`, `background_ammonium_concentration_mM`, `grams_per_ton_yield`, `final_ph`, `final_nitrate_concentration_mM`, `ferrous_iron_yield`, `ferrous_iron_yield_h2_pct`, `ferrous_iron_yield_nh3_pct`, `final_dissolved_oxygen_mg_L`, `final_conductivity_mS_cm`, `final_alkalinity_mg_L`, `co2_partial_pressure_MPa`, `sampling_volume_mL`, `ammonium_quant_method`, `background_experiment_fk`, `scalar_measurement_date`, `nmr_run_date` |
| `public.v_results_h2` | `result_id`, `experiment_id`, `experiment_fk`, `time_post_reaction_days`, `time_post_reaction_bucket_days`, `h2_concentration`, `h2_concentration_unit`, `gas_sampling_volume_ml`, `gas_sampling_pressure_MPa`, `h2_micromoles`, `h2_mass_ug`, `h2_grams_per_ton_yield`, `gc_run_date` |
| `public.v_results_icp` | `result_id`, `experiment_id`, `experiment_fk`, `time_post_reaction_days`, `time_post_reaction_bucket_days`, `icp_dilution_factor`, `icp_instrument_used`, `icp_raw_label`, `icp_sample_date`, `icp_run_date`, `fe_ppm` … `tl_ppm` (27 element columns) |

---

## Sample Views

| View | Key columns |
|---|---|
| `public.v_sample_info` | `sample_id`, `rock_classification`, `state`, `country`, `locality`, `latitude`, `longitude`, `description`, `characterized` |
| `public.v_sample_characterization` | `sample_id`, `external_analysis_id`, `analysis_type`, `analysis_date`, `laboratory`, `analyst`, `description`, `magnetic_susceptibility`, `pxrf_reading_no` |
| `public.v_pxrf_characterization` | `sample_id`, `pxrf_reading_no`, `analysis_date`, `fe_ppm`, `mg_ppm`, `ni_ppm`, `cu_ppm`, `si_ppm`, `co_ppm`, `mo_ppm`, `al_ppm`, `ca_ppm`, `k_ppm`, `au_ppm`, `zn_ppm` |
| `public.v_sample_elemental_comp` | `sample_id`, `external_analysis_id`, `analysis_date`, `laboratory`, `analyst`, `FeO`, `SiO2`, `Al2O3`, `Fe2O3`, `MnO`, `MgO`, `CaO`, … (63 analyte columns) |
| `public.v_sample_xrd` | `sample_id`, `mineral_name`, `amount_pct`, `analysis_date`, `laboratory`, `analyst` |

---

## Relationships

```
v_experiments (experiment_id)    1 ──── 1 v_experiment_conditions (experiment_id)
v_experiments (experiment_id)    1 ──── * v_chemical_additives (experiment_id)
v_experiments (experiment_id)    1 ──── 1 v_experiment_additives_summary (experiment_id)
v_experiments (experiment_id)    1 ──── * v_experiment_xrd (experiment_id)
v_experiments (experiment_id)    1 ──── * v_results_scalar (experiment_id)
v_results_scalar (result_id)     1 ──── 1 v_results_h2 (result_id)
v_results_scalar (result_id)     1 ──── 1 v_results_icp (result_id)

v_sample_info (sample_id)        1 ──── * v_experiments (sample_id)
v_sample_info (sample_id)        1 ──── * v_sample_characterization (sample_id)
v_sample_info (sample_id)        1 ──── * v_pxrf_characterization (sample_id)
v_sample_info (sample_id)        1 ──── * v_sample_elemental_comp (sample_id)
v_sample_info (sample_id)        1 ──── * v_sample_xrd (sample_id)
```

---

## Notes

- `v_experiment_xrd` covers Aeris time-series XRD data (`experiment_fk IS NOT NULL`).
- `v_sample_xrd` covers sample characterisation XRD (Mode A + ActLabs reports), where
  `time_post_reaction_days IS NULL` and the phase is linked to a sample rather than an experiment.
- All ICP element columns in `v_results_icp` use `_ppm` suffix to avoid name collisions in
  Power BI when joining with `v_sample_elemental_comp` (which uses oxide symbols).
- `v_experiment_additives_summary` is a convenience view; `v_chemical_additives` is the
  normalised long-format alternative for per-additive analysis.
