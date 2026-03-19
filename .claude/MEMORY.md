# Experiment Tracking System — Schema & Architecture Reference

## Quick Reference: Current Database State

**Total Records (SQLite baseline):**
- Experiments: 625 | Samples: 598 | Compounds: 70
- Experimental Results: 928 (Scalar: 713, ICP: 238)
- External Analyses: 632 | Chemical Additives: 917
- XRD Phases: 233 | pXRF Readings: 708
- Notes: 706 | Modifications Log: 2,281

---

## Core Schema Blocks

### 1. Experiment Hub (experiments.py)
- `Experiment` (PK: id, unique: experiment_id)
  - **Key fields:** experiment_number (auto-inc), status (ONGOING/COMPLETED/CANCELLED)
  - **Lineage:** base_experiment_id, parent_experiment_fk (tracks inheritance)
  - **Relations:** conditions (1:1), results (1:M), notes (1:M), modifications (1:M), external_analyses (1:M), xrd_phases (1:M)

### 2. Experimental Setup (conditions.py, chemicals.py)
- `ExperimentalConditions` (1:1 with Experiment)
  - Temperature, pH, rock mass, water volume, reactor number, pressure fields
  - FK: `chemical_additives` (1:M) → `Compound` (many:1)

- `Compound` (70 total)
  - Inventory: formula, CAS, density, hazard_class
  - **Catalyst logic:** `catalyst_formula`, `elemental_fraction` for ppm calculations

- `ChemicalAdditive` (917 records)
  - **Calculated fields:** mass_in_grams, moles_added, final_concentration, catalyst_ppm
  - Join table: (experiment_id, compound_id) unique

### 3. Results Branch (results.py)
- `ExperimentalResults` (parent, 928 total)
  - FK: experiment_fk
  - **Timepoint tracking:** time_post_reaction_days, time_post_reaction_bucket_days, cumulative_time_post_reaction_days
  - **Flag:** is_primary_timepoint_result (1 per experiment per bucket)
  - Relations: scalar_data (1:1 ScalarResults), icp_data (1:1 ICPResults), files (1:M ResultFiles)

- `ScalarResults` (713 records)
  - Solution chemistry: pH, conductivity, dissolved oxygen, nitrate, alkalinity
  - **H2 handling:** always stored as ppm, derives micromoles/mass/yield
  - Background correction: background_experiment_fk (optional)
  - Ammonium: gross + background, quant_method (NMR/Colorimetric/IonChromo)

- `ICPResults` (238 records)
  - **Fixed columns:** fe, si, mg, ca, ni, cu, mo, zn, mn, cr, co, al, sr, y, nb, sb, cs, ba, nd, gd, pt, rh, ir, pd, ru, os, tl (all ppm)
  - **Flexible:** all_elements (JSON), detection_limits (JSON)
  - Metadata: dilution_factor, instrument_used, raw_label, measurement_date

### 4. Samples & Inventory (samples.py)
- `SampleInfo` (598 records, PK: sample_id String)
  - Geological: rock_classification, state, country, locality, lat/long
  - Relations: experiments (1:M), external_analyses (1:M), photos (1:M), elemental_results (1:M)

- `SamplePhotos` (227 files)

### 5. External Analysis (analysis.py, xrd.py, characterization.py)
- `ExternalAnalysis` (632 records)
  - Can link: sample_id (characterization) and/or experiment_fk (post-reaction)
  - Metadata: analysis_type, analysis_date, laboratory, analyst
  - Relations: analysis_files (1:M), xrd_analysis (1:1)

- `XRDAnalysis` (1:1 with ExternalAnalysis)
  - **Flexible:** mineral_phases (JSON), peak_positions (JSON), analysis_parameters (JSON)

- `XRDPhase` (233 records)
  - **Dual-link:** can be (sample_id) OR (experiment_fk + time_post_reaction_days)
  - For Aeris time-series: experiment_fk + time_post_reaction_days + mineral_name = unique
  - Fields: mineral_name, amount (%), rwp

- `PXRFReading` (708 records, PK: reading_no String)
  - Raw elemental data: Fe, Mg, Ni, Cu, Si, Co, Mo, Al, Ca, K, Au, Zn

- `Analyte` (61 records)
  - Definitional: analyte_symbol (unique), unit

- `ElementalAnalysis` (0 current)
  - Links ExternalAnalysis → Analyte with composition value
  - Unique: (external_analysis_id, analyte_id)

---

## Key Design Decisions (READ-ONLY)

1. **JSON Fields Are Intentional**
   - ICPResults: `all_elements`, `detection_limits`
   - XRDAnalysis: `mineral_phases`, `peak_positions`, `d_spacings`, `analysis_parameters`
   - In PostgreSQL: become JSONB for query performance ✅ do NOT flatten to separate tables

2. **Chemical Additives Calculated Fields**
   - `catalyst_ppm`, `final_concentration`, `elemental_metal_mass` are derived
   - Recalculated on write via SQLAlchemy hybrid properties
   - ✅ Preserve formulas in models, do NOT denormalize to storage

3. **H2 Storage Convention**
   - Always ppm (vol/vol) in database
   - Derives: h2_micromoles, h2_mass_ug, h2_grams_per_ton_yield (using PV=nRT @ 20°C)
   - ✅ Do NOT add alternative unit columns; normalize on upload

4. **Timepoint Organization**
   - `time_post_reaction_days` = actual measured timepoint
   - `time_post_reaction_bucket_days` = rounded/bucketed for grouping
   - `is_primary_timepoint_result` = flag for single canonical result per bucket
   - Views use this for one-row-per-experiment aggregation

5. **XRD Dual-Link Pattern**
   - Can link to SampleInfo (characterization pre-experiment)
   - OR link to Experiment + timepoint (post-reaction)
   - `XRDPhase` is the normalized fact table

---

## Migration Path: SQLite → PostgreSQL (Milestone 1)

**Before writing any Alembic migration:**
1. Verify all models in `database/models/` are database-agnostic (no SQLite-specific overrides)
2. JSON columns verified to use generic SQLAlchemy types, migrate to JSONB via Alembic
3. AUTOINCREMENT → SERIAL/IDENTITY handled by Alembic
4. Use SQLAlchemy Core (not ORM) for bulk data transfer

**After migration:**
- ✅ All 625 experiments + 598 samples + all related records present
- ✅ FK constraints enforce in PostgreSQL
- ✅ Views created and queryable
- ✅ Alembic downgrade works

---

## Reporting Views (Power BI Integration)

**v_experiment_additives_summary**
- One row per experiment: flattened additives (e.g. "Mg(OH)₂ 5 g; Magnetite 1 g")

**v_primary_experiment_results**
- One row per experiment per primary timepoint
- Joins: Experiment → ExperimentalResults (primary only) → ScalarResults + ICPResults
- Columns: experiment_id, time_post_reaction_days, scalars (pH, conductivity, H2), ICP elements (fe_ppm, si_ppm, ...)

---

## Before Schema Changes: Checklist

See `.claude/rules/schema-checklist.md` before modifying models.

---

## Frontend Contract: Results UI (from Bulk Upload)

See `memory/project_bulk_upload_frontend_contract.md` for the full field mapping.

**Summary:** Results UI field labels and grouping must mirror the master bulk upload spreadsheet:
- **Headline metrics:** NH4 (mM), H2 (ppm)
- **Chemistry:** Sample pH, Sample Conductivity (mS/cm)
- **H2 inputs:** Gas Volume (mL), Gas Pressure (psi) — secondary/collapsed
- **Dates:** Sample Date, NMR Run Date, ICP Run Date, GC Run Date — "Provenance" section
- **Derived (display-only):** h2_micromoles, h2_grams_per_ton_yield, grams_per_ton_yield
