"""Issue #83: data-migration logic that backfills bucket_days on results.

Loads the migration module from its file (alembic version filenames are not
importable) and executes its SQL constants against the test session, so the
demotion ranking and the backfill are pinned without running alembic itself.
"""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from database import Base
from database.models.experiments import Experiment
from database.models.results import (
    ExperimentalResults, ScalarResults, ICPResults,
)
from database.models.enums import ExperimentStatus

# This migration's SQL uses Postgres-only cast syntax (::numeric, ::float8),
# so the test session must be a real Postgres connection, not SQLite. This
# module lives directly under tests/ (not tests/api/), which has no
# db_session fixture of its own, so it defines a local one here, mirroring
# the Postgres savepoint-per-test pattern in tests/api/conftest.py.
_TEST_DB_URL = (
    "postgresql://experiments_user:password@localhost:5432/experiments_test"
)
_test_engine = create_engine(_TEST_DB_URL, pool_pre_ping=True)
_TestSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=_test_engine,
)


@pytest.fixture(scope="module", autouse=True)
def _create_test_tables():
    """Create all tables once per test module, drop after."""
    Base.metadata.create_all(bind=_test_engine)
    yield
    Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture()
def db_session(_create_test_tables):
    """Per-test session in a savepoint; rolled back after the test."""
    connection = _test_engine.connect()
    transaction = connection.begin()
    session = _TestSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def _load_migration_module():
    matches = list(
        Path("alembic/versions").glob("*_backfill_result_timepoint_buckets.py")
    )
    assert len(matches) == 1, (
        f"expected exactly one backfill migration, got {matches}"
    )
    spec = importlib.util.spec_from_file_location(
        "backfill_buckets_migration", matches[0],
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_backfill(db):
    mod = _load_migration_module()
    db.execute(text(mod.DEMOTE_COLLIDING_PRIMARIES_SQL))
    db.execute(text(mod.BACKFILL_BUCKETS_SQL))
    db.flush()


def _make_experiment(db, experiment_id, number):
    exp = Experiment(experiment_id=experiment_id, experiment_number=number,
                     status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _add_result(db, exp, days, bucket, primary,
                with_scalar=False, with_icp=False):
    row = ExperimentalResults(
        experiment_fk=exp.id, description=f"t={days}",
        time_post_reaction_days=days, time_post_reaction_bucket_days=bucket,
        is_primary_timepoint_result=primary,
    )
    db.add(row)
    db.flush()
    if with_scalar:
        db.add(ScalarResults(result_id=row.id,
                             gross_ammonium_concentration_mM=1.0))
    if with_icp:
        db.add(ICPResults(result_id=row.id, fe=1.0))
    db.flush()
    return row


def test_backfill_fills_null_bucket_from_days(db_session):
    exp = _make_experiment(db_session, "BF_001", 9810)
    row = _add_result(db_session, exp, days=7.123456, bucket=None,
                      primary=True)
    _run_backfill(db_session)
    db_session.expire_all()
    got = db_session.get(ExperimentalResults, row.id)
    assert got.time_post_reaction_bucket_days == 7.1235


def test_backfill_leaves_null_days_and_existing_buckets_alone(db_session):
    exp = _make_experiment(db_session, "BF_002", 9811)
    no_days = _add_result(db_session, exp, days=None, bucket=None,
                          primary=True)
    bulk = _add_result(db_session, exp, days=3.0, bucket=3.0, primary=True)
    _run_backfill(db_session)
    db_session.expire_all()
    no_days_row = db_session.get(ExperimentalResults, no_days.id)
    bulk_row = db_session.get(ExperimentalResults, bulk.id)
    assert no_days_row.time_post_reaction_bucket_days is None
    assert bulk_row.time_post_reaction_bucket_days == 3.0


def test_backfill_demotes_dataless_row_when_bulk_row_exists(db_session):
    """Hand row (scalar only, null bucket) colliding with a bulk row that has
    scalar+icp and a real bucket: the bulk row keeps primary (data-first rank,
    mirroring result_merge_utils._rank_primary_candidate)."""
    exp = _make_experiment(db_session, "BF_003", 9812)
    hand = _add_result(db_session, exp, days=7.0, bucket=None, primary=True,
                       with_scalar=True)
    bulk = _add_result(db_session, exp, days=7.0, bucket=7.0, primary=True,
                       with_scalar=True, with_icp=True)
    _run_backfill(db_session)
    db_session.expire_all()
    hand_row = db_session.get(ExperimentalResults, hand.id)
    bulk_row = db_session.get(ExperimentalResults, bulk.id)
    assert bulk_row.is_primary_timepoint_result is True
    assert hand_row.is_primary_timepoint_result is False
    assert hand_row.time_post_reaction_bucket_days == 7.0  # still backfilled


def test_backfill_same_rank_ties_break_to_newest(db_session):
    """Two hand-entered rows, same day, both scalar-only: highest id wins."""
    exp = _make_experiment(db_session, "BF_004", 9813)
    older = _add_result(db_session, exp, days=7.0, bucket=None, primary=True,
                        with_scalar=True)
    newer = _add_result(db_session, exp, days=7.0, bucket=None, primary=True,
                        with_scalar=True)
    _run_backfill(db_session)
    db_session.expire_all()
    newer_row = db_session.get(ExperimentalResults, newer.id)
    older_row = db_session.get(ExperimentalResults, older.id)
    assert newer_row.is_primary_timepoint_result is True
    assert older_row.is_primary_timepoint_result is False
