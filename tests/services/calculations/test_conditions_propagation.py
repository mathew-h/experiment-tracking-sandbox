"""Test that updating ExperimentalConditions propagates recalculation to linked ScalarResults."""
import types
import unittest.mock

from backend.services.calculations.conditions_calcs import recalculate_conditions


SESSION = types.SimpleNamespace()


def make_propagation_chain(
    rock_mass_g=10.0,
    water_volume_mL=100.0,
    **scalar_fields,
):
    """Build a complete bidirectional chain: conditions ↔ experiment ↔ result ↔ scalar.

    Both the forward path (conditions → experiment → results → scalar_data)
    and the back-reference path (scalar → result_entry → experiment → conditions)
    are wired so recalculate_scalar can resolve total_ferrous_iron_g from the scalar.

    Note: total_ferrous_iron_g is intentionally omitted — recalculate_conditions
    computes and writes it during the test. Control it via the get_analyte_wt_pct mock.
    """
    scalar_defaults = {
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
    scalar_defaults.update(scalar_fields)

    conditions = types.SimpleNamespace(
        water_volume_mL=water_volume_mL,
        rock_mass_g=rock_mass_g,
        water_to_rock_ratio=None,
        # total_ferrous_iron_g is set by recalculate_conditions during the test
    )
    experiment_ns = types.SimpleNamespace(conditions=conditions)
    conditions.experiment = experiment_ns

    scalar = types.SimpleNamespace(**scalar_defaults)
    result_ns = types.SimpleNamespace(experiment=experiment_ns, scalar_data=scalar)
    scalar.result_entry = result_ns
    experiment_ns.results = [result_ns]

    return conditions, scalar


def test_conditions_update_propagates_to_scalar_h2_yield():
    """When total_ferrous_iron_g is computable, linked scalar results are recalculated.

    Verifies recalculate_conditions walks experiment → results → scalar_data
    and calls recalculate_scalar, which sets ferrous_iron_yield_h2_pct.
    """
    conditions, scalar = make_propagation_chain(
        h2_concentration=100.0,
        gas_sampling_volume_ml=10.0,
        gas_sampling_pressure_MPa=0.1,
    )

    with unittest.mock.patch(
        'backend.services.calculations.conditions_calcs.get_analyte_wt_pct',
        return_value=10.0,
    ):
        recalculate_conditions(conditions, SESSION)

    assert scalar.ferrous_iron_yield_h2_pct is not None
    assert scalar.ferrous_iron_yield_h2_pct > 0


def test_conditions_update_propagates_to_scalar_nh3_yield():
    """NH3 yield is also recalculated when conditions change."""
    conditions, scalar = make_propagation_chain(
        gross_ammonium_concentration_mM=10.0,
        background_ammonium_concentration_mM=0.3,
        sampling_volume_mL=100.0,
    )

    with unittest.mock.patch(
        'backend.services.calculations.conditions_calcs.get_analyte_wt_pct',
        return_value=10.0,
    ):
        recalculate_conditions(conditions, SESSION)

    assert scalar.ferrous_iron_yield_nh3_pct is not None
    assert scalar.ferrous_iron_yield_nh3_pct > 0


def test_conditions_no_experiment_does_not_crash():
    """Conditions with no linked experiment must not raise."""
    conditions = types.SimpleNamespace(
        water_volume_mL=100.0,
        rock_mass_g=10.0,
        water_to_rock_ratio=None,
        total_ferrous_iron_g=1.0,
        experiment=None,
    )
    recalculate_conditions(conditions, SESSION)  # Must not raise


def test_conditions_result_with_no_scalar_skipped():
    """Results with no scalar_data are silently skipped."""
    conditions = types.SimpleNamespace(
        water_volume_mL=100.0,
        rock_mass_g=10.0,
        water_to_rock_ratio=None,
        total_ferrous_iron_g=1.0,
    )
    experiment_ns = types.SimpleNamespace(conditions=conditions, results=[
        types.SimpleNamespace(scalar_data=None),
    ])
    conditions.experiment = experiment_ns
    recalculate_conditions(conditions, SESSION)  # Must not raise
