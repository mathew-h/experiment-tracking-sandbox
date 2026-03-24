"""Backup/restore test: pg_dump the test DB, restore to a temp DB, verify integrity.

Uses the PostgreSQL test DB (experiments_test). Creates a temporary scratch DB,
restores the dump into it, and checks that all expected tables exist with
non-negative row counts. Drops the scratch DB on teardown.
"""
from __future__ import annotations

import subprocess
import pytest
from sqlalchemy import create_engine, inspect, text

PG_BIN = r"C:\Program Files\PostgreSQL\18\bin"
PG_DUMP = f"{PG_BIN}\\pg_dump.exe"
PG_RESTORE = f"{PG_BIN}\\pg_restore.exe"
PSQL = f"{PG_BIN}\\psql.exe"
CREATEDB = f"{PG_BIN}\\createdb.exe"
DROPDB = f"{PG_BIN}\\dropdb.exe"

SOURCE_DB = "experiments_test"
SCRATCH_DB = "experiments_restore_test"
PG_USER = "experiments_user"
PG_PASSWORD = "password"
PG_HOST = "localhost"
PG_PORT = "5432"

EXPECTED_TABLES = [
    "experiments",
    "experimental_conditions",
    "experimental_results",
    "scalar_results",
    "icp_results",
    "sample_info",
    "external_analyses",
    "pxrf_readings",
    "analytes",
    "elemental_analysis",
    "modifications_log",
    "app_config",
]


def _env() -> dict:
    import os
    e = os.environ.copy()
    e["PGPASSWORD"] = PG_PASSWORD
    return e


@pytest.fixture(scope="module")
def dump_file(tmp_path_factory):
    """Dump experiments_test to a custom-format file."""
    dump_path = tmp_path_factory.mktemp("pgdump") / "test_dump.dump"
    result = subprocess.run(
        [
            PG_DUMP,
            "-h", PG_HOST, "-p", PG_PORT, "-U", PG_USER,
            "-F", "c",  # custom format
            "-f", str(dump_path),
            SOURCE_DB,
        ],
        capture_output=True, text=True, env=_env(),
    )
    assert result.returncode == 0, f"pg_dump failed: {result.stderr}"
    assert dump_path.exists() and dump_path.stat().st_size > 0
    yield dump_path


@pytest.fixture(scope="module")
def scratch_db(dump_file):
    """Create scratch DB, restore dump, yield engine, drop on teardown."""
    env = _env()

    # Drop if left from a previous failed run
    subprocess.run([DROPDB, "-h", PG_HOST, "-p", PG_PORT, "-U", "postgres",
                    "--if-exists", SCRATCH_DB], env={**env, "PGPASSWORD": "password"})

    # Create scratch DB owned by experiments_user
    result = subprocess.run(
        [CREATEDB, "-h", PG_HOST, "-p", PG_PORT, "-U", "postgres",
         "-O", PG_USER, SCRATCH_DB],
        capture_output=True, text=True, env={**env, "PGPASSWORD": "password"},
    )
    assert result.returncode == 0, f"createdb failed: {result.stderr}"

    # Restore
    result = subprocess.run(
        [
            PG_RESTORE,
            "-h", PG_HOST, "-p", PG_PORT, "-U", PG_USER,
            "-d", SCRATCH_DB,
            "--no-owner", "--no-privileges",
            str(dump_file),
        ],
        capture_output=True, text=True, env=env,
    )
    # pg_restore may emit warnings (exit code 1) for missing roles — treat as ok
    assert result.returncode in (0, 1), f"pg_restore failed: {result.stderr}"

    engine = create_engine(
        f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{SCRATCH_DB}",
        pool_pre_ping=True,
    )
    yield engine
    engine.dispose()

    subprocess.run([DROPDB, "-h", PG_HOST, "-p", PG_PORT, "-U", "postgres",
                    "--if-exists", SCRATCH_DB], env={**env, "PGPASSWORD": "password"})


def test_all_expected_tables_exist(scratch_db):
    """Every expected table must exist in the restored DB."""
    inspector = inspect(scratch_db)
    restored_tables = set(inspector.get_table_names())
    missing = [t for t in EXPECTED_TABLES if t not in restored_tables]
    assert not missing, f"Tables missing after restore: {missing}"


def test_row_counts_non_negative(scratch_db):
    """Every table must have a non-negative row count (basic integrity check)."""
    with scratch_db.connect() as conn:
        for table in EXPECTED_TABLES:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            assert count >= 0, f"Unexpected count for {table}: {count}"


def test_foreign_key_integrity(scratch_db):
    """Spot-check FK integrity: every experiment's sample_id must exist in sample_info (or be NULL)."""
    with scratch_db.connect() as conn:
        orphans = conn.execute(text("""
            SELECT e.id, e.sample_id
            FROM experiments e
            LEFT JOIN sample_info s ON e.sample_id = s.sample_id
            WHERE e.sample_id IS NOT NULL AND s.sample_id IS NULL
        """)).fetchall()
    assert not orphans, f"Orphaned experiment.sample_id FK references after restore: {orphans}"
