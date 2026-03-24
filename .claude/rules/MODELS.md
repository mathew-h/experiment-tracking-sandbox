# Database Schema Documentation

This document provides a comprehensive overview of the database schema for the Experiment Tracking System. The schema is built using SQLAlchemy ORM and deployed on SQLite.

The models are modularized within the `database/models/` directory.

**Reporting intent:** The schema and the SQL views described below are designed to support **dynamic Power BI dashboards**. Views provide flattened, reporting-friendly datasets (one row per experiment timepoint, joined scalars and ICP, additives summary) so Power BI can connect directly to the database and refresh dashboards as data changes, without application-layer ETL.

## Core Experiment Models
Defined in `database/models/experiments.py`.

### `Experiment`
The central hub for all experimental data.
- **Primary Key**: `id` (Integer)
- **Key Fields**:
  - `experiment_id` (String, unique): User-defined identifier (e.g., "Serum_MH_101").
  - `experiment_number` (Integer, unique): Auto-incrementing sequence number.
  - `status`: Enum (`ONGOING`, `COMPLETED`, `CANCELLED`).
  - `sample_id`: FK to `SampleInfo`.
  - `researcher`, `date` (optional).
- **Lineage Tracking**:
  - `base_experiment_id`: Tracks the root of a series (e.g., "HPHT_001" for "HPHT_001-2").
  - `parent_experiment_fk`: FK to the immediate parent experiment.
- **Relationships**:
  - `conditions`: One-to-One with `ExperimentalConditions`.
  - `results`: One-to-Many with `ExperimentalResults`.
  - `notes`: One-to-Many with `ExperimentNotes`.
  - `modifications`: One-to-Many with `ModificationsLog`.
  - `external_analyses`: One-to-Many with `ExternalAnalysis`.
  - `xrd_phases`: One-to-Many with `XRDPhase` (Aeris time-series).

### `ExperimentNotes`
Stores timestamped notes/logs for an experiment.
- **Fields**: `experiment_id`, `experiment_fk`, `note_text`, `created_at`, `updated_at`.
- **Relationships**: Linked to `Experiment`.

### `ModificationsLog`
Audit trail for tracking changes to records.
- **Fields**: `experiment_id`, `experiment_fk`, `sample_id` (String, nullable — bare String ID, no FK, matching `experiment_id` pattern), `modified_by`, `modification_type` (create/update/delete), `modified_table`, `old_values` (JSON), `new_values` (JSON), `created_at`.

---

## Experimental Conditions & Chemicals
Defined in `database/models/conditions.py` and `database/models/chemicals.py`.

### `ExperimentalConditions`
Defines the parameters and setup for an experiment.
- **Key Fields**:
  - `temperature_c`, `initial_ph`, `rock_mass_g`, `water_volume_mL`.
  - `reactor_number`, `stir_speed_rpm`, `room_temp_pressure_psi`, `rxn_temp_pressure_psi`.
  - `experiment_type` (e.g., "Serum", "HPHT"), `particle_size`, `feedstock`.
  - `initial_conductivity_mS_cm`, `core_height_cm`, `core_width_cm`, `core_volume_cm3`.
  - `co2_partial_pressure_MPa`, `confining_pressure`, `pore_pressure`, `flow_rate`.
  - `initial_nitrate_concentration`, `initial_dissolved_oxygen`, `initial_alkalinity`.
- **Derived Fields**: `water_to_rock_ratio` (hybrid/property: `formatted_additives` from chemical_additives).
- **Relationships**: `chemical_additives` → One-to-Many with `ChemicalAdditive`.
- **Note**: Legacy fields like `catalyst`, `buffer_system`, `surfactant` are deprecated in favor of `ChemicalAdditive`.

### `Compound`
Inventory of chemical reagents.
- **Fields**: `name` (unique), `formula`, `cas_number`, `molecular_weight_g_mol`.
- **Properties**: `density_g_cm3`, `melting_point_c`, `boiling_point_c`, `solubility`, `hazard_class`.
- **Catalyst Logic**: `preferred_unit`, `catalyst_formula`, `elemental_fraction` for automated catalyst calculations.
- **Metadata**: `supplier`, `catalog_number`, `notes`.

### `ChemicalAdditive`
Join table linking `ExperimentalConditions` to `Compound` with specific quantities.
- **Keys**: `experiment_id` (FK to `experimental_conditions.id`), `compound_id` (FK to `compounds.id`); unique per (experiment, compound).
- **Fields**: `amount`, `unit` (AmountUnit enum: g, mg, mM, ppm, % of Rock, etc.), `addition_order`, `addition_method`, `purity`, `lot_number`, `supplier_lot`.
- **Calculated Fields**:
  - `mass_in_grams`, `moles_added`, `final_concentration`, `concentration_units`.
  - For catalysts: `elemental_metal_mass`, `catalyst_percentage`, `catalyst_ppm`.

---

## Experimental Results
Defined in `database/models/results.py`.

### `ExperimentalResults`
Parent table for all result data at a specific timepoint.
- **Key Fields**:
  - `experiment_fk`, `time_post_reaction_days`, `time_post_reaction_bucket_days`, `cumulative_time_post_reaction_days`.
  - `is_primary_timepoint_result`: Boolean flag for the main result record of a timepoint (unique per experiment+bucket).
  - `description` (required).
- **Relationships**: `scalar_data` (One-to-One `ScalarResults`), `icp_data` (One-to-One `ICPResults`), `files` (One-to-Many `ResultFiles`).

### `ScalarResults`
Stores solution chemistry measurements.
- **Fields**:
  - `final_ph`, `final_conductivity_mS_cm`, `final_dissolved_oxygen_mg_L`, `final_nitrate_concentration_mM`, `final_alkalinity_mg_L`.
  - `gross_ammonium_concentration_mM`, `background_ammonium_concentration_mM`, `ammonium_quant_method`.
  - `ferrous_iron_yield`, `grams_per_ton_yield`, `sampling_volume_mL`, `measurement_date`.
  - `co2_partial_pressure_MPa`.
- **Hydrogen (H2)** — always stored in **ppm (vol/vol)**:
  - Inputs: `h2_concentration` (ppm), `h2_concentration_unit` (always `'ppm'`), `gas_sampling_volume_ml`, `gas_sampling_pressure_MPa`.
  - Derived (PV = nRT at 20 °C): `h2_micromoles`, `h2_mass_ug`, `h2_grams_per_ton_yield`.
- **Background**: `background_experiment_id`, `background_experiment_fk` (optional FK to `Experiment`).

### `ICPResults`
Stores ICP-OES elemental analysis data.
- **Fixed Columns**: `fe`, `si`, `mg`, `ca`, `ni`, `cu`, `mo`, `zn`, `mn`, `cr`, `co`, `al`, `sr`, `y`, `nb`, `sb`, `cs`, `ba`, `nd`, `gd`, `pt`, `rh`, `ir`, `pd`, `ru`, `os`, `tl` (Float, ppm).
- **Flexible Data**: `all_elements` (JSON) stores full dataset.
- **Metadata**: `dilution_factor`, `instrument_used`, `detection_limits` (JSON), `measurement_date`, `sample_date`, `raw_label`, `created_at`, `updated_at`.

### `ResultFiles`
Stores paths to files associated with a result (e.g., raw instrument logs).
- **Fields**: `result_id`, `file_path`, `file_name`, `file_type`, `created_at`.

---

## Samples & Inventory
Defined in `database/models/samples.py`.

### `SampleInfo`
Geological sample metadata.
- **Primary Key**: `sample_id` (String).
- **Fields**: `rock_classification`, `state`, `country`, `locality`, `latitude`, `longitude`, `description`, `characterized` (Boolean), `created_at`, `updated_at`.
- **Relationships**: `experiments`, `external_analyses`, `photos` (`SamplePhotos`), `elemental_results` (`ElementalAnalysis`).

### `SamplePhotos`
Photos associated with a sample.
- **Fields**: `sample_id`, `file_path`, `file_name`, `file_type`, `description`, `created_at`.

---

## External Analysis
Defined in `database/models/analysis.py`, `database/models/xrd.py`, and `database/models/characterization.py`.

### `ExternalAnalysis`
Container for external lab reports.
- **Key Fields**: `sample_id`, `experiment_fk`, `experiment_id`, `analysis_type`, `analysis_date`, `laboratory`, `analyst`, `pxrf_reading_no`, `description`, `analysis_metadata` (JSON), `magnetic_susceptibility`.
- **Links**: Can link to `SampleInfo` (characterization) and/or `Experiment` (post-reaction analysis).
- **Relationships**: `analysis_files` (`AnalysisFiles`), `xrd_analysis` (One-to-One `XRDAnalysis`).

### `AnalysisFiles`
Files attached to an external analysis.
- **Fields**: `external_analysis_id`, `file_path`, `file_name`, `file_type`, `created_at`.

### `XRDAnalysis` & `XRDPhase`
- **`XRDAnalysis`**: One-to-One with `ExternalAnalysis`. Stores `mineral_phases` (JSON), `peak_positions`, `intensities`, `d_spacings`, `analysis_parameters` (JSON).
- **`XRDPhase`**: Normalized mineral phases; can link to `sample_id` and/or `external_analysis_id`, or to `experiment_fk`/`experiment_id` for Aeris time-series. Fields: `mineral_name`, `amount` (%), `time_post_reaction_days`, `measurement_date`, `rwp`. Unique on (experiment_id, time_post_reaction_days, mineral_name).

### `PXRFReading`
Raw data from portable XRF scans.
- **PK**: `reading_no` (String).
- **Fields**: Elemental columns (`fe`, `mg`, `ni`, `cu`, `si`, `co`, `mo`, `al`, `ca`, `k`, `au`, `zn`), `ingested_at`, `updated_at`.

### `Analyte` & `ElementalAnalysis`
- **`Analyte`**: Definitional table for elements/oxides; `analyte_symbol` (unique), `unit`.
- **`ElementalAnalysis`**: Links `ExternalAnalysis` to `Analyte` with `analyte_composition` (value in Analyte’s unit). Optional `sample_id`. Unique on (external_analysis_id, analyte_id).

---

## Enumerations
Defined in `database/models/enums.py`.
- **ExperimentStatus**: ONGOING, COMPLETED, CANCELLED.
- **ExperimentType**: Serum, Autoclave, HPHT, Core Flood, Other.
- **FeedstockType**: Nitrogen, Nitrate, Blank.
- **ComponentType**: catalyst, promoter, support, additive, inhibitor.
- **AnalysisType**: pXRF, XRD, SEM, Elemental, Magnetic Susceptibility, Titration, Other.
- **AmmoniumQuantMethod**: NMR, Colorimetric Assay, Ion Chromatography.
- **TitrationType**: Acid-Base, Complexometric, Redox, Precipitation.
- **CharacterizationStatus**: not_started, in_progress, completed, partial.
- **ConcentrationUnit**: ppm, mM, M, %, wt%.
- **PressureUnit**: psi, bar, atm, Pa, kPa, MPa.
- **AmountUnit**: g, mg, μg, kg, μL, mL, L, μmol, mmol, mol, ppm, mM, M, %, wt%, % of Rock.

---

## Reporting Views (Power BI)

SQL views are created at application startup so Power BI (and other reporting tools) can query flattened, one-row-per-primary-result datasets. View creation runs in `database/event_listeners.py` on engine connect: views are dropped and recreated so their definitions stay in sync with the current schema.

### `v_experiment_additives_summary`

One row per experiment: concatenated chemical additives for reporting.

- **Purpose:** Power BI and reports can show “additives” as a single text column (e.g. “Mg(OH)₂ 5 g; Magnetite 1 g”) without joining through conditions and compounds.
- **Definition:** `chemical_additives` → `experimental_conditions` → `experiments`, joined to `compounds`; `GROUP BY e.experiment_id` with `GROUP_CONCAT(c.name || ' ' || amount || ' ' || unit, '; ')` as `additives_summary`.
- **Key column:** `experiment_id`, `additives_summary`.

### `v_primary_experiment_results`

One row per **primary** result timepoint per experiment, with scalar and ICP data resolved by experiment + time bucket.

- **Purpose:** Dynamic Power BI dashboards can use this as the main fact table: one row per experiment per timepoint, with all key scalars and ICP elements in one place. No need to join `experimental_results`, `scalar_results`, and `icp_results` in the report.
- **Logic:**
  - **Base:** Rows from `experimental_results` where `is_primary_timepoint_result = 1`.
  - **Scalar/ICP resolution:** For each (experiment_fk, time_post_reaction_bucket_days), scalar and ICP rows are picked with `ROW_NUMBER() ... ORDER BY is_primary_timepoint_result DESC, id DESC` so the primary (or latest) result per bucket is chosen.
- **Columns (summary):**
  - Experiment and result: `experiment_id`, `experiment_fk`, `result_id`, `time_post_reaction_days`, `time_post_reaction_bucket_days`, `cumulative_time_post_reaction_days`, `result_description`, `result_created_at`.
  - Scalar: `scalar_result_id`, `gross_ammonium_concentration_mM`, `background_ammonium_concentration_mM`, `grams_per_ton_yield`, `final_ph`, `final_nitrate_concentration_mM`, `ferrous_iron_yield`, `final_dissolved_oxygen_mg_L`, `final_conductivity_mS_cm`, `final_alkalinity_mg_L`, `co2_partial_pressure_MPa`, `sampling_volume_mL`, `ammonium_quant_method`, `background_experiment_fk`, `scalar_measurement_date`.
  - H2: `h2_concentration`, `h2_concentration_unit`, `gas_sampling_volume_ml`, `gas_sampling_pressure_MPa`, `h2_micromoles`, `h2_mass_ug`, `h2_grams_per_ton_yield`.
  - ICP metadata: `icp_result_id`, `icp_dilution_factor`, `icp_raw_label`, `icp_measurement_date`, `icp_sample_date`, `icp_instrument_used`.
  - ICP elements (ppm): `icp_fe_ppm`, `icp_si_ppm`, `icp_ni_ppm`, … (all fixed ICP element columns with `icp_*_ppm` naming).

**Where views are created:** `database/event_listeners.py` runs `DROP VIEW IF EXISTS` then `CREATE VIEW` for each view in a `try` block on module import (using the shared `engine`). Failures are ignored so startup is not blocked if the DB is unavailable; views are also recreated in Alembic migrations when dependent tables change (e.g. new ICP columns), so the canonical definitions stay aligned with the schema documented here.
