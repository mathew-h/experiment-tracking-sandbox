from backend.api.schemas.experiments import ExperimentCreate, ExperimentResponse
from backend.api.schemas.conditions import ConditionsCreate, ConditionsResponse


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
