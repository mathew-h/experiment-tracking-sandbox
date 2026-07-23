"""Service tests for create_replicate_experiments (issue #70 P2)."""
import pytest

from database.lineage_utils import create_replicate_experiments
from database.models import (
    ChemicalAdditive, Compound, Experiment, ExperimentalConditions,
)
from database.models.enums import AmountUnit, ExperimentStatus


def _make_parent(db, experiment_id="CRS_001", number=9800, with_additive=True):
    parent = Experiment(experiment_id=experiment_id, experiment_number=number,
                        status=ExperimentStatus.ONGOING, researcher="MH",
                        sample_id=None)
    db.add(parent)
    db.flush()
    cond = ExperimentalConditions(
        experiment_id=parent.experiment_id, experiment_fk=parent.id,
        experiment_type="Serum", rock_mass_g=10.0, water_volume_mL=50.0,
        temperature_c=90.0,
    )
    db.add(cond)
    db.flush()
    if with_additive:
        compound = Compound(name=f"NiCl2-{number}", formula="NiCl2")
        db.add(compound)
        db.flush()
        db.add(ChemicalAdditive(experiment_id=cond.id, compound_id=compound.id,
                                amount=5.0, unit=AmountUnit.MILLIGRAM))
        db.flush()
    return parent


class TestCreateReplicateExperiments:
    def test_creates_linked_replicates_with_conditions_and_additives(self, test_db):
        parent = _make_parent(test_db)
        created, skipped = create_replicate_experiments(test_db, "CRS_001", count=3)
        test_db.flush()
        assert skipped == []
        assert [e.experiment_id for e in created] == ["CRS_001a", "CRS_001b", "CRS_001c"]
        for e in created:
            assert e.parent_experiment_fk == parent.id
            assert e.base_experiment_id == "CRS_001"
            assert e.replicate_label in ("a", "b", "c")
            assert e.status == ExperimentStatus.ONGOING
            assert e.researcher == "MH"
            assert e.conditions is not None
            assert e.conditions.rock_mass_g == 10.0
            assert e.conditions.temperature_c == 90.0
            additives = e.conditions.chemical_additives
            assert len(additives) == 1
            assert additives[0].amount == 5.0
            assert additives[0].unit == AmountUnit.MILLIGRAM
            # Copied additive must be a new row, not the parent's
            assert additives[0].id != parent.conditions.chemical_additives[0].id

    def test_letters_continue_after_existing_members(self, test_db):
        _make_parent(test_db, "CRS_002", 9810)
        test_db.add(Experiment(experiment_id="CRS_002a", experiment_number=9811,
                               status=ExperimentStatus.ONGOING))
        test_db.flush()
        created, skipped = create_replicate_experiments(test_db, "CRS_002", count=2)
        assert [e.experiment_id for e in created] == ["CRS_002b", "CRS_002c"]
        assert skipped == []

    def test_missing_parent_raises_lookup_error(self, test_db):
        with pytest.raises(LookupError):
            create_replicate_experiments(test_db, "CRS_MISSING_001", count=3)

    def test_lettered_input_resolves_to_stem(self, test_db):
        _make_parent(test_db, "CRS_003", 9820)
        created, _ = create_replicate_experiments(test_db, "CRS_003a", count=1)
        # Passing a lettered ID targets the same group: next free letter is "a"
        assert [e.experiment_id for e in created] == ["CRS_003a"]

    def test_parent_without_conditions_still_creates_experiments(self, test_db):
        exp = Experiment(experiment_id="CRS_004", experiment_number=9830,
                         status=ExperimentStatus.ONGOING)
        test_db.add(exp)
        test_db.flush()
        created, skipped = create_replicate_experiments(test_db, "CRS_004", count=2)
        assert len(created) == 2
        assert all(e.conditions is None for e in created)
        assert skipped == []
