# Duplicate Sample Analysis and Cleanup Guide

## Problem
You're seeing 594 samples in the database but expect fewer. This is likely due to duplicate sample IDs with different formatting (e.g., "ROCK-1" vs "ROCK_1" vs "rock-1").

## Step 1: Identify Duplicates

Run the diagnostic script to see exactly what duplicates exist:

```bash
# In Git Bash or Command Prompt with Python
python database/data_migrations/identify_duplicate_samples.py
```

This will show:
- Total samples vs expected unique samples
- Each duplicate group with details
- What's causing the duplicates (case, separators, spacing)
- How many records will be merged

## Step 2: Review the Results

The script will output:
- Groups of duplicates (e.g., "20250710-2D" and "20250710_2D")
- Which sample has more data/references (this will become the primary)
- How many duplicate records will be removed

## Step 3: Merge Duplicates (Dry Run First)

First, run in DRY RUN mode to see what would happen:

```bash
python database/data_migrations/merge_duplicate_samples_007.py
```

This shows what will happen WITHOUT making changes.

## Step 4: Apply the Merge

If the dry run looks good, apply the changes:

```bash
python database/data_migrations/merge_duplicate_samples_007.py --apply
```

This will:
1. Choose the best sample ID to keep (prefers canonical format: UPPERCASE, no spaces/underscores)
2. Migrate all experiments, analyses, photos to the primary sample
3. Merge metadata (keeping non-null values)
4. Delete duplicate sample records
5. Commit changes to database

## Expected Results

After running the merge:
- Sample count should decrease from 594 to the unique count
- PowerBI should show no more duplicates
- All relationships preserved (no data loss)

## Troubleshooting

### If Python command doesn't work:
Try these alternatives:
```bash
py database/data_migrations/identify_duplicate_samples.py
python3 database/data_migrations/identify_duplicate_samples.py
```

### If you're using a virtual environment:
```bash
# Activate your venv first
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate  # Windows

# Then run the scripts
python database/data_migrations/identify_duplicate_samples.py
```

### If duplicates keep appearing:
Make sure the updated `rock_inventory.py` with the normalization fix is deployed before uploading more samples.

## Prevention

The updated bulk upload service now:
1. Normalizes sample IDs before insertion (UPPERCASE, no spaces/underscores)
2. Matches existing samples using normalized comparison
3. Shows warnings (not errors) when format differs
4. Prevents new duplicates from being created

## Backup Recommendation

Before running the merge with `--apply`, consider backing up your database:

```bash
# Windows PowerShell
Copy-Item experiments.db experiments_backup_before_merge.db

# Git Bash / Linux
cp experiments.db experiments_backup_before_merge.db
```

