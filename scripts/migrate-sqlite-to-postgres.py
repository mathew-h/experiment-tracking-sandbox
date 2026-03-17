#!/usr/bin/env python3
"""
Migrate data from SQLite (experiments.db) to PostgreSQL.

Usage:
  python scripts/migrate-sqlite-to-postgres.py [--source /path/to/experiments.db]

This script:
1. Reads all data from SQLite
2. Writes all rows to PostgreSQL in FK-safe dependency order
3. Uses per-row savepoints so individual FK violations don't abort the table transaction
4. Validates row counts per table
"""

import sqlite3
import sys
from pathlib import Path
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

SQLITE_PATH = Path("docs/sample_data/experiments.db")
POSTGRES_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://experiments_user:experiments_dev_password@localhost:5432/experiments"
)

# Tables in FK-safe insertion order (parents before children).
# Any table not listed here is appended at the end.
FK_ORDERED_TABLES = [
    "analytes",
    "compounds",
    "pxrf_readings",
    "sample_info",
    "experiments",
    "experimental_conditions",
    "chemical_additives",
    "experiment_notes",
    "modifications_log",
    "experimental_results",
    "scalar_results",
    "icp_results",
    "result_files",
    "external_analyses",
    "analysis_files",
    "xrd_analysis",
    "xrd_phases",
    "sample_photos",
    "elemental_analysis",
]


def get_sqlite_connection():
    if not SQLITE_PATH.exists():
        print(f"SQLite file not found: {SQLITE_PATH}")
        sys.exit(1)
    return sqlite3.connect(str(SQLITE_PATH))


def get_postgres_engine():
    return create_engine(POSTGRES_URL, echo=False)


def get_boolean_columns(engine, table: str) -> set:
    """Return set of column names that are BOOLEAN type in PostgreSQL."""
    inspector = inspect(engine)
    bool_cols = set()
    for col in inspector.get_columns(table):
        if str(col["type"]).upper() == "BOOLEAN":
            bool_cols.add(col["name"])
    return bool_cols


# Nullable FK columns where orphaned references should be nulled out
# rather than skipping the row. Format: {table: [col, ...]}
NULLABLE_FK_NULLOUT = {
    # sample_id: orphaned references nulled out (data to be cleaned in source)
    # parent_experiment_fk: self-referential FK, restored in a second pass below
    "experiments": ["sample_id", "parent_experiment_fk"],
    # experiment_fk: audit logs for deleted experiments — nullable, null out orphans
    "modifications_log": ["experiment_fk"],
}


def get_valid_fk_values(engine, table: str, column: str) -> set:
    """Return the set of existing values for a column (used to validate FK references)."""
    with engine.connect() as conn:
        rows = conn.execute(text(f'SELECT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL')).fetchall()
    return {r[0] for r in rows}


def migrate_table(engine, sqlite_conn, table: str) -> tuple[int, int]:
    """
    Migrate a single table. Returns (attempted, inserted) row counts.
    Uses per-row savepoints so a FK violation on one row doesn't abort the batch.
    Nullable FK columns with orphaned references are nulled out rather than skipped.
    """
    cursor = sqlite_conn.execute(f"SELECT * FROM [{table}]")
    rows = cursor.fetchall()
    column_names = [desc[0] for desc in cursor.description]

    if not rows:
        return 0, 0

    attempted = len(rows)
    inserted = 0
    errors = 0

    # Detect boolean columns so SQLite's 0/1 integers are cast to Python bool
    bool_cols = get_boolean_columns(engine, table)

    # Pre-load valid FK values for nullable FK columns in this table
    nullout_cols = NULLABLE_FK_NULLOUT.get(table, [])
    valid_fk: dict[str, set] = {}
    for col in nullout_cols:
        # Look up the referenced table/column from the PostgreSQL FK constraints
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT ccu.table_name, ccu.column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_name = :table
                  AND kcu.column_name = :col
            """), {"table": table, "col": col}).fetchone()
        if result:
            valid_fk[col] = get_valid_fk_values(engine, result[0], result[1])

    with engine.connect() as conn:
        with conn.begin():
            for row in rows:
                values = dict(zip(column_names, row))

                # Cast SQLite integer booleans to Python bool
                for col in bool_cols:
                    if col in values and values[col] is not None:
                        values[col] = bool(values[col])

                # Null out orphaned nullable FK references (empty string also treated as NULL)
                for col in nullout_cols:
                    val = values.get(col)
                    if not val or (col in valid_fk and val not in valid_fk[col]):
                        values[col] = None
                placeholders = ", ".join([f":{k}" for k in values.keys()])
                columns = ", ".join(f'"{k}"' for k in values.keys())
                sql = f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

                # Use a savepoint so a FK violation only rolls back this one row
                savepoint = conn.begin_nested()
                try:
                    conn.execute(text(sql), values)
                    savepoint.commit()
                    inserted += 1
                except Exception as e:
                    savepoint.rollback()
                    errors += 1
                    if errors <= 3:
                        # Show first few errors only
                        short_err = str(e).split("\n")[0]
                        print(f"    Warning ({table}): {short_err}")

    return attempted, inserted


def migrate_data():
    print("SQLite -> PostgreSQL Migration")
    print("=" * 50)

    sqlite_conn = get_sqlite_connection()
    sqlite_conn.row_factory = sqlite3.Row
    engine = get_postgres_engine()

    # Get all tables in SQLite
    cursor = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version'"
    )
    all_tables = {row[0] for row in cursor.fetchall()}

    # Build ordered list: known FK order first, then any remaining tables
    ordered = [t for t in FK_ORDERED_TABLES if t in all_tables]
    remaining = sorted(all_tables - set(ordered))
    tables = ordered + remaining

    print(f"\nFound {len(tables)} tables to migrate\n")

    total_attempted = 0
    total_inserted = 0

    for table in tables:
        count_cursor = sqlite_conn.execute(f"SELECT COUNT(*) FROM [{table}]")
        sqlite_count = count_cursor.fetchone()[0]

        if sqlite_count == 0:
            print(f"  --  {table}: 0 rows")
            continue

        attempted, inserted = migrate_table(engine, sqlite_conn, table)
        total_attempted += attempted
        total_inserted += inserted

        skipped = attempted - inserted
        if skipped > 0:
            print(f"  OK  {table}: {inserted}/{attempted} rows ({skipped} skipped)")
        else:
            print(f"  OK  {table}: {inserted} rows")

    print(f"\n{'=' * 50}")
    print(f"Migration complete: {total_inserted}/{total_attempted} rows inserted")
    print(f"{'=' * 50}\n")

    # Second pass: restore experiment parent_experiment_fk links that were nulled out.
    # Now that all experiments exist in PostgreSQL, self-referential FKs can be set safely.
    print("Restoring experiment lineage (parent_experiment_fk)...")
    cursor = sqlite_conn.execute(
        "SELECT id, parent_experiment_fk FROM experiments WHERE parent_experiment_fk IS NOT NULL"
    )
    lineage_rows = cursor.fetchall()
    restored = 0
    with engine.connect() as conn:
        with conn.begin():
            for exp_id, parent_fk in lineage_rows:
                savepoint = conn.begin_nested()
                try:
                    conn.execute(
                        text('UPDATE experiments SET parent_experiment_fk = :parent WHERE id = :id'),
                        {"parent": parent_fk, "id": exp_id}
                    )
                    savepoint.commit()
                    restored += 1
                except Exception:
                    savepoint.rollback()
    print(f"  Restored {restored}/{len(lineage_rows)} parent links\n")

    # Validate row counts
    print("Validating...")
    mismatches = []
    with engine.connect() as conn:
        for table in tables:
            sqlite_cursor = sqlite_conn.execute(f"SELECT COUNT(*) FROM [{table}]")
            sqlite_count = sqlite_cursor.fetchone()[0]
            pg_count = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()

            if sqlite_count == pg_count:
                print(f"  OK  {table}: {pg_count} rows")
            else:
                print(f"  MISMATCH  {table}: SQLite={sqlite_count}, PostgreSQL={pg_count}")
                mismatches.append(table)

    sqlite_conn.close()

    if mismatches:
        print(f"\nMismatched tables: {', '.join(mismatches)}")
        print("These may be due to FK violations on orphaned rows in the source data.")
        sys.exit(1)
    else:
        print(f"\nAll {len(tables)} tables validated successfully.\n")


if __name__ == "__main__":
    try:
        migrate_data()
    except Exception as e:
        print(f"\nMigration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
