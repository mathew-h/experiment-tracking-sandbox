"""Pins the 018 cleanup: which duplicate row survives, when the script refuses,
and that the backfill rewrites a stale string from its FK."""
from sqlalchemy import select

from database.data_migrations.dedupe_conditions_and_backfill_ids_018 import (
    backfill_strings,
    dedupe,
    find_duplicate_groups,
    find_stale_strings,
)
from database.models.chemicals import ChemicalAdditive, Compound
from database.models.conditions import ExperimentalConditions
from database.models.enums import AmountUnit, ExperimentStatus
from database.models.experiments import Experiment


def _exp(db, eid, num):
    exp = Experiment(experiment_id=eid, experiment_number=num, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _cond(db, exp, string, **kw):
    cond = ExperimentalConditions(experiment_fk=exp.id, experiment_id=string, **kw)
    db.add(cond)
    db.flush()
    return cond


def test_keeps_the_row_whose_string_matches_the_experiment(migration_session):
    """The survivor is chosen by correctness of the string, not by age."""
    exp = _exp(migration_session, "DEDUP_001", 61001)
    stale = _cond(migration_session, exp, "DEDUP_OLD_NAME", temperature_c=90.0)
    correct = _cond(migration_session, exp, "DEDUP_001", temperature_c=90.0)

    groups = [g for g in find_duplicate_groups(migration_session) if g.experiment_fk == exp.id]
    assert len(groups) == 1
    assert groups[0].keep_id == correct.id
    assert groups[0].delete_ids == [stale.id]
    assert groups[0].blocked_reason is None

    deleted, refusals = dedupe(migration_session, groups)
    assert deleted == [stale.id]
    assert refusals == []
    remaining = migration_session.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
    ).scalars().all()
    assert [c.id for c in remaining] == [correct.id]


def test_keeps_lowest_id_when_neither_string_is_correct(migration_session):
    exp = _exp(migration_session, "DEDUP_002", 61002)
    first = _cond(migration_session, exp, "WRONG_A", temperature_c=80.0)
    second = _cond(migration_session, exp, "WRONG_B", temperature_c=80.0)

    group = next(g for g in find_duplicate_groups(migration_session) if g.experiment_fk == exp.id)
    assert group.keep_id == min(first.id, second.id)


def test_refuses_when_measurement_values_differ(migration_session):
    """Not equivalent means a human decides — the script must not pick for them."""
    exp = _exp(migration_session, "DEDUP_003", 61003)
    _cond(migration_session, exp, "DEDUP_003", temperature_c=90.0)
    _cond(migration_session, exp, "DEDUP_OTHER", temperature_c=120.0)

    group = next(g for g in find_duplicate_groups(migration_session) if g.experiment_fk == exp.id)
    assert group.blocked_reason is not None
    assert "temperature_c" in group.blocked_reason

    deleted, refusals = dedupe(migration_session, [group])
    assert deleted == []
    assert len(refusals) == 1
    survivors = migration_session.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
    ).scalars().all()
    assert len(survivors) == 2


def test_refuses_when_the_doomed_row_holds_an_additive_the_survivor_lacks(migration_session):
    """ChemicalAdditive.experiment_id is an integer FK to experimental_conditions.id,
    so deleting a row destroys its additives via delete-orphan."""
    compound = Compound(name="Dedup Test Magnetite", molecular_weight_g_mol=231.5)
    migration_session.add(compound)
    migration_session.flush()

    exp = _exp(migration_session, "DEDUP_004", 61004)
    _cond(migration_session, exp, "DEDUP_004", temperature_c=90.0)
    doomed = _cond(migration_session, exp, "DEDUP_OLD", temperature_c=90.0)
    migration_session.add(ChemicalAdditive(
        experiment_id=doomed.id, compound_id=compound.id, amount=1.0, unit=AmountUnit.GRAM
    ))
    migration_session.flush()

    group = next(g for g in find_duplicate_groups(migration_session) if g.experiment_fk == exp.id)
    assert group.blocked_reason is not None
    assert "additive" in group.blocked_reason.lower()


def test_allows_deletion_when_both_rows_carry_the_same_additive(migration_session):
    """The real production case: 'Add Details' re-entered an identical additive."""
    compound = Compound(name="Dedup Test Brucite", molecular_weight_g_mol=58.3)
    migration_session.add(compound)
    migration_session.flush()

    exp = _exp(migration_session, "DEDUP_005", 61005)
    keep = _cond(migration_session, exp, "DEDUP_005", temperature_c=90.0)
    doomed = _cond(migration_session, exp, "DEDUP_OLD_5", temperature_c=90.0)
    for cond_id in (keep.id, doomed.id):
        migration_session.add(ChemicalAdditive(
            experiment_id=cond_id, compound_id=compound.id, amount=0.149, unit=AmountUnit.GRAM
        ))
    migration_session.flush()

    group = next(g for g in find_duplicate_groups(migration_session) if g.experiment_fk == exp.id)
    assert group.blocked_reason is None
    deleted, refusals = dedupe(migration_session, [group])
    assert deleted == [doomed.id]
    assert refusals == []


def test_backfill_rewrites_a_stale_string_from_its_fk(migration_session):
    exp = _exp(migration_session, "STALE_001", 61010)
    cond = _cond(migration_session, exp, "STALE_OLD_NAME", temperature_c=70.0)

    stale = [s for s in find_stale_strings(migration_session) if s.conditions_id == cond.id]
    assert len(stale) == 1
    assert stale[0].current == "STALE_OLD_NAME"
    assert stale[0].correct == "STALE_001"

    assert backfill_strings(migration_session) >= 1
    migration_session.refresh(cond)
    assert cond.experiment_id == "STALE_001"


def test_backfill_leaves_a_correct_string_alone(migration_session):
    exp = _exp(migration_session, "STALE_002", 61011)
    cond = _cond(migration_session, exp, "STALE_002", temperature_c=70.0)
    assert [s for s in find_stale_strings(migration_session) if s.conditions_id == cond.id] == []
