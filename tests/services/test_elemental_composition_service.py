# tests/services/test_elemental_composition_service.py
import pytest
from backend.services.elemental_composition_service import (
    calculate_total_ferrous_iron_g,
    FE_IN_FEO_FRACTION,
)


def test_constant_value():
    """FE_IN_FEO_FRACTION must equal 55.845 / 71.844."""
    assert FE_IN_FEO_FRACTION == pytest.approx(55.845 / 71.844)


def test_known_numeric_result():
    """(10.0 / 100) * FE_IN_FEO_FRACTION * 5.0 ≈ 0.38866 g."""
    result = calculate_total_ferrous_iron_g(feo_wt_pct=10.0, rock_mass_g=5.0)
    assert result == pytest.approx(0.38866, rel=1e-3)


def test_none_feo_returns_none():
    assert calculate_total_ferrous_iron_g(feo_wt_pct=None, rock_mass_g=5.0) is None


def test_none_rock_mass_returns_none():
    assert calculate_total_ferrous_iron_g(feo_wt_pct=10.0, rock_mass_g=None) is None


def test_zero_rock_mass_returns_none():
    assert calculate_total_ferrous_iron_g(feo_wt_pct=10.0, rock_mass_g=0) is None


def test_negative_rock_mass_returns_none():
    assert calculate_total_ferrous_iron_g(feo_wt_pct=10.0, rock_mass_g=-1.0) is None


def test_zero_feo_returns_zero():
    """0.0 wt% FeO → 0.0 g (not None)."""
    result = calculate_total_ferrous_iron_g(feo_wt_pct=0.0, rock_mass_g=5.0)
    assert result == pytest.approx(0.0)
