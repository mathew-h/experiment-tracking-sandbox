# Rock Inventory Upload Template

**Source:** [backend/services/bulk_uploads/rock_inventory.py](../../backend/services/bulk_uploads/rock_inventory.py)

## Overview
Facilitates the bulk upsert of rock sample records (`SampleInfo`) and allows for the attachment of associated sample photos and pXRF readings.

## Excel Format
- **Target Sheet:** Reads from a single sheet.
- **Headers:** Normalized to lowercase for robust matching.

## Column Specifications

### Required Columns
- `sample_id`

### Optional Columns
rock_classification, state, country, locality, latitude, longitude, description, characterized, overwrite, pxrf_reading_no.

## Parsing Logic
- **Sample ID Normalization:** The `sample_id` is normalized into a canonical format (converted to uppercase, spaces and underscores removed, hyphens preserved).
- **Matching:** Database matching uses a delimiter-insensitive and case-insensitive strategy to prevent duplicates caused by minor formatting differences.
- **Overwrite Behavior:** The `overwrite` flag can be set per-row or globally (`true`/`yes`/`1`). When active, it clears optional fields before applying new values.
- **pXRF Readings (`pxrf_reading_no`):** Accepts comma-separated reading numbers. It splits them using `split_normalized_pxrf_readings` and links each to an `ExternalAnalysis` record of type `"pXRF"`.

## Image Attachment
If image files are provided in the upload payload:
- File names (excluding the extension) are matched against the normalized `sample_id`.
- Successfully matched images are saved to the storage backend under `sample_photos/{sample_id}/`.

## Output
Returns `(created, updated, images_attached, skipped, errors, warnings)`.
