# M2 Calculation Engine Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract all derived-field calculation logic from SQLAlchemy model methods into `backend/services/calculations/`, leaving models as pure storage, and wire up a registry M3 can call after writes.

**Architecture:** Per-domain formula modules (`additive_calcs.py`, `scalar_calcs.py`, `conditions_calcs.py`) each register a `recalculate_*` function into a central dispatch dict in `registry.py`. M3 calls `registry.recalculate(instance, session)` after any write. Model methods that performed these calculations are deleted (clean break — no wrappers).

**Tech Stack:** Python 3.11+, SQLAlchemy 2.x, pytest, `types.SimpleNamespace` (for unit-test stubs — no DB required for calc tests)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `backend/services/calculations/__init__.py` | Imports all formula modules to trigger `@register` decorators |
| Create | `backend/services/calculations/registry.py` | Dispatch dict + `recalculate(instance, session)` entry point |
| Create | `backend/services/calculations/conditions_calcs.py` | `water_to_rock_ratio` formula |
| Create | `backend/services/calculations/additive_calcs.py` | Unit conversions, moles, concentration, catalyst fields; `format_additives()` |
| Create | `backend/services/calculations/scalar_calcs.py` | Ammonium yield, H2 PV=nRT, `h2_grams_per_ton_yield` |
| Create | `tests/services/calculations/__init__.py` | Package marker |
| Create | `tests/services/calculations/test_registry.py` | Registry dispatch tests |
| Create | `tests/services/calculations/test_conditions_calcs.py` | Conditions formula tests |
| Create | `tests/services/calculations/test_additive_calcs.py` | Additive formula tests |
| Create | `tests/services/calculations/test_scalar_calcs.py` | Scalar formula tests |
| Create | `docs/CALCULATIONS.md` | Formula reference for researchers and developers |
| Create | `docs/milestones/M2_calculation_engine.md` | Milestone spec |
| Modify | `database/models/chemicals.py` | Delete `calculate_derived_values`, `_convert_to_grams` |
| Modify | `database/models/conditions.py` | Delete `calculate_derived_conditions`, `formatted_additives` hybrid_property; remove unused imports |
| Modify | `database/models/results.py` | Delete `calculate_yields`, `calculate_hydrogen` |
| Modify | `docs/milestones/MILESTONE_INDEX.md` | M1 → Complete, M2 → Active |
| Modify | `docs/working/plan.md` | M1 → COMPLETE, M2 → IN PROGRESS |

---

## Chunk 1: Registry + Package Setup

### Task 1: Cut branch and create empty package files

**Files:**
- Create: `backend/services/calculations/__init__.py`
- Create: `backend/services/calculations/registry.py`
- Create: `tests/services/calculations/__init__.py`

- [ ] **Step 1: Verify you are on the right branch**

```bash
git branch
```

Expected: `* feature/m1-postgres-migration`
If not on that branch: `git checkout feature/m1-postgres-migration`

- [ ] **Step 2: Cut the M2 branch**

```bash
git checkout -b feature/m2-calculation-engine
```

- [ ] **Step 3: Create the calculations package directory and empty files**

```bash
mkdir -p backend/services/calculations
touch backend/services/calculations/__init__.py
touch backend/services/calculations/registry.py
touch backend/services/calculations/conditions_calcs.py
touch backend/services/calculations/additive_calcs.py
touch backend/services/calculations/scalar_calcs.py
mkdir -p tests/services/calculations
touch tests/services/calculations/__init__.py
```

- [ ] **Step 4: Verify structure**

```bash
find backend/services/calculations tests/services/calculations -type f
```

Expected output:
```
backend/services/calculations/__init__.py
backend/services/calculations/registry.py
backend/services/calculations/conditions_calcs.py
backend/services/calculations/additive_calcs.py
backend/services/calculations/scalar_calcs.py
tests/services/calculations/__init__.py
```

---

### Task 2: Registry — write test, implement, pass, commit

**Files:**
- Modify: `backend/services/calculations/registry.py`
- Create: `tests/services/calculations/test_registry.py`

- [ ] **Step 1: Write failing tests**

Create `tests/services/calculations/test_registry.py`:

```python
import types
import pytest
from backend.services.calculations import registry


class FakeModel:
    pass


class OtherModel:
    pass


def test_register_and_dispatch():
    """Registered function is called with instance and session."""
    called_with = {}

    @registry.register(FakeModel)
    def recalc(instance, session):
        called_with['instance'] = instance
        called_with['session'] = session

    instance = FakeModel()
    session = types.SimpleNamespace()
    registry.recalculate(instance, session)

    assert called_with['instance'] is instance
    assert called_with['session'] is session

    # Cleanup: remove registration so other tests are not affected
    registry._REGISTRY.pop(FakeModel, None)


def test_unregistered_model_is_noop():
    """recalculate silently does nothing for unregistered model types."""
    instance = OtherModel()
    session = types.SimpleNamespace()
    # Should not raise
    registry.recalculate(instance, session)


def test_register_overwrites_previous():
    """Re-registering a model class replaces the previous function."""
    results = []

    @registry.register(FakeModel)
    def first(instance, session):
        results.append('first')

    @registry.register(FakeModel)
    def second(instance, session):
        results.append('second')

    registry.recalculate(FakeModel(), types.SimpleNamespace())
    assert results == ['second']

    registry._REGISTRY.pop(FakeModel, None)
```

- [ ] **Step 2: Run tests — expect FAIL (ImportError)**

```bash
python -m pytest tests/services/calculations/test_registry.py -v
```

Expected: `ImportError: cannot import name 'registry' from 'backend.services.calculations'`

- [ ] **Step 3: Implement registry**

Write `backend/services/calculations/registry.py`:

```python
from __future__ import annotations

from typing import Any, Callable
from sqlalchemy.orm import Session

_REGISTRY: dict[type, Callable] = {}


def register(model_class: type) -> Callable:
    """Decorator: register a recalculate function for a model class.

    Usage::

        @registry.register(ScalarResults)
        def recalculate_scalar(instance: ScalarResults, session: Session) -> None:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        _REGISTRY[model_class] = fn
        return fn
    return decorator


def recalculate(instance: Any, session: Session) -> None:
    """Call the registered recalculate function for this model instance.

    If no function is registered for the instance's type, this is a no-op.
    Called by M3 API write endpoints after every DB commit.
    """
    fn = _REGISTRY.get(type(instance))
    if fn is not None:
        fn(instance, session)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest tests/services/calculations/test_registry.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/services/calculations/registry.py tests/services/calculations/test_registry.py tests/services/calculations/__init__.py backend/services/calculations/__init__.py backend/services/calculations/conditions_calcs.py backend/services/calculations/additive_calcs.py backend/services/calculations/scalar_calcs.py
git commit -m "[M2] Add calculation engine registry with dispatch and tests"
```

> Note: `test_registry.py` and `registry.py` are both written in Task 2. The empty placeholder files (`conditions_calcs.py`, `additive_calcs.py`, `scalar_calcs.py`, `__init__.py`) are staged here so the package is importable for subsequent tasks. `tests/services/calculations/__init__.py` is also staged here.

---

## Chunk 2: Conditions Calculations

### Task 3: conditions_calcs — write tests, implement, pass, commit

**Files:**
- Modify: `backend/services/calculations/conditions_calcs.py`
- Create: `tests/services/calculations/test_conditions_calcs.py`

- [ ] **Step 1: Write failing tests**

Create `tests/services/calculations/test_conditions_calcs.py`:

```python
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
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
python -m pytest tests/services/calculations/test_conditions_calcs.py -v
```

Expected: `ImportError` or `AttributeError` — `recalculate_conditions` not implemented.

- [ ] **Step 3: Implement conditions_calcs**

Write `backend/services/calculations/conditions_calcs.py`:

```python
from __future__ import annotations

from sqlalchemy.orm import Session
from backend.services.calculations.registry import register
from database.models.conditions import ExperimentalConditions


@register(ExperimentalConditions)
def recalculate_conditions(instance: ExperimentalConditions, session: Session) -> None:
    """Recalculate derived fields on ExperimentalConditions.

    Derived fields:
    - water_to_rock_ratio = water_volume_mL / rock_mass_g
    """
    water_vol = instance.water_volume_mL
    rock_mass = instance.rock_mass_g

    if (
        water_vol is not None
        and rock_mass is not None
        and rock_mass > 0
    ):
        instance.water_to_rock_ratio = water_vol / rock_mass
    else:
        instance.water_to_rock_ratio = None
```

Also update `backend/services/calculations/__init__.py` to import all formula modules so decorators fire at import time:

```python
# Import formula modules to trigger @register decorators.
# The order does not matter — registry.recalculate() uses type(instance) as key.
from backend.services.calculations import conditions_calcs  # noqa: F401
from backend.services.calculations import additive_calcs    # noqa: F401
from backend.services.calculations import scalar_calcs      # noqa: F401
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest tests/services/calculations/test_conditions_calcs.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/services/calculations/conditions_calcs.py backend/services/calculations/__init__.py tests/services/calculations/test_conditions_calcs.py
git commit -m "[M2] Add conditions calculation engine: water_to_rock_ratio"
```

---

## Chunk 3: Additive Calculations

### Task 4: additive_calcs — unit conversion and concentration tests + implementation

**Files:**
- Modify: `backend/services/calculations/additive_calcs.py`
- Create: `tests/services/calculations/test_additive_calcs.py`

The additive recalculate function needs access to `instance.compound` and `instance.experiment`.
Tests use `types.SimpleNamespace` stubs — no DB.

- [ ] **Step 1: Write failing tests (unit conversions + concentration)**

Create `tests/services/calculations/test_additive_calcs.py`:

```python
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
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
python -m pytest tests/services/calculations/test_additive_calcs.py -v
```

Expected: `ImportError` — `recalculate_additive` not implemented.

- [ ] **Step 3: Implement additive_calcs**

Write `backend/services/calculations/additive_calcs.py`:

```python
from __future__ import annotations

from sqlalchemy.orm import Session
from backend.services.calculations.registry import register
from database.models.chemicals import ChemicalAdditive
from database.models.enums import AmountUnit


@register(ChemicalAdditive)
def recalculate_additive(instance: object, session: Session) -> None:
    """Recalculate all derived fields on a ChemicalAdditive instance.

    Sets: mass_in_grams, moles_added, final_concentration, concentration_units,
          elemental_metal_mass, catalyst_percentage, catalyst_ppm.

    Reads experiment.water_volume_mL and experiment.rock_mass_g from the
    linked ExperimentalConditions (via instance.experiment relationship).
    """
    # --- gather context ---
    water_volume_ml: float | None = None
    rock_mass: float | None = None
    volume_liters: float | None = None

    experiment = getattr(instance, 'experiment', None)
    if experiment is not None:
        water_volume_ml = getattr(experiment, 'water_volume_mL', None)
        rock_mass = getattr(experiment, 'rock_mass_g', None)
        if isinstance(water_volume_ml, (int, float)) and water_volume_ml and water_volume_ml > 0:
            volume_liters = water_volume_ml / 1000.0

    compound = getattr(instance, 'compound', None)
    molecular_weight: float | None = (
        getattr(compound, 'molecular_weight_g_mol', None) if compound else None
    )

    # --- reset outputs ---
    instance.mass_in_grams = None
    instance.moles_added = None
    instance.final_concentration = None
    instance.concentration_units = None
    instance.elemental_metal_mass = None
    instance.catalyst_percentage = None
    instance.catalyst_ppm = None

    amount = float(instance.amount)
    unit = instance.unit

    # --- mass / moles / concentration by unit ---
    if unit == AmountUnit.PERCENT_OF_ROCK:
        if rock_mass is not None and isinstance(rock_mass, (int, float)) and rock_mass > 0:
            instance.mass_in_grams = (amount / 100.0) * rock_mass
        if instance.mass_in_grams is not None and molecular_weight:
            instance.moles_added = instance.mass_in_grams / molecular_weight

    elif unit in (AmountUnit.PERCENT, AmountUnit.WEIGHT_PERCENT):
        if water_volume_ml is not None and water_volume_ml > 0:
            instance.mass_in_grams = (amount / 100.0) * water_volume_ml
        if instance.mass_in_grams is not None and molecular_weight:
            instance.moles_added = instance.mass_in_grams / molecular_weight
        instance.final_concentration = amount
        instance.concentration_units = unit.value

    elif unit == AmountUnit.PPM:
        # ppm = mg/L; mass_g = ppm * L / 1000
        if volume_liters is not None:
            instance.mass_in_grams = (amount * volume_liters) / 1000.0
        if instance.mass_in_grams is not None and molecular_weight:
            instance.moles_added = instance.mass_in_grams / molecular_weight
        instance.final_concentration = amount
        instance.concentration_units = 'ppm'

    elif unit == AmountUnit.MILLIMOLAR:
        if volume_liters is not None:
            moles = (amount / 1000.0) * volume_liters
            instance.moles_added = moles
            if molecular_weight:
                instance.mass_in_grams = moles * molecular_weight
        instance.final_concentration = amount
        instance.concentration_units = 'mM'

    elif unit == AmountUnit.MOLAR:
        if volume_liters is not None:
            moles = amount * volume_liters
            instance.moles_added = moles
            if molecular_weight:
                instance.mass_in_grams = moles * molecular_weight
        instance.final_concentration = amount
        instance.concentration_units = 'M'

    elif unit in (AmountUnit.MICROMOLE, AmountUnit.MILLIMOLE, AmountUnit.MOLE):
        scale = {
            AmountUnit.MICROMOLE: 1e-6,
            AmountUnit.MILLIMOLE: 1e-3,
            AmountUnit.MOLE: 1.0,
        }[unit]
        moles = amount * scale
        instance.moles_added = moles
        if molecular_weight:
            instance.mass_in_grams = moles * molecular_weight
        if volume_liters is not None:
            instance.final_concentration = (moles / volume_liters) * 1000.0
            instance.concentration_units = 'mM'

    else:
        # Mass / volume inputs: convert to grams
        instance.mass_in_grams = _to_grams(amount, unit)
        if instance.mass_in_grams is not None and molecular_weight:
            instance.moles_added = instance.mass_in_grams / molecular_weight
        if instance.mass_in_grams is not None and volume_liters is not None:
            instance.final_concentration = (instance.mass_in_grams / volume_liters) * 1_000_000.0
            instance.concentration_units = 'ppm'

    # --- catalyst fields ---
    if instance.mass_in_grams and instance.mass_in_grams > 0 and compound is not None:
        elemental_fraction = getattr(compound, 'elemental_fraction', None)
        if elemental_fraction:
            instance.elemental_metal_mass = instance.mass_in_grams * elemental_fraction
            if rock_mass is not None and rock_mass > 0:
                instance.catalyst_percentage = (instance.elemental_metal_mass / rock_mass) * 100
            if water_volume_ml is not None and water_volume_ml > 0:
                raw_ppm = (instance.elemental_metal_mass / water_volume_ml) * 1_000_000
                instance.catalyst_ppm = round(raw_ppm / 10) * 10


def _to_grams(amount: float, unit: AmountUnit) -> float | None:
    """Convert a mass/volume amount to grams. Returns None for concentration units."""
    conversions: dict[AmountUnit, float | None] = {
        AmountUnit.GRAM: 1.0,
        AmountUnit.MILLIGRAM: 1e-3,
        AmountUnit.MICROGRAM: 1e-6,
        AmountUnit.KILOGRAM: 1000.0,
        AmountUnit.MICROLITER: 1e-3,   # density ~1 g/mL
        AmountUnit.MILLILITER: 1.0,    # density ~1 g/mL
        AmountUnit.LITER: 1000.0,      # density ~1 g/mL
    }
    factor = conversions.get(unit)
    return amount * factor if factor is not None else None


def format_additives(conditions: object) -> str:
    """Return a newline-separated display string of all chemical additives.

    Replaces ExperimentalConditions.formatted_additives hybrid_property.
    Example output: "5 g Mg(OH)2\\n1 g Magnetite"
    """
    additives = getattr(conditions, 'chemical_additives', [])
    if not additives:
        return ""
    parts = []
    for a in additives:
        compound_name = getattr(getattr(a, 'compound', None), 'name', 'Unknown')
        parts.append(f"{a.amount} {a.unit.value} {compound_name}")
    return "\n".join(parts)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest tests/services/calculations/test_additive_calcs.py -v
```

Expected: all tests pass. If `moles_added is None` test fails, confirm `molecular_weight_g_mol=None` on the stub compound.

- [ ] **Step 5: Commit**

```bash
git add backend/services/calculations/additive_calcs.py tests/services/calculations/test_additive_calcs.py
git commit -m "[M2] Add additive calculation engine: unit conversions, moles, catalyst fields"
```

---

## Chunk 4: Scalar Calculations

### Task 5: scalar_calcs — H2 and yield tests + implementation

**Files:**
- Modify: `backend/services/calculations/scalar_calcs.py`
- Create: `tests/services/calculations/test_scalar_calcs.py`

- [ ] **Step 1: Write failing tests**

Create `tests/services/calculations/test_scalar_calcs.py`:

```python
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
    n_total = PV/RT = (0.986923 * 0.01) / (0.082057 * 293.15) ≈ 4.094e-4 mol
    fraction = 100 / 1e6 = 1e-4
    h2_mol = 4.094e-4 * 1e-4 ≈ 4.094e-8 mol
    h2_micromol ≈ 0.04094
    h2_mass_ug  ≈ 0.04094 * 2.01588 * 1e6 / 1e6 * 1e6 ≈ 0.08254
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
    mass_NH4 = (9.7/1000) mol/L * 0.1 L * 18.04 g/mol = 0.017499 g
    yield = 1e6 * 0.017499 / 10 = 1749.9 g/ton
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
    # Supply H2 inputs that produce a known h2_mass_ug, check normalization
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
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
python -m pytest tests/services/calculations/test_scalar_calcs.py -v
```

Expected: `ImportError` — `recalculate_scalar` not defined.

- [ ] **Step 3: Implement scalar_calcs**

Write `backend/services/calculations/scalar_calcs.py`:

```python
from __future__ import annotations

from sqlalchemy.orm import Session
from backend.services.calculations.registry import register
from database.models.results import ScalarResults


@register(ScalarResults)
def recalculate_scalar(instance: object, session: Session) -> None:
    """Recalculate all derived fields on a ScalarResults instance.

    Sets: grams_per_ton_yield, h2_micromoles, h2_mass_ug, h2_grams_per_ton_yield.

    Reads rock_mass_g and water_volume_mL via:
        instance.result_entry.experiment.conditions
    """
    rock_mass: float | None = None
    liquid_volume_ml: float | None = None

    result_entry = getattr(instance, 'result_entry', None)
    if result_entry is not None:
        experiment = getattr(result_entry, 'experiment', None)
        if experiment is not None:
            conditions = getattr(experiment, 'conditions', None)
            if conditions is not None:
                rock_mass = getattr(conditions, 'rock_mass_g', None)
                liquid_volume_ml = getattr(conditions, 'water_volume_mL', None)

    # Prefer sampling_volume_mL when available
    sampling_vol = getattr(instance, 'sampling_volume_mL', None)
    if sampling_vol is not None and sampling_vol > 0:
        liquid_volume_ml = sampling_vol

    # H2 calculation
    _calculate_hydrogen(instance)

    # h2_grams_per_ton_yield
    h2_mass_ug = getattr(instance, 'h2_mass_ug', None)
    if rock_mass is not None and rock_mass > 0 and h2_mass_ug is not None:
        h2_mass_g = h2_mass_ug / 1_000_000.0
        instance.h2_grams_per_ton_yield = 1_000_000.0 * (h2_mass_g / rock_mass)
    else:
        instance.h2_grams_per_ton_yield = None

    # Ammonium yield
    gross = getattr(instance, 'gross_ammonium_concentration_mM', None)
    if gross is not None and liquid_volume_ml is not None and liquid_volume_ml > 0:
        bg = getattr(instance, 'background_ammonium_concentration_mM', None)
        bg = bg if bg is not None else 0.3
        net_conc = max(0.0, gross - bg)
        ammonia_mass_g = (net_conc / 1000.0) * (liquid_volume_ml / 1000.0) * 18.04
        if rock_mass is not None and rock_mass > 0:
            instance.grams_per_ton_yield = 1_000_000.0 * (ammonia_mass_g / rock_mass)
        else:
            instance.grams_per_ton_yield = None
    else:
        instance.grams_per_ton_yield = None


def _calculate_hydrogen(instance: object) -> None:
    """Calculate H2 amount from gas-phase ppm using PV = nRT at 20°C.

    Inputs (on instance):
        h2_concentration       — ppm (vol/vol)
        gas_sampling_volume_ml — mL
        gas_sampling_pressure_MPa — MPa

    Outputs set on instance:
        h2_micromoles  (μmol)
        h2_mass_ug     (μg)
    """
    h2_ppm = getattr(instance, 'h2_concentration', None)
    vol_ml = getattr(instance, 'gas_sampling_volume_ml', None)
    pressure_mpa = getattr(instance, 'gas_sampling_pressure_MPa', None)

    if h2_ppm is None or vol_ml is None or vol_ml <= 0 or pressure_mpa is None or pressure_mpa <= 0:
        instance.h2_micromoles = None
        instance.h2_mass_ug = None
        return

    R = 0.082057          # L·atm/(mol·K)
    T_K = 293.15          # 20°C
    H2_MOLAR_MASS = 2.01588  # g/mol

    P_atm = pressure_mpa * 9.86923
    V_L = vol_ml / 1000.0
    n_total = (P_atm * V_L) / (R * T_K)
    fraction = h2_ppm / 1_000_000.0

    if fraction < 0:
        instance.h2_micromoles = None
        instance.h2_mass_ug = None
        return

    h2_moles = n_total * fraction
    instance.h2_micromoles = h2_moles * 1_000_000.0
    instance.h2_mass_ug = h2_moles * H2_MOLAR_MASS * 1_000_000.0
```

- [ ] **Step 4: Run all calculation tests**

```bash
python -m pytest tests/services/calculations/ -v
```

Expected: all tests pass. Count should be ~20.

- [ ] **Step 5: Commit**

```bash
git add backend/services/calculations/scalar_calcs.py tests/services/calculations/test_scalar_calcs.py
git commit -m "[M2] Add scalar calculation engine: H2 PV=nRT, ammonium yield, g/ton"
```

---

## Chunk 5: Model Cleanup

### Task 6: Delete calculation methods from models

**Files:**
- Modify: `database/models/chemicals.py`
- Modify: `database/models/conditions.py`
- Modify: `database/models/results.py`

- [ ] **Step 1: Search for callers of model calculation methods**

Before deleting, confirm nothing in the active codebase calls these methods.
These are Streamlit-era calls that no longer have a runtime path in M2.

```bash
grep -r "calculate_derived_values\|calculate_derived_conditions\|calculate_yields\|calculate_hydrogen\|formatted_additives" --include="*.py" . \
  --exclude-dir=".venv" --exclude-dir="tests"
```

Review the output. If any file outside `database/models/` calls these methods,
note them — they are Streamlit legacy code. Do NOT update those callers here;
they will be replaced in M3/M4. The model method deletion is safe because:
- M3 has not been written yet (the only caller will be the new registry)
- The Streamlit frontend is being replaced by React

- [ ] **Step 2: Delete calculation methods from `database/models/chemicals.py`**

Open `database/models/chemicals.py`. Remove:
- The entire `calculate_derived_values(self)` method (lines ~126–308)
- The entire `_convert_to_grams(self)` method (lines ~310–336)
- The `hybrid_property` import if it is no longer used after the deletion

Also remove the `from sqlalchemy.ext.hybrid import hybrid_property` import from `conditions.py` (handled in next step).

The `format_additive()` and `format_additives_list()` methods on `ChemicalAdditive` are **kept** — they are display helpers, not calculated fields.

- [ ] **Step 3: Delete calculation methods from `database/models/conditions.py`**

Remove:
- The `@hybrid_property` `formatted_additives` property (the decorator + method body)
- The entire `calculate_derived_conditions(self)` method
- The `from sqlalchemy.ext.hybrid import hybrid_property` import line (no longer needed)

- [ ] **Step 4: Delete calculation methods from `database/models/results.py`**

Remove:
- The entire `calculate_yields(self)` method
- The entire `calculate_hydrogen(self)` method

**Do not remove** `get_element_concentration()` or `validate_json()` — these are lookup/validation helpers, not calculations.

- [ ] **Step 5: Verify models still import cleanly**

```bash
python -c "from database.models.chemicals import ChemicalAdditive, Compound; print('OK')"
python -c "from database.models.conditions import ExperimentalConditions; print('OK')"
python -c "from database.models.results import ScalarResults, ICPResults; print('OK')"
```

Expected: `OK` for each line.

- [ ] **Step 6: Run full test suite to confirm no regressions**

```bash
python -m pytest tests/ -v --ignore=tests/test_icp_service.py --ignore=tests/test_time_field_guardrails.py --ignore=tests/test_yield_calcs.py 2>&1 | tail -30
```

The three ignored files are known pre-existing failures (documented in `docs/working/plan.md`).
All other tests should pass.

- [ ] **Step 7: Commit**

```bash
git add database/models/chemicals.py database/models/conditions.py database/models/results.py
git commit -m "[M2] Remove calculation methods from models — pure storage only"
```

---

## Chunk 6: Documentation and Milestone Housekeeping

### Task 7: Create docs/CALCULATIONS.md

**Files:**
- Create: `docs/CALCULATIONS.md`

- [ ] **Step 1: Write the formula reference**

Create `docs/CALCULATIONS.md`:

```markdown
# Calculations Reference

This document is the source of truth for all derived-field formulas in the experiment tracking system.

Formulas live in `backend/services/calculations/`. The Documentation Agent keeps this file
in sync with the implementation after every change.

---

## How the Calculation Engine Works

After any database write, M3 API endpoints call:

```python
from backend.services.calculations import registry
registry.recalculate(instance, session)
```

The registry dispatches to the correct formula function based on `type(instance)`.
Each formula module registers itself with `@registry.register(ModelClass)`.

To add a new formula:
1. Create or open the relevant `*_calcs.py` module in `backend/services/calculations/`
2. Decorate your function with `@registry.register(YourModel)`
3. Import the module in `backend/services/calculations/__init__.py`
4. Update this document

---

## Conditions Calculations (`conditions_calcs.py`)

### `water_to_rock_ratio`

```
water_to_rock_ratio = water_volume_mL / rock_mass_g
```

- Set to `None` if either input is missing or `rock_mass_g ≤ 0`
- Units: mL/g (dimensionless ratio)

---

## Additive Calculations (`additive_calcs.py`)

### Unit Conversion to Grams (`mass_in_grams`)

| Input Unit | Conversion |
|------------|------------|
| g | 1× |
| mg | ÷ 1,000 |
| µg | ÷ 1,000,000 |
| kg | × 1,000 |
| mL | × 1 (assumes density 1 g/mL) |
| µL | × 0.001 |
| L | × 1,000 |
| mM | `(amount / 1000) × volume_L × MW` |
| M | `amount × volume_L × MW` |
| ppm | `amount × volume_L / 1000` (ppm = mg/L) |
| % of Rock | `(amount / 100) × rock_mass_g` |
| %, wt% | `(amount / 100) × water_volume_mL` |

### Moles (`moles_added`)

```
moles_added = mass_in_grams / molecular_weight_g_mol
```

Requires `Compound.molecular_weight_g_mol` to be set. `None` if MW unavailable.

### Final Concentration (`final_concentration`, `concentration_units`)

For concentration-input units (mM, M, ppm, %, wt%): mirrors the input value.
For mass inputs with known volume: `(mass_g / volume_L) × 1,000,000` → ppm.

### Catalyst Fields (`elemental_metal_mass`, `catalyst_percentage`, `catalyst_ppm`)

Requires `Compound.elemental_fraction` to be set (pre-calculated fraction of elemental metal
to compound mass, e.g., `58.69 / 237.69` for Ni in NiCl₂·6H₂O).

```
elemental_metal_mass = mass_in_grams × elemental_fraction

catalyst_percentage  = (elemental_metal_mass / rock_mass_g) × 100

catalyst_ppm         = round((elemental_metal_mass / water_volume_mL) × 1,000,000 / 10) × 10
```

`catalyst_ppm` is rounded to the nearest 10 ppm.
All three fields are `None` if `elemental_fraction` is not set on the compound.

---

## Scalar Calculations (`scalar_calcs.py`)

### Ammonium Yield (`grams_per_ton_yield`)

```
net_concentration_mM = max(0, gross_ammonium_concentration_mM − background_ammonium_concentration_mM)

ammonia_mass_g = (net_concentration_mM / 1000) × (volume_mL / 1000) × 18.04
              = mol/L × L × g/mol   [MW of NH₄⁺ = 18.04 g/mol]

grams_per_ton_yield = 1,000,000 × (ammonia_mass_g / rock_mass_g)
```

- `volume_mL`: uses `sampling_volume_mL` if provided; otherwise falls back to `water_volume_mL` from conditions
- `background_ammonium_concentration_mM` defaults to `0.3 mM` if not set
- Net concentration is clamped to `≥ 0` (negative background subtraction → 0 yield, not negative)
- Set to `None` if `rock_mass_g` is missing or `≤ 0`

### Hydrogen Amount (PV = nRT, `h2_micromoles`, `h2_mass_ug`)

```
P_atm = gas_sampling_pressure_MPa × 9.86923      [MPa → atm]
V_L   = gas_sampling_volume_ml / 1000             [mL → L]

n_total_mol = (P_atm × V_L) / (R × T_K)          [R = 0.082057 L·atm/(mol·K), T = 293.15 K = 20°C]
h2_fraction = h2_concentration_ppm / 1,000,000   [ppm → mole fraction]
h2_mol      = n_total_mol × h2_fraction

h2_micromoles = h2_mol × 1,000,000               [μmol]
h2_mass_ug    = h2_mol × 2.01588 × 1,000,000     [μg; MW H₂ = 2.01588 g/mol]
```

- Temperature fixed at 20°C (293.15 K)
- `h2_concentration` always stored in ppm (vol/vol)
- All three inputs required and > 0; otherwise both outputs are `None`

### Hydrogen Yield (`h2_grams_per_ton_yield`)

```
h2_mass_g = h2_mass_ug / 1,000,000

h2_grams_per_ton_yield = 1,000,000 × (h2_mass_g / rock_mass_g)
```

Set to `None` if `rock_mass_g` is missing or H2 inputs are insufficient.

---

## Utility Functions

### `format_additives(conditions)` — `additive_calcs.py`

Returns a newline-separated display string of all chemical additives.

```
"5 g Mg(OH)₂\n1 g Magnetite"
```

Replaces the former `ExperimentalConditions.formatted_additives` hybrid_property.
The SQL view `v_experiment_additives_summary` handles the Power BI reporting case.
```

- [ ] **Step 2: Verify file looks correct**

```bash
python -c "import pathlib; print(pathlib.Path('docs/CALCULATIONS.md').stat().st_size, 'bytes')"
```

Expected: > 2000 bytes.

- [ ] **Step 3: Commit**

```bash
git add docs/CALCULATIONS.md
git commit -m "[M2] Add CALCULATIONS.md — formula reference for all derived fields"
```

---

### Task 8: Create M2 milestone file and update tracking docs

**Files:**
- Create: `docs/milestones/M2_calculation_engine.md`
- Modify: `docs/milestones/MILESTONE_INDEX.md`
- Modify: `docs/working/plan.md`

- [ ] **Step 1: Create the M2 milestone file**

Create `docs/milestones/M2_calculation_engine.md`:

```markdown
# Milestone 2: Calculation Engine

**Owner:** api-developer (primary), db-architect (model cleanup review)
**Branch:** `feature/m2-calculation-engine`

**Objective:** Extract all derived-field calculation logic from SQLAlchemy model methods
into a dedicated `backend/services/calculations/` package. Models become pure storage.
A registry pattern lets M3 call `registry.recalculate(instance, session)` after writes.

**Tasks:**
1. Build `registry.py` — dispatch dict with `@register` decorator and `recalculate()` entry point
2. Implement `conditions_calcs.py` — water_to_rock_ratio
3. Implement `additive_calcs.py` — unit conversions, moles, concentration, catalyst fields, format_additives()
4. Implement `scalar_calcs.py` — H2 (PV=nRT), ammonium yield, h2_grams_per_ton_yield
5. Delete calculation methods from `chemicals.py`, `conditions.py`, `results.py`
6. Write full unit tests (~20 cases) — pure functions, no DB required
7. Create `docs/CALCULATIONS.md` — formula reference

**Acceptance criteria:**
- `pytest tests/services/calculations/ -v` passes all ~20 tests
- `python -c "from database.models.chemicals import ChemicalAdditive"` succeeds (no calc methods)
- `docs/CALCULATIONS.md` exists and documents all formulas
- No `@hybrid_property` or `calculate_*` methods remain in `database/models/`

**Test Writer Agent:** See `tests/services/calculations/` — full coverage already provided in M2.

**Documentation Agent:** `docs/CALCULATIONS.md` created in this milestone. Keep it in sync
with `backend/services/calculations/` in future milestones.
```

- [ ] **Step 2: Update MILESTONE_INDEX.md**

Edit `docs/milestones/MILESTONE_INDEX.md`:
- Change `**Active:** M0 — Infrastructure Setup` → `**Active:** M2 — Calculation Engine`
- Change M0 status to `Complete`
- Change M1 status to `Complete`
- Change M2 status to `In Progress`

- [ ] **Step 3: Update docs/working/plan.md**

In `docs/working/plan.md`:
- Update the header: `**Active Milestone:** M2 — Calculation Engine`
- Mark M1 as `COMPLETE` (add completion note)
- Add an M2 section with the tasks from the milestone file and mark it `IN PROGRESS`

- [ ] **Step 4: Commit all housekeeping**

```bash
git add docs/milestones/M2_calculation_engine.md docs/milestones/MILESTONE_INDEX.md docs/working/plan.md
git commit -m "[M2] Add M2 milestone file; mark M1 complete in tracking docs"
```

---

## Final Verification

- [ ] **Run full calculation test suite**

```bash
python -m pytest tests/services/calculations/ -v
```

Expected: all ~20 tests pass.

- [ ] **Run broader test suite (excluding known pre-existing failures)**

```bash
python -m pytest tests/ -v \
  --ignore=tests/test_icp_service.py \
  --ignore=tests/test_time_field_guardrails.py \
  --ignore=tests/test_yield_calcs.py \
  2>&1 | tail -20
```

Expected: no new failures introduced by M2.

- [ ] **Confirm models are clean**

```bash
grep -n "def calculate_\|@hybrid_property\|def _convert_to_grams" database/models/chemicals.py database/models/conditions.py database/models/results.py
```

Expected: no output (all methods deleted).

- [ ] **Confirm registry is wired**

```bash
python -c "
from backend.services.calculations import registry
from database.models.results import ScalarResults
from database.models.chemicals import ChemicalAdditive
from database.models.conditions import ExperimentalConditions
print('ScalarResults registered:', ScalarResults in registry._REGISTRY)
print('ChemicalAdditive registered:', ChemicalAdditive in registry._REGISTRY)
print('ExperimentalConditions registered:', ExperimentalConditions in registry._REGISTRY)
"
```

Expected: all three print `True`.
