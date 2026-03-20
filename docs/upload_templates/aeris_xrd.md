# Aeris XRD Upload Template

**Source:** [backend/services/bulk_uploads/aeris_xrd.py](../../backend/services/bulk_uploads/aeris_xrd.py)

## Overview
Handles bulk uploading of Aeris XRD time-series mineral-phase data from Excel files.

## Excel Format
- **Target Sheet:** Reads from a single sheet.
- **Structure:** The file must contain at least 4 columns to be considered valid.

## Column Specifications

### Required Columns
- `Sample ID` (or `sample_id`): Must follow the specific Aeris naming convention format: `DATE_ExperimentID-dDAYS_SCAN` (e.g., `20260218_HPHT070-d19_02`).

### Fixed Columns (Skipped from Mineral Parsing)
The following columns are identified case-insensitively and are excluded from being treated as mineral columns:
- Sample ID
- Rwp
- Scan Number
- scan_number

### Mineral Columns
All remaining columns are parsed as mineral columns. Headers may include trailing percentage indicators like `[%]` or `(%)` which are automatically stripped by the parser.

## Parsing Logic

### Sample ID Parsing
Uses the regular expression `^(\d{8})_(.+?)-d(\d+)_\d+$` to extract:
1. `measurement_date` (format: YYYYMMDD)
2. `experiment_id_raw`
3. `days_post_reaction`

**Experiment Lookup:** Employs a delimiter-insensitive matching strategy to locate the experiment in the database (e.g., matching `HPHT070` to `HPHT_070`).

### Additional Logic
- **Rwp:** Parsed as an optional float value if present.
- **Mineral Amounts:** Parsed as float values; blank or non-numeric entries are skipped.
- **Overwrite Behavior (`overwrite_existing`):** If `True`, updates existing database rows; if `False`, skips duplicate rows entirely.

## Data Model and Flow
Upserts data into the `XRDPhase` table, keyed uniquely by a combination of `(experiment_id, time_post_reaction_days, mineral_name)`.

## Output
Returns a tuple detailing the operation summary: `(created, updated, skipped, errors)`.
