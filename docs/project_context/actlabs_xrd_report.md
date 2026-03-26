# Actlabs XRD Report Upload Template

**Source:** [backend/services/bulk_uploads/actlabs_xrd_report.py](../../backend/services/bulk_uploads/actlabs_xrd_report.py)

## Overview
This service handles the upsert of XRD mineralogy data per sample from an Excel file, specifically tailored for Actlabs reports.

## Excel Format
- **Target Sheet:** Reads data from the first sheet.
- **Structure:** Requires a minimum of 2 columns to function properly.

## Column Specifications

### Required Columns
- `sample_id` (must be the first column): Evaluated using a case-insensitive match. The sample ID must exist in the `SampleInfo` database table.

### Mineral Columns
- All columns other than `sample_id` are treated as mineral names. The values in these columns represent the numeric amounts (percent or wt%) of each mineral.

## Parsing Logic
- **Header Normalization:** Column headers are stripped of leading and trailing whitespace.
- **Sample ID Lookup:** The system verifies that the provided `sample_id` exists in the `SampleInfo` table using an exact match.
- **Mineral Values:** Values are converted to floats. Blank, missing, or non-numeric values are safely skipped without failing the entire row.

## Data Model and Flow
For each valid row:
1. Finds or creates an `ExternalAnalysis` record of type `"XRD"` for the specified sample.
2. Updates or creates an `XRDAnalysis` JSON record with a `mineral_phases` dictionary containing the parsed mineral data.
3. Upserts individual `XRDPhase` rows representing the relationship between the sample, mineral name, and its quantified amount.

## Output
Returns a comprehensive tuple containing the operation's results:
`(created_ext, updated_ext, created_json, updated_json, created_phase, updated_phase, skipped_rows, errors)`
