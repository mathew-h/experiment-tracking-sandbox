# Timepoint Modifications Upload Template

**Source:** [backend/services/bulk_uploads/timepoint_modifications.py](../../backend/services/bulk_uploads/timepoint_modifications.py)

## Overview
Bulk populates the `brine_modification_description` text field on existing `experimental_results` database rows corresponding to specific timepoints.

## File Format
- **Format:** CSV or Excel.
- **Excel Specifics:** Selects the first sheet that does not contain "INSTRUCTION" in its name.

## Column Specifications

### Required Columns
- `experiment_id`
- `time_point`
- `experiment_modification`

### Optional Columns
- `timepoint_type` (Valid values: `actual_day` or `bucket_day`)
- `overwrite_existing` (`true` or `false`)

### Column Aliases
Supports flexible header naming:
- **Experiment ID:** `experiment_id`, `experiment id`
- **Time Point:** `time_point`, `time (days)`
- **Modification:** `experiment_modification`, `description`, `modification`
- **Overwrite:** `overwrite_existing`, `overwrite`

## Parsing Logic
- **Time Point:** Converted to a float representing days (e.g., `0` for pre-reaction).
- **Matching:** Utilizes `find_timepoint_candidates` to locate the correct result row, applying a default `±0.0001` day tolerance. Specifying `timepoint_type=actual_day` restricts the match strictly to exact measured days.
- **Duplicate Handling:** Scans for duplicate `(experiment_id, time_point)` pairs within the upload. The batch is rejected if duplicates exist without `overwrite_existing=true`. If all duplicate rows have overwrite enabled, a "last-row-wins" policy is applied.

## Write Logic
- Blank modification + `overwrite_existing=False` → Row is skipped.
- Blank modification + `overwrite_existing=True` → Clears the existing field.
- Non-blank modification → Sets the description and automatically generates an audit entry in the `ModificationsLog` detailing the old value, new value, and source filename.

## Template Generation
The service provides a `generate_template_bytes()` method which dynamically constructs an Excel template highlighting required headers (with specific background colors and asterisks) and includes an `INSTRUCTIONS` sheet.

## Output
Returns `(updated, skipped, errors, feedbacks)`.
