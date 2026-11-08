---
paths:
  - "database/models/**"
  - "database/data_migrations/**"
  - "alembic/**"
  - "tests/models/**"
---

# Database Schema Documentation

This document provides a comprehensive overview of the database schema for the Experiment Tracking System. The schema is built using SQLAlchemy ORM and deployed on PostgreSQL.

The models are modularized within the `database/models/` directory.

**Reporting intent:** The schema and the SQL views (`.claude/rules/MODELS-views.md`) are designed to support **dynamic Power BI dashboards**. Views provide flattened, reporting-friendly datasets (one row per experiment timepoint, joined scalars and ICP, additives summary) so Power BI can connect directly to the database and refresh dashboards as data changes, without application-layer ETL.

## Where each topic lives

This file is the index. The detailed notes are split into rule files that load only when Claude works with the matching code; read the one you need directly when your task touches its topic from elsewhere.

| Topic | File |
|---|---|
| Experiment deletion (single + bulk), impact counts, audit row (issues #99, #109) | `.claude/rules/MODELS-deletion.md` |
| Lineage, ID grammar, `-t` timepoint tokens, letter vs vial, group addressing (issues #86, #87, #98, #101) | `.claude/rules/MODELS-lineage.md` |
| `ExperimentNotes` — typed notes, scope rules, write paths (issues #118, #122) | `.claude/rules/MODELS-notes.md` |
| `ExperimentalConditions` — vial size, pore volume, `reactor_series` (Parr), `reactor_slot`, `total_ferrous_iron_g`, 1:1 identity | `.claude/rules/MODELS-conditions.md` |
| `ExperimentalResults`, `ScalarResults` (H2, merge, dates, overwrite), `ICPResults` | `.claude/rules/MODELS-results.md` |
| Power BI views, rollup statistics, `v_core_flood_samples`, `v_hpht_samples`, `v_results_h2_bkg_adjusted*` | `.claude/rules/MODELS-views.md` |

Field names, types and relationships: read the model file named in each section (`database/models/*.py`) — they are the authoritative definition and are not repeated here.

## Core Experiment Models
Defined in `database/models/experiments.py`.

### `Experiment`
The central hub for all experimental data.
- `is_outlier` (Boolean, non-null, default `false`): flags a bad vial (leak, cracked septum). Flagged experiments are excluded from `v_results_scalar_rollup` aggregates **including `n_vials`**, but remain fully visible in all per-row views (`v_results_scalar`, `v_results_h2`, `v_results_icp`, `v_primary_experiment_results`) and on their own pages.
- Deletion, lineage and notes: see the topic files above.

### `ModificationsLog`
Audit trail for tracking changes to records.
- **Fields**: `experiment_id`, `experiment_fk`, `sample_id` (String, nullable — bare String ID, no FK, matching `experiment_id` pattern), `modified_by`, `modification_type` (create/update/delete), `modified_table`, `old_values` (JSON), `new_values` (JSON), `created_at`.

### `H2BackgroundLink` (issue #144)
Defined in `database/models/backgrounds.py`, table `h2_background_links`. Which serum background to subtract from a sample group's H₂. **One row per sample group**, keyed by the base-ID *string* (`base_experiment_id`, UNIQUE, the `COALESCE(base_experiment_id, experiment_id)` group key), so it works for groups with no parent row.
- Exactly one of `background_base_id` (group mode: a whole background replicate set) or `background_stem_id` (vial mode: one stem such as `SERUM_009a`, covering its `-t` vials) is set. The mode is implied by which column is set; there is no enum. `CHECK num_nonnulls(background_base_id, background_stem_id) = 1` and `CHECK background_base_id IS DISTINCT FROM base_experiment_id`.
- Bare String IDs, **no FKs** (like `ModificationsLog.sample_id`). Renaming a group or a background stem therefore disconnects the link, by decision (not in the `denormalized_ids.py` rename fan-out). Deleting a background experiment leaves the link; see `h2_background_for` in `.claude/rules/MODELS-deletion.md`.
- `created_by` (Firebase email), `created_at`, `updated_at`.
- Distinct from `scalar_results.background_experiment_id` / `background_experiment_fk`, which are per-row ammonium provenance and are untouched.
- Writes (`PUT`/`DELETE /api/experiments/groups/{base_id}/h2-background`) log to `ModificationsLog` (`modified_table='h2_background_links'`, `experiment_id=<base_id>`, `experiment_fk=NULL`) and call no `recalculate()`: nothing derived is stored. Adjusted values are view columns (`.claude/rules/MODELS-views.md`).
- Alembic `b7e2d9c4a1f6` creates the table. Its `downgrade` drops both dependent views before the table, because `event_listeners.py` recreates every view on API import.

---

## Chemicals
Defined in `database/models/chemicals.py`. (`ExperimentalConditions` is in `.claude/rules/MODELS-conditions.md`.)

### `Compound`
Inventory of chemical reagents.
- **Catalyst Logic**: `preferred_unit`, `catalyst_formula`, `elemental_fraction` for automated catalyst calculations.

### `ChemicalAdditive`
Join table linking `ExperimentalConditions` to `Compound` with specific quantities.
- **Keys**: `experiment_id` (FK to `experimental_conditions.id`), `compound_id` (FK to `compounds.id`); unique per (experiment, compound).
- **Fields**: `amount`, `unit` (AmountUnit enum: g, mg, mM, ppm, % of Rock, etc.), `addition_order`, `addition_method` (Text, free-text prep/addition description; app-layer bound of 500 chars enforced by `ADDITION_METHOD_MAX_LENGTH` in `database/models/chemicals.py` — the DB column itself is unbounded, per issue #96), `purity`, `lot_number`, `supplier_lot`.
- **Calculated Fields**:
  - `mass_in_grams`, `moles_added`, `final_concentration`, `concentration_units`.
  - For catalysts: `elemental_metal_mass`, `catalyst_percentage`, `catalyst_ppm`.

---

## Results
`ExperimentalResults`, `ScalarResults`, `ICPResults`: `.claude/rules/MODELS-results.md`. `ResultFiles` (`database/models/results.py`) stores file paths for a result.

---

## Samples & Inventory
Defined in `database/models/samples.py`.

### `SampleInfo`
Geological sample metadata.
- **Primary Key**: `sample_id` (String).
- **Fields**:
  - `well_name` (String, nullable): Well or borehole name for core samples (e.g. "Tuscarora Project CT-3").
  - `core_lender` (String, nullable): Organization lending the core sample (e.g. "Geologica").
  - `core_interval_ft` (String, nullable): Depth interval stored as a string (e.g. "895'").
  - `on_loan_return_date` (Date, nullable): Date the core must be returned to the lender.

### `SamplePhotos`
Photos associated with a sample.

---

## External Analysis
Defined in `database/models/analysis.py`, `database/models/xrd.py`, and `database/models/characterization.py`.

### `ExternalAnalysis`
Container for external lab reports.
- **Links**: Can link to `SampleInfo` (characterization) and/or `Experiment` (post-reaction analysis).

### `AnalysisFiles`
Files attached to an external analysis.

### `XRDAnalysis` & `XRDPhase`
- **`XRDAnalysis`**: One-to-One with `ExternalAnalysis`. Stores `mineral_phases` (JSON), `peak_positions`, `intensities`, `d_spacings`, `analysis_parameters` (JSON).
- **`XRDPhase`**: Normalized mineral phases; can link to `sample_id` and/or `external_analysis_id`, or to `experiment_fk`/`experiment_id` for Aeris time-series. Fields: `mineral_name`, `amount` (%), `time_post_reaction_days`, `measurement_date`, `rwp`. Unique on (experiment_id, time_post_reaction_days, mineral_name).

### `PXRFReading`
Raw data from portable XRF scans.
- **PK**: `reading_no` (String).

### `Analyte` & `ElementalAnalysis`
- **`Analyte`**: Definitional table for elements/oxides; `analyte_symbol` (unique), `unit`.
- **`ElementalAnalysis`**: Links `ExternalAnalysis` to `Analyte` with `analyte_composition` (value in Analyte’s unit). Optional `sample_id`. Unique on (external_analysis_id, analyte_id).

---

## Enumerations
Defined in `database/models/enums.py` (read it for current values; changing them breaks existing data).

---
