# Spec: Sample Chemical Composition Upload

**Upload card title:** Sample Chemical Composition
**Backend parser:** `backend/services/bulk_uploads/elemental_composition.py`
**Template:** `docs/upload_templates/elemental_composition_template.xlsx` (downloadable)

---

## Overview

Accepts a wide-format Excel or CSV file where:
- The first column identifies a **Sample ID**
- All remaining columns identify chemical analytes, with units embedded in the column header

This replaces the need for a separate analyte-definition step. The parser extracts both
the analyte symbol and its unit from the column header in one pass.

This parser handles the **flexible custom multi-element upload** pattern. The existing
`ActlabsRockTitrationService` (for structured ActLabs report files) remains a separate
upload card and is unchanged.

---

## File Format

- **Format:** Excel (`.xlsx`) or CSV
- **Target sheet:** First sheet not containing "INSTRUCTION" in its name
- **Headers:** First row is always the header row (no multi-row header heuristics)

---

## Column Specifications

### Required Column
- `Sample ID` (case-insensitive): The first column. Must match an existing `SampleInfo`
  record. Matching is case-insensitive and delimiter-insensitive (same strategy as rock
  inventory parser).

### Analyte Columns (all remaining columns)
Header format: `Symbol (unit)` or `Symbol_unit` or bare `Symbol`

#### Unit extraction rules (applied in order)

1. **Parenthetical unit:** `Sulfur (%)` → symbol=`Sulfur`, unit=`%`
2. **Bracketed unit:** `Fe [ppm]` → symbol=`Fe`, unit=`ppm`
3. **Underscore-separated unit:** `Ca_ppb` → symbol=`Ca`, unit=`ppb`
4. **No unit present:** `SiO2` → symbol=`SiO2`, unit=`%` (default)

Supported units (case-insensitive): `%`, `wt%`, `ppm`, `ppb`, `mg/kg`, `g/t`

If an unrecognized unit string is encountered, default to `ppm` and log a warning.

#### Symbol normalization
After unit extraction, the symbol string is:
- Stripped of whitespace
- Not further modified (preserve case — `SiO2` stays `SiO2`, `Fe` stays `Fe`)

---

## Parsing Logic

### Sample ID lookup
- Normalize the sample ID: uppercase, remove spaces, preserve hyphens
- Match against `SampleInfo.sample_id` using the same delimiter-insensitive strategy
  as `rock_inventory.py`
- If no match: skip row, log error

### Analyte resolution
For each analyte column:
1. Parse the symbol and unit from the header (rules above)
2. Look up the `Analyte` table for a record with matching `analyte_symbol` (case-insensitive)
3. If not found: **auto-create** the `Analyte` record with the extracted unit
   (log a warning that a new analyte was created)
4. Convert cell value to float. Skip blank, NaN, or non-numeric cells without failing the row.

### Upsert logic
For each valid `(sample_id, analyte_id, value)` triple:
- If an `ElementalAnalysis` record exists: update `analyte_composition`
- If not: create a new `ElementalAnalysis` record linked to an `ExternalAnalysis`
  record for the sample (type=`Elemental`)

### ExternalAnalysis record
- One `ExternalAnalysis` record per sample per upload (type=`Elemental`)
- `analysis_date` = today's date
- `laboratory` = `None` (not specified in this upload format)
- If an `ExternalAnalysis` record of type `Elemental` already exists for the sample,
  reuse it rather than creating a duplicate

---

## Overwrite Behavior

- Default: if an `ElementalAnalysis` row exists for the `(sample_id, analyte_id)` pair,
  skip it (do not overwrite)
- Global overwrite checkbox in the UI sets `overwrite=True` for all rows
- An `Overwrite` column in the file provides per-row control (truthy: `TRUE`, `true`, `1`)

---

## Template

Two-row header template:

```
Sample ID | Sulfur (%) | Iron (%) | SiO2 (%) | Ni (ppm) | Cu (ppm)
          | Required   |          |           |           |
```

Row 2 is an instructions row (shaded, not parsed). The parser skips rows where
`Sample ID` is blank.

---

## Relationship to ActLabs Parser

The `ActlabsRockTitrationService` (upload card: **ActLabs Rock Titration**) remains
unchanged and is kept as a separate card. It handles the heuristic multi-header
ActLabs report format. This flexible upload handles simpler custom tables.

Users who receive ActLabs reports use the ActLabs card.
Users who want to enter custom analyte data from any source use this card.

---

## API Endpoint

```
POST /api/bulk-uploads/elemental-composition
```

- `multipart/form-data`: `file` (required), `overwrite` (boolean, optional, default false)
- Returns `UploadResult`
- Requires Firebase auth

---

## Output

```python
UploadResult(
    created=N,      # ElementalAnalysis rows created
    updated=N,      # ElementalAnalysis rows updated
    skipped=N,      # rows skipped (sample not found or overwrite=false on existing)
    errors=[...],   # rows that failed entirely
    warnings=[...], # new analytes auto-created; unrecognized units defaulted
    feedbacks=[...] # per-row detail for the UI error table
)
```
