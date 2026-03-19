from datetime import datetime
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


# --- M5 schema tests ---

def test_experiment_list_item_has_additives_summary():
    from backend.api.schemas.experiments import ExperimentListItem
    item = ExperimentListItem(
        id=1, experiment_id="X", experiment_number=1,
        status="ONGOING", created_at=datetime.now(),
        additives_summary=None, condition_note=None,
        experiment_type=None, reactor_number=None,
    )
    assert item.additives_summary is None


def test_experiment_create_no_number_required():
    from backend.api.schemas.experiments import ExperimentCreate
    payload = ExperimentCreate(experiment_id="TEST_001", status="ONGOING")
    assert payload.experiment_number is None


def test_experiment_status_update():
    from backend.api.schemas.experiments import ExperimentStatusUpdate
    from database.models.enums import ExperimentStatus
    u = ExperimentStatusUpdate(status="COMPLETED")
    assert u.status == ExperimentStatus.COMPLETED


def test_next_id_response():
    from backend.api.schemas.experiments import NextIdResponse
    r = NextIdResponse(next_id="HPHT_003")
    assert r.next_id == "HPHT_003"


def test_conditions_update_has_all_fields():
    from backend.api.schemas.conditions import ConditionsUpdate
    u = ConditionsUpdate(
        particle_size="<75um",
        room_temp_pressure_psi=100.0,
        rxn_temp_pressure_psi=200.0,
        initial_conductivity_mS_cm=1.5,
        confining_pressure=500.0,
        pore_pressure=200.0,
        core_height_cm=5.0,
        core_width_cm=3.0,
    )
    assert u.confining_pressure == 500.0


def test_result_with_flags_response():
    from backend.api.schemas.results import ResultWithFlagsResponse
    r = ResultWithFlagsResponse(
        id=1, experiment_fk=1,
        time_post_reaction_days=7.0,
        time_post_reaction_bucket_days=7.0,
        cumulative_time_post_reaction_days=7.0,
        is_primary_timepoint_result=True,
        description="T7",
        created_at=datetime.now(),
        has_scalar=True, has_icp=False,
        grams_per_ton_yield=50.0, h2_grams_per_ton_yield=None, final_ph=7.2,
    )
    assert r.has_scalar is True


# --- end M5 schema tests ---

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
