import types
import pytest
from backend.services.calculations import conditions_calcs  # noqa: F401 — triggers register
from backend.services.calculations.conditions_calcs import recalculate_conditions


def make_conditions(**kwargs):
    """Minimal ExperimentalConditions-like object."""
    defaults = {
        'water_volume_mL': None,
        'rock_mass_g': None,
        'water_to_rock_ratio': None,
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


SESSION = types.SimpleNamespace()


def test_water_to_rock_ratio_computed():
    """Standard case: ratio = water_volume_mL / rock_mass_g."""
    cond = make_conditions(water_volume_mL=500.0, rock_mass_g=10.0)
    recalculate_conditions(cond, SESSION)
    assert cond.water_to_rock_ratio == pytest.approx(50.0)


def test_water_to_rock_ratio_zero_rock_mass_is_none():
    """Zero rock mass must not produce divide-by-zero — result is None."""
    cond = make_conditions(water_volume_mL=500.0, rock_mass_g=0.0)
    recalculate_conditions(cond, SESSION)
    assert cond.water_to_rock_ratio is None


def test_water_to_rock_ratio_missing_volume_is_none():
    """Missing water volume → ratio is None."""
    cond = make_conditions(water_volume_mL=None, rock_mass_g=10.0)
    recalculate_conditions(cond, SESSION)
    assert cond.water_to_rock_ratio is None


def test_water_to_rock_ratio_missing_rock_mass_is_none():
    """Missing rock mass → ratio is None."""
    cond = make_conditions(water_volume_mL=500.0, rock_mass_g=None)
    recalculate_conditions(cond, SESSION)
    assert cond.water_to_rock_ratio is None
