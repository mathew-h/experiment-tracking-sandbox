# Experiment Status Upload Template

**Source:** [backend/services/bulk_uploads/experiment_status.py](../../backend/services/bulk_uploads/experiment_status.py)

## Overview
Allows bulk updating of experiment statuses on a per-row basis: each row sets an explicit `status` (`ONGOING`, `COMPLETED`, `CANCELLED`, or `QUEUED`) for one experiment. Applies to experiments of any type — Serum, Autoclave, HPHT, Core Flood. There is no blanket "complete every unlisted ongoing HPHT" behavior — an experiment not referenced in the file is never touched.

## Excel Format
- **Target Sheet:** Reads from a single sheet.

## Column Specifications

### Required Columns
- `experiment_id`
- `status`: one of `ONGOING`, `COMPLETED`, `CANCELLED`, `QUEUED` (case-insensitive)

### Optional Columns
- `reactor_number`: only meaningful for HPHT / Core Flood experiments
- `date`: experiment start date (`YYYY-MM-DD` or Excel date). Also used to decide reactor demotion order.

## Parsing Logic
- **Headers:** Evaluated case-insensitively.
- **Rows:** Each row is parsed independently into a planned change (`experiment_id`, `status`, optional `reactor_number`, optional `date`). Invalid `status`/`reactor_number`/`date` values produce a row-level error.
- **Missing required columns:** A missing `experiment_id` or `status` column hard-fails the whole upload with no changes applied.
- **Same-reactor conflict:** If two rows both set an HPHT/Core-Flood-eligible experiment to `ONGOING` in the same `reactor_number`, the file is rejected as internally inconsistent.

## Behavior and Flow

### Preview Phase (`preview_status_changes_from_excel`)
Generates a `StatusChangePreview` object that includes:
- `changes`: planned per-row status/date/reactor changes (`PlannedChange` list).
- `demotions`: planned reactor demotions (`PlannedDemotion` list) — for HPHT/Core-Flood-eligible rows set to `ONGOING` with a `reactor_number`, where an older same-reactor occupant exists.
- `missing_ids`: experiment IDs from the file not found in the database.
- `errors`: column/row-level validation errors and same-reactor conflicts (any non-empty `errors` blocks the whole upload).
- `warnings`: explanatory notes, including cases where a same-reactor occupant is *not* demoted (newer-or-equal start date, or a missing start date on either side).

### Application Phase (`apply_status_changes`)
- Sets each row's `status` on its experiment.
- Writes `date` to the experiment's start date when provided.
- Updates `reactor_number` in `ExperimentalConditions` when provided and different from the current value.
- For eligible ONGOING rows with a `reactor_number`, executes the planned demotion via `manage_reactor_occupancy` (only demotes an occupant whose start date is strictly older; otherwise leaves it `ONGOING` with a warning).

## Output
The apply step returns an `ApplyResult` with fields: `status_changes_applied`, `demotions_applied`, `reactor_updates`, `date_updates`, `warnings`, `errors`.
