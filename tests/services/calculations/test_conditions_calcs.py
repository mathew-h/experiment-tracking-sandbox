import types
import pytest
from unittest.mock import MagicMock
from backend.services.calculations import conditions_calcs  # noqa: F401 — triggers register
from backend.services.calculations.conditions_calcs import recalculate_conditions


def make_conditions(**kwargs):
    """Minimal ExperimentalConditions-like namespace."""
    defaults = {
        "experiment_fk": None,
        "water_volume_mL": None,
        "rock_mass_g": None,
        "water_to_rock_ratio": None,
        "total_ferrous_iron_g": None,
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def make_session(experiment_sample_id=None, feo_wt_pct=None):
    """Mock session. get() returns a stub Experiment; execute() returns feo_wt_pct."""
    session = MagicMock()
    if experiment_sample_id is not None:
        exp_stub = types.SimpleNamespace(sample_id=experiment_sample_id)
        session.get.return_value = exp_stub
    else:
        session.get.return_value = None
    session.execute.return_value.scalar_one_or_none.return_value = feo_wt_pct
    return session


def test_water_to_rock_ratio_computed():
    cond = make_conditions(water_volume_mL=500.0, rock_mass_g=10.0)
    recalculate_conditions(cond, make_session())
    assert cond.water_to_rock_ratio == pytest.approx(50.0)


def test_water_to_rock_ratio_zero_rock_mass_is_none():
    cond = make_conditions(water_volume_mL=500.0, rock_mass_g=0.0)
    recalculate_conditions(cond, make_session())
    assert cond.water_to_rock_ratio is None


def test_water_to_rock_ratio_missing_volume_is_none():
    cond = make_conditions(water_volume_mL=None, rock_mass_g=10.0)
    recalculate_conditions(cond, make_session())
    assert cond.water_to_rock_ratio is None


def test_water_to_rock_ratio_missing_rock_mass_is_none():
    cond = make_conditions(water_volume_mL=500.0, rock_mass_g=None)
    recalculate_conditions(cond, make_session())
    assert cond.water_to_rock_ratio is None


def test_total_ferrous_iron_g_computed():
    """Full happy path: sample has FeO → field is populated."""
    cond = make_conditions(experiment_fk=1, rock_mass_g=5.0)
    session = make_session(experiment_sample_id="SAMPLE-001", feo_wt_pct=10.0)
    recalculate_conditions(cond, session)
    assert cond.total_ferrous_iron_g == pytest.approx(0.38866, rel=1e-3)


def test_total_ferrous_iron_g_no_sample_on_experiment():
    """Experiment exists but has no sample_id → field is None."""
    session = MagicMock()
    session.get.return_value = types.SimpleNamespace(sample_id=None)
    session.execute.return_value.scalar_one_or_none.return_value = None
    cond = make_conditions(experiment_fk=1, rock_mass_g=5.0)
    recalculate_conditions(cond, session)
    assert cond.total_ferrous_iron_g is None


def test_total_ferrous_iron_g_experiment_not_found():
    """No Experiment row in DB → field is None."""
    cond = make_conditions(experiment_fk=99, rock_mass_g=5.0)
    session = make_session(experiment_sample_id=None, feo_wt_pct=None)
    recalculate_conditions(cond, session)
    assert cond.total_ferrous_iron_g is None


def test_total_ferrous_iron_g_no_feo_analysis():
    """Sample exists but has no FeO ElementalAnalysis → field is None."""
    cond = make_conditions(experiment_fk=1, rock_mass_g=5.0)
    session = make_session(experiment_sample_id="SAMPLE-001", feo_wt_pct=None)
    recalculate_conditions(cond, session)
    assert cond.total_ferrous_iron_g is None
