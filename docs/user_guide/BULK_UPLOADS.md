# Bulk Uploads User Guide

The Bulk Uploads page lets you ingest large datasets into the experiment tracking system
without entering rows one at a time. Each upload type is an accordion row — click a row
header to expand it, drop a file, and submit. Only one row can be open at a time.

---

## Common behaviour for all upload types

| Behaviour | Details |
|-----------|---------|
| **Auth required** | You must be logged in. Uploads fail silently if your session has expired — refresh the page and re-login. |
| **Result summary** | After processing you see Created / Updated / Skipped counts and an expandable error list. |
| **Atomic transactions** | If the file fails validation mid-way, **zero rows are written**. Fix the file and resubmit. |
| **Template download** | Rows that have a template show a download button. Use the template to avoid column name errors. |
| **Calc engine** | Where relevant (scalar results), derived fields (H₂ yield, g/t yield, etc.) are recalculated automatically. |

---

## 1 — Master Results Sync

**Endpoint:** `POST /api/bulk-uploads/master-results`

Reads the team's shared Excel tracker from a configured SharePoint path
(`C:\Users\MathewHearl\Addis Energy\...\Master Reactor Sampling Tracker.xlsx`).

Two modes:
- **Sync from SharePoint** — click the "Sync from SharePoint" button to pull from the
  configured path. No file upload needed.
- **Manual upload** — drag-and-drop the xlsx file for a one-off import when the
  SharePoint path is unavailable.

### Expected sheet: `Dashboard`

| Column | Required | Notes |
|--------|----------|-------|
| Experiment ID | ✓ | Must match an existing experiment |
| Duration (Days) | ✓ | Float; rows with missing duration are skipped |
| Description | | Free text |
| Sample Date | | Date |
| NMR Run Date | | Date |
| ICP Run Date | | Date |
| GC Run Date | | Date |
| NH4 (mM) | | Ammonium concentration |
| H2 (ppm) | | H₂ concentration in ppm vol/vol |
| Gas Volume (mL) | | |
| Gas Pressure (psi) | | Converted to MPa automatically |
| Sample pH | | |
| Sample Conductivity (mS/cm) | | |
| Sampled Solution Volume (mL) | | Volume of production fluid collected at this timepoint (mL) |
| Modification | | Brine modification note |
| Overwrite | | `TRUE` / `FALSE` — overwrite existing result row at same timepoint |

Rows where both Experiment ID and Duration (Days) are present create or update a
`ScalarResults` record. The calc engine re-runs for every affected row.

---

## 2 — ICP-OES Data

**Endpoint:** `POST /api/bulk-uploads/icp-oes`

Imports raw ICP-OES output CSV files directly from the instrument export.

The parser expects the standard instrument CSV format:
- Column 1: `Sample_ID` matching an existing `ExperimentalResults` row
- Remaining columns: one per element (e.g. `Fe_ppm`, `Si_ppm`, `Mg_ppm`, …)
- Blank rows and rows with `QC` / `BLANK` sample IDs are skipped
- When multiple spectral lines exist for the same element the best intensity is used

No template available — use the raw instrument export.

---

## 3 — XRD Mineralogy

**Endpoint:** `POST /api/bulk-uploads/xrd-mineralogy`
**Template:** available in the download button (ActLabs wide-format)

The XRD upload auto-detects which format your file uses:

| Detected format | How detected | What it does |
|-----------------|-------------|--------------|
| **Aeris** | Sample ID column matches `^\d{8}_.+?-d\d+_\d+$` | Routes to Aeris time-series XRD parser |
| **ActLabs** | First column is `sample_id` with plain sample IDs | Routes to ActLabs XRD report parser |
| **Unknown** | Neither pattern found | Returns an error — no rows written |

**ActLabs wide-format template columns:**

| Column | Notes |
|--------|-------|
| sample_id | Existing sample ID |
| Quartz / Calcite / … | One column per mineral; values are percentages |

Mineral column headers may include a `%` suffix — it is stripped automatically.

**Aeris format:** comes directly from the Aeris diffractometer export. No template
needed; upload the raw `.xlsx` file from the instrument.

---

## 4 — Solution Chemistry

**Endpoint:** `POST /api/bulk-uploads/scalar-results`
**Template:** available

Bulk-creates or updates `ScalarResults` rows (solution chemistry measurements).

| Column | Required | Notes |
|--------|----------|-------|
| experiment_id | ✓ | Must match an existing experiment |
| time_post_reaction_days | ✓ | Float |
| description | ✓ | Short label for the timepoint |
| final_ph | | |
| final_conductivity_mS_cm | | |
| gross_ammonium_concentration_mM | | |
| h2_concentration | | ppm vol/vol |
| gas_sampling_volume_ml | | |
| gas_sampling_pressure_MPa | | MPa |
| overwrite | | `TRUE` overwrites an existing row at the same timepoint |

The calc engine recalculates H₂ yield, g/t yield, and ammonium yield after each write.

---

## 5 — New Experiments

**Endpoint:** `POST /api/bulk-uploads/new-experiments`
**Template:** available — includes next-ID hints before download

Creates `Experiment` records and optional `ExperimentalConditions` rows in bulk.

The expanded card shows **Next ID chips** (e.g. "Next HPHT: 072 · Next Serum: 043 · Next CF: 008")
so you can fill the template with the correct experiment IDs before uploading.

| Column | Required | Notes |
|--------|----------|-------|
| experiment_id | ✓ | e.g. `HPHT_072` |
| experiment_type | ✓ | HPHT / Serum / Autoclave / Core Flood / Other |
| status | | Default ONGOING |
| researcher | | |
| date | | YYYY-MM-DD |
| sample_id | | Must exist in SampleInfo |
| temperature_c | | |
| initial_ph | | |
| rock_mass_g | | |
| water_volume_mL | | |
| reactor_number | | |

---

## 6 — Timepoint Modifications

**Endpoint:** `POST /api/bulk-uploads/timepoint-modifications`
**Template:** available

Bulk-sets the brine modification description on existing result rows.
Use this when you added or replaced chemicals mid-experiment at a specific sampling point.

| Column | Required | Notes |
|--------|----------|-------|
| experiment_id | ✓ | Must match an existing experiment |
| time_point | ✓ | Days (float); must match an existing result row within ±0.0001 day |
| modification_description | ✓ | Text to set as `brine_modification_description` |

Validation rules:
- Duplicate `(experiment_id, time_point)` pairs in one file are rejected — the whole file
  is returned with an error and nothing is written
- If a row already has a modification, it is skipped unless `overwrite_existing=TRUE`

An audit log entry (`ModificationsLog`) is written for every changed row.

---

## 7 — Rock Inventory

**Endpoint:** `POST /api/bulk-uploads/rock-inventory`
**Template:** available

Creates or updates `SampleInfo` records (geological sample metadata).

Sample IDs are normalised to uppercase with spaces and underscores removed
(`S_ROCK_002` → `SROCK002`). The normalised form is stored. Existing records are
found by normalised matching, so format inconsistencies are handled gracefully.

| Column | Required | Notes |
|--------|----------|-------|
| sample_id | ✓ | |
| rock_classification | | e.g. "Dunite", "Basalt" |
| state | | Province/state |
| country | | |
| locality | | Specific collection site |
| latitude / longitude | | Decimal degrees |
| description | | Free text |
| characterized | | `TRUE` / `FALSE` |
| pxrf_reading_no | | Links existing pXRF readings to the sample |
| overwrite | | `TRUE` clears and rewrites all optional fields from this row |

Image files can be attached during upload — file names (without extension) must
match a sample ID to be linked automatically.

---

## 8 — Chemical Inventory

**Endpoint:** `POST /api/bulk-uploads/chemical-inventory`
**Template:** available

Creates or updates `Compound` records in the reagent inventory.
Lookup is by name (case-insensitive) or CAS number.

| Column | Required | Notes |
|--------|----------|-------|
| name | ✓ | Case-insensitive unique identifier |
| formula | | e.g. `Mg(OH)₂` |
| cas_number | | e.g. `1309-42-8` |
| density | | g/cm³ |
| melting_point | | °C |
| boiling_point | | °C |
| solubility | | Free text |
| hazard_class | | |
| supplier | | |
| catalog_number | | |
| notes | | |

> **Known issue:** The service currently ignores the `molecular_weight` column due to a
> column naming mismatch (`molecular_weight` vs `molecular_weight_g_mol`). All other
> fields are processed correctly.

---

## 9 — Sample Chemical Composition

**Endpoint:** `POST /api/bulk-uploads/elemental-composition`
**Template:** available

Imports wide-format elemental composition data into `ElementalAnalysis` rows.

File format: first column `sample_id`; remaining columns are analyte symbols
(e.g. `SiO2`, `Fe2O3`, `MgO`). Values are numeric percentages or concentrations.

- Analyte symbols must match existing `Analyte` records, **or** provide a `default_unit`
  query parameter (`?default_unit=wt%`) to auto-create unknown analytes.
- Rows with unknown `sample_id` are recorded as errors.
- Blank cells for a given analyte are silently skipped.

---

## 10 — ActLabs Rock Analysis

**Endpoint:** `POST /api/bulk-uploads/actlabs-rock`

Imports ActLabs geochemical analysis reports (Excel or CSV).
Use the raw file from the ActLabs client portal — no reformatting needed.

The parser uses heuristic header detection:
- Row 2 (0-indexed row 2): analyte symbols
- Row 3 (0-indexed row 3): unit symbols
- Data starts after the "Analysis Method" row

Values prefixed with `<` or `>` (e.g. `<0.01`) are stored as numeric only.
`nd`, `na`, `n/a` values are treated as blank and skipped.

No template available — upload the ActLabs-exported file directly.

---

## 11 — Experiment Status Update

**Endpoint:** `POST /api/bulk-uploads/experiment-status`
**Template:** available

Preview and apply bulk experiment status transitions (ONGOING / COMPLETED).

Logic:
- All experiments listed in the file are moved to **ONGOING**
- All ONGOING experiments with HPHT conditions **not** in the file are moved to **COMPLETED**
- Experiment IDs not found in the database are reported as `missing_ids`

The endpoint uses a two-phase preview → apply workflow:
1. Upload the file to see a preview of what will change
2. The UI displays the pending changes; user confirms
3. Changes are applied atomically

| Column | Required | Notes |
|--------|----------|-------|
| experiment_id | ✓ | |
| reactor_number | | Optional; updates the reactor assignment if provided |

---

## 12 — pXRF Readings

**Endpoint:** `POST /api/bulk-uploads/pxrf`

Imports raw pXRF scan data into `PXRFReading` records.

Use the raw Excel export from the Olympus Vanta or equivalent portable XRF device.
No template available — upload the raw instrument file directly.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "Missing required column" error | Column header typo or wrong template | Download the current template and re-map your columns |
| All rows skipped | `sample_id` or `experiment_id` column values don't match DB | Check for extra spaces, underscores, or capitalisation differences |
| Counts look wrong but no errors | Rows already existed and `overwrite` was not `TRUE` | Set `overwrite = TRUE` in the relevant rows |
| Master Results sync returns "not found" | SharePoint path not accessible from the server | Upload the file manually instead |
| Zero rows written despite valid file | Mid-file validation failure or DB constraint violation — see the errors list | Fix the flagged rows and resubmit |
