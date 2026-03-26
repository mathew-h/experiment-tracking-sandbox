"""Tests for database/data_migrations/recalculate_all_registry_012.py

Covers _backfill_conditions:
- water_to_rock_ratio is computed from water_volume_mL / rock_mass_g
- mass_in_grams is computed for each ChemicalAdditive

Uses the PostgreSQL test DB (db_session fixture from tests/api/conftest.py) because
model columns use JSONB which is not supported by the SQLite in-memory test_db fixture.
"""
import pytest
from sqlalchemy.orm import Session

from database.models import Experiment, ExperimentalConditions
from database.models.chemicals import ChemicalAdditive, Compound
from database.models.enums import AmountUnit
from database.data_migrations.recalculate_all_registry_012 import _backfill_conditions

# Pull in PostgreSQL fixtures from tests/api/conftest.py
from tests.api.conftest import db_session, create_test_tables  # noqa: F401


class TestBackfillConditionsWaterToRockRatio:
    def test_backfill_conditions_computes_water_to_rock_ratio(self, db_session: Session):
        """_backfill_conditions sets water_to_rock_ratio = water_volume_mL / rock_mass_g."""
        experiment = Experiment(
            experiment_id="BACKFILL_001",
            experiment_number=901,
        )
        db_session.add(experiment)
        db_session.flush()

        conditions = ExperimentalConditions(
            experiment_id="BACKFILL_001",
            experiment_fk=experiment.id,
            rock_mass_g=100.0,
            water_volume_mL=500.0,
        )
        db_session.add(conditions)
        db_session.flush()

        # Simulate a pre-existing NULL (as would be found before backfill)
        conditions.water_to_rock_ratio = None
        db_session.flush()

        _backfill_conditions(db_session)

        db_session.refresh(conditions)
        assert conditions.water_to_rock_ratio == pytest.approx(5.0)


class TestBackfillConditionsAdditiveMass:
    def test_backfill_conditions_computes_additive_mass(self, db_session: Session):
        """_backfill_conditions sets mass_in_grams on linked ChemicalAdditives."""
        experiment = Experiment(
            experiment_id="BACKFILL_002",
            experiment_number=902,
        )
        db_session.add(experiment)
        db_session.flush()

        conditions = ExperimentalConditions(
            experiment_id="BACKFILL_002",
            experiment_fk=experiment.id,
            rock_mass_g=100.0,
            water_volume_mL=500.0,
        )
        db_session.add(conditions)
        db_session.flush()

        compound = Compound(
            name="NaCl_backfill_test",
            formula="NaCl",
            molecular_weight_g_mol=58.44,
        )
        db_session.add(compound)
        db_session.flush()

        additive = ChemicalAdditive(
            experiment_id=conditions.id,
            compound_id=compound.id,
            amount=500.0,
            unit=AmountUnit.MILLIGRAM,
        )
        db_session.add(additive)
        db_session.flush()

        # Simulate pre-existing NULL
        additive.mass_in_grams = None
        db_session.flush()

        _backfill_conditions(db_session)

        db_session.refresh(additive)
        assert additive.mass_in_grams == pytest.approx(0.5)
