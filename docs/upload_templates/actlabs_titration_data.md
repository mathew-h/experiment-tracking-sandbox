# Actlabs Titration Data Upload Templates

**Source:** [backend/services/bulk_uploads/actlabs_titration_data.py](../../backend/services/bulk_uploads/actlabs_titration_data.py)

## Overview
This module provides services for uploading rock titration data, defining analytes, and importing wide-format elemental compositions. It handles both standard and specific ActLabs format reports.

There are three primary services in this module:
1. **AnalyteService**: For defining or updating analytes and their units.
2. **ElementalCompositionService**: For uploading a simple wide-format table of sample compositions.
3. **ActlabsRockTitrationService**: A specialized parser for ActLabs raw export files (Excel or CSV).

---

## 1. AnalyteService

Handles bulk upsert of analyte definitions.

### Excel Format
- **Format:** Excel file (read using pandas `read_excel`).
- **Headers:** Stripped of whitespace and converted to lowercase.

### Required Columns
- `analyte_symbol` (e.g., "Fe", "SiO2")
- `unit` (e.g., "%", "ppm")

### Parsing Logic
- Iterates over each row to extract `analyte_symbol` and `unit`.
- Blank or missing symbols/units result in the row being skipped.
- **Data Flow:** Upserts the `Analyte` table. If the `analyte_symbol` already exists (case-insensitive match), it updates the unit. Otherwise, it creates a new record.

---

## 2. ElementalCompositionService

Handles bulk upsert of wide-format elemental composition data.

### Excel Format
- **Format:** Excel file.
- **Headers:** Stripped of leading/trailing whitespace.

### Column Specifications
- **Sample ID Column:** Must include a column named `sample_id` (case-insensitive).
- **Analyte Columns:** All other columns are treated as analyte symbols.

### Parsing Logic
- Ensures the `sample_id` exists in the `SampleInfo` table. If not, the row is skipped and an error is logged.
- Iterates over the analyte header columns. The header name must match an existing `analyte_symbol` in the database (case-insensitive). Unknown analytes are skipped.
- Cell values are converted to numeric (`float`). Blanks, `NaN`, or non-numeric values are skipped.
- **Data Flow:** Upserts the `ElementalAnalysis` table for each `(sample_id, analyte_id)` pair, updating existing compositions or creating new entries.

---

## 3. ActlabsRockTitrationService

A specialized, robust parser for native ActLabs report files, designed to heuristically extract headers, units, and data blocks.

### File Format
- **Format:** Excel or CSV. Reads the file entirely without headers (`header=None`).

### Parsing Logic & Heuristics
1. **Sample ID Column Detection:**
   - Scans the first 6 rows across all columns.
   - Searches for cells containing both "sample" and "id" or the exact string "sample_id" (case-insensitive).
   - If no column matches, it defaults to column `0`.
2. **Analyte and Unit Mapping:**
   - Extracts analyte symbols from **row index 2** (the 3rd row of the file).
   - Extracts units from **row index 3** (the 4th row of the file).
   - If duplicate analyte columns exist, the *last* occurrence overwrites previous ones ("last column wins" logic).
3. **Data Start Detection:**
   - Scans up to the first 12 rows looking for a cell starting with "analysis method" in the first column.
   - Data is assumed to start on the row *immediately following* the "analysis method" row. If not found, defaults to starting at row index 4.
4. **Numeric Coercion:**
   - Cells containing "nd", "na", or "n/a" (case-insensitive) are treated as blank.
   - Values with inequality symbols (e.g., `<0.01` or `>100`) have the symbols stripped (`<` or `>`) and the numeric part is parsed as a float.

### Data Flow & Output
- **Analyte Upsert:** Analyte symbols extracted from row 2 are upserted into the `Analyte` table. Missing units default to "ppm".
- **Validation:** Extracts the `sample_id` from the data rows. Validates that the sample exists in the `SampleInfo` table.
- **Result Upsert:** For every valid numeric cell, it upserts the `ElementalAnalysis` table for the corresponding `(sample_id, analyte_id)`.
- **Output:** Returns `(results_created, results_updated, skipped_rows, errors)`. It also provides a `diagnose` method to preview file structure and data quality before committing to the database.