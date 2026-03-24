"""Test that updating ExperimentalConditions propagates recalculation to linked ScalarResults."""
import types
import pytest

from backend.services.calculations.conditions_calcs import recalculate_conditions


SESSION = types.SimpleNamespace()


def make_scalar_ns(**kwargs):
    defaults = {
        'h2_concentration': None,
        'gas_sampling_volume_ml': None,
        'gas_sampling_pressure_MPa': None,
        'gross_ammonium_concentration_mM': None,
        'background_ammonium_concentration_mM': None,
        'sampling_volume_mL': None,
        'h2_micromoles': None,
        'h2_mass_ug': None,
        'grams_per_ton_yield': None,
        'h2_grams_per_ton_yield': None,
        'ferrous_iron_yield_h2_pct': None,
        'ferrous_iron_yield_nh3_pct': None,
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def test_conditions_update_propagates_to_scalar_h2_yield():
    """When total_ferrous_iron is set on conditions, linked scalar results are recalculated.

    Verifies that recalculate_conditions walks experiment → results → scalar_data
    and calls recalculate_scalar on each scalar, which sets ferrous_iron_yield_h2_pct.
    """
    scalar = make_scalar_ns(
        h2_concentration=100.0,
        gas_sampling_volume_ml=10.0,
        gas_sampling_pressure_MPa=0.1,
    )
    result_ns = types.SimpleNamespace(scalar_data=scalar)
    experiment_ns = types.SimpleNamespace(results=[result_ns])
    conditions = types.SimpleNamespace(
        water_volume_mL=100.0,
        rock_mass_g=10.0,
        water_to_rock_ratio=None,
        total_ferrous_iron=1.0,
        experiment=experiment_ns,
    )

    recalculate_conditions(conditions, SESSION)

    assert scalar.ferrous_iron_yield_h2_pct is not None
    assert scalar.ferrous_iron_yield_h2_pct > 0


def test_conditions_update_propagates_to_scalar_nh3_yield():
    """NH3 yield is also recalculated when conditions change."""
    scalar = make_scalar_ns(
        gross_ammonium_concentration_mM=10.0,
        background_ammonium_concentration_mM=0.3,
        sampling_volume_mL=100.0,
    )
    result_ns = types.SimpleNamespace(scalar_data=scalar)
    experiment_ns = types.SimpleNamespace(results=[result_ns])
    conditions = types.SimpleNamespace(
        water_volume_mL=100.0,
        rock_mass_g=10.0,
        water_to_rock_ratio=None,
        total_ferrous_iron=1.0,
        experiment=experiment_ns,
    )

    recalculate_conditions(conditions, SESSION)

    assert scalar.ferrous_iron_yield_nh3_pct is not None
    assert scalar.ferrous_iron_yield_nh3_pct > 0


def test_conditions_no_experiment_does_not_crash():
    """Conditions with no linked experiment must not raise."""
    conditions = types.SimpleNamespace(
        water_volume_mL=100.0,
        rock_mass_g=10.0,
        water_to_rock_ratio=None,
        total_ferrous_iron=1.0,
        experiment=None,
    )
    recalculate_conditions(conditions, SESSION)  # Must not raise


def test_conditions_result_with_no_scalar_skipped():
    """Results with no scalar_data are silently skipped."""
    result_ns = types.SimpleNamespace(scalar_data=None)
    experiment_ns = types.SimpleNamespace(results=[result_ns])
    conditions = types.SimpleNamespace(
        water_volume_mL=100.0,
        rock_mass_g=10.0,
        water_to_rock_ratio=None,
        total_ferrous_iron=1.0,
        experiment=experiment_ns,
    )
    recalculate_conditions(conditions, SESSION)  # Must not raise
