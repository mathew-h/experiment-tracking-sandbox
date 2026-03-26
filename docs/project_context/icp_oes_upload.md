# ICP-OES Upload Template

**Source:** [backend/services/icp_service.py](../../backend/services/icp_service.py)

## Overview
This service processes long-format ICP elemental analysis data, extracting sample metadata from labels, applying dilution corrections, selecting the optimal spectral lines, and updating the database with wide-format elemental concentrations.

## File Format
- **Format:** Supports CSV files. The delimiter (e.g., comma, tab, semicolon) is inferred dynamically.
- **Header Row:** Automatically detected based on the presence of a `Label` column and ICP keywords. Blank lines and non-data header rows are safely ignored.

## Column Specifications

### Required Columns
- `Label`: The sample identifier (contains embedded metadata).
- `Element Label`: The measured element and spectral line (e.g., "Al 394.401").
- `Concentration`: The raw concentration measurement.
- `Intensity`: The measurement intensity, used to resolve the best line when multiple lines per element are present.

### Optional Columns
- `Type`: Used to filter out blank samples (e.g., `BLK`).
- `Date Time`: Used to extract the `measurement_date`.

## Parsing Logic

### Sample Identification (`Label` Parsing)
Sample metadata is extracted directly from the `Label` column via regex matching the pattern `ExpID_(Day|Time)Number_DilutionFactorx` (e.g., `Serum_MH_011_Day5_5x` or `Serum-MH-025_Time3_10x`).
Extracts:
1. `experiment_id`: The ID of the experiment (dashes/underscores allowed).
2. `time_post_reaction`: Extracted from the `Day` or `Time` suffix.
3. `dilution_factor`: Extracted from the `[N]x` suffix.

Rows that do not match this pattern (e.g., "Blank", "Standard 1") are skipped without halting the upload.

### Filtering and Correction
- **Blanks Removed:** Filters out any rows where `Type` is `BLK` or `Label` contains the word "Blank" (case-insensitive).
- **Dilution Correction:** Automatically multiplies the `Concentration` value by the sample's `dilution_factor` to yield the `Corrected_Concentration`.
- **Negative Values:** Corrected concentrations less than `0.0` are floored to `0.0`.

### Best Line Selection
If a sample has multiple measurements for the same element (different spectral lines), the service groups them and selects the row with the maximum `Intensity` to represent the final concentration.

## Data Model and Flow
- **Pivoting to Wide Format:** The service transforms the long-format data into a wide format (one row per sample/timepoint). The element symbol is parsed from the `Element Label` (e.g., "Al" from "Al 394.401") and standardized.
- **Experimental Results:** Finds or creates a parent `ExperimentalResults` row using `find_timepoint_candidates` based on `experiment_id` and `time_post_reaction`.
- **ICP Results (`ICPResults`):** 
  - Standard elements (e.g., Fe, Si, Ca) map to dedicated table columns.
  - All uploaded elements are stored collectively in the `all_elements` JSON column.
- **Update Behavior:** If an ICP result already exists for the timepoint, it selectively overwrites elements present in the CSV while preserving existing data for other elements.
- **Audit Logging:** Logs creation and updates to the `ModificationsLog` detailing old and new values.

## Output
The bulk creation method returns a tuple: `(successful_results, error_messages)`.
