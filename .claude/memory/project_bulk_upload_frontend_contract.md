---
name: bulk_upload_frontend_contract
description: Master bulk upload spreadsheet columns and how they map to DB fields — drives Results UI field labels and display priorities in M5+
type: project
---

The primary data entry path for results is `master_bulk_upload.py` + `scalar_results_service.py`. Frontend Results UI should mirror the spreadsheet's column names as user-facing labels.

**Required columns (must be present for a row to be accepted):**
- `Experiment ID` → `experiment_id`
- `Duration (Days)` → `time_post_reaction_days`

**Solution chemistry columns (the core result measurements):**
| Spreadsheet Label | DB Field | Notes |
|---|---|---|
| `NH4 (mM)` | `gross_ammonium_concentration_mM` | Primary yield metric |
| `H2 (ppm)` | `h2_concentration` | Always stored ppm; unit hardcoded |
| `Gas Volume (mL)` | `gas_sampling_volume_ml` | Required for H2 yield calc |
| `Gas Pressure (psi)` | `gas_sampling_pressure_MPa` | Converted psi→MPa on ingest |
| `Sample pH` | `final_ph` | |
| `Sample Conductivity (mS/cm)` | `final_conductivity_mS_cm` | |

**Date/provenance columns:**
| Spreadsheet Label | DB Field |
|---|---|
| `Sample Date` | `measurement_date` |
| `NMR Run Date` | `nmr_run_date` |
| `ICP Run Date` | `icp_run_date` |
| `GC Run Date` | `gc_run_date` |

**Other columns:**
- `Description` → `experiment_notes` (`note_type='observation'`, scoped to the result, `created_by='master_bulk_upload'`; blank writes no note)
- `Modification` → `experiment_notes` (`note_type='modification'`, scoped to the result, `created_by='master_bulk_upload'`)
- `Overwrite` → `_overwrite` bool — controls merge behaviour

**Fields in `SCALAR_UPDATABLE_FIELDS` NOT in the bulk upload CSV** (set via API/manual entry only):
- `ferrous_iron_yield`, `background_ammonium_concentration_mM`, `background_experiment_id`
- `final_nitrate_concentration_mM`, `final_dissolved_oxygen_mg_L`, `co2_partial_pressure_MPa`
- `final_alkalinity_mg_L`, `sampling_volume_mL`

**Derived fields (calculated by `calculate_yields()`, display-only in frontend):**
- `h2_micromoles`, `h2_mass_ug`, `h2_grams_per_ton_yield`
- `grams_per_ton_yield` (ammonium yield from gross - background)

**How to apply:**
- Results tab in ExperimentDetail should group fields to match the spreadsheet: timepoint → chemistry (NH4, H2, pH, conductivity) → dates (Sample/NMR/ICP/GC) → derived yields
- Use spreadsheet column names as display labels (not DB field names)
- NH4 (mM) and H2 (ppm) are the headline metrics — surface these first/largest in any result card
- Gas volume + pressure are supporting inputs for H2 yield; show them collapsed/secondary
- Run dates (NMR/ICP/GC) are metadata; show in a collapsed "Provenance" section
- The `Overwrite` flag is not displayed in the results UI; it is upload-only behaviour
