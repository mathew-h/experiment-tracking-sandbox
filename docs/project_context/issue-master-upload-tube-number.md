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

- [ ] `tests/api/test_bulk_uploads.py`: a Dashboard row with Tube Number 7 sets the tube on the merged timepoint
- [ ] A 0 cell is treated as blank
- [ ] A liquid/gas pair with tubes 7 and blank stores 7. A pair with 7 and 9 stores 7 and warns
- [ ] When the column is missing, existing tube numbers are left untouched. With OVERWRITE and the column present, a blank cell clears the tube
- [ ] The existing master upload tests and `tests/integration/test_master_results_sync_endpoint.py` pass unchanged

## Notes

The column can land in the workbook before this PR merges; the parser ignores headers it doesn't recognize. Check that before rolling out.
