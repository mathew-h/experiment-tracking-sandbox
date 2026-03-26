# Experiment Status Upload Template

**Source:** [backend/services/bulk_uploads/experiment_status.py](../../backend/services/bulk_uploads/experiment_status.py)

## Overview
Allows for bulk updating of experiment statuses, specifically marking active experiments as `ONGOING` and automatically handling the transition of unlisted HPHT experiments to `COMPLETED`.

## Excel Format
- **Target Sheet:** Reads from a single sheet.

## Column Specifications

### Required Columns
- `experiment_id`

### Optional Columns
- `reactor_number`

## Parsing Logic
- **Headers:** Evaluated case-insensitively.
- **Experiment IDs:** Compiles a list of unique `experiment_id`s that should be marked as `ONGOING`.
- **Reactor Numbers:** Parses the optional `reactor_number` per row, storing it in a mapping dictionary for later application to the experiment's conditions.

## Behavior and Flow

### Preview Phase (`preview_status_changes_from_excel`)
Generates a `StatusChangePreview` object that includes:
- Experiments to be set to `ONGOING` (from the uploaded file).
- Experiments to be set to `COMPLETED` (currently `ONGOING` HPHT experiments that are *not* present in the uploaded file).
- Missing IDs and validation errors.

### Application Phase (`apply_status_changes`)
- Sets the listed experiments to `ONGOING`.
- Sets the unlisted `ONGOING` experiments to `COMPLETED`.
- Updates the `reactor_number` in `ExperimentalConditions` when a value is provided in the upload.

## Output
The apply step returns a tuple: `(marked_ongoing, marked_completed, reactor_updates, errors)`.
