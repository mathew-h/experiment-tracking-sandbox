# Scalar Results Upload Template

**Source:** [backend/services/bulk_uploads/scalar_results.py](../../backend/services/bulk_uploads/scalar_results.py)

## Overview
This service parses the Solution Chemistry Excel template and delegates the creation or updating of scalar results to `ScalarResultsService`.

## Excel Format
- **Target Sheet:** Prefers a sheet named `Solution Chemistry`; otherwise, it uses the first sheet that does not contain `INSTRUCTION` in its name.
- **Headers:** Any asterisks (`*`) used to mark required columns in the template are stripped (e.g., `Date*` becomes `Date`).
- **Column Mapping:** Headers are mapped to internal database field names based on `SCALAR_RESULTS_TEMPLATE_HEADERS` defined in `frontend/config/variable_config.py`.

## Column Specifications

### Required Columns
- `experiment_id`
- `time_post_reaction` (commonly labeled as "Time (days)")
- `measurement_date` (when provided, parsed into a valid date/time)

### Optional Columns
Date, Description, Gross Ammonium (mM), Bkg Ammonium (mM), Bkg Exp ID, H2 Conc (ppm), Gas Sample Vol (mL), Gas Pressure (MPa), Final pH, Fe2+ Yield (%), Final DO (mg/L), Conductivity (mS/cm), Sampling Vol (mL), Overwrite.

## Parsing Logic
- **Header Normalization:** Performs case-insensitive lookups and supports legacy aliases (e.g., `time (days)`, `experimentid`) to ensure backward compatibility with older templates.
- **Date Parsing (`measurement_date`):** Accepts various formats including Python `datetime`, `date`, Pandas `Timestamp`, string-like values, and Excel serial dates. Uses `pd.to_datetime` with `coerce` to handle invalid entries gracefully.
- **Time Post Reaction (`time_post_reaction`):** Must be a numeric value (float). A value of `0` should be used for pre-reaction baselines.
- **Overwrite Behavior:** A per-row `overwrite` column or a global `overwrite_all` flag controls whether existing data in the database should be updated or preserved.
- **Data Cleaning:** Empty rows are skipped, and `NaN` or blank string values are excluded from the parsed records.

## Output and Data Flow
The cleaned records are passed to `ScalarResultsService.bulk_create_scalar_results_ex(db, cleaned_records)`. The service returns a tuple containing:
- `created` (int)
- `updated` (int)
- `skipped` (int)
- `errors` (List[str])
- `feedbacks` (List[dict])
