import types
import pytest
from backend.services.calculations import additive_calcs  # noqa: F401 — triggers register
from backend.services.calculations.additive_calcs import recalculate_additive, format_additives
from database.models.enums import AmountUnit


SESSION = types.SimpleNamespace()


def make_compound(**kwargs):
    defaults = {
        'name': 'Test Compound',
        'molecular_weight_g_mol': None,
        'elemental_fraction': None,
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def make_experiment(**kwargs):
    defaults = {
        'water_volume_mL': None,
        'rock_mass_g': None,
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def make_additive(**kwargs):
    defaults = {
        'amount': 1.0,
        'unit': AmountUnit.GRAM,
        'compound': None,
        'experiment': None,
        'mass_in_grams': None,
        'moles_added': None,
        'final_concentration': None,
        'concentration_units': None,
        'elemental_metal_mass': None,
        'catalyst_percentage': None,
        'catalyst_ppm': None,
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


# --- Unit conversion tests ---

def test_gram_input_passthrough():
    """1 g input → mass_in_grams = 1.0."""
    a = make_additive(amount=5.0, unit=AmountUnit.GRAM)
    recalculate_additive(a, SESSION)
    assert a.mass_in_grams == pytest.approx(5.0)


def test_milligram_conversion():
    """500 mg → 0.5 g."""
    a = make_additive(amount=500.0, unit=AmountUnit.MILLIGRAM)
    recalculate_additive(a, SESSION)
    assert a.mass_in_grams == pytest.approx(0.5)


def test_kilogram_conversion():
    """0.002 kg → 2.0 g."""
    a = make_additive(amount=0.002, unit=AmountUnit.KILOGRAM)
    recalculate_additive(a, SESSION)
    assert a.mass_in_grams == pytest.approx(2.0)


def test_moles_computed_when_mw_known():
    """5 g + MW 100 g/mol → 0.05 mol."""
    a = make_additive(
        amount=5.0,
        unit=AmountUnit.GRAM,
        compound=make_compound(molecular_weight_g_mol=100.0),
    )
    recalculate_additive(a, SESSION)
    assert a.moles_added == pytest.approx(0.05)


def test_moles_none_when_no_mw():
    """No MW on compound → moles_added is None."""
    a = make_additive(
        amount=5.0,
        unit=AmountUnit.GRAM,
        compound=make_compound(molecular_weight_g_mol=None),
    )
    recalculate_additive(a, SESSION)
    assert a.moles_added is None


def test_millimolar_input_sets_moles_and_concentration():
    """10 mM in 100 mL water = 0.001 mol; concentration = 10 mM."""
    a = make_additive(
        amount=10.0,
        unit=AmountUnit.MILLIMOLAR,
        experiment=make_experiment(water_volume_mL=100.0),
    )
    recalculate_additive(a, SESSION)
    assert a.moles_added == pytest.approx(0.001)
    assert a.final_concentration == pytest.approx(10.0)
    assert a.concentration_units == 'mM'


def test_ppm_input_computes_mass_from_volume():
    """100 ppm in 500 mL → mass = 0.05 g."""
    # ppm = mg/L; 100 mg/L * 0.5 L = 50 mg = 0.05 g
    a = make_additive(
        amount=100.0,
        unit=AmountUnit.PPM,
        experiment=make_experiment(water_volume_mL=500.0),
    )
    recalculate_additive(a, SESSION)
    assert a.mass_in_grams == pytest.approx(0.05)
    assert a.final_concentration == pytest.approx(100.0)
    assert a.concentration_units == 'ppm'


def test_percent_of_rock_computes_mass():
    """5% of Rock with 200 g rock → 10 g."""
    a = make_additive(
        amount=5.0,
        unit=AmountUnit.PERCENT_OF_ROCK,
        experiment=make_experiment(rock_mass_g=200.0),
    )
    recalculate_additive(a, SESSION)
    assert a.mass_in_grams == pytest.approx(10.0)


def test_missing_volume_leaves_concentration_none():
    """mM input without a water volume → moles and concentration are None."""
    a = make_additive(
        amount=10.0,
        unit=AmountUnit.MILLIMOLAR,
        experiment=make_experiment(water_volume_mL=None),
    )
    recalculate_additive(a, SESSION)
    assert a.moles_added is None


# --- Catalyst tests ---

def test_catalyst_with_elemental_fraction():
    """Compound with elemental_fraction: elemental_metal_mass, %, ppm all computed."""
    # 2 g of compound with 0.5 elemental fraction in 100 g rock + 1000 mL water
    a = make_additive(
        amount=2.0,
        unit=AmountUnit.GRAM,
        compound=make_compound(elemental_fraction=0.5),
        experiment=make_experiment(rock_mass_g=100.0, water_volume_mL=1000.0),
    )
    recalculate_additive(a, SESSION)
    assert a.elemental_metal_mass == pytest.approx(1.0)          # 2 * 0.5
    assert a.catalyst_percentage == pytest.approx(1.0)           # (1.0/100) * 100
    assert a.catalyst_ppm == pytest.approx(1000.0, rel=0.01)     # (1.0/1000) * 1e6 = 1000, rounded to nearest 10


def test_catalyst_without_elemental_fraction_is_none():
    """No elemental_fraction → catalyst fields are None."""
    a = make_additive(
        amount=2.0,
        unit=AmountUnit.GRAM,
        compound=make_compound(elemental_fraction=None),
        experiment=make_experiment(rock_mass_g=100.0, water_volume_mL=1000.0),
    )
    recalculate_additive(a, SESSION)
    assert a.elemental_metal_mass is None
    assert a.catalyst_percentage is None
    assert a.catalyst_ppm is None


# --- format_additives test ---

def test_format_additives_returns_string():
    """format_additives joins additive display strings with newline."""
    c1 = types.SimpleNamespace(
        amount=5.0, unit=AmountUnit.GRAM,
        compound=types.SimpleNamespace(name='Mg(OH)2')
    )
    c2 = types.SimpleNamespace(
        amount=1.0, unit=AmountUnit.GRAM,
        compound=types.SimpleNamespace(name='Magnetite')
    )
    conditions = types.SimpleNamespace(chemical_additives=[c1, c2])
    result = format_additives(conditions)
    assert 'Mg(OH)2' in result
    assert 'Magnetite' in result


def test_format_additives_empty_returns_empty_string():
    conditions = types.SimpleNamespace(chemical_additives=[])
    assert format_additives(conditions) == ""
