from backend.api.schemas.experiments import ExperimentCreate, ExperimentResponse
from backend.api.schemas.conditions import ConditionsCreate, ConditionsResponse
from backend.api.schemas.results import ScalarCreate, ResultResponse
from backend.api.schemas.chemicals import CompoundResponse, AdditiveCreate


def test_experiment_create_requires_experiment_id():
    from pydantic import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        ExperimentCreate()  # missing experiment_id


def test_experiment_create_valid():
    e = ExperimentCreate(experiment_id="Serum_MH_001", experiment_number=1)
    assert e.experiment_id == "Serum_MH_001"


def test_conditions_create_valid():
    c = ConditionsCreate(experiment_fk=1, experiment_id="Serum_MH_001")
    assert c.experiment_fk == 1


def test_scalar_create_valid():
    s = ScalarCreate(result_id=1, final_ph=7.2)
    assert s.final_ph == 7.2


def test_compound_response_from_orm():
    from types import SimpleNamespace
    obj = SimpleNamespace(id=1, name="NaCl", formula="NaCl", cas_number=None,
                          molecular_weight_g_mol=58.44, created_at=None, updated_at=None,
                          preferred_unit=None, catalyst_formula=None, elemental_fraction=None,
                          density_g_cm3=None, supplier=None, notes=None,
                          melting_point_c=None, boiling_point_c=None, solubility=None,
                          hazard_class=None, catalog_number=None)
    r = CompoundResponse.model_validate(obj)
    assert r.name == "NaCl"
