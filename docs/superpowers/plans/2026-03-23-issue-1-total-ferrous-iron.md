# Issue #1 — Total Ferrous Iron Derived Field Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `total_ferrous_iron_g` derived field to `ExperimentalConditions` by querying FeO wt% from pre-experiment rock characterization and computing Fe mass from `rock_mass_g`.

**Architecture:** New `backend/services/elemental_composition_service.py` holds the pure calculation and DB lookup. The existing `conditions_calcs.py` is extended to call the service and write the result into `total_ferrous_iron_g`. The conditions router already fires `recalculate()` after every write — no router changes needed. Schema change is additive only.

**Tech Stack:** SQLAlchemy 2.x (`session.get`, `session.execute(select(...))`), Pydantic v2, pytest with `unittest.mock.MagicMock` for service unit tests and real PostgreSQL `experiments_test` for API tests.

**Closes:** [GitHub Issue #1](https://github.com/mathew-h/experiment-tracking-sandbox/issues/1)

---

## File Map

**Create:**
- `backend/services/elemental_composition_service.py` — `FE_IN_FEO_FRACTION` constant, `calculate_total_ferrous_iron_g` (pure), `get_analyte_wt_pct` (DB lookup)
- `tests/services/test_elemental_composition_service.py` — pure + mock-DB unit tests

**Modify:**
- `database/models/conditions.py` — add `total_ferrous_iron_g = Column(Float, nullable=True)`
- `alembic/versions/<hash>_add_total_ferrous_iron_g_to_conditions.py` — new additive migration
- `backend/api/schemas/conditions.py` — add `total_ferrous_iron_g: Optional[float] = None` to `ConditionsResponse`
- `backend/services/calculations/conditions_calcs.py` — extend `recalculate_conditions` with new field
- `tests/services/calculations/test_conditions_calcs.py` — update `make_conditions`/`SESSION`; add new field tests
- `tests/api/test_conditions.py` — add integration tests for `total_ferrous_iron_g`
- `docs/CALCULATIONS.md` — add Characterization-Derived Fields section

---

## Task 1: Pure Calculation Function + Service Skeleton

**Files:**
- Create: `backend/services/elemental_composition_service.py`
- Create: `tests/services/test_elemental_composition_service.py`

- [ ] **Step 1: Write failing tests for `calculate_total_ferrous_iron_g`**

```python
# tests/services/test_elemental_composition_service.py
import pytest
from backend.services.elemental_composition_service import (
    calculate_total_ferrous_iron_g,
    FE_IN_FEO_FRACTION,
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
```

- [ ] **Step 2: Run — expect ImportError**

```
.venv/Scripts/pytest tests/services/test_elemental_composition_service.py -v
```

Expected: `ImportError: cannot import name 'calculate_total_ferrous_iron_g'`

- [ ] **Step 3: Create `backend/services/elemental_composition_service.py` with constant and pure function**

```python
# backend/services/elemental_composition_service.py
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

log = structlog.get_logger(__name__)

# Fe atomic mass (55.845) / FeO molar mass (71.844)
FE_IN_FEO_FRACTION: float = 55.845 / 71.844


def calculate_total_ferrous_iron_g(
    feo_wt_pct: float | None,
    rock_mass_g: float | None,
) -> float | None:
    """Compute total ferrous iron mass in grams from FeO wt% and rock mass.

    Formula:
        fe_mass_fraction = (feo_wt_pct / 100) * FE_IN_FEO_FRACTION
        total_ferrous_iron_g = fe_mass_fraction * rock_mass_g

    Returns None when any required input is missing or rock_mass_g <= 0.
    """
    if feo_wt_pct is None or rock_mass_g is None:
        return None
    if rock_mass_g <= 0:
        log.warning("total_ferrous_iron_g_skipped", reason="rock_mass_g <= 0", rock_mass_g=rock_mass_g)
        return None
    return (feo_wt_pct / 100.0) * FE_IN_FEO_FRACTION * rock_mass_g
```

`select` and `Session` are imported here even though Task 1 only uses the pure function — Task 2 adds `get_analyte_wt_pct` without reshuffling imports. If you run Task 1’s tests alone, those two imports are unused until Task 2 lands.

- [ ] **Step 4: Run — expect all 7 tests PASS**

```
.venv/Scripts/pytest tests/services/test_elemental_composition_service.py -v
```

- [ ] **Step 5: Commit**

```
git add backend/services/elemental_composition_service.py tests/services/test_elemental_composition_service.py
git commit -m "[Issue #1] Task 1: FE_IN_FEO_FRACTION + calculate_total_ferrous_iron_g + tests"
```

---

## Task 2: DB Lookup Function (`get_analyte_wt_pct`)

**`analysis_type` (production):** Wide-format elemental Excel uploads (`ElementalCompositionService` in `actlabs_titration_data.py`) store `ExternalAnalysis.analysis_type == "Bulk Elemental Composition"`. Actlabs titration uploads use `"Elemental"`. The lookup must accept **both** strings; filtering on `"Elemental"` alone misses the main pre-experiment FeO path.

**Files:**
- Modify: `backend/services/elemental_composition_service.py`
- Modify: `tests/services/test_elemental_composition_service.py`

- [ ] **Step 1: Add mock-DB tests to the test file**

Append these tests below the existing ones:

```python
# append to tests/services/test_elemental_composition_service.py
from unittest.mock import MagicMock
from backend.services.elemental_composition_service import get_analyte_wt_pct


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
    # Verify the query was called (analyte_symbol binding is inside SQLAlchemy — just assert called)
    session.execute.assert_called_once()
```

- [ ] **Step 2: Run — expect 4 new ImportErrors/failures**

```
.venv/Scripts/pytest tests/services/test_elemental_composition_service.py -v
```

Expected: `ImportError: cannot import name 'get_analyte_wt_pct'`

- [ ] **Step 3: Add `get_analyte_wt_pct` to the service file**

Append this function after `calculate_total_ferrous_iron_g`:

```python
def get_analyte_wt_pct(
    sample_id: str | None,
    db: Session,
    analyte_symbol: str = "FeO",
) -> float | None:
    """Return the wt% composition for analyte_symbol from the most recent
    elemental characterization ExternalAnalysis linked to sample_id.

    Matches analysis_type in ('Elemental', 'Bulk Elemental Composition') — the
    titration uploader vs wide-format bulk elemental Excel uploader respectively.

    Returns analyte_composition (float) from ElementalAnalysis, or None if:
    - sample_id is None
    - No matching ExternalAnalysis exists for the sample
    - No ElementalAnalysis row exists for the given analyte_symbol with unit '%'
    - analyte_composition is NULL

    When multiple ExternalAnalysis records exist for the same sample and analyte,
    the most recent by analysis_date is used.
    """
    if sample_id is None:
        return None

    from database.models.analysis import ExternalAnalysis
    from database.models.characterization import ElementalAnalysis, Analyte

    result = db.execute(
        select(ElementalAnalysis.analyte_composition)
        .join(ExternalAnalysis, ElementalAnalysis.external_analysis_id == ExternalAnalysis.id)
        .join(Analyte, ElementalAnalysis.analyte_id == Analyte.id)
        .where(ExternalAnalysis.sample_id == sample_id)
        .where(
            ExternalAnalysis.analysis_type.in_(["Elemental", "Bulk Elemental Composition"])
        )
        .where(Analyte.analyte_symbol == analyte_symbol)
        .where(Analyte.unit == "%")
        .order_by(ExternalAnalysis.analysis_date.desc())
        .limit(1)
    ).scalar_one_or_none()

    return result
```

- [ ] **Step 4: Run — expect all 11 tests PASS**

```
.venv/Scripts/pytest tests/services/test_elemental_composition_service.py -v
```

- [ ] **Step 5: Commit**

```
git add backend/services/elemental_composition_service.py tests/services/test_elemental_composition_service.py
git commit -m "[Issue #1] Task 2: get_analyte_wt_pct DB lookup + mock tests"
```

---

## Task 3: Schema Change + Alembic Migration

**Files:**
- Modify: `database/models/conditions.py`
- Create: new file in `alembic/versions/`

- [ ] **Step 1: Add `total_ferrous_iron_g` column to `ExperimentalConditions`**

In `database/models/conditions.py`, add the new column after `water_to_rock_ratio` (line 33):

```python
    water_to_rock_ratio = Column(Float, nullable=True)
    total_ferrous_iron_g = Column(Float, nullable=True)  # Derived: (FeO wt% / 100) * FE_IN_FEO_FRACTION * rock_mass_g
```

- [ ] **Step 2: Generate the migration**

```
.venv/Scripts/alembic revision --autogenerate -m "add total_ferrous_iron_g to experimental_conditions"
```

- [ ] **Step 3: Open the generated file in `alembic/versions/` and verify it looks like this**

```python
def upgrade() -> None:
    op.add_column(
        "experimental_conditions",
        sa.Column("total_ferrous_iron_g", sa.Float(), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("experimental_conditions", "total_ferrous_iron_g")
```

If the autogenerated content is wrong (e.g., it tries to drop/rename other columns), **stop and investigate** before running. Autogenerate can detect unrelated drift.

- [ ] **Step 4: Apply migration to dev DB**

```
.venv/Scripts/alembic upgrade head
```

Expected: migration runs without error.

- [ ] **Step 5: Test downgrade then re-upgrade**

```
.venv/Scripts/alembic downgrade -1
.venv/Scripts/alembic upgrade head
```

Both must succeed without error.

- [ ] **Step 6: Confirm test DB has the new column**

**Primary path:** Run the API test suite (or any flow that uses `create_test_tables` / `Base.metadata.create_all()`). That path picks up the new column from the SQLAlchemy model without a separate Alembic run against `experiments_test`.

**Optional — migrate `experiments_test` with Alembic:** `alembic/env.py` reads **`DATABASE_URL`** (not `SQLALCHEMY_DATABASE_URL`). Example (PowerShell):

```
$env:DATABASE_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"
.venv/Scripts/alembic upgrade head
```

Skip this if your workflow relies only on metadata `create_all` for tests.

- [ ] **Step 7: Commit**

```
git add database/models/conditions.py alembic/versions/
git commit -m "[Issue #1] Task 3: add total_ferrous_iron_g column + Alembic migration"
```

---

## Task 4: Pydantic Schema Update

**Files:**
- Modify: `backend/api/schemas/conditions.py`

- [ ] **Step 1: Add `total_ferrous_iron_g` to `ConditionsResponse`**

In `backend/api/schemas/conditions.py`, add to `ConditionsResponse` after `water_to_rock_ratio`:

```python
    water_to_rock_ratio: Optional[float] = None
    total_ferrous_iron_g: Optional[float] = None
```

Do **not** add it to `ConditionsCreate` or `ConditionsUpdate` — this field is derived and must never be set directly by the caller.

- [ ] **Step 2: Run schema tests to confirm no regressions**

```
.venv/Scripts/pytest tests/api/test_schemas.py -v
```

Expected: all pass.

- [ ] **Step 3: Commit**

```
git add backend/api/schemas/conditions.py
git commit -m "[Issue #1] Task 4: add total_ferrous_iron_g to ConditionsResponse schema"
```

---

## Task 5: Wire into the Calculation Engine

**Files:**
- Modify: `backend/services/calculations/conditions_calcs.py`
- Modify: `tests/services/calculations/test_conditions_calcs.py`

- [ ] **Step 1: Update the test helper to support the new session requirement**

The current `test_conditions_calcs.py` uses `SESSION = types.SimpleNamespace()` (no methods). The updated `recalculate_conditions` will call `session.get(Experiment, ...)`. Update the test file so all tests pass correctly:

Replace the top of `tests/services/calculations/test_conditions_calcs.py`:

```python
import types
import pytest
from unittest.mock import MagicMock
from backend.services.calculations import conditions_calcs  # noqa: F401 — triggers register
from backend.services.calculations.conditions_calcs import recalculate_conditions


def make_conditions(**kwargs):
    """Minimal ExperimentalConditions-like namespace."""
    defaults = {
        "experiment_fk": None,
        "water_volume_mL": None,
        "rock_mass_g": None,
        "water_to_rock_ratio": None,
        "total_ferrous_iron_g": None,
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def make_session(experiment_sample_id=None, feo_wt_pct=None):
    """Mock session. get() returns a stub Experiment; execute() returns feo_wt_pct."""
    session = MagicMock()
    if experiment_sample_id is not None:
        exp_stub = types.SimpleNamespace(sample_id=experiment_sample_id)
        session.get.return_value = exp_stub
    else:
        session.get.return_value = None
    session.execute.return_value.scalar_one_or_none.return_value = feo_wt_pct
    return session
```

- [ ] **Step 2: Update the four existing tests to use `make_session()`**

Replace `recalculate_conditions(cond, SESSION)` with `recalculate_conditions(cond, make_session())` in all four existing tests. They use `experiment_fk=None` (default) so `session.get()` returns `None` and `total_ferrous_iron_g` stays `None`.

```python
def test_water_to_rock_ratio_computed():
    cond = make_conditions(water_volume_mL=500.0, rock_mass_g=10.0)
    recalculate_conditions(cond, make_session())
    assert cond.water_to_rock_ratio == pytest.approx(50.0)


def test_water_to_rock_ratio_zero_rock_mass_is_none():
    cond = make_conditions(water_volume_mL=500.0, rock_mass_g=0.0)
    recalculate_conditions(cond, make_session())
    assert cond.water_to_rock_ratio is None


def test_water_to_rock_ratio_missing_volume_is_none():
    cond = make_conditions(water_volume_mL=None, rock_mass_g=10.0)
    recalculate_conditions(cond, make_session())
    assert cond.water_to_rock_ratio is None


def test_water_to_rock_ratio_missing_rock_mass_is_none():
    cond = make_conditions(water_volume_mL=500.0, rock_mass_g=None)
    recalculate_conditions(cond, make_session())
    assert cond.water_to_rock_ratio is None
```

- [ ] **Step 3: Add new tests for `total_ferrous_iron_g`**

Append to the same test file:

```python
def test_total_ferrous_iron_g_computed():
    """Full happy path: sample has FeO → field is populated."""
    cond = make_conditions(experiment_fk=1, rock_mass_g=5.0)
    session = make_session(experiment_sample_id="SAMPLE-001", feo_wt_pct=10.0)
    recalculate_conditions(cond, session)
    assert cond.total_ferrous_iron_g == pytest.approx(0.38866, rel=1e-3)


def test_total_ferrous_iron_g_no_sample_on_experiment():
    """Experiment exists but has no sample_id → field is None."""
    session = MagicMock()
    session.get.return_value = types.SimpleNamespace(sample_id=None)
    session.execute.return_value.scalar_one_or_none.return_value = None
    cond = make_conditions(experiment_fk=1, rock_mass_g=5.0)
    recalculate_conditions(cond, session)
    assert cond.total_ferrous_iron_g is None


def test_total_ferrous_iron_g_experiment_not_found():
    """No Experiment row in DB → field is None."""
    cond = make_conditions(experiment_fk=99, rock_mass_g=5.0)
    session = make_session(experiment_sample_id=None, feo_wt_pct=None)
    recalculate_conditions(cond, session)
    assert cond.total_ferrous_iron_g is None


def test_total_ferrous_iron_g_no_feo_analysis():
    """Sample exists but has no FeO ElementalAnalysis → field is None."""
    cond = make_conditions(experiment_fk=1, rock_mass_g=5.0)
    session = make_session(experiment_sample_id="SAMPLE-001", feo_wt_pct=None)
    recalculate_conditions(cond, session)
    assert cond.total_ferrous_iron_g is None
```

- [ ] **Step 4: Run BEFORE implementing Step 5 — expect 4 old tests pass, 4 new tests fail**

```
.venv/Scripts/pytest tests/services/calculations/test_conditions_calcs.py -v
```

Expected: the 4 existing `water_to_rock_ratio` tests pass; the 4 new `total_ferrous_iron_g` tests fail (field stays `None` because the old implementation doesn't set it).

- [ ] **Step 5: Update `conditions_calcs.py` to compute `total_ferrous_iron_g`**

```python
# backend/services/calculations/conditions_calcs.py
from __future__ import annotations

from sqlalchemy.orm import Session
from backend.services.calculations.registry import register
from backend.services.elemental_composition_service import (
    calculate_total_ferrous_iron_g,
    get_analyte_wt_pct,
)
from database.models.conditions import ExperimentalConditions


@register(ExperimentalConditions)
def recalculate_conditions(instance: ExperimentalConditions, session: Session) -> None:
    """Recalculate derived fields on ExperimentalConditions.

    Derived fields:
    - water_to_rock_ratio = water_volume_mL / rock_mass_g
    - total_ferrous_iron_g = (FeO wt% / 100) * FE_IN_FEO_FRACTION * rock_mass_g
      where FeO wt% is looked up from the most recent elemental characterization
      ExternalAnalysis (`Elemental` or `Bulk Elemental Composition`) for the
      experiment's sample.
    """
    water_vol = instance.water_volume_mL
    rock_mass = instance.rock_mass_g

    # water_to_rock_ratio
    if water_vol is not None and rock_mass is not None and rock_mass > 0:
        instance.water_to_rock_ratio = water_vol / rock_mass
    else:
        instance.water_to_rock_ratio = None

    # total_ferrous_iron_g: resolve sample_id through the parent Experiment
    from database.models.experiments import Experiment  # local import avoids circular import risk

    sample_id = None
    if instance.experiment_fk is not None:
        experiment = session.get(Experiment, instance.experiment_fk)
        if experiment is not None:
            sample_id = experiment.sample_id

    feo_wt_pct = get_analyte_wt_pct(sample_id=sample_id, db=session)
    instance.total_ferrous_iron_g = calculate_total_ferrous_iron_g(
        feo_wt_pct=feo_wt_pct,
        rock_mass_g=rock_mass,
    )
```

- [ ] **Step 6: Run — expect all 8 tests PASS**

```
.venv/Scripts/pytest tests/services/calculations/test_conditions_calcs.py -v
```

- [ ] **Step 7: Run the full service test suite — no regressions**

```
.venv/Scripts/pytest tests/services/ -v
```

- [ ] **Step 8: Commit**

```
git add backend/services/calculations/conditions_calcs.py tests/services/calculations/test_conditions_calcs.py
git commit -m "[Issue #1] Task 5: wire total_ferrous_iron_g into conditions calc engine"
```

---

## Task 6: API Integration Tests

**Files:**
- Modify: `tests/api/test_conditions.py`

These tests use the real `experiments_test` PostgreSQL DB (via `client` + `db_session` fixtures).

- [ ] **Step 1: Add helper and two new integration tests to `tests/api/test_conditions.py`**

Append to the file:

```python
from database.models.samples import SampleInfo
from database.models.analysis import ExternalAnalysis
from database.models.characterization import ElementalAnalysis, Analyte
import datetime
from sqlalchemy import select


def _seed_sample_with_feo(db, sample_id="IRON_SAMPLE_001", feo_wt_pct=10.0):
    """Insert SampleInfo + ExternalAnalysis + ElementalAnalysis + Analyte for FeO.

    Uses analysis_type='Bulk Elemental Composition' to match the wide-format
    ElementalCompositionService uploader (production path for pre-exp FeO).
    """
    sample = SampleInfo(sample_id=sample_id)
    db.add(sample)
    db.flush()

    analyte = db.execute(
        select(Analyte).where(Analyte.analyte_symbol == "FeO")
    ).scalar_one_or_none()
    if analyte is None:
        analyte = Analyte(analyte_symbol="FeO", unit="%")
        db.add(analyte)
        db.flush()

    ext = ExternalAnalysis(
        sample_id=sample_id,
        analysis_type="Bulk Elemental Composition",
        analysis_date=datetime.datetime(2025, 1, 1),
    )
    db.add(ext)
    db.flush()

    ea = ElementalAnalysis(
        external_analysis_id=ext.id,
        sample_id=sample_id,
        analyte_id=analyte.id,
        analyte_composition=feo_wt_pct,
    )
    db.add(ea)
    db.commit()
    return sample


def test_total_ferrous_iron_g_populated_on_create(client, db_session):
    """POST /conditions: field is computed when sample has FeO analysis."""
    _seed_sample_with_feo(db_session, feo_wt_pct=10.0)
    exp = _make_experiment(db_session, eid="IRON_EXP_001", num=8001)
    # Link the experiment to the sample
    exp.sample_id = "IRON_SAMPLE_001"
    db_session.commit()

    payload = {
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "rock_mass_g": 5.0,
    }
    resp = client.post("/api/conditions", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["total_ferrous_iron_g"] == pytest.approx(0.38866, rel=1e-3)


def test_total_ferrous_iron_g_none_when_no_analysis(client, db_session):
    """POST /conditions: field is None when sample has no FeO characterization."""
    exp = _make_experiment(db_session, eid="NO_FEO_EXP_001", num=8002)
    payload = {
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "rock_mass_g": 5.0,
    }
    resp = client.post("/api/conditions", json=payload)
    assert resp.status_code == 201
    assert resp.json()["total_ferrous_iron_g"] is None


def test_total_ferrous_iron_g_recalculated_on_patch(client, db_session):
    """PATCH /conditions: field updates when rock_mass_g changes."""
    _seed_sample_with_feo(db_session, sample_id="IRON_SAMPLE_003", feo_wt_pct=10.0)
    exp = _make_experiment(db_session, eid="IRON_EXP_003", num=8003)
    exp.sample_id = "IRON_SAMPLE_003"
    db_session.commit()

    created = client.post("/api/conditions", json={
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "rock_mass_g": 5.0,
    }).json()
    assert created["total_ferrous_iron_g"] == pytest.approx(0.38866, rel=1e-3)

    patched = client.patch(f"/api/conditions/{created['id']}", json={"rock_mass_g": 10.0})
    assert patched.status_code == 200
    # Double the rock_mass → double the iron
    assert patched.json()["total_ferrous_iron_g"] == pytest.approx(0.77731, rel=1e-3)
```

- [ ] **Step 2: Add imports if missing**

Ensure `pytest` and `from sqlalchemy import select` are available (the snippet above adds `select` next to the helper; merge with existing imports in `test_conditions.py`).

- [ ] **Step 3: Run — confirm the 3 new tests PASS alongside existing tests**

```
.venv/Scripts/pytest tests/api/test_conditions.py -v
```

Expected: all tests pass (existing 2 + new 3 = 5 total).

- [ ] **Step 4: Run full API test suite — no regressions**

```
.venv/Scripts/pytest tests/api/ -v
```

- [ ] **Step 5: Commit**

```
git add tests/api/test_conditions.py
git commit -m "[Issue #1] Task 6: API integration tests for total_ferrous_iron_g"
```

---

## Task 7: Documentation + Close Issue

**Files:**
- Modify: `docs/CALCULATIONS.md`

- [ ] **Step 1: Add Characterization-Derived Fields section to `docs/CALCULATIONS.md`**

Append after the existing Scalar Calculations section:

```markdown
---

## Characterization-Derived Fields (`elemental_composition_service.py`, `conditions_calcs.py`)

These fields are computed from pre-experiment rock characterization data stored in
`ExternalAnalysis → ElementalAnalysis → Analyte`. The lookup traverses the `sample_id`
path only (not `experiment_fk`) to isolate pre-reaction characterization.

### `total_ferrous_iron_g` (on `ExperimentalConditions`)

**Analyte source:** `Analyte.analyte_symbol = 'FeO'`, `Analyte.unit = '%'`
**Stored in:** `ElementalAnalysis.analyte_composition` (numeric wt%)

**Lookup path:**
```
Experiment.sample_id
  → ExternalAnalysis (sample_id path, analysis_type in ('Elemental', 'Bulk Elemental Composition'))
    → ElementalAnalysis
      → Analyte (analyte_symbol = 'FeO', unit = '%')
        → ElementalAnalysis.analyte_composition  [FeO wt%]
```

**Multiple analyses resolution:** When multiple `ExternalAnalysis` records exist for the
same sample with FeO data, the most recent by `analysis_date` is used.

**Chemistry:**
```
Fe atomic mass  = 55.845 g/mol
O atomic mass   = 15.999 g/mol
FeO molar mass  = 71.844 g/mol

FE_IN_FEO_FRACTION = 55.845 / 71.844 ≈ 0.77731  (named constant in service)

fe_mass_fraction     = (feo_wt_pct / 100) × FE_IN_FEO_FRACTION
total_ferrous_iron_g = fe_mass_fraction × rock_mass_g
```

**Set to `None` when any of these are true:**
- `rock_mass_g` is missing or `≤ 0`
- No `ExternalAnalysis` with `analysis_type` in `'Elemental'` or `'Bulk Elemental Composition'` is linked to the sample via `sample_id`
- No `ElementalAnalysis` row exists for `Analyte.analyte_symbol = 'FeO'`
- `analyte_composition` is NULL

**Trigger:** Fires via `registry.recalculate()` on `POST /conditions` and `PATCH /conditions`.

**Extensibility:** `get_analyte_wt_pct(sample_id, db, analyte_symbol='FeO')` accepts any
`analyte_symbol` — future oxides (MgO, SiO2, Al2O3) reuse the same traversal.
```

- [ ] **Step 2: Run full test suite one final time**

```
.venv/Scripts/pytest tests/services/ tests/api/ tests/regression/ -v
```

All tests must pass.

- [ ] **Step 3: Commit documentation**

Stage **`docs/CALCULATIONS.md` only** (avoid `git add docs/project_context/`, which can pick up unrelated untracked mirrors). After editing, run `python .cursor/hooks/sync_docs_to_project_context.py --all` from repo root if your workflow syncs to `docs/project_context/`; then add only the mirrored file(s) you intentionally changed, or rely on your hook to keep them in sync.

```
git add docs/CALCULATIONS.md
git commit -m "[Issue #1] Task 7: update CALCULATIONS.md with characterization-derived fields"
```

- [ ] **Step 4: Close the GitHub issue**

```
/c/Program\ Files/GitHub\ CLI/gh.exe issue close 1 --repo mathew-h/experiment-tracking-sandbox --comment "Implemented in feature/m8-testing-docs. total_ferrous_iron_g added to ExperimentalConditions via additive migration, computed by elemental_composition_service.py and wired through conditions_calcs.py. All acceptance criteria met."
```
