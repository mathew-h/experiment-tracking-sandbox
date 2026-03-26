# Spec: XRD Mineralogy Upload

**Upload card title:** XRD Mineralogy
**Backend parser:** `backend/services/bulk_uploads/xrd_upload.py` (new unified parser)
**Template:** `docs/upload_templates/xrd_mineralogy_template.xlsx` (downloadable)

---

## Overview

Accepts a wide-format Excel file containing XRD mineral phase data.
Each row represents either:
- A **sample** at characterization time (identified by `Sample ID`), or
- An **experiment** at a specific post-reaction timepoint (identified by `Experiment ID` + `Time (days)`)

The parser auto-detects which mode applies based on the columns present.
Both modes write to `XRDPhase` and `XRDAnalysis` / `ExternalAnalysis`.

---

## File Format

- **Format:** Excel (`.xlsx`) or CSV
- **Target sheet:** First sheet that does not contain "INSTRUCTION" in its name
- **Headers:** Case-insensitive; leading/trailing whitespace stripped

---

## Column Detection and Mode Selection

### Detection logic (evaluated in order)

**Mode A — Sample-based** (characterization data):
- Required column: any column whose normalized name matches `sample_id` or `sample id`
- Optional: `Time (days)` may be absent or blank — treated as characterization (not time-series)

**Mode B — Experiment+timepoint** (post-reaction time-series):
- Required columns: any column matching `experiment_id` or `experiment id` AND any column matching `time (days)`, `time_days`, or `duration (days)`
- `Sample ID` column must be absent OR all values in it must be blank

If neither pattern is detected, the upload is rejected with a clear error:
> "Could not determine upload mode. File must contain either a 'Sample ID' column
> (sample characterization) or both an 'Experiment ID' and 'Time (days)' column
> (post-reaction data)."

### Mineral columns
All columns that are not the identity column(s) (`Sample ID`, `Experiment ID`,
`Time (days)`) are treated as mineral names. Values must be numeric (float) — blanks
and non-numeric cells are skipped without failing the row.

Mineral column header cleaning:
- Strip leading/trailing whitespace
- Strip trailing `[%]`, `(%)`, `%` indicators — these are display decorators only;
  all XRD phase values are stored as percent/wt% regardless

---

## Mode A: Sample-Based

Writes to: `ExternalAnalysis` (type=XRD) → `XRDAnalysis` → `XRDPhase`

For each row:
1. Look up `SampleInfo` by `sample_id` (case-insensitive, delimiter-insensitive match)
2. If not found: skip row, log error
3. Find or create `ExternalAnalysis` record for the sample (type=XRD)
4. Upsert `XRDAnalysis.mineral_phases` JSON with the full mineral dict from the row
5. Upsert individual `XRDPhase` rows keyed on `(sample_id, mineral_name)`
   - `time_post_reaction_days` = `None` (characterization, not time-series)

---

## Mode B: Experiment+Timepoint

Writes to: `ExternalAnalysis` (type=XRD) → `XRDAnalysis` → `XRDPhase`

For each row:
1. Look up `Experiment` by `experiment_id` (delimiter-insensitive match, same strategy as Aeris parser)
2. If not found: skip row, log error
3. Find or create `ExternalAnalysis` record linked to the experiment (type=XRD)
4. Upsert `XRDAnalysis.mineral_phases` JSON
5. Upsert individual `XRDPhase` rows keyed on `(experiment_id, time_post_reaction_days, mineral_name)`

---

## Overwrite Behavior

An `Overwrite` column may be present (truthy: `TRUE`, `true`, `1`, `yes`).

- `Overwrite = FALSE` (default): if a `XRDPhase` row already exists for the key,
  skip without updating
- `Overwrite = TRUE`: update the existing row's `amount` value

A global overwrite checkbox is also available in the UI as a fallback for files
that do not include an `Overwrite` column.

---

## Template

The downloadable template is a two-sheet Excel workbook:

**Sheet 1: Instructions**
- Explains both modes and how to fill the file

**Sheet 2: Data**
Headers (mode A example):
```
Sample ID | Quartz | Calcite | Dolomite | Olivine | Serpentine | ...
```
Headers (mode B example):
```
Experiment ID | Time (days) | Quartz | Calcite | Dolomite | Olivine | ...
```

The template download button shows a toggle in the UI:
> Template format: [Sample-based ▼] / [Experiment + Timepoint]

Selecting a format generates the appropriate header layout.

---

## API Endpoint

```
POST /api/bulk-uploads/xrd-mineralogy
```

- `multipart/form-data`: `file` (required), `overwrite` (boolean, optional, default false)
- Returns `UploadResult`
- Requires Firebase auth

---

## Output

```python
UploadResult(
    created=N,      # XRDPhase rows created
    updated=N,      # XRDPhase rows updated
    skipped=N,      # rows skipped (not found in DB or overwrite=false on existing)
    errors=[...],   # rows that failed validation
    warnings=[...], # experiment/sample IDs not found
    feedbacks=[...] # per-row detail for the UI error table
)
```
