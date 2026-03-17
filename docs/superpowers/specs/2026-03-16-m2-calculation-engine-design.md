# M2 Calculation Engine — Design Spec

**Date:** 2026-03-16
**Status:** Approved
**Branch:** `feature/m2-calculation-engine`

---

## Overview

Extract all derived-field calculation logic from SQLAlchemy model methods into a dedicated
`backend/services/calculations/` package. Models become pure storage definitions. A registry
dispatches recalculation after writes — M3 calls one entry point.

---

## Decisions

| Question | Decision |
|---|---|
| Model method handling | Delete (clean break — no wrappers, no dead code) |
| Registry design | Simple dispatch dict with `recalculate(instance, session)` entry point |
| Test coverage | Full unit tests (~20 cases), pure functions, no DB required |

---

## File Structure

```
backend/services/calculations/
├── __init__.py           # imports all formula modules to trigger registration
├── registry.py           # dispatch dict + recalculate() entry point
├── additive_calcs.py     # ChemicalAdditive formulas
├── scalar_calcs.py       # ScalarResults formulas
└── conditions_calcs.py   # ExperimentalConditions formulas

tests/services/calculations/
├── __init__.py
├── test_additive_calcs.py
├── test_scalar_calcs.py
└── test_conditions_calcs.py

docs/CALCULATIONS.md       # formula reference, created in this milestone
docs/milestones/M2_calculation_engine.md
```

---

## Registry

```python
# registry.py
_REGISTRY: dict[type, Callable] = {}

def register(model_class: type):
    def decorator(fn):
        _REGISTRY[model_class] = fn
        return fn
    return decorator

def recalculate(instance: Any, session: Session) -> None:
    fn = _REGISTRY.get(type(instance))
    if fn:
        fn(instance, session)
```

Formula modules self-register via `@registry.register(ModelClass)`.
M3 usage: `from backend.services.calculations import registry; registry.recalculate(instance, session)`

---

## Formula Modules

### `conditions_calcs.py`
- `recalculate_conditions(instance, session)` — sets `water_to_rock_ratio`

### `additive_calcs.py`
- `recalculate_additive(instance, session)` — sets `mass_in_grams`, `moles_added`,
  `final_concentration`, `concentration_units`, `elemental_metal_mass`,
  `catalyst_percentage`, `catalyst_ppm`
- `format_additives(conditions)` — replaces `@hybrid_property formatted_additives`

### `scalar_calcs.py`
- `recalculate_scalar(instance, session)` — sets `grams_per_ton_yield`,
  `h2_micromoles`, `h2_mass_ug`, `h2_grams_per_ton_yield`
- `_calculate_hydrogen(instance)` — private helper (PV=nRT at 20°C)

---

## Model Changes

**Deleted from `chemicals.py`:**
- `ChemicalAdditive.calculate_derived_values()`
- `ChemicalAdditive._convert_to_grams()`

**Deleted from `conditions.py`:**
- `ExperimentalConditions.calculate_derived_conditions()`
- `ExperimentalConditions.formatted_additives` (`@hybrid_property`)

**Deleted from `results.py`:**
- `ScalarResults.calculate_yields()`
- `ScalarResults.calculate_hydrogen()`

**Kept (not calculations):**
- `ChemicalAdditive.format_additive()` / `format_additives_list()` — display helpers
- `ICPResults.get_element_concentration()` — lookup helper

---

## Tests (~20 cases)

**`test_conditions_calcs.py`** (3): ratio computed, zero rock mass → None, missing inputs → None

**`test_additive_calcs.py`** (10): g/mg/kg/µg conversions, mM→moles, ppm→mass, % of Rock,
catalyst with elemental_fraction, missing MW → moles None, missing volume → concentration None

**`test_scalar_calcs.py`** (7): H2 PV=nRT regression, missing pressure → None,
negative concentration → None, ammonium yield, background clamp to zero,
h2_grams_per_ton_yield, missing rock mass → None

---

## Documentation

`docs/CALCULATIONS.md` created with: overview, additive formula table, scalar formulas
(ammonium yield, H2 PV=nRT), conditions formulas, registry usage guide.

---

## Out of Scope

- No schema changes, no Alembic migrations
- `ICPResults.get_all_detected_elements()` not moved (imports `frontend.config.variable_config`
  which doesn't exist until M4 — tracked as pre-existing issue)
- No recalculation admin endpoints (M3 task)
