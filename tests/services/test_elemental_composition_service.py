# tests/services/test_elemental_composition_service.py
import pytest
from unittest.mock import MagicMock
from backend.services.elemental_composition_service import (
    calculate_total_ferrous_iron_g,
    FE_IN_FEO_FRACTION,
    get_analyte_wt_pct,
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


def _mock_session(scalar_result):
    """Return a session mock whose execute().scalar_one_or_none() returns scalar_result."""
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = scalar_result
    return session


def test_get_analyte_wt_pct_happy_path():
    """Returns analyte_composition when a matching row exists."""
    session = _mock_session(12.5)
    result = get_analyte_wt_pct(sample_id="SAMPLE-001", db=session)
    assert result == 12.5


def test_get_analyte_wt_pct_missing_analyte_returns_none():
    """Returns None when no matching ElementalAnalysis row exists."""
    session = _mock_session(None)
    result = get_analyte_wt_pct(sample_id="SAMPLE-NO-FEO", db=session)
    assert result is None


def test_get_analyte_wt_pct_none_sample_id_returns_none():
    """Skips the DB query entirely when sample_id is None."""
    session = MagicMock()
    result = get_analyte_wt_pct(sample_id=None, db=session)
    assert result is None
    session.execute.assert_not_called()


def test_get_analyte_wt_pct_custom_analyte_symbol():
    """analyte_symbol parameter is forwarded to the query."""
    session = _mock_session(45.0)
    result = get_analyte_wt_pct(sample_id="SAMPLE-001", db=session, analyte_symbol="SiO2")
    assert result == 45.0
    session.execute.assert_called_once()
