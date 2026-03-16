# Alternative Methods to Detect Duplicate Samples

If you can't run Python scripts directly, here are alternative ways to detect duplicates:

## Method 1: Using SQLite Browser (Easiest)

1. Open `experiments.db` in SQLite Browser (DB Browser for SQLite)
2. Go to "Execute SQL" tab
3. Copy and paste the contents of `check_duplicates.sql`
4. Click "Execute"
5. Review the results showing duplicate groups

## Method 2: Using PowerShell with SQLite

```powershell
# Install SQLite if needed
# Download from https://www.sqlite.org/download.html

# Run query
sqlite3 experiments.db < database/data_migrations/check_duplicates.sql
```

## Method 3: Using Python in Streamlit

If the Streamlit app is running, you can add this temporary diagnostic to the app:

```python
# Add to any page temporarily
import streamlit as st
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
result = db.execute(text("""
    SELECT COUNT(*) as total_samples FROM sample_info
"""))
st.write("Total samples:", result.scalar())

result = db.execute(text("""
    SELECT COUNT(DISTINCT LOWER(REPLACE(REPLACE(REPLACE(sample_id, '-', ''), '_', ''), ' ', ''))) as unique_samples
    FROM sample_info
"""))
st.write("Unique samples (normalized):", result.scalar())
db.close()
```

## Method 4: Check Sample Count in PowerBI

Your current PowerBI dashboard shows 594 samples. After running the merge:
- The count should match the "Expected After Merge" count from the SQL query
- Duplicate entries in visualizations should disappear

## Method 5: Quick Count via Python One-Liner

If Python works but scripts don't:

```bash
python -c "from database import SessionLocal; db = SessionLocal(); print('Total:', db.query(db.query('SELECT COUNT(*) FROM sample_info').statement.columns[0]).scalar()); db.close()"
```

Or simpler:

```bash
python -c "import sqlite3; conn = sqlite3.connect('experiments.db'); cur = conn.cursor(); print('Total samples:', cur.execute('SELECT COUNT(*) FROM sample_info').fetchone()[0]); total_normalized = cur.execute('SELECT COUNT(DISTINCT LOWER(REPLACE(REPLACE(REPLACE(sample_id, \"-\", \"\"), \"_\", \"\"), \" \", \"\"))) FROM sample_info').fetchone()[0]; print('Unique samples:', total_normalized); print('Duplicates to remove:', cur.execute('SELECT COUNT(*) FROM sample_info').fetchone()[0] - total_normalized); conn.close()"
```

## What to Look For

In any of these methods, you should see:
- **Total Samples**: 594 (your current count)
- **Unique Samples**: [Lower number - this is what you expect]
- **Duplicate Groups**: Number of sample groups with multiple entries
- **Extra Duplicate Records**: How many will be removed by merge

## Example Output

```
Total Samples: 594
Unique Samples (normalized): 547
Duplicate Groups: 47
Extra Duplicate Records: 47

Sample duplicate groups:
- "20250710-2D" | "20250710_2D" (2 duplicates)
- "rock-001" | "ROCK-001" | "ROCK_001" (3 duplicates)
...
```

This tells you:
- You have 594 total records
- Only 547 are truly unique (normalized)
- 47 duplicate records need to be removed
- After merge, you'll have 547 samples

