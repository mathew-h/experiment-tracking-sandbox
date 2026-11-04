# Master Results upload: carry Tube Number onto the timepoint

**Type:** feat
**Area:** `backend/services/bulk_uploads/master_bulk_upload.py` (locked; Mat signed off 2026-11-03)
**Priority:** medium
**Related:** issue-core-flood-run-page.md (parent), depends on issue-core-flood-schema-and-views.md

---

## Problem

The tracker keeps an integer Tube Number on its Sampling, Liquid Sampling, ICP List and pH sheets. The number is reused across dates: 21 values repeat, and a sample is identified by the Sample Key `<exp>|<date>|T<tube>`. But the Dashboard sheet the parser reads (`_DASHBOARD_SHEET`, line 77) has no tube column, so uploads can't fill `sample_tube_number`.

## Impact

Tube numbers would only be entered by hand, and uploaded timepoints couldn't be traced back to their centrifuge tube.

## Fix

1. **Workbook (team change, outside the repo).** Add a "Tube Number" column to the Dashboard sheet, looked up by Sample Key from the Sampling sheet.
2. **Parsing.** Recognize an optional "Tube Number" column and parse it as an integer. XLOOKUP returns 0 for an empty source cell, so treat 0 as blank, the same rule as `_ZERO_BLANK_COLUMNS` at lines 207-212.
3. **Merging.** In `_merge_group` (line 600), handle tube like `_RUN_DATE_COLUMNS` (line 223): the first non-null value wins and a clash is a warning. Gas-only rows (`Sgas` keys) carry no tube.
4. **Writing.** Keep tube out of `result_data`, because `sheet_fields = frozenset(result_data)` would otherwise claim a field `ScalarResults` doesn't have. After `create_scalar_result_ex` returns (around line 1048), set `exp_result.sample_tube_number` inside the same SAVEPOINT. Inside the SAVEPOINT, an OVERWRITE row whose Tube Number cell is blank clears the stored value, but only when the column is present.
5. **Docs.** Update `docs/upload_templates/master_bulk_upload.md`.

## Acceptance criteria

- [x] A Dashboard row with Tube Number 7 sets the tube on the merged timepoint. The tests are in `tests/services/bulk_uploads/test_master_bulk_upload.py`, not `tests/api/test_bulk_uploads.py`: the API tests mock the parser, so the parser tests live with the other merge and OVERWRITE tests (`test_tube_number_is_stored_on_the_timepoint`, `test_tube_number_is_set_on_the_merged_timepoint`)
- [x] A 0 cell is treated as blank (`test_zero_tube_cell_is_blank`, `test_parse_tube_blank_cells`)
- [x] A liquid/gas pair with tubes 7 and blank stores 7. A pair with 7 and 9 stores 7 and warns (`test_tube_clash_stores_the_first_and_warns`, `test_merge_group_tube_clash_is_a_note_not_a_conflict`)
- [x] When the column is missing, existing tube numbers are left untouched. With OVERWRITE and the column present, a blank cell clears the tube (`test_missing_tube_column_leaves_stored_tube_untouched`, `test_overwrite_with_blank_tube_cell_clears_it`; also covered: blank without OVERWRITE keeps the tube, mixed OVERWRITE does not clear it)
- [x] The existing master upload tests and `tests/integration/test_master_results_sync_endpoint.py` pass unchanged (531 baseline -> 562 with the 31 new tests; broad suite 1481 passed)

**Decision during implementation (2026-11-04):** a tube cell that is not a positive whole number (`7.5`, `T7`, text) is ignored with one file-level warning naming the rows, and the rest of the row uploads. It is provenance, like a run date. The spec didn't cover this case.

**Real-data check (2026-11-04, `Master_Results_Tracker_v5.xlsx`, dev DB, rolled back):** the Dashboard had no Tube Number column yet, so one was derived from `Sample Key` (`|T<n>` -> n, otherwise 0). 202 of 637 rows carry a tube; 156 written vial-days got one; created/updated, row actions, errors and non-tube warnings were identical to an upload without the column, apart from one blank row (below). 0 of 346 written vial-days stored a tube other than the first non-zero tube among their rows. Two real tube clashes (rows 316/362/443 and 366/429/452) were stored first-wins with the warning. Re-check once the team's column exists.

## Notes

The column can land in the workbook before this PR merges; the parser ignores headers it doesn't recognize. Check that before rolling out.

**Pre-existing, found during the real-data check (not fixed here, out of the signed-off scope):** a fully blank Dashboard row whose only non-NaN cell is a NaT date (v5 row 529) is reported as `Row 529: invalid Duration (Days) 'NaT'` instead of being skipped. This happens on develop with the unmodified workbook. `df.iterrows()` gives an all-NaN/NaT row a `datetime64` dtype, so the blank Experiment ID arrives as `NaT`, which `_resolve_row_identity` does not treat as blank. An int column on the row (such as Tube Number = 0) keeps it an `object` row, so it then skips. That is the only difference between the with- and without-column runs above.
