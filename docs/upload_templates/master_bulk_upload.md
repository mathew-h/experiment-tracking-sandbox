# Master Bulk Upload Template

**Source:** [backend/services/bulk_uploads/master_bulk_upload.py](../../backend/services/bulk_uploads/master_bulk_upload.py)

## Overview
Processes comprehensive Master Bulk Upload files containing consolidated scalar and analytical results.

## File Format
- **Format:** Supports both CSV and Excel files.
- **Excel Specifics:** Prefers a sheet named `Dashboard`. If the file contains multiple sheets and no `Dashboard` sheet exists, the upload will trigger an error.

## Column Specifications

### Required Columns
- `Experiment ID`: The ID must exist within the database.
- `Duration (Days)`: Must be a numeric value representing the time point.

### Optional Columns
Description, Sample Date, NMR Run Date, ICP Run Date, GC Run Date, NH4 (mM), H2 (ppm), Gas Volume (mL), Gas Pressure (psi), Sample pH, Sample Conductivity (mS/cm), Modification, Overwrite.

## Parsing Logic
- **Date Parsing (`_parse_date`):** Handles string dates, Python datetimes, and Excel serial dates. Safely rejects dates with a year ≤ 1900 and spreadsheet errors like `#DIV/0!`.
- **Numeric Parsing (`_parse_numeric`):** Handles errors like `#DIV/0!`, empty strings, and numbers containing commas, converting valid entries to floats.
- **Unit Conversions:** Converts `Gas Pressure (psi)` to MPa automatically by multiplying by `0.00689476`.
- **Overwrite Behavior:** Looks for a per-row `Overwrite` flag (e.g., "TRUE") or falls back to the global setting. If existing results are found and overwrite is false, the row is skipped to prevent accidental data loss.

## Data Model and Flow
Delegates the parsed and cleaned records to `ScalarResultsService.bulk_create_scalar_results_ex`. Validates that the experiment exists in the database before attempting to insert or update results.

## Output
Returns a tuple: `(created, updated, skipped, errors, feedbacks)`.
