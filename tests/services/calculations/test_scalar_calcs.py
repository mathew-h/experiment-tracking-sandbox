import types
import pytest
from backend.services.calculations import scalar_calcs  # noqa: F401
from backend.services.calculations.scalar_calcs import recalculate_scalar


SESSION = types.SimpleNamespace()

# Physical constants used in H2 calculation (PV=nRT at 20°C)
R = 0.082057   # L·atm/(mol·K)
T_K = 293.15   # 20°C
MPa_TO_ATM = 9.86923
H2_MOLAR_MASS = 2.01588  # g/mol


def make_result_chain(rock_mass_g=10.0, water_volume_mL=100.0):
    """Build a minimal result → experiment → conditions chain."""
    conditions = types.SimpleNamespace(rock_mass_g=rock_mass_g, water_volume_mL=water_volume_mL)
    experiment = types.SimpleNamespace(conditions=conditions)
    result_entry = types.SimpleNamespace(experiment=experiment)
    return result_entry


def make_scalar(**kwargs):
    defaults = {
        'result_entry': make_result_chain(),
        'h2_concentration': None,
        'h2_concentration_unit': 'ppm',
        'gas_sampling_volume_ml': None,
        'gas_sampling_pressure_MPa': None,
        'gross_ammonium_concentration_mM': None,
        'background_ammonium_concentration_mM': None,
        'sampling_volume_mL': None,
        'h2_micromoles': None,
        'h2_mass_ug': None,
        'grams_per_ton_yield': None,
        'h2_grams_per_ton_yield': None,
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


# --- H2 tests ---

def test_h2_calculation_regression():
    """Regression: known inputs produce expected µmol and µg.

    100 ppm H2 in 10 mL headspace at 0.1 MPa, 20°C.
    P_atm = 0.1 * 9.86923 = 0.986923
    V_L   = 10 / 1000 = 0.01
    n_total = PV/RT = (0.986923 * 0.01) / (0.082057 * 293.15)
    fraction = 100 / 1e6 = 1e-4
    h2_mol = n_total * fraction
    """
    s = make_scalar(
        h2_concentration=100.0,
        gas_sampling_volume_ml=10.0,
        gas_sampling_pressure_MPa=0.1,
    )
    recalculate_scalar(s, SESSION)

    P_atm = 0.1 * MPa_TO_ATM
    V_L = 0.01
    n_total = (P_atm * V_L) / (R * T_K)
    fraction = 100.0 / 1_000_000.0
    h2_mol = n_total * fraction
    expected_umol = h2_mol * 1_000_000.0
    expected_ug = h2_mol * H2_MOLAR_MASS * 1_000_000.0

    assert s.h2_micromoles == pytest.approx(expected_umol, rel=1e-4)
    assert s.h2_mass_ug == pytest.approx(expected_ug, rel=1e-4)


def test_h2_missing_pressure_produces_none():
    """No pressure input → H2 derived fields are None."""
    s = make_scalar(h2_concentration=100.0, gas_sampling_volume_ml=10.0)
    recalculate_scalar(s, SESSION)
    assert s.h2_micromoles is None
    assert s.h2_mass_ug is None


def test_h2_zero_volume_produces_none():
    """Zero gas sampling volume → H2 derived fields are None."""
    s = make_scalar(
        h2_concentration=100.0,
        gas_sampling_volume_ml=0.0,
        gas_sampling_pressure_MPa=0.1,
    )
    recalculate_scalar(s, SESSION)
    assert s.h2_micromoles is None


def test_h2_negative_concentration_produces_none():
    """Negative H2 concentration (invalid input) → derived fields are None."""
    s = make_scalar(
        h2_concentration=-10.0,
        gas_sampling_volume_ml=10.0,
        gas_sampling_pressure_MPa=0.1,
    )
    recalculate_scalar(s, SESSION)
    assert s.h2_micromoles is None
    assert s.h2_mass_ug is None


def test_h2_none_concentration_produces_none():
    """None H2 concentration → derived fields are None."""
    s = make_scalar(gas_sampling_volume_ml=10.0, gas_sampling_pressure_MPa=0.1)
    recalculate_scalar(s, SESSION)
    assert s.h2_micromoles is None


# --- Ammonium yield tests ---

def test_grams_per_ton_yield_standard():
    """Standard ammonium yield calculation.

    10 mM gross, 0.3 mM background, 100 mL volume, 10 g rock.
    net_conc = 9.7 mM
    mass_NH4 = (9.7/1000) mol/L * 0.1 L * 18.04 g/mol
    yield = 1e6 * mass_NH4 / 10
    """
    s = make_scalar(
        gross_ammonium_concentration_mM=10.0,
        background_ammonium_concentration_mM=0.3,
        sampling_volume_mL=100.0,
        result_entry=make_result_chain(rock_mass_g=10.0),
    )
    recalculate_scalar(s, SESSION)
    net = 10.0 - 0.3
    mass_nh4 = (net / 1000.0) * 0.1 * 18.04
    expected = 1_000_000.0 * mass_nh4 / 10.0
    assert s.grams_per_ton_yield == pytest.approx(expected, rel=1e-4)


def test_background_subtraction_clamps_to_zero():
    """When gross < background, net concentration clamps to 0 → yield = 0."""
    s = make_scalar(
        gross_ammonium_concentration_mM=0.1,
        background_ammonium_concentration_mM=0.3,
        sampling_volume_mL=100.0,
        result_entry=make_result_chain(rock_mass_g=10.0),
    )
    recalculate_scalar(s, SESSION)
    assert s.grams_per_ton_yield == pytest.approx(0.0)


def test_missing_rock_mass_yield_is_none():
    """No rock mass → grams_per_ton_yield is None."""
    s = make_scalar(
        gross_ammonium_concentration_mM=10.0,
        sampling_volume_mL=100.0,
        result_entry=make_result_chain(rock_mass_g=None),
    )
    recalculate_scalar(s, SESSION)
    assert s.grams_per_ton_yield is None


def test_h2_grams_per_ton_yield_computed():
    """h2_grams_per_ton_yield = h2_mass_ug converted to g, then g/ton."""
    s = make_scalar(
        h2_concentration=100.0,
        gas_sampling_volume_ml=10.0,
        gas_sampling_pressure_MPa=0.1,
        result_entry=make_result_chain(rock_mass_g=10.0),
    )
    recalculate_scalar(s, SESSION)
    assert s.h2_mass_ug is not None
    expected = 1_000_000.0 * (s.h2_mass_ug / 1_000_000.0) / 10.0
    assert s.h2_grams_per_ton_yield == pytest.approx(expected, rel=1e-4)
