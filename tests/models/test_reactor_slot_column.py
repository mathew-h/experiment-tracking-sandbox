"""Column-level tests for experimental_conditions.reactor_slot (issue #97).

The parity test is the important one: the Alembic backfill re-expresses
derive_reactor_slot's rules in SQL, and nothing but a test stops the two from
drifting.
"""
from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from database.models import ExperimentalConditions
from database.models.enums import ExperimentStatus
from database.models.experiments import Experiment
from database.reactor_slot import derive_reactor_slot


def test_reactor_slot_column_exists_and_is_indexed(db_session: Session):
    insp = inspect(db_session.get_bind())
    cols = {c["name"]: c for c in insp.get_columns("experimental_conditions")}
    assert "reactor_slot" in cols
    assert cols["reactor_slot"]["nullable"] is True
    indexed = {
        col
        for ix in insp.get_indexes("experimental_conditions")
        for col in ix["column_names"]
    }
    assert "reactor_slot" in indexed


# The SQL expression below is structurally equivalent to the one in the
# Alembic migration's upgrade(), not character-identical: the migration reads
# a bare `reactor_number::text` column reference inside an UPDATE, while this
# is a parametrized `(:rnum)::int::text` inside a SELECT so it can be driven
# from Python for every case below. That cast is the deliberate difference.
# What this test actually pins is semantic equivalence over real
# experiment_type spellings and number widths — if you change one CASE,
# change the other and this test will tell you if they disagree.
_BACKFILL_SQL = """
SELECT CASE
    WHEN lower(btrim(regexp_replace(coalesce(:etype, ''), '\\s+', ' ', 'g')))
         IN ('core flood', 'coreflood', 'cf')
        THEN 'CF' || lpad((:rnum)::int::text, GREATEST(2, length((:rnum)::int::text)), '0')
    WHEN lower(btrim(regexp_replace(coalesce(:etype, ''), '\\s+', ' ', 'g')))
         = 'hpht'
        THEN 'R' || lpad((:rnum)::int::text, GREATEST(2, length((:rnum)::int::text)), '0')
    ELSE NULL
END AS slot
"""


@pytest.mark.parametrize(
    "rnum,etype",
    [
        (1, "HPHT"),
        (16, "HPHT"),
        (1, "Core Flood"),
        (3, "CF"),
        (2, "CoreFlood"),
        (4, "Core  Flood"),
        (5, "SERUM"),
        (6, "Serum"),
        (7, "Autoclave"),
        (8, "AUTO"),
        (9, "Other"),
        (10, None),
        (100, "HPHT"),
        (1234, "Core Flood"),
    ],
)
def test_backfill_sql_matches_python_deriver(db_session: Session, rnum, etype):
    """The migration's SQL CASE and derive_reactor_slot must agree on every
    experiment_type spelling present in production data."""
    sql_result = db_session.execute(
        text(_BACKFILL_SQL), {"etype": etype, "rnum": rnum}
    ).scalar_one()
    assert sql_result == derive_reactor_slot(rnum, etype)


def test_zero_and_null_reactor_numbers_are_excluded_by_the_backfill_predicate():
    """The migration's WHERE clause is `reactor_number IS NOT NULL AND reactor_number > 0`,
    so the SQL CASE is never evaluated for those rows. Python must return None for
    them too, which is what makes the two equivalent overall."""
    assert derive_reactor_slot(0, "HPHT") is None
    assert derive_reactor_slot(None, "HPHT") is None


def test_column_accepts_and_returns_a_slot_value(db_session: Session):
    """Storage-level round trip only. Nothing populates reactor_slot yet — the
    listener that derives it lands in Task 3 — so this writes the value directly
    to prove the column persists a string of the expected width.
    """
    exp = Experiment(
        experiment_id="HPHT_SLOT_001",
        experiment_number=97001,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id=exp.experiment_id,
        experiment_type="HPHT",
        reactor_number=4,
    )
    cond.reactor_slot = "R04"
    db_session.add(cond)
    db_session.flush()
    db_session.expire(cond)
    assert cond.reactor_slot == "R04"
