"""Tests for the v_experiment_additive_names_summary reporting view."""
import datetime
import pytest
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker, Session

from database import Base
from database.models import (
    Experiment, ExperimentalConditions, ChemicalAdditive, Compound, AmountUnit
)

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"


@pytest.fixture(scope="module")
def view_engine():
    engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def view_db(view_engine):
    """Per-test session wrapped in a savepoint; creates views then rolls back."""
    connection = view_engine.connect()
    transaction = connection.begin()

    from database.event_listeners import _VIEWS
    for view_name, view_sql in _VIEWS:
        try:
            connection.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
            connection.execute(text(view_sql))
        except Exception:
            pass

    TestSession = sessionmaker(bind=connection)
    db = TestSession()
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()


def _make_experiment(db: Session, exp_id: str, number: int) -> Experiment:
    exp = Experiment(
        experiment_id=exp_id,
        experiment_number=number,
        status="ONGOING",
        date=datetime.date(2026, 1, 1),
    )
    cond = ExperimentalConditions(
        experiment_id=exp_id,
        rock_mass_g=100.0,
        water_volume_mL=500.0,
    )
    exp.conditions = cond
    db.add(exp)
    db.flush()
    cond.experiment_fk = exp.id
    return exp


def _make_compound(db: Session, name: str, n: int) -> Compound:
    c = Compound(name=name, formula=f"X{n}", molecular_weight_g_mol=100.0)
    db.add(c)
    db.flush()
    return c


def _add_additive(db: Session, cond: ExperimentalConditions, compound: Compound) -> None:
    ca = ChemicalAdditive(
        experiment_id=cond.id,
        compound_id=compound.id,
        amount=1.0,
        unit=AmountUnit.GRAM,
    )
    db.add(ca)
    db.flush()


class TestViewQueryable:
    def test_view_exists_and_returns_no_rows_on_empty_db(self, view_db):
        rows = view_db.execute(
            text("SELECT * FROM v_experiment_additive_names_summary")
        ).fetchall()
        assert rows == []


class TestNoAdditives:
    def test_experiment_with_no_additives_appears_with_null(self, view_db):
        _make_experiment(view_db, "EXP_001", 1)
        view_db.commit()

        rows = view_db.execute(
            text("SELECT experiment_id, additive_names FROM v_experiment_additive_names_summary")
        ).fetchall()
        assert len(rows) == 1
        row = rows[0]._mapping
        assert row["experiment_id"] == "EXP_001"
        assert row["additive_names"] is None


class TestSingleAdditive:
    def test_single_additive_returns_compound_name(self, view_db):
        exp = _make_experiment(view_db, "EXP_001", 1)
        compound = _make_compound(view_db, "Nickel Chloride", 1)
        _add_additive(view_db, exp.conditions, compound)
        view_db.commit()

        row = view_db.execute(
            text("SELECT additive_names FROM v_experiment_additive_names_summary WHERE experiment_id = 'EXP_001'")
        ).fetchone()
        assert row._mapping["additive_names"] == "Nickel Chloride"


class TestMultipleAdditives:
    def test_multiple_additives_alphabetically_sorted(self, view_db):
        exp = _make_experiment(view_db, "EXP_001", 1)
        copper = _make_compound(view_db, "Copper Sulfate", 1)
        nickel = _make_compound(view_db, "Nickel Chloride", 2)
        _add_additive(view_db, exp.conditions, nickel)   # insert nickel first
        _add_additive(view_db, exp.conditions, copper)   # copper should sort before nickel
        view_db.commit()

        row = view_db.execute(
            text("SELECT additive_names FROM v_experiment_additive_names_summary WHERE experiment_id = 'EXP_001'")
        ).fetchone()
        assert row._mapping["additive_names"] == "Copper Sulfate, Nickel Chloride"


class TestOneRowPerExperiment:
    def test_two_experiments_two_rows(self, view_db):
        exp1 = _make_experiment(view_db, "EXP_001", 1)
        exp2 = _make_experiment(view_db, "EXP_002", 2)
        compound = _make_compound(view_db, "Copper Sulfate", 1)
        _add_additive(view_db, exp1.conditions, compound)
        view_db.commit()

        rows = view_db.execute(
            text("SELECT experiment_id FROM v_experiment_additive_names_summary ORDER BY experiment_id")
        ).fetchall()
        ids = [r._mapping["experiment_id"] for r in rows]
        assert ids == ["EXP_001", "EXP_002"]

    def test_experiment_count_matches_experiments_table(self, view_db):
        _make_experiment(view_db, "EXP_001", 1)
        _make_experiment(view_db, "EXP_002", 2)
        _make_experiment(view_db, "EXP_003", 3)
        view_db.commit()

        view_count = view_db.execute(
            text("SELECT COUNT(*) FROM v_experiment_additive_names_summary")
        ).scalar()
        exp_count = view_db.execute(
            text("SELECT COUNT(*) FROM experiments")
        ).scalar()
        assert view_count == exp_count
