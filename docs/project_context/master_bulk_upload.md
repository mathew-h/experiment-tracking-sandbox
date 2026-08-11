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
Description, Sample Collection Date, NMR Run Date, ICP Run Date, GC Run Date, XRD Run Date, NH4 (mM), H2 (ppm), Gas Volume (mL), Gas Pressure (psi), Sample pH, Sample Conductivity (mS/cm), Sampled Solution Volume (mL), Modification, Overwrite.

- `Sample Collection Date` is the date the sample was **collected**, and is stored as `measurement_date`. It is a different event from `GC Run Date` (when the instrument ran) — the two disagree on 116 of the 270 workbook rows carrying both, so neither substitutes for the other. Accepted aliases, for archived workbooks: `Sample Date`, `Liquid/Solid Sample Date`, `HPHT + Liquid/Solid Date Sampled`. A sheet with none of these spellings uploads normally but emits a warning saying no measurement date was ingested.

- `Replicate` (optional, issue #70 P3): single letter `a`–`z` routing the row to the lettered sibling of the base Experiment ID (`0`/blank = the base itself). Malformed or conflicting values skip that row with a per-row error.

## Parsing Logic
- **Date Parsing (`_parse_date`):** Handles string dates, Python datetimes, and Excel serial dates. Safely rejects dates with a year ≤ 1900 and spreadsheet errors like `#DIV/0!`.
- **Numeric Parsing (`_parse_numeric`):** Handles errors like `#DIV/0!`, empty strings, and numbers containing commas, converting valid entries to floats.
- **Unit Conversions:** Converts `Gas Pressure (psi)` to MPa automatically by multiplying by `0.00689476`.
- **Overwrite Behavior:** Looks for a per-row `Overwrite` flag (e.g., "TRUE") or falls back to the global setting. If existing results are found and overwrite is false, the row is skipped to prevent accidental data loss.
- **Overwrite Scope (issue #116):** overwrite is bounded to the fields this sheet has columns for. The parser passes `_sheet_fields` — derived from the keys of its own `result_data` literal, so it cannot drift — and `create_scalar_result_ex` clears only within that set. A carried column left blank still clears (this is what keeps #114's stale carryover geometry from being re-asserted); the eight `SCALAR_UPDATABLE_FIELDS` entries with no column here (`background_ammonium_concentration_mM`, `ammonium_quant_method`, `final_nitrate_concentration_mM`, `final_alkalinity_mg_L`, `co2_partial_pressure_MPa`, `final_dissolved_oxygen_mg_L`, `background_experiment_id`, `ferrous_iron_yield`) are left untouched. Callers that pass no `_sheet_fields` keep the previous whole-list behavior.

## Timepoint ID Token (Issue #81)
- If the resolved Experiment ID carries a `-t<days>` token (e.g. `SERUM_001a-t7`), a blank `Duration (Days)` cell is filled from the ID; a different `Duration (Days)` value errors the row rather than being silently overwritten. This is the one case where `Duration (Days)` may be omitted and the row still processes.
- Checked at the string level in `master_bulk_upload.py` (`split_timepoint_token`, `apply_id_timepoint`) before the row reaches `ScalarResultsService`, which applies the same rule again as a second layer of defense.

## Several Rows Per Vial-Day (row merge, 2026-08-11)

Gas is drawn and run on one date; the liquid/solid fraction is collected later. Each fraction gets its own sheet row, and both name the same vial and the same day — so rows sharing a `(normalized ID, timepoint)` key are **merged field by field** into one stored result rather than rejected as duplicates.

- **Complementary rows merge.** A gas row supplying H2 and geometry, and a later liquid row supplying pH and conductivity, become one result.
- **A genuine disagreement rejects that vial-day whole.** If two rows fill the same field with different values, nothing is written for that vial-day and one error names every row, the field, and both values. Other vial-days in the file still land.
- **A `0` in the pH, conductivity or gas volume/pressure columns is a blank,** not a measurement — the template writes 0 into them on a row that did no such sampling. A `0` in an `H2 (ppm)` column IS a real reading.
- **Grouping matches the exact timepoint.** Two rows with the same Duration are a request to merge; rows a day apart stay separate vial-days.
- **`OVERWRITE` is honoured only when every row of the vial-day is TRUE,** since clearing is destructive and a merged vial-day is one write. A mixed setting is reported and not applied.
- **`created + updated` no longer equals the sheet row count.** A file-level warning states the merge count (e.g. "Merged 72 rows into 36 vial-days").

## Data Model and Flow
Calls `ScalarResultsService.create_scalar_result_ex` once per **merged vial-day**, each inside its own SAVEPOINT so one bad row does not discard the rows already written. Validates that the experiment exists in the database before attempting to insert or update results.

## Warnings

- **Missing GC Run Date (issue #115):** if a row carries an `H2 (ppm)` reading (either GC block) but the `GC Run Date` cell is missing or unreadable, the upload still stores the reading — nothing errors — but emits one file-level warning reporting how many of the H2-bearing rows were affected (e.g. "missing or unreadable on 3 of 40 rows carrying an H2 reading"). The affected sheet rows are named only when there are 10 or fewer; above that the warning reports the ratio with no row list. Silent when the row has no H2 reading at all. The gate is a fact about the sheet cell, not the stored row: on the non-overwrite path a blank cell is stripped before it reaches the service, so any `gc_run_date` already stored is left untouched — the warning says only that no date was supplied on this upload, not that the row goes uncounted. This matters because the Dashboard's "GC Measurements" KPI card counts `GC Run Date` entries falling in the last 7 workdays, not H2 readings — and because that window is rolling, backfilling an older date can never make a row appear there; only dates entered going forward will count. See `docs/issues/issue-115-gc-run-date-visibility.md`.
- **Superseded direct-injection reading (issue #114):** if a row carries an H2 reading in both the Full Loop and direct-injection GC blocks, Full Loop wins and the file-level warnings list names the affected rows once, at file level.

## Output
`from_bytes_ex` returns a `MasterUploadResult` with `created`, `updated`, `skipped`, `errors`, `feedbacks` and `warnings`. The tuple-returning `as_tuple`, `from_bytes` and `sync_from_path` were deleted by issue #114 item 4 — they dropped `warnings` by construction.
