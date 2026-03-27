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


def make_result_chain(rock_mass_g=10.0, water_volume_mL=100.0, total_ferrous_iron=None):
    """Build a minimal result → experiment → conditions chain."""
    conditions = types.SimpleNamespace(
        rock_mass_g=rock_mass_g,
        water_volume_mL=water_volume_mL,
        total_ferrous_iron=total_ferrous_iron,
    )
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
        'ferrous_iron_yield_h2_pct': None,
        'ferrous_iron_yield_nh3_pct': None,
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


# --- Ferrous Iron Yield — H2 tests ---


def test_ferrous_iron_yield_h2_regression():
    """Regression: 1,000 µmol H2 with 1.0 g total_ferrous_iron → 16.75%.

    Fe2+_consumed_g = (1000 * 3 / 1e6) * 55.845 = 0.167535
    yield = (0.167535 / 1.0) * 100 = 16.7535%
    """
    from backend.services.calculations.scalar_calcs import calculate_ferrous_iron_yield_h2
    result = calculate_ferrous_iron_yield_h2(
        h2_micromoles=1000.0,
        total_ferrous_iron_g=1.0,
    )
    assert result == pytest.approx(16.7535, rel=1e-4)


def test_ferrous_iron_yield_h2_none_when_no_h2():
    from backend.services.calculations.scalar_calcs import calculate_ferrous_iron_yield_h2
    result = calculate_ferrous_iron_yield_h2(
        h2_micromoles=None,
        total_ferrous_iron_g=1.0,
    )
    assert result is None


def test_ferrous_iron_yield_h2_none_when_no_total_fe():
    from backend.services.calculations.scalar_calcs import calculate_ferrous_iron_yield_h2
    result = calculate_ferrous_iron_yield_h2(
        h2_micromoles=1000.0,
        total_ferrous_iron_g=None,
    )
    assert result is None


def test_ferrous_iron_yield_h2_none_when_total_fe_zero():
    from backend.services.calculations.scalar_calcs import calculate_ferrous_iron_yield_h2
    result = calculate_ferrous_iron_yield_h2(
        h2_micromoles=1000.0,
        total_ferrous_iron_g=0.0,
    )
    assert result is None


def test_ferrous_iron_yield_h2_none_when_total_fe_negative():
    from backend.services.calculations.scalar_calcs import calculate_ferrous_iron_yield_h2
    result = calculate_ferrous_iron_yield_h2(
        h2_micromoles=1000.0,
        total_ferrous_iron_g=-0.5,
    )
    assert result is None


# --- Ferrous Iron Yield — NH3 tests ---


def test_ferrous_iron_yield_nh3_regression():
    """Regression: 10 mM gross ammonium (0.3 mM bg), 100 mL volume, 1.0 g total_ferrous_iron → ≈24.38%.

    net_mM = 10.0 - 0.3 = 9.7
    total_NH3_mol = (9.7 / 1000) * (100 / 1000) = 0.00097
    Fe2+_consumed_g = 0.00097 * 4.5 * 55.845 = 0.24375... g
    yield = (0.24375 / 1.0) * 100 ≈ 24.38%
    """
    from backend.services.calculations.scalar_calcs import calculate_ferrous_iron_yield_nh3
    result = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=10.0,
        background_ammonium_mM=0.3,
        solution_volume_mL=100.0,
        total_ferrous_iron_g=1.0,
    )
    # (9.7/1000) * 0.1 * 4.5 * 55.845 / 1.0 * 100
    expected = (9.7 / 1000.0) * (100.0 / 1000.0) * 4.5 * 55.845 / 1.0 * 100
    assert result == pytest.approx(expected, rel=1e-4)


def test_ferrous_iron_yield_nh3_default_background():
    """When background is None, defaults to 0.2 mM — same result as explicit 0.2 mM."""
    from backend.services.calculations.scalar_calcs import calculate_ferrous_iron_yield_nh3
    result_explicit = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=10.0,
        background_ammonium_mM=0.2,
        solution_volume_mL=100.0,
        total_ferrous_iron_g=1.0,
    )
    result_default = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=10.0,
        background_ammonium_mM=None,
        solution_volume_mL=100.0,
        total_ferrous_iron_g=1.0,
    )
    assert result_explicit == pytest.approx(result_default, rel=1e-6)


def test_ferrous_iron_yield_nh3_background_exceeds_gross_clamps_to_zero():
    """gross < background → net = 0 → yield = 0.0 (not None)."""
    from backend.services.calculations.scalar_calcs import calculate_ferrous_iron_yield_nh3
    result = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=0.1,
        background_ammonium_mM=0.5,
        solution_volume_mL=100.0,
        total_ferrous_iron_g=1.0,
    )
    assert result == pytest.approx(0.0)


def test_ferrous_iron_yield_nh3_none_when_no_gross_ammonium():
    from backend.services.calculations.scalar_calcs import calculate_ferrous_iron_yield_nh3
    result = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=None,
        background_ammonium_mM=None,
        solution_volume_mL=100.0,
        total_ferrous_iron_g=1.0,
    )
    assert result is None


def test_ferrous_iron_yield_nh3_none_when_no_volume():
    from backend.services.calculations.scalar_calcs import calculate_ferrous_iron_yield_nh3
    result = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=10.0,
        background_ammonium_mM=None,
        solution_volume_mL=None,
        total_ferrous_iron_g=1.0,
    )
    assert result is None


def test_ferrous_iron_yield_nh3_none_when_no_total_fe():
    from backend.services.calculations.scalar_calcs import calculate_ferrous_iron_yield_nh3
    result = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=10.0,
        background_ammonium_mM=None,
        solution_volume_mL=100.0,
        total_ferrous_iron_g=None,
    )
    assert result is None


def test_ferrous_iron_yield_nh3_none_when_total_fe_zero():
    """Zero total_ferrous_iron_g → returns None (guard against division by zero)."""
    from backend.services.calculations.scalar_calcs import calculate_ferrous_iron_yield_nh3
    result = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=10.0,
        background_ammonium_mM=None,
        solution_volume_mL=100.0,
        total_ferrous_iron_g=0.0,
    )
    assert result is None


def test_ferrous_iron_yield_nh3_none_when_total_fe_negative():
    """Negative total_ferrous_iron_g → returns None (invalid input)."""
    from backend.services.calculations.scalar_calcs import calculate_ferrous_iron_yield_nh3
    result = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=10.0,
        background_ammonium_mM=None,
        solution_volume_mL=100.0,
        total_ferrous_iron_g=-0.5,
    )
    assert result is None


def test_ferrous_iron_yield_nh3_none_when_zero_volume():
    from backend.services.calculations.scalar_calcs import calculate_ferrous_iron_yield_nh3
    result = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=10.0,
        background_ammonium_mM=None,
        solution_volume_mL=0.0,
        total_ferrous_iron_g=1.0,
    )
    assert result is None


# --- recalculate_scalar integration: ferrous iron yield wiring ---


def test_recalculate_scalar_sets_h2_yield_when_total_fe_set():
    """recalculate_scalar populates ferrous_iron_yield_h2_pct when total_ferrous_iron is set."""
    s = make_scalar(
        h2_concentration=100.0,
        gas_sampling_volume_ml=10.0,
        gas_sampling_pressure_MPa=0.1,
        result_entry=make_result_chain(rock_mass_g=10.0, total_ferrous_iron=1.0),
    )
    recalculate_scalar(s, SESSION)
    assert s.ferrous_iron_yield_h2_pct is not None
    assert s.ferrous_iron_yield_h2_pct > 0


def test_recalculate_scalar_h2_yield_none_when_no_total_fe():
    """ferrous_iron_yield_h2_pct is None when total_ferrous_iron not set."""
    s = make_scalar(
        h2_concentration=100.0,
        gas_sampling_volume_ml=10.0,
        gas_sampling_pressure_MPa=0.1,
        result_entry=make_result_chain(rock_mass_g=10.0, total_ferrous_iron=None),
    )
    recalculate_scalar(s, SESSION)
    assert s.ferrous_iron_yield_h2_pct is None


def test_recalculate_scalar_sets_nh3_yield_when_total_fe_set():
    """recalculate_scalar populates ferrous_iron_yield_nh3_pct when inputs are present."""
    s = make_scalar(
        gross_ammonium_concentration_mM=10.0,
        background_ammonium_concentration_mM=0.3,
        sampling_volume_mL=100.0,
        result_entry=make_result_chain(rock_mass_g=10.0, total_ferrous_iron=1.0),
    )
    recalculate_scalar(s, SESSION)
    assert s.ferrous_iron_yield_nh3_pct is not None
    assert s.ferrous_iron_yield_nh3_pct > 0


def test_recalculate_scalar_nh3_yield_none_when_no_total_fe():
    """ferrous_iron_yield_nh3_pct is None when total_ferrous_iron not set."""
    s = make_scalar(
        gross_ammonium_concentration_mM=10.0,
        sampling_volume_mL=100.0,
        result_entry=make_result_chain(rock_mass_g=10.0, total_ferrous_iron=None),
    )
    recalculate_scalar(s, SESSION)
    assert s.ferrous_iron_yield_nh3_pct is None
