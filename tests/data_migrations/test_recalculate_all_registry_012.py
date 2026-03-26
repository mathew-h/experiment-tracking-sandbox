"""Tests for database/data_migrations/recalculate_all_registry_012.py

Covers _backfill_conditions:
- water_to_rock_ratio is computed from water_volume_mL / rock_mass_g
- mass_in_grams is computed for each ChemicalAdditive

Uses the PostgreSQL test DB (migration_session fixture from tests/data_migrations/conftest.py)
because model columns use JSONB which is not supported by the SQLite in-memory test_db fixture.

migration_session uses begin_nested() (savepoints) so that when _backfill_conditions calls
db.commit() it only releases the savepoint, not the outer transaction. The outer transaction
is rolled back on teardown, keeping the test DB clean.
"""
import pytest
from sqlalchemy.orm import Session

from database.models import Experiment, ExperimentalConditions
from database.models.chemicals import ChemicalAdditive, Compound
from database.models.enums import AmountUnit
from database.data_migrations.recalculate_all_registry_012 import _backfill_conditions


class TestBackfillConditionsWaterToRockRatio:
    def test_backfill_conditions_computes_water_to_rock_ratio(self, migration_session: Session):
        """_backfill_conditions sets water_to_rock_ratio = water_volume_mL / rock_mass_g."""
        experiment = Experiment(
            experiment_id="BACKFILL_001",
            experiment_number=901,
        )
        migration_session.add(experiment)
        migration_session.flush()

        conditions = ExperimentalConditions(
            experiment_id="BACKFILL_001",
            experiment_fk=experiment.id,
            rock_mass_g=100.0,
            water_volume_mL=500.0,
        )
        migration_session.add(conditions)
        migration_session.flush()

        # Simulate a pre-existing NULL (as would be found before backfill)
        conditions.water_to_rock_ratio = None
        migration_session.flush()

        _backfill_conditions(migration_session)

        migration_session.refresh(conditions)
        assert conditions.water_to_rock_ratio == pytest.approx(5.0)


class TestBackfillConditionsAdditiveMass:
    def test_backfill_conditions_computes_additive_mass(self, migration_session: Session):
        """_backfill_conditions sets mass_in_grams on linked ChemicalAdditives."""
        experiment = Experiment(
            experiment_id="BACKFILL_002",
            experiment_number=902,
        )
        migration_session.add(experiment)
        migration_session.flush()

        conditions = ExperimentalConditions(
            experiment_id="BACKFILL_002",
            experiment_fk=experiment.id,
            rock_mass_g=100.0,
            water_volume_mL=500.0,
        )
        migration_session.add(conditions)
        migration_session.flush()

        compound = Compound(
            name="NaCl_backfill_test",
            formula="NaCl",
            molecular_weight_g_mol=58.44,
        )
        migration_session.add(compound)
        migration_session.flush()

        additive = ChemicalAdditive(
            experiment_id=conditions.id,
            compound_id=compound.id,
            amount=500.0,
            unit=AmountUnit.MILLIGRAM,
        )
        migration_session.add(additive)
        migration_session.flush()

        # Simulate pre-existing NULL
        additive.mass_in_grams = None
        migration_session.flush()

        _backfill_conditions(migration_session)

        migration_session.refresh(additive)
        assert additive.mass_in_grams == pytest.approx(0.5)


def test_backfill_scalars_computes_grams_per_ton_yield(migration_session):
    """_backfill_scalars should populate grams_per_ton_yield from gross ammonium + rock mass."""
    from database.data_migrations.recalculate_all_registry_012 import _backfill_scalars
    from database.models import ExperimentalResults, ScalarResults

    experiment = Experiment(experiment_id="BACKFILL_003", experiment_number=903)
    migration_session.add(experiment)
    migration_session.flush()

    conditions = ExperimentalConditions(
        experiment_id="BACKFILL_003",
        experiment_fk=experiment.id,
        rock_mass_g=100.0,
        water_volume_mL=500.0,
    )
    migration_session.add(conditions)
    migration_session.flush()

    result_entry = ExperimentalResults(
        experiment_fk=experiment.id,
        time_post_reaction_days=7.0,
        time_post_reaction_bucket_days=7,
        description="t=7d",
        is_primary_timepoint_result=True,
    )
    migration_session.add(result_entry)
    migration_session.flush()

    scalar = ScalarResults(
        result_id=result_entry.id,
        gross_ammonium_concentration_mM=10.0,
        background_ammonium_concentration_mM=0.3,
        sampling_volume_mL=100.0,
        grams_per_ton_yield=None,  # simulate pre-existing NULL
    )
    migration_session.add(scalar)
    migration_session.flush()

    _backfill_scalars(migration_session)

    migration_session.refresh(scalar)
    # net = 9.7 mM, vol = 0.1 L → ammonia_mass_g = (9.7/1000) * 0.1 * 18.04 ≈ 0.01750 g
    # yield = 1e6 * 0.01750 / 100 ≈ 174.99 g/t
    assert scalar.grams_per_ton_yield is not None
    assert scalar.grams_per_ton_yield == pytest.approx(174.99, rel=0.01)
