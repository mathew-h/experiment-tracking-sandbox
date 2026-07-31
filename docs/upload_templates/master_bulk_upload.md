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

- `Replicate` (optional, issue #70 P3): single letter `a`–`z` routing the row to the lettered sibling of the base Experiment ID (`0`/blank = the base itself). Malformed or conflicting values skip that row with a per-row error.

## Parsing Logic
- **Date Parsing (`_parse_date`):** Handles string dates, Python datetimes, and Excel serial dates. Safely rejects dates with a year ≤ 1900 and spreadsheet errors like `#DIV/0!`.
- **Numeric Parsing (`_parse_numeric`):** Handles errors like `#DIV/0!`, empty strings, and numbers containing commas, converting valid entries to floats.
- **Unit Conversions:** Converts `Gas Pressure (psi)` to MPa automatically by multiplying by `0.00689476`.
- **Overwrite Behavior:** Looks for a per-row `Overwrite` flag (e.g., "TRUE") or falls back to the global setting. If existing results are found and overwrite is false, the row is skipped to prevent accidental data loss.

## Timepoint ID Token (Issue #81)
- If the resolved Experiment ID carries a `-t<days>` token (e.g. `SERUM_001a-t7`), a blank `Duration (Days)` cell is filled from the ID; a different `Duration (Days)` value errors the row rather than being silently overwritten. This is the one case where `Duration (Days)` may be omitted and the row still processes.
- Checked at the string level in `master_bulk_upload.py` (`split_timepoint_token`, `apply_id_timepoint`) before the row reaches `ScalarResultsService`, which applies the same rule again as a second layer of defense.

## Data Model and Flow
Delegates the parsed and cleaned records to `ScalarResultsService.bulk_create_scalar_results_ex`. Validates that the experiment exists in the database before attempting to insert or update results.

## Warnings

- **Missing GC Run Date (issue #115):** if a row carries an `H2 (ppm)` reading (either GC block) but the `GC Run Date` column is blank, the upload still stores the reading — nothing errors — but emits one file-level warning naming the affected sheet rows (up to 10, then "and N more"). Silent when the row has no H2 reading at all. This matters because the Dashboard's "GC Measurements" KPI card counts `GC Run Date` entries, not H2 readings — a row that stores an H2 value with no run date is invisible to that card until the date is filled in and the sheet is re-uploaded. See `docs/issues/issue-115-gc-run-date-visibility.md`.
- **Superseded direct-injection reading (issue #114):** if a row carries an H2 reading in both the Full Loop and direct-injection GC blocks, Full Loop wins and the file-level warnings list names the affected rows once, at file level.

## Output
Returns a tuple: `(created, updated, skipped, errors, feedbacks)`.
