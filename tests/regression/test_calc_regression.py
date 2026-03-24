"""Calculation regression tests — verify derived fields for known inputs.

The calc engine works by mutating ORM instances in place.  Tests create
lightweight mock objects with the required attributes and verify the
mutated values after calling the registry functions directly.
No database connection required.
"""
from __future__ import annotations

import pytest
from types import SimpleNamespace


# ── Water : Rock Ratio ──────────────────────────────────────────────────────

def test_water_to_rock_ratio_normal():
    """water_volume_mL=100, rock_mass_g=10 → water_to_rock_ratio=10.0"""
    from backend.services.calculations.conditions_calcs import recalculate_conditions
    instance = SimpleNamespace(
        water_volume_mL=100.0,
        rock_mass_g=10.0,
        water_to_rock_ratio=None,
        chemical_additives=[],
        formatted_additives=None,
    )
    recalculate_conditions(instance, session=None)
    assert instance.water_to_rock_ratio == pytest.approx(10.0)


def test_water_to_rock_ratio_zero_rock():
    """rock_mass_g=0 → water_to_rock_ratio=None (guard against division by zero)"""
    from backend.services.calculations.conditions_calcs import recalculate_conditions
    instance = SimpleNamespace(
        water_volume_mL=100.0,
        rock_mass_g=0.0,
        water_to_rock_ratio=None,
        chemical_additives=[],
        formatted_additives=None,
    )
    recalculate_conditions(instance, session=None)
    assert instance.water_to_rock_ratio is None


def test_water_to_rock_ratio_none_inputs():
    """Both None → water_to_rock_ratio=None"""
    from backend.services.calculations.conditions_calcs import recalculate_conditions
    instance = SimpleNamespace(
        water_volume_mL=None,
        rock_mass_g=None,
        water_to_rock_ratio=None,
        chemical_additives=[],
        formatted_additives=None,
    )
    recalculate_conditions(instance, session=None)
    assert instance.water_to_rock_ratio is None


# ── H2 Micromoles (PV = nRT at 20 °C) ─────────────────────────────────────

def test_h2_micromoles_known_value():
    """
    h2=100 ppm, gas_vol=10 mL, pressure=0.1 MPa at 20 °C

    P_atm  = 0.1 × 9.86923  = 0.986923 atm
    V_L    = 10 / 1000       = 0.01 L
    n_total = (0.986923 × 0.01) / (0.082057 × 293.15)  ≈ 4.104 × 10⁻⁴ mol
    h2_mol  = 4.104e-4 × (100 / 1e6)                   ≈ 4.104 × 10⁻⁸ mol
    µmol    = 4.104e-8 × 1e6                            ≈ 0.04104 µmol
    """
    from backend.services.calculations.scalar_calcs import _calculate_hydrogen
    instance = SimpleNamespace(
        h2_concentration=100.0,
        gas_sampling_volume_ml=10.0,
        gas_sampling_pressure_MPa=0.1,
        h2_micromoles=None,
        h2_mass_ug=None,
    )
    _calculate_hydrogen(instance)
    assert instance.h2_micromoles == pytest.approx(0.04104, rel=0.01)


def test_h2_micromoles_none_when_missing_volume():
    """Missing gas_sampling_volume_ml → h2_micromoles=None"""
    from backend.services.calculations.scalar_calcs import _calculate_hydrogen
    instance = SimpleNamespace(
        h2_concentration=100.0,
        gas_sampling_volume_ml=None,
        gas_sampling_pressure_MPa=0.1,
        h2_micromoles=None,
        h2_mass_ug=None,
    )
    _calculate_hydrogen(instance)
    assert instance.h2_micromoles is None


def test_h2_micromoles_none_when_zero_pressure():
    """pressure=0 → h2_micromoles=None (guard against non-physical inputs)"""
    from backend.services.calculations.scalar_calcs import _calculate_hydrogen
    instance = SimpleNamespace(
        h2_concentration=100.0,
        gas_sampling_volume_ml=10.0,
        gas_sampling_pressure_MPa=0.0,
        h2_micromoles=None,
        h2_mass_ug=None,
    )
    _calculate_hydrogen(instance)
    assert instance.h2_micromoles is None
