# Data Migrations

This directory contains data migration scripts for updating existing data in the database.

## Quick Reference

| Migration | Purpose | When to Run |
|-----------|---------|-------------|
| `normalize_pxrf_reading_numbers_008` | Fix "1.0" → "1" formatting in pXRF readings | When readings don't match in Power BI |
| `backfill_pxrf_readings_009` | Ensure pXRF analyses reference valid readings | After importing historical pXRF data |
| `split_pxrf_external_analyses_010` | Split multi-reading analyses into separate rows | After backfill, for proper 1:1 mapping |
| `merge_duplicate_samples_007` | Merge duplicate sample IDs (case/formatting) | After identifying duplicates |
| `identify_duplicate_samples.py` | Diagnostic: find duplicate samples | Before merge, to preview changes |
| `establish_experiment_lineage_006` | Link experiment derivations and treatments | After lineage columns added |
| `recompute_calculated_fields_005` | Recalculate all derived fields | After formula changes |
| `calculate_grams_per_ton_yield_004` | Calculate g/ton yield for existing data | After adding yield calculation |
---

## Recovery: Re-Upload for NULL `time_post_reaction` Rows

Historical scalar results rows had `time_post_reaction_days` stored as NULL because the original upload paths never enforced non-null time. These are recovered by **re-uploading the original bulk upload `.xlsx` templates** through the Streamlit bulk upload UI.

**What was changed to support this:**
- Legacy column aliases added to the bulk upload parser (both old raw column names and current friendly headers are accepted)
- Null-time fallback matching: when re-uploading, the system finds existing NULL-time rows by experiment + description and updates them in-place instead of creating duplicates
- Guardrails added to `save_results()`, `create_experimental_result_row()`, and ICP service to prevent future NULL-time rows

**Procedure:**
1. Back up the production database
2. Deploy the code changes and restart Streamlit
3. Upload each historical `.xlsx` through the Streamlit bulk upload UI using **Partial Update** mode (overwrite unchecked)
4. Verify: `sqlite3 experiments.db "SELECT COUNT(*), SUM(CASE WHEN time_post_reaction_days IS NULL THEN 1 ELSE 0 END) FROM experimental_results;"`
5. Refresh Power BI and confirm time-series plots

---

## Active Migrations

### normalize_pxrf_reading_numbers_008
**Fix float formatting in pXRF reading numbers**

Converts "1.0", "2.0" → "1", "2" in both `pxrf_readings.reading_no` and `external_analyses.pxrf_reading_no`.

**Why needed:** Excel imports store integers as floats (1 → 1.0), breaking matches in Power BI.

```bash
python database/data_migrations/normalize_pxrf_reading_numbers_008.py         # Preview
python database/data_migrations/normalize_pxrf_reading_numbers_008.py --apply # Apply
```

### backfill_pxrf_readings_009
**Ensure pXRF analyses reference valid readings**

- Removes legacy pXRF analyses with blank/NULL `pxrf_reading_no`
- Creates missing reading entries or renames when safe
- Normalizes comma-separated lists

```bash
python database/data_migrations/backfill_pxrf_readings_009.py         # Preview
python database/data_migrations/backfill_pxrf_readings_009.py --apply # Apply
```

### split_pxrf_external_analyses_010
**Split multi-reading analyses into separate rows**

Converts comma-separated readings (e.g., "1,2,3") into individual ExternalAnalysis rows (one per reading). Preserves all metadata and avoids duplicates.

**Run after:** `backfill_pxrf_readings_009`

```bash
python database/data_migrations/split_pxrf_external_analyses_010.py         # Preview
python database/data_migrations/split_pxrf_external_analyses_010.py --apply # Apply
```

### merge_duplicate_samples_007
**Merge duplicate sample IDs differing only in formatting**

Finds samples like "rock-001", "ROCK-001", "rock 001" and merges into canonical form (UPPERCASE, hyphens). Migrates all foreign key references (experiments, analyses, photos) and merges metadata intelligently.

**Workflow:**
```bash
# 1. Identify (diagnostic only)
python database/data_migrations/identify_duplicate_samples.py

# 2. Preview merge
python database/data_migrations/merge_duplicate_samples_007.py

# 3. Apply
python database/data_migrations/merge_duplicate_samples_007.py --apply
```

### identify_duplicate_samples
**Diagnostic: find all duplicate samples**

Reports total samples vs. unique count, lists all duplicate groups with formatting differences and FK reference counts. Shows which sample will become primary.

```bash
python database/data_migrations/identify_duplicate_samples.py
```

**Example output:** "594 total, 547 unique → 47 duplicates to merge"

### establish_experiment_lineage_006
**Link experiment derivations and treatment variants**

Parses experiment IDs to establish parent-child relationships:
- **Sequential derivations:** `HPHT_MH_001-2` → links to `HPHT_MH_001`
- **Treatment variants:** `HPHT_MH_001_Desorption` → tracked but no parent
- **Combined:** `HPHT_MH_001-2_Desorption` → links to base, tracks treatment

Sets `base_experiment_id` and `parent_experiment_fk` fields. Handles orphaned derivations gracefully.

```bash
python database/data_migrations/establish_experiment_lineage_006.py         # Preview
py database/data_migrations/establish_experiment_lineage_006.py --apply # Apply
```

### recompute_calculated_fields_005
**Recalculate derived fields across the database**

Updates all derived values by running the logic defined in `@database/models/results.py` and `@database/services.py`.
Specifically, it triggers:
- `ExperimentalConditions.calculate_derived_conditions()`
- `ChemicalAdditive.calculate_derived_values()`
- `ScalarResults.calculate_yields()`

**When to run:** After updating formulas or logic in `database/models/` or `database/services.py`.

```bash
python database/data_migrations/recompute_calculated_fields_005.py
```

---

## Historical/Utility Migrations

These migrations were run during development and may not be needed for current databases.

| Migration | Purpose |
|-----------|---------|
| `calculate_grams_per_ton_yield_004` | Backfill g/ton yield for existing ScalarResults |
| `update_catalyst_ppm_rounding_003` | Update catalyst PPM rounding consistency |
| `recalculate_yields_002` | Recalculate yields with updated logic |
| `recalculate_derived_conditions_001` | Recalculate water-to-rock ratio, etc. |
| `chemical_migration.py` | Migrate deprecated catalyst/buffer fields to ChemicalAdditive |
| `data_migration_update_statuses_001` | Update experiment statuses to enum format |

---

## Diagnostic Tools

### check_duplicates.sql
SQL query to identify duplicate samples directly in SQLite Browser. Returns normalized IDs and duplicate counts.

### ALTERNATIVE_DETECTION_METHODS.md
Detailed guide for detecting duplicates when Python scripts won't run:
- Streamlit app sidebar indicators
- SQL queries in SQLite Browser
- Power BI verification methods

### RUN_DUPLICATE_ANALYSIS.md
Complete workflow guide for identifying and merging duplicate samples.

---

## Running Migrations

**Standard pattern:**
```bash
python database/data_migrations/<migration_name>.py         # Dry run (preview)
python database/data_migrations/<migration_name>.py --apply # Apply changes
```

**Using runner script (alternative):**
```bash
python scripts/run_data_migration.py <migration_name>
```

## Safety Guidelines

⚠️ **Always:**
- Run dry-run mode first to preview changes
- Backup your database before applying migrations
- Test on a copy of production data when possible
- Review output logs for errors or warnings

✅ **Built-in protections:**
- All migrations include error handling and rollback
- Detailed logging of all operations
- Dry-run mode for safe preview 