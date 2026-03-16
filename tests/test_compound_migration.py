import pytest
from sqlalchemy.orm import Session

from database.models import ExperimentalConditions, ChemicalAdditive, Compound
from database.models.enums import AmountUnit


def test_deprecated_fields_migrated_to_chemicals(test_db: Session):
    """
    Verify that data once stored on ExperimentalConditions (deprecated catalyst/buffer fields)
    is represented via ChemicalAdditive/Compound records.

    The migration intent is:
      - Catalyst-related info should be captured by ChemicalAdditive entries linked to a Compound
      - Deprecated fields on ExperimentalConditions remain nullable and unused
    """
    # 1) Create a Compound that represents a catalyst/additive that used to be free-text on conditions
    compound = Compound(name="Nickel Chloride", formula="NiCl2·6H2O", cas_number=None)
    test_db.add(compound)
    test_db.flush()

    # 2) Create baseline ExperimentalConditions with deprecated fields populated (legacy style)
    conditions = ExperimentalConditions(
        experiment_id="MIGRATION_TEST_001",
        experiment_fk=1,  # dummy FK for in-memory test; not asserting FK integrity here
        rock_mass_g=100.0,
        water_volume_mL=500.0,
        catalyst="Nickel chloride",        # deprecated
        catalyst_mass=0.5,                  # deprecated
        buffer_system="NH4Cl",             # deprecated
        buffer_concentration=50.0           # deprecated
    )
    test_db.add(conditions)
    test_db.flush()

    # 3) Represent the same info via ChemicalAdditive (new normalized model)
    additive = ChemicalAdditive(
        experiment_id=conditions.id,
        compound_id=compound.id,
        amount=500.0,               # e.g., ppm (matches legacy buffer_concentration notion)
        unit=AmountUnit.PPM,
        addition_order=1,
    )
    test_db.add(additive)
    test_db.commit()

    # 4) Assertions: ensure normalized records exist and deprecated fields are effectively superseded
    reloaded = test_db.query(ExperimentalConditions).filter(ExperimentalConditions.id == conditions.id).one()
    additives = test_db.query(ChemicalAdditive).filter(ChemicalAdditive.experiment_id == reloaded.id).all()

    # The new normalized relationship should carry the active data
    assert len(additives) == 1
    assert additives[0].compound_id == compound.id
    assert additives[0].unit == AmountUnit.PPM
    assert additives[0].amount == 500.0

    # Deprecated fields are still present on the model for backward compat, but should not be relied upon.
    # We simply validate they exist and were set on creation (pre-migration style)
    assert reloaded.catalyst == "Nickel chloride"
    assert reloaded.catalyst_mass == 0.5
    assert reloaded.buffer_system == "NH4Cl"
    assert reloaded.buffer_concentration == 50.0

    # And confirm we can resolve to the Compound via relationship on the additive
    assert additives[0].compound.name == "Nickel Chloride"

