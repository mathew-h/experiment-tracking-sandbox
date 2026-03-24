"""Fresh-install migration test: verify the documented fresh-install procedure on a blank DB.

The initial Alembic migration (b1fc58c4119d) is intentionally empty — it was
written against an existing SQLite DB. The correct fresh-install procedure is:

    Base.metadata.create_all(engine)   # create all tables from ORM metadata
    alembic stamp head                 # mark DB as fully migrated

This test verifies that procedure produces a schema with all expected tables and
that subsequent alembic migrations (additive columns) can be applied cleanly on
top of it. See docs/working/plan.md M0 section for the authoritative rationale.
"""
from __future__ import annotations

import subprocess
import pytest
from sqlalchemy import create_engine, inspect, text

PG_BIN = r"C:\Program Files\PostgreSQL\18\bin"
CREATEDB = f"{PG_BIN}\\createdb.exe"
DROPDB = f"{PG_BIN}\\dropdb.exe"

FRESH_DB = "experiments_fresh_install_test"
PG_USER = "experiments_user"
PG_PASSWORD = "password"
PG_HOST = "localhost"
PG_PORT = "5432"

EXPECTED_TABLES = [
    "experiments",
    "experimental_conditions",
    "chemical_additives",
    "compounds",
    "experimental_results",
    "scalar_results",
    "icp_results",
    "result_files",
    "experiment_notes",
    "modifications_log",
    "sample_info",
    "sample_photos",
    "external_analyses",
    "analysis_files",
    "xrd_analysis",
    "xrd_phases",
    "pxrf_readings",
    "analytes",
    "elemental_analysis",
    "app_config",
]

EXPECTED_COLUMNS = {
    "scalar_results": ["h2_concentration", "h2_micromoles", "h2_mass_ug", "h2_grams_per_ton_yield"],
    # co2_partial_pressure_MPa is stored with mixed case (SQLAlchemy quotes it in PostgreSQL DDL)
    "experimental_conditions": ["co2_partial_pressure_MPa", "confining_pressure"],
    "app_config": ["key", "value", "updated_at"],
}

PROJECT_ROOT = r"C:\Users\MathewHearl\Documents\0x_Software\database_sandbox\experiment_tracking_sandbox"


def _super_env() -> dict:
    import os
    return {**os.environ.copy(), "PGPASSWORD": "password"}


def _user_env(db_url: str) -> dict:
    import os
    e = os.environ.copy()
    e["PGPASSWORD"] = PG_PASSWORD
    e["DATABASE_URL"] = db_url
    return e


@pytest.fixture(scope="module")
def fresh_db_engine():
    """Create blank DB → Base.metadata.create_all → alembic stamp head → yield engine."""
    super_env = _super_env()

    # Drop any leftover scratch DB
    subprocess.run(
        [DROPDB, "-h", PG_HOST, "-p", PG_PORT, "-U", "postgres", "--if-exists", FRESH_DB],
        env=super_env,
    )

    # Create blank DB owned by experiments_user
    result = subprocess.run(
        [CREATEDB, "-h", PG_HOST, "-p", PG_PORT, "-U", "postgres", "-O", PG_USER, FRESH_DB],
        capture_output=True, text=True, env=super_env,
    )
    assert result.returncode == 0, f"createdb failed: {result.stderr}"

    fresh_url = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{FRESH_DB}"

    # Step 1: create all tables from ORM metadata (documented fresh-install procedure)
    from database import Base
    engine = create_engine(fresh_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)

    # Step 2: stamp alembic at head so it knows the DB is fully migrated
    result = subprocess.run(
        [r".venv\Scripts\alembic.exe", "stamp", "head"],
        capture_output=True, text=True,
        env=_user_env(fresh_url),
        cwd=PROJECT_ROOT,
    )
    assert result.returncode == 0, f"alembic stamp head failed: {result.stderr}"

    yield engine
    engine.dispose()

    subprocess.run(
        [DROPDB, "-h", PG_HOST, "-p", PG_PORT, "-U", "postgres", "--if-exists", FRESH_DB],
        env=super_env,
    )


def test_all_tables_created(fresh_db_engine):
    """Every expected table must exist after Base.metadata.create_all."""
    inspector = inspect(fresh_db_engine)
    existing = set(inspector.get_table_names())
    missing = [t for t in EXPECTED_TABLES if t not in existing]
    assert not missing, f"Tables missing after fresh-install: {missing}"


def test_critical_columns_exist(fresh_db_engine):
    """Spot-check columns from key migrations exist in the fresh schema."""
    inspector = inspect(fresh_db_engine)
    errors = []
    for table, cols in EXPECTED_COLUMNS.items():
        existing_cols = {c["name"] for c in inspector.get_columns(table)}
        for col in cols:
            if col not in existing_cols:
                errors.append(f"{table}.{col}")
    assert not errors, f"Missing columns after fresh-install: {errors}"


def test_alembic_stamped_at_head(fresh_db_engine):
    """alembic_version must contain exactly one row after stamp head."""
    with fresh_db_engine.connect() as conn:
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    assert len(rows) == 1, f"Expected 1 alembic_version row, got: {rows}"


def test_no_pending_migrations(fresh_db_engine):
    """alembic check should report no pending migrations on the fresh-installed DB."""
    # str(engine.url) masks the password — reconstruct from known constants
    fresh_url = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{FRESH_DB}"
    result = subprocess.run(
        [r".venv\Scripts\alembic.exe", "check"],
        capture_output=True, text=True,
        env=_user_env(fresh_url),
        cwd=PROJECT_ROOT,
    )
    # Exit 0 = no pending migrations; exit 1 = pending migrations exist
    assert result.returncode == 0, (
        f"Pending migrations detected on fresh install.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
