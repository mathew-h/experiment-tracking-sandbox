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

The `Label` column is parsed right-to-left:

1. `_<N>x` dilution token — **required** (the trailing `x` is optional).
2. An optional `_Day<N>` or `_Time<N>` token.
3. Whatever remains is the experiment ID (dashes/underscores allowed).

**The experiment ID's trailing `-t<days>` token wins.** A destructively-sampled
vial encodes its own day in its ID (`SERUM_Cation_005c-t5`), and that day is
canonical. When the ID carries the token, any `Day<n>` in the label is ignored —
the upload reports the disagreement in its warnings and never rejects a row for
it. (A named row can still fail to load for an unrelated reason, such as an
experiment ID that does not exist; those appear under `errors`.)

| Label | Experiment | Day | Dilution |
|---|---|---|---|
| `SERUM_Cation_005c-t5_21x` | `SERUM_Cation_005c-t5` | 5 (from ID) | 21 |
| `SERUM_Cation_005c-t5_Day12_21x` | `SERUM_Cation_005c-t5` | 5 (from ID; `Day12` ignored, warned) | 21 |
| `HPHT_231_Day6_21x` | `HPHT_231` | 6 (from label) | 21 |
| `Serum_MH_011_Day5_5x` | `Serum_MH_011` | 5 (from label) | 5 |

A label with **no** timepoint from either source is skipped and named in the
upload's warnings — for example `HPHT_231_21x`, or `SERUM_Cation_005c-T5_21x`,
because **the timepoint token is lowercase `-t` only**. Standards and blanks
(`Standard 1`, `Blank`) are skipped silently, as before.

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
