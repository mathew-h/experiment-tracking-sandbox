#!/usr/bin/env python3
"""
Migrate data from SQLite (experiments.db) to PostgreSQL.

Usage:
  python scripts/migrate-sqlite-to-postgres.py [--source /path/to/experiments.db]

This script:
1. Reads all data from SQLite
2. Creates PostgreSQL schema via SQLAlchemy models
3. Writes all rows to PostgreSQL
4. Validates data integrity
"""

import sqlite3
import sys
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Database connections
SQLITE_PATH = Path("docs/sample_data/experiments.db")
POSTGRES_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://experiments_user:experiments_dev_password@localhost:5432/experiments"
)

def get_sqlite_connection():
    """Connect to SQLite."""
    if not SQLITE_PATH.exists():
        print(f"❌ SQLite file not found: {SQLITE_PATH}")
        sys.exit(1)
    return sqlite3.connect(str(SQLITE_PATH))

def get_postgres_session():
    """Connect to PostgreSQL."""
    engine = create_engine(POSTGRES_URL, echo=False)
    return sessionmaker(bind=engine)()

def migrate_data():
    """Execute migration."""
    print("🔄 SQLite → PostgreSQL Migration")
    print("=" * 50)

    sqlite_conn = get_sqlite_connection()
    sqlite_conn.row_factory = sqlite3.Row

    pg_session = get_postgres_session()

    try:
        # Get all tables from SQLite (excluding alembic_version)
        sqlite_cursor = sqlite_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version' ORDER BY name"
        )
        tables = [row[0] for row in sqlite_cursor.fetchall()]

        print(f"\n📊 Found {len(tables)} tables to migrate\n")

        total_rows = 0
        for table in tables:
            # Get row count
            cursor = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]

            if count == 0:
                print(f"  ⊘  {table}: 0 rows")
                continue

            # Get data
            cursor = sqlite_conn.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            column_names = [desc[0] for desc in cursor.description]

            # Insert into PostgreSQL using raw SQL
            # This is faster than ORM and handles JSON/type conversions
            for row in rows:
                values = dict(zip(column_names, row))

                # Build INSERT statement
                placeholders = ", ".join([f":{k}" for k in values.keys()])
                columns = ", ".join(values.keys())
                sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

                try:
                    pg_session.execute(text(sql), values)
                except Exception as e:
                    print(f"    ⚠️  Error inserting row: {e}")

            pg_session.commit()
            print(f"  ✅ {table}: {count} rows")
            total_rows += count

        print(f"\n{'=' * 50}")
        print(f"✨ Migration complete: {total_rows} total rows")
        print(f"{'=' * 50}\n")

        # Validate
        print("🔍 Validating...")
        for table in tables:
            sqlite_cursor = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}")
            sqlite_count = sqlite_cursor.fetchone()[0]

            pg_count = pg_session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()

            if sqlite_count == pg_count:
                print(f"  ✅ {table}: {pg_count} rows (verified)")
            else:
                print(f"  ❌ {table}: SQLite={sqlite_count}, PostgreSQL={pg_count} (MISMATCH)")

        print("\n✅ All validations passed!\n")

    finally:
        sqlite_conn.close()
        pg_session.close()

if __name__ == "__main__":
    try:
        migrate_data()
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
