# Issue #3: Ferrous Iron Yield Calculations — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two derived ferrous-iron yield fields to `ScalarResults` (H₂-derived and NH₃-derived), backed by a new `total_ferrous_iron` input on `ExperimentalConditions`, following the existing calculation-engine pattern.

**Architecture:** Formula functions live in `scalar_calcs.py` (pure functions, primitives in/out). The `recalculate_scalar` handler calls them at write time. `conditions_calcs.py` is extended to propagate recalculation to all linked scalar results when conditions are updated (currently missing — must be added). Schema changes are purely additive; no existing columns touched.

**Tech Stack:** SQLAlchemy (PostgreSQL), Alembic, FastAPI, Pydantic v2, pytest, structlog

---

## File Map

| File | Change |
|------|--------|
| `database/models/conditions.py` | Add `total_ferrous_iron` column (Float, nullable) after `initial_alkalinity` |
| `database/models/results.py` | Add `ferrous_iron_yield_h2_pct` and `ferrous_iron_yield_nh3_pct` columns (Float, nullable) after `h2_grams_per_ton_yield` |
| `alembic/versions/<hash>_add_ferrous_iron_yield_columns.py` | New additive migration — CREATE |
| `backend/services/calculations/scalar_calcs.py` | Add `FE_MOLAR_MASS`, two pure formula functions, wire into `recalculate_scalar` |
| `backend/services/calculations/conditions_calcs.py` | Add propagation: when conditions change, recalculate all linked scalar results |
| `backend/api/schemas/conditions.py` | Add `total_ferrous_iron: float \| None = None` to Create, Update, Response |
| `backend/api/schemas/results.py` | Add `ferrous_iron_yield_h2_pct` and `ferrous_iron_yield_nh3_pct` to `ScalarResponse` |
| `docs/CALCULATIONS.md` | Add two new formula sections under Scalar Calculations |
| `tests/services/calculations/test_scalar_calcs.py` | Add unit tests for both formula functions + integration tests |

---

## Task 1: Write Failing Tests for Formula Functions

**Files:**
- Modify: `tests/services/calculations/test_scalar_calcs.py`

### Step 1.1: Update test helpers to include new fields

Add `total_ferrous_iron` to the conditions namespace in `make_result_chain`, and add the two new yield fields to `make_scalar` defaults. This is a non-breaking change — all existing tests continue passing.

- [ ] Open `tests/services/calculations/test_scalar_calcs.py`
- [ ] Update `make_result_chain` to accept `total_ferrous_iron`:

```python
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
```

- [ ] Update `make_scalar` defaults to include the two new yield fields:

```python
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
```

### Step 1.2: Write failing tests for `calculate_ferrous_iron_yield_h2`

- [ ] Add these tests at the bottom of the file (they will fail because the function doesn't exist yet):

```python
# --- Ferrous Iron Yield — H2 tests ---

from backend.services.calculations.scalar_calcs import (
    calculate_ferrous_iron_yield_h2,
    calculate_ferrous_iron_yield_nh3,
)


def test_ferrous_iron_yield_h2_regression():
    """Regression: 1,000 µmol H2 with 1.0 g total_ferrous_iron → 16.75%.

    Fe2+_consumed_g = (1000 * 3 / 1e6) * 55.845 = 0.167535
    yield = (0.167535 / 1.0) * 100 = 16.7535%
    """
    result = calculate_ferrous_iron_yield_h2(
        h2_micromoles=1000.0,
        total_ferrous_iron_g=1.0,
    )
    assert result == pytest.approx(16.7535, rel=1e-4)


def test_ferrous_iron_yield_h2_none_when_no_h2():
    result = calculate_ferrous_iron_yield_h2(
        h2_micromoles=None,
        total_ferrous_iron_g=1.0,
    )
    assert result is None


def test_ferrous_iron_yield_h2_none_when_no_total_fe():
    result = calculate_ferrous_iron_yield_h2(
        h2_micromoles=1000.0,
        total_ferrous_iron_g=None,
    )
    assert result is None


def test_ferrous_iron_yield_h2_none_when_total_fe_zero():
    result = calculate_ferrous_iron_yield_h2(
        h2_micromoles=1000.0,
        total_ferrous_iron_g=0.0,
    )
    assert result is None


def test_ferrous_iron_yield_h2_none_when_total_fe_negative():
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
    """When background is None, defaults to 0.3 mM — same result as explicit 0.3 mM."""
    result_explicit = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=10.0,
        background_ammonium_mM=0.3,
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
    result = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=0.1,
        background_ammonium_mM=0.5,
        solution_volume_mL=100.0,
        total_ferrous_iron_g=1.0,
    )
    assert result == pytest.approx(0.0)


def test_ferrous_iron_yield_nh3_none_when_no_gross_ammonium():
    result = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=None,
        background_ammonium_mM=None,
        solution_volume_mL=100.0,
        total_ferrous_iron_g=1.0,
    )
    assert result is None


def test_ferrous_iron_yield_nh3_none_when_no_volume():
    result = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=10.0,
        background_ammonium_mM=None,
        solution_volume_mL=None,
        total_ferrous_iron_g=1.0,
    )
    assert result is None


def test_ferrous_iron_yield_nh3_none_when_no_total_fe():
    result = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=10.0,
        background_ammonium_mM=None,
        solution_volume_mL=100.0,
        total_ferrous_iron_g=None,
    )
    assert result is None


def test_ferrous_iron_yield_nh3_none_when_zero_volume():
    result = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=10.0,
        background_ammonium_mM=None,
        solution_volume_mL=0.0,
        total_ferrous_iron_g=1.0,
    )
    assert result is None
```

### Step 1.3: Write integration tests for `recalculate_scalar` wiring

These test that `recalculate_scalar` populates the new yield fields on the instance when conditions provide `total_ferrous_iron`:

```python
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
```

### Step 1.4: Run tests to confirm they fail

- [ ] Run: `pytest tests/services/calculations/test_scalar_calcs.py -v -k "ferrous_iron"`

Expected: `ImportError` or `AttributeError` — function/attribute not yet defined.

- [ ] Commit the failing tests:

```bash
git add tests/services/calculations/test_scalar_calcs.py
git commit -m "[#3] TDD: add failing tests for ferrous iron yield calculations"
```

---

## Task 2: Implement Formula Functions in `scalar_calcs.py`

**Files:**
- Modify: `backend/services/calculations/scalar_calcs.py`

### Step 2.1: Add constants and pure formula functions

- [ ] Open `backend/services/calculations/scalar_calcs.py`
- [ ] Add the molar mass constant and two pure functions **before** `@register(ScalarResults)`:

```python
FE_MOLAR_MASS = 55.845  # g/mol


def calculate_ferrous_iron_yield_h2(
    h2_micromoles: float | None,
    total_ferrous_iron_g: float | None,
) -> float | None:
    """H2-derived ferrous iron yield (%).

    Stoichiometry: 3 mol Fe2+ per 1 mol H2

        Fe2+_consumed_g = (h2_micromoles * 3 / 1e6) * FE_MOLAR_MASS
        yield_h2_pct    = (Fe2+_consumed_g / total_ferrous_iron_g) * 100

    Returns None if h2_micromoles is None or total_ferrous_iron_g is None or <= 0.
    """
    if h2_micromoles is None or total_ferrous_iron_g is None or total_ferrous_iron_g <= 0:
        return None
    fe2_consumed_g = (h2_micromoles * 3 / 1_000_000) * FE_MOLAR_MASS
    return (fe2_consumed_g / total_ferrous_iron_g) * 100


def calculate_ferrous_iron_yield_nh3(
    gross_ammonium_mM: float | None,
    background_ammonium_mM: float | None,
    solution_volume_mL: float | None,
    total_ferrous_iron_g: float | None,
) -> float | None:
    """NH3-derived ferrous iron yield (%).

    Stoichiometry: 9 mol Fe2+ per 2 mol NH3 (ratio = 4.5)

        net_ammonium_mM  = max(0, gross_ammonium_mM - background_ammonium_mM)
                           [background defaults to 0.3 mM if None]
        total_NH3_mol    = (net_ammonium_mM / 1000) * (solution_volume_mL / 1000)
        Fe2+_consumed_g  = total_NH3_mol * 4.5 * FE_MOLAR_MASS
        yield_nh3_pct    = (Fe2+_consumed_g / total_ferrous_iron_g) * 100

    Returns None if gross_ammonium_mM, solution_volume_mL, or total_ferrous_iron_g
    is None or <= 0.
    """
    if (
        gross_ammonium_mM is None
        or solution_volume_mL is None
        or solution_volume_mL <= 0
        or total_ferrous_iron_g is None
        or total_ferrous_iron_g <= 0
    ):
        return None
    bg = background_ammonium_mM if background_ammonium_mM is not None else 0.3
    net_mM = max(0.0, gross_ammonium_mM - bg)
    total_nh3_mol = (net_mM / 1000.0) * (solution_volume_mL / 1000.0)
    fe2_consumed_g = total_nh3_mol * 4.5 * FE_MOLAR_MASS
    return (fe2_consumed_g / total_ferrous_iron_g) * 100
```

### Step 2.2: Run the pure-function tests

- [ ] Run: `pytest tests/services/calculations/test_scalar_calcs.py -v -k "yield_h2 or yield_nh3"`

Expected: all pure-function tests (`test_ferrous_iron_yield_h2_*` and `test_ferrous_iron_yield_nh3_*`) pass. Integration tests (`test_recalculate_scalar_*ferrous*`) still fail because wiring isn't done yet.

---

## Task 3: Wire Formulas into `recalculate_scalar`

**Files:**
- Modify: `backend/services/calculations/scalar_calcs.py`

The existing handler (`recalculate_scalar`) already resolves `liquid_volume_ml` and reads conditions via the `result_entry → experiment → conditions` chain. Extend it to also read `total_ferrous_iron` from conditions and call both new formula functions.

### Step 3.1: Extend `recalculate_scalar` to call both formula functions

- [ ] In `recalculate_scalar`, after the existing `liquid_volume_ml` resolution block (lines 17–31), add:

```python
    total_ferrous_iron_g: float | None = None
    if result_entry is not None:
        experiment = getattr(result_entry, 'experiment', None)
        if experiment is not None:
            conditions = getattr(experiment, 'conditions', None)
            if conditions is not None:
                total_ferrous_iron_g = getattr(conditions, 'total_ferrous_iron', None)
```

- [ ] At the bottom of `recalculate_scalar` (after the existing ammonium yield block), add:

```python
    # Ferrous iron yield — H2 derived
    h2_micromoles = getattr(instance, 'h2_micromoles', None)
    instance.ferrous_iron_yield_h2_pct = calculate_ferrous_iron_yield_h2(
        h2_micromoles=h2_micromoles,
        total_ferrous_iron_g=total_ferrous_iron_g,
    )

    # Ferrous iron yield — NH3 derived
    gross = getattr(instance, 'gross_ammonium_concentration_mM', None)
    bg_nh3 = getattr(instance, 'background_ammonium_concentration_mM', None)
    instance.ferrous_iron_yield_nh3_pct = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=gross,
        background_ammonium_mM=bg_nh3,
        solution_volume_mL=liquid_volume_ml,
        total_ferrous_iron_g=total_ferrous_iron_g,
    )
```

**Note:** `h2_micromoles` is read **after** `_calculate_hydrogen(instance)` is called (line 35), so it reflects the freshly computed value. The existing `liquid_volume_ml` (already resolved with sampling_volume_mL preference + water_volume_mL fallback) is reused as `solution_volume_mL` — this is identical to the fallback logic in `grams_per_ton_yield`. Do not duplicate the resolution logic.

### Step 3.2: Run all scalar tests

- [ ] Run: `pytest tests/services/calculations/test_scalar_calcs.py -v`

Expected: all tests pass (including the 4 new integration tests).

- [ ] Commit:

```bash
git add backend/services/calculations/scalar_calcs.py
git commit -m "[#3] Add ferrous iron yield formula functions and wire into recalculate_scalar"
```

---

## Task 4: Add Conditions → Scalar Propagation

**Files:**
- Modify: `backend/services/calculations/conditions_calcs.py`

Currently `recalculate_conditions` only updates `water_to_rock_ratio` on the conditions instance itself. It does **not** propagate to linked `ScalarResults`. When `total_ferrous_iron` is updated via PATCH `/api/conditions/{id}`, any existing scalar results won't be recalculated unless we add this propagation.

**Implementation approach:** Use a lazy import of `recalculate_scalar` directly (not via registry dispatch). The registry dispatch (`recalculate(scalar, session)`) would be a no-op in tests because `SimpleNamespace` is not a registered type. A direct call to `recalculate_scalar` is explicit, testable, and avoids import-order issues at module load time.

### Step 4.1: Write a test for conditions propagation

Add to `tests/services/calculations/test_scalar_calcs.py` — this test uses `recalculate_scalar` directly (imported via the propagation path), so it works with `SimpleNamespace`. Place it in a new file to keep concerns clean:

- [ ] Create `tests/services/calculations/test_conditions_propagation.py`:

```python
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
```

- [ ] Run: `pytest tests/services/calculations/test_conditions_propagation.py -v`

Expected: all 4 tests FAIL (propagation not yet implemented).

### Step 4.2: Implement propagation in `conditions_calcs.py`

- [ ] Open `backend/services/calculations/conditions_calcs.py`
- [ ] **No new top-level imports needed.** Add the propagation block at the bottom of `recalculate_conditions`, after the `water_to_rock_ratio` assignment. Use a lazy import inside the function body to avoid circular import issues at module load time:

```python
    # Propagate to all linked ScalarResults so that changes to total_ferrous_iron
    # (and rock_mass_g / water_volume_mL) are reflected in previously-stored scalar results.
    # Lazy import avoids load-time circular import: conditions_calcs ← scalar_calcs.
    from backend.services.calculations.scalar_calcs import recalculate_scalar
    experiment = getattr(instance, 'experiment', None)
    if experiment is not None:
        for result in getattr(experiment, 'results', None) or []:
            scalar = getattr(result, 'scalar_data', None)
            if scalar is not None:
                recalculate_scalar(scalar, session)
```

### Step 4.3: Verify propagation tests pass

- [ ] Run: `pytest tests/services/calculations/test_conditions_propagation.py -v`

Expected: all 4 pass.

- [ ] Run full calculation suite to confirm no regressions:

```bash
pytest tests/services/calculations/ -v
```

Expected: all tests pass.

- [ ] Commit:

```bash
git add backend/services/calculations/conditions_calcs.py tests/services/calculations/test_conditions_propagation.py
git commit -m "[#3] Propagate conditions recalculation to linked scalar results"
```

---

## Task 5: Schema Changes — Add Columns

**Files:**
- Modify: `database/models/conditions.py`
- Modify: `database/models/results.py`

These are **locked models** but the change is purely additive (new nullable columns only — no field names, types, or relationships modified).

### Step 5.1: Add `total_ferrous_iron` to `ExperimentalConditions`

- [ ] Open `database/models/conditions.py`
- [ ] After line 57 (`initial_alkalinity = Column(Float, nullable=True)`), add:

```python
    total_ferrous_iron = Column(Float, nullable=True)  # grams of initial Fe(II) in the system
```

### Step 5.2: Add yield columns to `ScalarResults`

- [ ] Open `database/models/results.py`
- [ ] After line 99 (`h2_grams_per_ton_yield = Column(Float, nullable=True)`), add:

```python
    # Ferrous iron yield derived from H2 and NH3 measurements
    ferrous_iron_yield_h2_pct = Column(Float, nullable=True)   # H2-derived Fe(II) yield (%)
    ferrous_iron_yield_nh3_pct = Column(Float, nullable=True)  # NH3-derived Fe(II) yield (%)
```

---

## Task 6: Alembic Migration

**Files:**
- Create: `alembic/versions/<hash>_add_ferrous_iron_yield_columns.py`

### Step 6.1: Generate the migration

- [ ] Run (from project root, using the venv):

```bash
.venv/Scripts/alembic revision --autogenerate -m "add ferrous iron yield columns"
```

- [ ] Open the generated file in `alembic/versions/`
- [ ] Verify it contains **exactly** these operations in `upgrade()`:
  - `op.add_column('experimental_conditions', sa.Column('total_ferrous_iron', sa.Float(), nullable=True))`
  - `op.add_column('scalar_results', sa.Column('ferrous_iron_yield_h2_pct', sa.Float(), nullable=True))`
  - `op.add_column('scalar_results', sa.Column('ferrous_iron_yield_nh3_pct', sa.Float(), nullable=True))`
- [ ] Verify `downgrade()` has the corresponding `op.drop_column` calls for all three
- [ ] If autogenerate includes anything else (e.g., index changes, view recreation), remove it — keep migration minimal

### Step 6.2: Apply and test the migration round-trip

- [ ] Apply: `.venv/Scripts/alembic upgrade head`
- [ ] Downgrade: `.venv/Scripts/alembic downgrade -1`
- [ ] Re-apply: `.venv/Scripts/alembic upgrade head`

Expected: all three commands succeed with no errors.

- [ ] Commit:

```bash
git add alembic/versions/
git commit -m "[#3] Add migration: total_ferrous_iron, ferrous_iron_yield_h2_pct, ferrous_iron_yield_nh3_pct"
```

---

## Task 7: Update Pydantic Schemas

**Files:**
- Modify: `backend/api/schemas/conditions.py`
- Modify: `backend/api/schemas/results.py`

### Step 7.1: Add `total_ferrous_iron` to conditions schemas

- [ ] Open `backend/api/schemas/conditions.py`

In `ConditionsCreate` (after `initial_alkalinity`):
```python
    total_ferrous_iron: Optional[float] = None
```

In `ConditionsUpdate` (after `initial_alkalinity`):
```python
    total_ferrous_iron: Optional[float] = None
```

In `ConditionsResponse` (after `initial_alkalinity`, before `created_at`):
```python
    total_ferrous_iron: Optional[float] = None
```

### Step 7.2: Add yield fields to `ScalarResponse`

- [ ] Open `backend/api/schemas/results.py`

In `ScalarResponse` (after `h2_grams_per_ton_yield: Optional[float] = None`, before `co2_partial_pressure_MPa`):
```python
    ferrous_iron_yield_h2_pct: Optional[float] = None
    ferrous_iron_yield_nh3_pct: Optional[float] = None
```

These are **read-only derived fields** — do not add them to `ScalarCreate` or `ScalarUpdate`.

### Step 7.3: Verify schema changes with import test

- [ ] Run: `python -c "from backend.api.schemas.conditions import ConditionsCreate, ConditionsUpdate, ConditionsResponse; from backend.api.schemas.results import ScalarResponse; print('OK')"`

Expected: `OK` printed, no import errors.

- [ ] Run API test suite: `pytest tests/api/ -v`

Expected: all existing API tests pass. No 422 validation errors or schema mismatches.

- [ ] Commit:

```bash
git add backend/api/schemas/conditions.py backend/api/schemas/results.py
git commit -m "[#3] Add total_ferrous_iron and yield fields to Pydantic schemas"
```

---

## Task 8: Update `docs/CALCULATIONS.md`

**Files:**
- Modify: `docs/CALCULATIONS.md`

### Step 8.1: Add new formula sections

- [ ] Open `docs/CALCULATIONS.md`
- [ ] After the `### Hydrogen Yield` section (line ~137), add before `---\n\n## Utility Functions`:

```markdown
### Ferrous Iron Yield — H₂ Derived (`ferrous_iron_yield_h2_pct`)

Stoichiometry: 3 mol Fe²⁺ per 1 mol H₂

```
Fe²⁺_consumed_g = (h2_micromoles × 3 / 1,000,000) × 55.845
yield_h2_pct    = (Fe²⁺_consumed_g / total_ferrous_iron_g) × 100
```

- Reads `h2_micromoles` (already computed from H₂ gas inputs — see above)
- Reads `total_ferrous_iron` from `ExperimentalConditions` via `result_entry → experiment → conditions`
- Set to `None` if `h2_micromoles` is `None` or `total_ferrous_iron` is `None` or ≤ 0

**Verification:** 1,000 µmol H₂ with 1.0 g `total_ferrous_iron` → (0.003 mol × 55.845) / 1.0 × 100 = **16.75%**

### Ferrous Iron Yield — NH₃ Derived (`ferrous_iron_yield_nh3_pct`)

Stoichiometry: 9 mol Fe²⁺ per 2 mol NH₃ (ratio = 4.5)

```
net_ammonium_mM  = max(0, gross_ammonium_concentration_mM − background_ammonium_concentration_mM)
                   [background defaults to 0.3 mM if not provided]
total_NH3_mol    = (net_ammonium_mM / 1000) × (solution_volume_mL / 1000)
Fe²⁺_consumed_g  = total_NH3_mol × 4.5 × 55.845
yield_nh3_pct    = (Fe²⁺_consumed_g / total_ferrous_iron_g) × 100
```

- `solution_volume_mL`: prefers `sampling_volume_mL`; falls back to `water_volume_mL` from conditions
  (identical fallback chain as `grams_per_ton_yield`)
- Set to `None` if `gross_ammonium_concentration_mM`, `solution_volume_mL`, or `total_ferrous_iron` is `None` or ≤ 0
- Net concentration clamped to ≥ 0

**Verification:** 10 mM gross (0.3 mM background), 100 mL, 1.0 g `total_ferrous_iron` →
0.00097 mol × 4.5 × 55.845 / 1.0 × 100 = **24.38%**

> Note: legacy `ferrous_iron_yield` column (manual-entry, deprecated) remains in the schema for
> backward data compatibility but is excluded from new calculations and UI forms.
```

- [ ] Commit:

```bash
git add docs/CALCULATIONS.md
git commit -m "[#3] Document ferrous iron yield formula functions in CALCULATIONS.md

- Tests added: yes
- Docs updated: yes"
```

---

## Task 9: Final Verification

### Step 9.1: Run complete test suite

- [ ] Run: `pytest tests/services/calculations/ tests/api/ -v`

Expected: all tests pass. Note existing known xfails (`tests/test_icp_service.py`, etc.) are pre-existing and unrelated.

### Step 9.2: Verify acceptance criteria manually

Walk through each acceptance criterion from the issue:

- [ ] `alembic upgrade head` succeeds
- [ ] `alembic downgrade -1` succeeds
- [ ] `alembic upgrade head` succeeds again
- [ ] H₂ regression: 1,000 µmol H₂, `total_ferrous_iron = 1.0 g` → `ferrous_iron_yield_h2_pct ≈ 16.75` (covered by `test_ferrous_iron_yield_h2_regression`)
- [ ] NH₃ regression: 10 mM gross (0.3 mM background), 100 mL, `total_ferrous_iron = 1.0 g` → `ferrous_iron_yield_nh3_pct` matches expected formula output (covered by `test_ferrous_iron_yield_nh3_regression`)
- [ ] Both fields `None` when `total_ferrous_iron` not set (covered by `test_*_none_when_no_total_fe` tests)
- [ ] `ferrous_iron_yield_h2_pct` is `None` when `h2_micromoles` is `None` (covered by test)
- [ ] `ferrous_iron_yield_nh3_pct` is `None` when ammonium or volume missing (covered by tests)
- [ ] Conditions PATCH triggers scalar recalculation (covered by `test_conditions_propagation.py`)
- [ ] Both fields appear in `ScalarResponse` schema (verified in Task 7)
- [ ] `docs/CALCULATIONS.md` updated (Task 8)
- [ ] Formula functions have ≥ 80% test coverage (11 new tests cover all branches)

---

## Out of Scope (Do Not Implement)

- React UI for `total_ferrous_iron` input — tracked separately in M5 Conditions form
- Display of yield fields in Experiment Detail results tab — M5 Results view
- Power BI view update — requires schema migration to be deployed first
- Backfill of existing records — admin recalculation endpoint handles this post-deployment
- Deprecation of legacy `ferrous_iron_yield` column — tracked separately
