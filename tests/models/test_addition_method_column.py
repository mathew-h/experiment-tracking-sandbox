"""Tests for ChemicalAdditive.addition_method being widened to Text (issue #96)."""
import pytest
from sqlalchemy import create_engine, inspect, types
from sqlalchemy.orm import sessionmaker

from database import Base
from database.models.chemicals import Compound, ChemicalAdditive, ADDITION_METHOD_MAX_LENGTH
from database.models.enums import AmountUnit

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(TEST_DB_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=eng)
    yield eng


@pytest.fixture
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def test_addition_method_column_is_text(engine):
    """The chemical_additives.addition_method column must be TEXT (unbounded), not varchar(50).

    Note: `isinstance(col_type, types.String)` is not a useful negative check here — SQLAlchemy's
    `types.Text` is itself a subclass of `types.String`, so that check can never distinguish
    Text from VARCHAR(n) and would always fail for a correct implementation. `length is None` is
    the reliable signal: reflected TEXT columns report `length=None`, reflected VARCHAR(n)
    columns report `length=n`.
    """
    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("chemical_additives")}
    col_type = columns["addition_method"]["type"]
    assert isinstance(col_type, types.Text) and col_type.length is None, (
        f"expected unbounded Text, got {col_type!r} ({type(col_type)}, length={getattr(col_type, 'length', 'n/a')})"
    )


def _seed_conditions(db, experiment_id: str, experiment_number: int):
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(experiment_id=experiment_id, experiment_number=experiment_number, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    conditions = ExperimentalConditions(experiment_id=exp.experiment_id, experiment_fk=exp.id)
    db.add(conditions)
    db.flush()
    return conditions


def test_addition_method_85_char_value_round_trips_intact(db):
    """Reproduces the exact issue #96 example: an 85-char prep note must survive a real flush to
    PostgreSQL unmodified. Pre-fix, this raises StringDataRightTruncation (85 > varchar(50))."""
    long_method = "11.8 mL master stock diluted to 20 mL total with DI water; no rock (background blank)"
    assert len(long_method) == 85

    conditions = _seed_conditions(db, "MODEL_I96_001", 980001)
    compound = Compound(name="Iron Oxide Test I96")
    db.add(compound)
    db.flush()

    additive = ChemicalAdditive(
        experiment_id=conditions.id,
        compound_id=compound.id,
        amount=5.0,
        unit=AmountUnit.GRAM,
        addition_method=long_method,
    )
    db.add(additive)
    db.flush()  # pre-fix: raises StringDataRightTruncation here

    db.expire(additive)
    assert additive.addition_method == long_method
    assert len(additive.addition_method) == 85


def test_addition_method_has_no_database_level_length_ceiling(db):
    """The DB column itself must be unbounded — only the app layer (Tasks 2-4) caps at
    ADDITION_METHOD_MAX_LENGTH. A value far beyond that app-layer bound must still flush cleanly
    at the ORM/DB level; it is the parsers'/schemas' job to stop such values before they get here."""
    conditions = _seed_conditions(db, "MODEL_I96_002", 980002)
    compound = Compound(name="Iron Oxide Test I96 B")
    db.add(compound)
    db.flush()

    text_5000 = "x" * 5000
    additive = ChemicalAdditive(
        experiment_id=conditions.id,
        compound_id=compound.id,
        amount=1.0,
        unit=AmountUnit.GRAM,
        addition_method=text_5000,
    )
    db.add(additive)
    db.flush()  # pre-fix: raises StringDataRightTruncation here too

    db.expire(additive)
    assert len(additive.addition_method) == 5000


def test_addition_method_max_length_constant_is_500():
    """Pin the shared app-layer bound so Tasks 2-4 all import the same value."""
    assert ADDITION_METHOD_MAX_LENGTH == 500
