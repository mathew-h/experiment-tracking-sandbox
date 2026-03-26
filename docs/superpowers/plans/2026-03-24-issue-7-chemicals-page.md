# Issue #7 — Chemicals Page & Additive Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full compound library UI and wire the chemical additive picker to the live compounds table, end-to-end from backend to frontend.

**Architecture:** Extend existing `chemicals.py` schemas/router with validation and PATCH; add experiment-scoped additive endpoints to the experiments router; build a reusable `CompoundFormModal` React component used by both the `/chemicals` page and the inline create-from-picker flow; upgrade `Step3Additives` with per-row typeahead search; upgrade `ConditionsTab` with delete/upsert using the new experiment-scoped endpoints.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2.x, structlog, pytest + TestClient; React 18 + TypeScript strict, TanStack Query v5, Tailwind CSS v3

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/api/schemas/chemicals.py` | Modify | Add missing fields to CompoundCreate/Response; add CompoundUpdate + ChemicalAdditiveUpsert; add Pydantic validators |
| `backend/api/routers/chemicals.py` | Modify | Add `?search=` param; add `PATCH /compounds/{id}`; add uniqueness checks on create/update |
| `backend/api/routers/experiments.py` | Modify | Add `GET/PUT/DELETE /api/experiments/{id}/additives/{compound_id}` |
| `tests/api/test_chemicals.py` | Modify | Tests for search, PATCH, uniqueness, 409 conflict |
| `tests/api/test_experiments.py` | Modify | Tests for additive upsert/delete/list by experiment ID |
| `frontend/src/api/chemicals.ts` | Modify | Add `updateCompound`, `upsertAdditive`, `deleteAdditive`, `listExperimentAdditives`; extend types |
| `frontend/src/components/CompoundFormModal.tsx` | Create | Reusable create/edit compound modal (supports `minimal` prop for picker inline flow) |
| `frontend/src/pages/Chemicals.tsx` | Modify | Add "Add Compound" button + modal; add row "Edit" action |
| `frontend/src/pages/NewExperiment/Step3Additives.tsx` | Modify | Per-row typeahead search; "Create compound" inline option; dedup/upsert in row list |
| `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx` | Modify | Delete additive button; switch list to `listExperimentAdditives`; upsert via new endpoints |
| `frontend/src/pages/NewExperiment/index.tsx` | Modify | Switch additive submission to `upsertAdditive` (experiment-scoped) |

---

## Task 1: Extend Pydantic schemas

**Files:**
- Modify: `backend/api/schemas/chemicals.py`
- Test: `tests/api/test_schemas.py` (already exists — add compound schema tests)

- [ ] **Step 1.1: Write failing schema validation tests**

Add to `tests/api/test_schemas.py`:

```python
from pydantic import ValidationError
import pytest
from backend.api.schemas.chemicals import CompoundCreate, CompoundUpdate, ChemicalAdditiveUpsert
from database.models.enums import AmountUnit


def test_compound_create_name_too_short():
    with pytest.raises(ValidationError):
        CompoundCreate(name="X")  # length 1 < min 2


def test_compound_create_name_max_length():
    with pytest.raises(ValidationError):
        CompoundCreate(name="A" * 101)


def test_compound_create_cas_invalid_format():
    with pytest.raises(ValidationError):
        CompoundCreate(name="Sodium", cas_number="NaCl-X")  # letters not allowed


def test_compound_create_cas_too_short():
    with pytest.raises(ValidationError):
        CompoundCreate(name="Sodium", cas_number="123")  # < 5 chars


def test_compound_create_cas_valid():
    c = CompoundCreate(name="Sodium", cas_number="7647-14-5")
    assert c.cas_number == "7647-14-5"


def test_compound_create_mw_out_of_range():
    with pytest.raises(ValidationError):
        CompoundCreate(name="Sodium", molecular_weight_g_mol=0.0)  # must be > 0

    with pytest.raises(ValidationError):
        CompoundCreate(name="Sodium", molecular_weight_g_mol=20000)  # > 10000


def test_compound_create_density_out_of_range():
    with pytest.raises(ValidationError):
        CompoundCreate(name="Sodium", density_g_cm3=100)  # > 50


def test_compound_update_partial():
    u = CompoundUpdate(name="New Name")
    assert u.name == "New Name"
    assert u.formula is None  # other fields stay None


def test_additive_upsert_amount_must_be_positive():
    with pytest.raises(ValidationError):
        ChemicalAdditiveUpsert(amount=0, unit=AmountUnit.g)

    with pytest.raises(ValidationError):
        ChemicalAdditiveUpsert(amount=-1, unit=AmountUnit.g)


def test_additive_upsert_valid():
    a = ChemicalAdditiveUpsert(amount=5.0, unit=AmountUnit.g)
    assert a.amount == 5.0
    assert a.unit == AmountUnit.g
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
pytest tests/api/test_schemas.py -k "compound" -v
```
Expected: ImportError or ValidationError not raised (fields not yet added)

- [ ] **Step 1.3: Replace `backend/api/schemas/chemicals.py` with extended version**

```python
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
import re
from database.models.enums import AmountUnit


def _cas_pattern() -> str:
    return r'^[\d\-\.]+$'


class CompoundCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    formula: Optional[str] = None
    cas_number: Optional[str] = Field(
        None,
        min_length=5,
        max_length=20,
        pattern=r'^[\d\-\.]+$',
    )
    molecular_weight_g_mol: Optional[float] = Field(None, gt=0, le=10000)
    density_g_cm3: Optional[float] = Field(None, gt=0, le=50)
    melting_point_c: Optional[float] = None
    boiling_point_c: Optional[float] = None
    solubility: Optional[str] = None
    hazard_class: Optional[str] = None
    supplier: Optional[str] = None
    catalog_number: Optional[str] = None
    notes: Optional[str] = None
    preferred_unit: Optional[AmountUnit] = None
    elemental_fraction: Optional[float] = None
    catalyst_formula: Optional[str] = None


class CompoundUpdate(BaseModel):
    """Partial update — all fields optional, same validation rules."""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    formula: Optional[str] = None
    cas_number: Optional[str] = Field(
        None,
        min_length=5,
        max_length=20,
        pattern=r'^[\d\-\.]+$',
    )
    molecular_weight_g_mol: Optional[float] = Field(None, gt=0, le=10000)
    density_g_cm3: Optional[float] = Field(None, gt=0, le=50)
    melting_point_c: Optional[float] = None
    boiling_point_c: Optional[float] = None
    solubility: Optional[str] = None
    hazard_class: Optional[str] = None
    supplier: Optional[str] = None
    catalog_number: Optional[str] = None
    notes: Optional[str] = None
    preferred_unit: Optional[AmountUnit] = None
    elemental_fraction: Optional[float] = None
    catalyst_formula: Optional[str] = None


class CompoundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    formula: Optional[str] = None
    cas_number: Optional[str] = None
    molecular_weight_g_mol: Optional[float] = None
    density_g_cm3: Optional[float] = None
    melting_point_c: Optional[float] = None
    boiling_point_c: Optional[float] = None
    solubility: Optional[str] = None
    hazard_class: Optional[str] = None
    preferred_unit: Optional[AmountUnit] = None
    supplier: Optional[str] = None
    catalog_number: Optional[str] = None
    notes: Optional[str] = None
    elemental_fraction: Optional[float] = None
    catalyst_formula: Optional[str] = None


class ChemicalAdditiveUpsert(BaseModel):
    """Payload for PUT /api/experiments/{id}/additives/{compound_id}."""
    amount: float = Field(gt=0)
    unit: AmountUnit
    addition_order: Optional[int] = None
    addition_method: Optional[str] = None


class AdditiveCreate(BaseModel):
    compound_id: int
    amount: float = Field(gt=0)
    unit: AmountUnit
    addition_order: Optional[int] = None
    addition_method: Optional[str] = None
    purity: Optional[float] = None
    lot_number: Optional[str] = None


class AdditiveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    compound_id: int
    amount: float
    unit: AmountUnit
    mass_in_grams: Optional[float] = None
    moles_added: Optional[float] = None
    final_concentration: Optional[float] = None
    concentration_units: Optional[str] = None
    catalyst_ppm: Optional[float] = None
    catalyst_percentage: Optional[float] = None
    elemental_metal_mass: Optional[float] = None
    compound: Optional[CompoundResponse] = None
```

- [ ] **Step 1.4: Run schema tests to verify they pass**

```bash
pytest tests/api/test_schemas.py -k "compound or additive_upsert" -v
```
Expected: All PASS

- [ ] **Step 1.5: Commit**

```bash
git add backend/api/schemas/chemicals.py tests/api/test_schemas.py
git commit -m "[#7] Extend compound schemas with validation + CompoundUpdate"
```

---

## Task 2: Extend compounds router (search + PATCH + uniqueness)

**Files:**
- Modify: `backend/api/routers/chemicals.py`
- Modify: `tests/api/test_chemicals.py`

- [ ] **Step 2.1: Write failing tests**

Replace `tests/api/test_chemicals.py` with:

```python
from __future__ import annotations
import pytest
from database.models.chemicals import Compound


def _make_compound(db, name="TestCompound", cas_number=None):
    c = Compound(name=name, formula="TestF", molecular_weight_g_mol=100.0, cas_number=cas_number)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# --- list / search ---

def test_list_compounds_empty(client):
    resp = client.get("/api/chemicals/compounds")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_compounds_search(client, db_session):
    _make_compound(db_session, "Magnesium Hydroxide")
    _make_compound(db_session, "Iron Chloride")

    resp = client.get("/api/chemicals/compounds?search=magnes")
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert "Magnesium Hydroxide" in names
    assert "Iron Chloride" not in names


def test_list_compounds_search_case_insensitive(client, db_session):
    _make_compound(db_session, "Sodium Chloride")
    resp = client.get("/api/chemicals/compounds?search=SODIUM")
    assert resp.status_code == 200
    assert any(c["name"] == "Sodium Chloride" for c in resp.json())


# --- create ---

def test_create_compound(client):
    resp = client.post("/api/chemicals/compounds", json={
        "name": "Magnesium Hydroxide", "formula": "Mg(OH)2", "molecular_weight_g_mol": 58.32
    })
    assert resp.status_code == 201
    assert resp.json()["name"] == "Magnesium Hydroxide"


def test_create_compound_name_too_short(client):
    resp = client.post("/api/chemicals/compounds", json={"name": "X"})
    assert resp.status_code == 422


def test_create_compound_duplicate_name_case_insensitive(client, db_session):
    _make_compound(db_session, "Iron Oxide")
    resp = client.post("/api/chemicals/compounds", json={"name": "iron oxide"})
    assert resp.status_code == 409


def test_create_compound_duplicate_cas(client, db_session):
    _make_compound(db_session, "CompoundA", cas_number="1234-56-7")
    resp = client.post("/api/chemicals/compounds", json={
        "name": "CompoundB", "cas_number": "1234-56-7"
    })
    assert resp.status_code == 409


def test_create_compound_invalid_cas_format(client):
    resp = client.post("/api/chemicals/compounds", json={
        "name": "BadCAS", "cas_number": "abc-def"
    })
    assert resp.status_code == 422


# --- get ---

def test_get_compound_not_found(client):
    resp = client.get("/api/chemicals/compounds/99999")
    assert resp.status_code == 404


def test_get_compound(client, db_session):
    c = _make_compound(db_session, "IronChloride")
    resp = client.get(f"/api/chemicals/compounds/{c.id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "IronChloride"


# --- PATCH ---

def test_patch_compound(client, db_session):
    c = _make_compound(db_session, "OldName")
    resp = client.patch(f"/api/chemicals/compounds/{c.id}", json={"name": "NewName"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "NewName"


def test_patch_compound_not_found(client):
    resp = client.patch("/api/chemicals/compounds/99999", json={"name": "X" * 5})
    assert resp.status_code == 404


def test_patch_compound_duplicate_name(client, db_session):
    _make_compound(db_session, "AlreadyExists")
    c2 = _make_compound(db_session, "ToBeRenamed")
    resp = client.patch(f"/api/chemicals/compounds/{c2.id}", json={"name": "alreadyexists"})
    assert resp.status_code == 409


def test_patch_compound_duplicate_cas(client, db_session):
    _make_compound(db_session, "CompA", cas_number="9999-00-1")
    c2 = _make_compound(db_session, "CompB")
    resp = client.patch(f"/api/chemicals/compounds/{c2.id}", json={"cas_number": "9999-00-1"})
    assert resp.status_code == 409
```

- [ ] **Step 2.2: Run to verify failures**

```bash
pytest tests/api/test_chemicals.py -v
```
Expected: search tests FAIL (param not handled), PATCH tests FAIL (endpoint missing), 409 tests FAIL (no uniqueness check)

- [ ] **Step 2.3: Replace `backend/api/routers/chemicals.py` with extended version**

```python
from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from database.models.chemicals import Compound, ChemicalAdditive
from database.models.conditions import ExperimentalConditions
import backend.services.calculations  # noqa: F401 — registers @register decorators
from backend.services.calculations.registry import recalculate
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.chemicals import (
    CompoundCreate, CompoundUpdate, CompoundResponse,
    AdditiveCreate, AdditiveResponse,
)

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/chemicals", tags=["chemicals"])


def _check_name_unique(db: Session, name: str, exclude_id: int | None = None) -> None:
    """Raise 409 if a compound with the same name (case-insensitive) already exists."""
    stmt = select(Compound).where(func.lower(Compound.name) == func.lower(name))
    if exclude_id is not None:
        stmt = stmt.where(Compound.id != exclude_id)
    if db.execute(stmt).scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="A compound with this name already exists")


def _check_cas_unique(db: Session, cas_number: str, exclude_id: int | None = None) -> None:
    """Raise 409 if a compound with the same CAS number already exists."""
    stmt = select(Compound).where(Compound.cas_number == cas_number)
    if exclude_id is not None:
        stmt = stmt.where(Compound.id != exclude_id)
    if db.execute(stmt).scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="A compound with this CAS number already exists")


@router.get("/compounds", response_model=list[CompoundResponse])
def list_compounds(
    search: str | None = Query(None, description="Case-insensitive name or formula match"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[CompoundResponse]:
    """List all compounds ordered by name. Supports case-insensitive ?search= on name and formula."""
    stmt = select(Compound).order_by(Compound.name).offset(skip).limit(limit)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            func.lower(Compound.name).like(func.lower(pattern))
            | func.lower(func.coalesce(Compound.formula, "")).like(func.lower(pattern))
        )
    rows = db.execute(stmt).scalars().all()
    return [CompoundResponse.model_validate(r) for r in rows]


@router.get("/compounds/{compound_id}", response_model=CompoundResponse)
def get_compound(
    compound_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> CompoundResponse:
    """Return a single compound by primary key. 404 if not found."""
    c = db.get(Compound, compound_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Compound not found")
    return CompoundResponse.model_validate(c)


@router.post("/compounds", response_model=CompoundResponse, status_code=201)
def create_compound(
    payload: CompoundCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> CompoundResponse:
    """Create a new compound. Enforces case-insensitive name uniqueness and CAS uniqueness."""
    _check_name_unique(db, payload.name)
    if payload.cas_number:
        _check_cas_unique(db, payload.cas_number)
    compound = Compound(**payload.model_dump())
    db.add(compound)
    db.commit()
    db.refresh(compound)
    log.info("compound_created", name=compound.name, user=current_user.email)
    return CompoundResponse.model_validate(compound)


@router.patch("/compounds/{compound_id}", response_model=CompoundResponse)
def update_compound(
    compound_id: int,
    payload: CompoundUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> CompoundResponse:
    """Partially update a compound. Enforces name and CAS uniqueness excluding this record."""
    compound = db.get(Compound, compound_id)
    if compound is None:
        raise HTTPException(status_code=404, detail="Compound not found")
    if payload.name is not None:
        _check_name_unique(db, payload.name, exclude_id=compound_id)
    if payload.cas_number is not None:
        _check_cas_unique(db, payload.cas_number, exclude_id=compound_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(compound, k, v)
    db.commit()
    db.refresh(compound)
    log.info("compound_updated", compound_id=compound_id, user=current_user.email)
    return CompoundResponse.model_validate(compound)


@router.get("/additives/{conditions_id}", response_model=list[AdditiveResponse])
def list_additives(
    conditions_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[AdditiveResponse]:
    """List chemical additives for a conditions record, ordered by addition_order."""
    rows = db.execute(
        select(ChemicalAdditive)
        .where(ChemicalAdditive.experiment_id == conditions_id)
        .order_by(ChemicalAdditive.addition_order)
    ).scalars().all()
    return [AdditiveResponse.model_validate(r) for r in rows]


@router.post("/additives/{conditions_id}", response_model=AdditiveResponse, status_code=201)
def create_additive(
    conditions_id: int,
    payload: AdditiveCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> AdditiveResponse:
    """Add a chemical additive to a conditions record and trigger derived field recalculation."""
    conditions = db.get(ExperimentalConditions, conditions_id)
    if conditions is None:
        raise HTTPException(status_code=404, detail="Conditions record not found")
    additive = ChemicalAdditive(experiment_id=conditions_id, **payload.model_dump())
    db.add(additive)
    db.flush()
    recalculate(additive, db)
    db.commit()
    db.refresh(additive)
    log.info("additive_created", conditions_id=conditions_id, compound_id=payload.compound_id)
    return AdditiveResponse.model_validate(additive)
```

- [ ] **Step 2.4: Run tests to verify they pass**

```bash
pytest tests/api/test_chemicals.py -v
```
Expected: All PASS

- [ ] **Step 2.5: Commit**

```bash
git add backend/api/routers/chemicals.py tests/api/test_chemicals.py
git commit -m "[#7] Add search param, PATCH, and uniqueness validation to compounds API"
```

---

## Task 3: Experiment-based additive endpoints

**Files:**
- Modify: `backend/api/routers/experiments.py`
- Modify: `tests/api/test_experiments.py`

- [ ] **Step 3.1: Write failing tests**

Add the following to `tests/api/test_experiments.py` (append below the existing tests):

```python
# --- Additive endpoints ---
# These tests require an experiment + conditions + compound to exist.

from database.models.chemicals import Compound, ChemicalAdditive
from database.models.conditions import ExperimentalConditions


def _make_exp_with_conditions(db, exp_id="TEST_001"):
    """Helper: create experiment + conditions row, return (experiment, conditions)."""
    from database.models.experiments import Experiment
    from database.models.enums import ExperimentStatus
    exp = Experiment(experiment_id=exp_id, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    cond = ExperimentalConditions(experiment_fk=exp.id, experiment_id=exp_id)
    db.add(cond)
    db.commit()
    db.refresh(exp)
    db.refresh(cond)
    return exp, cond


def _make_compound(db, name="TestChem"):
    c = Compound(name=name, formula="TC", molecular_weight_g_mol=50.0)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_list_experiment_additives_empty(client, db_session):
    _make_exp_with_conditions(db_session, "ADDTEST_001")
    resp = client.get("/api/experiments/ADDTEST_001/additives")
    assert resp.status_code == 200
    assert resp.json() == []


def test_upsert_additive_creates(client, db_session):
    exp, _ = _make_exp_with_conditions(db_session, "ADDTEST_002")
    compound = _make_compound(db_session, "MgOH2")
    resp = client.put(
        f"/api/experiments/{exp.experiment_id}/additives/{compound.id}",
        json={"amount": 5.0, "unit": "g"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["compound_id"] == compound.id
    assert data["amount"] == 5.0


def test_upsert_additive_updates_existing(client, db_session):
    exp, cond = _make_exp_with_conditions(db_session, "ADDTEST_003")
    compound = _make_compound(db_session, "NaCl")
    # Create first
    client.put(
        f"/api/experiments/{exp.experiment_id}/additives/{compound.id}",
        json={"amount": 1.0, "unit": "g"}
    )
    # Update
    resp = client.put(
        f"/api/experiments/{exp.experiment_id}/additives/{compound.id}",
        json={"amount": 99.0, "unit": "mg"}
    )
    assert resp.status_code == 200
    assert resp.json()["amount"] == 99.0
    assert resp.json()["unit"] == "mg"


def test_upsert_additive_experiment_not_found(client, db_session):
    compound = _make_compound(db_session, "Orphan")
    resp = client.put(
        f"/api/experiments/NONEXISTENT/additives/{compound.id}",
        json={"amount": 1.0, "unit": "g"}
    )
    assert resp.status_code == 404


def test_upsert_additive_no_conditions(client, db_session):
    """Experiment exists but has no conditions row — should 404."""
    from database.models.experiments import Experiment
    from database.models.enums import ExperimentStatus
    exp = Experiment(experiment_id="NOCOND_001", status=ExperimentStatus.ONGOING)
    db_session.add(exp)
    db_session.commit()
    compound = _make_compound(db_session, "NoCond")
    resp = client.put(
        f"/api/experiments/NOCOND_001/additives/{compound.id}",
        json={"amount": 1.0, "unit": "g"}
    )
    assert resp.status_code == 404


def test_delete_additive(client, db_session):
    exp, cond = _make_exp_with_conditions(db_session, "ADDTEST_004")
    compound = _make_compound(db_session, "ToDelete")
    # Create additive first
    client.put(
        f"/api/experiments/{exp.experiment_id}/additives/{compound.id}",
        json={"amount": 2.0, "unit": "g"}
    )
    # Delete it
    resp = client.delete(f"/api/experiments/{exp.experiment_id}/additives/{compound.id}")
    assert resp.status_code == 204
    # Verify gone
    list_resp = client.get(f"/api/experiments/{exp.experiment_id}/additives")
    assert list_resp.json() == []


def test_delete_additive_not_found(client, db_session):
    _make_exp_with_conditions(db_session, "ADDTEST_005")
    resp = client.delete("/api/experiments/ADDTEST_005/additives/99999")
    assert resp.status_code == 404


def test_upsert_additive_compound_not_found(client, db_session):
    """Upsert with a compound_id that doesn't exist should 404."""
    _make_exp_with_conditions(db_session, "ADDTEST_006")
    resp = client.put(
        "/api/experiments/ADDTEST_006/additives/99999",
        json={"amount": 1.0, "unit": "g"}
    )
    assert resp.status_code == 404
```

- [ ] **Step 3.2: Run to verify failures**

```bash
pytest tests/api/test_experiments.py -k "additive" -v
```
Expected: All FAIL (endpoints not yet added to experiments router)

- [ ] **Step 3.3: Add additive endpoints to `backend/api/routers/experiments.py`**

Add these imports at the top of the file (after existing imports):

```python
from database.models.chemicals import Compound, ChemicalAdditive
from database.models.conditions import ExperimentalConditions
from backend.api.schemas.chemicals import AdditiveResponse, ChemicalAdditiveUpsert
from backend.services.calculations.registry import recalculate
```

Then add these three endpoints after the existing experiment endpoints (before or after `delete_experiment` — keep grouped):

```python
@router.get("/{experiment_id}/additives", response_model=list[AdditiveResponse])
def list_experiment_additives(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[AdditiveResponse]:
    """List chemical additives for an experiment by its string ID. Returns [] if no conditions exist."""
    conditions = db.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if conditions is None:
        return []
    rows = db.execute(
        select(ChemicalAdditive)
        .where(ChemicalAdditive.experiment_id == conditions.id)
        .order_by(ChemicalAdditive.addition_order)
    ).scalars().all()
    return [AdditiveResponse.model_validate(r) for r in rows]


@router.put("/{experiment_id}/additives/{compound_id}", response_model=AdditiveResponse)
def upsert_experiment_additive(
    experiment_id: str,
    compound_id: int,
    payload: ChemicalAdditiveUpsert,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> AdditiveResponse:
    """Upsert a chemical additive for an experiment — create if new, update if exists.

    Uses experiment string ID. Resolves conditions internally.
    """
    conditions = db.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if conditions is None:
        raise HTTPException(status_code=404, detail="Experiment conditions not found")
    compound = db.get(Compound, compound_id)
    if compound is None:
        raise HTTPException(status_code=404, detail="Compound not found")
    existing = db.execute(
        select(ChemicalAdditive)
        .where(ChemicalAdditive.experiment_id == conditions.id)
        .where(ChemicalAdditive.compound_id == compound_id)
    ).scalar_one_or_none()
    if existing:
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(existing, k, v)
        additive = existing
    else:
        additive = ChemicalAdditive(
            experiment_id=conditions.id,
            compound_id=compound_id,
            **payload.model_dump(),
        )
        db.add(additive)
    db.flush()
    recalculate(additive, db)
    db.commit()
    db.refresh(additive)
    log.info("additive_upserted", experiment_id=experiment_id, compound_id=compound_id)
    return AdditiveResponse.model_validate(additive)


@router.delete("/{experiment_id}/additives/{compound_id}", status_code=204)
def delete_experiment_additive(
    experiment_id: str,
    compound_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> None:
    """Remove a chemical additive from an experiment."""
    conditions = db.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if conditions is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    additive = db.execute(
        select(ChemicalAdditive)
        .where(ChemicalAdditive.experiment_id == conditions.id)
        .where(ChemicalAdditive.compound_id == compound_id)
    ).scalar_one_or_none()
    if additive is None:
        raise HTTPException(status_code=404, detail="Additive not found")
    db.delete(additive)
    db.commit()
    log.info("additive_deleted", experiment_id=experiment_id, compound_id=compound_id)
```

Also add `log = structlog.get_logger(__name__)` near the top of the experiments router if it is not already there.

- [ ] **Step 3.4: Run tests to verify they pass**

```bash
pytest tests/api/test_experiments.py -k "additive" -v
```
Expected: All PASS

- [ ] **Step 3.5: Run full backend test suite**

```bash
pytest tests/api/ -v
```
Expected: All PASS (no regressions)

- [ ] **Step 3.6: Commit**

```bash
git add backend/api/routers/experiments.py tests/api/test_experiments.py
git commit -m "[#7] Add experiment-scoped additive endpoints (GET/PUT/DELETE)"
```

---

## Task 4: Extend frontend API client

**Files:**
- Modify: `frontend/src/api/chemicals.ts`

- [ ] **Step 4.1: Replace `frontend/src/api/chemicals.ts` with extended version**

```typescript
import { apiClient } from './client'

export interface Compound {
  id: number
  name: string
  formula: string | null
  cas_number: string | null
  molecular_weight_g_mol: number | null
  density_g_cm3: number | null
  melting_point_c: number | null
  boiling_point_c: number | null
  solubility: string | null
  hazard_class: string | null
  preferred_unit: string | null
  supplier: string | null
  catalog_number: string | null
  notes: string | null
  elemental_fraction: number | null
  catalyst_formula: string | null
}

export interface ChemicalAdditive {
  id: number
  compound_id: number
  amount: number
  unit: string
  addition_order: number | null
  mass_in_grams: number | null
  moles_added: number | null
  catalyst_ppm: number | null
  compound: Compound | null
}

export interface AdditivePayload {
  compound_id: number
  amount: number
  unit: string
  addition_order?: number
}

export interface AdditiveUpsertPayload {
  amount: number
  unit: string
  addition_order?: number
  addition_method?: string
}

export type CompoundCreatePayload = Omit<Compound, 'id'>
export type CompoundUpdatePayload = Partial<Omit<Compound, 'id'>>

export const chemicalsApi = {
  listCompounds: (params?: { search?: string; skip?: number; limit?: number }) =>
    apiClient.get<Compound[]>('/chemicals/compounds', { params }).then((r) => r.data),

  getCompound: (id: number) =>
    apiClient.get<Compound>(`/chemicals/compounds/${id}`).then((r) => r.data),

  createCompound: (payload: CompoundCreatePayload) =>
    apiClient.post<Compound>('/chemicals/compounds', payload).then((r) => r.data),

  updateCompound: (id: number, payload: CompoundUpdatePayload) =>
    apiClient.patch<Compound>(`/chemicals/compounds/${id}`, payload).then((r) => r.data),

  /** Legacy: list by conditions integer ID. Used by wizard step during submission. */
  listAdditives: (conditionsId: number) =>
    apiClient.get<ChemicalAdditive[]>(`/chemicals/additives/${conditionsId}`).then((r) => r.data),

  /** Legacy: create additive by conditions integer ID. Used by wizard during submission. */
  addAdditive: (conditionsId: number, payload: AdditivePayload) =>
    apiClient.post<ChemicalAdditive>(`/chemicals/additives/${conditionsId}`, payload).then((r) => r.data),

  /** List additives by experiment string ID (experiment-scoped endpoint). */
  listExperimentAdditives: (experimentId: string) =>
    apiClient.get<ChemicalAdditive[]>(`/experiments/${experimentId}/additives`).then((r) => r.data),

  /** Upsert an additive by experiment string ID + compound ID. */
  upsertAdditive: (experimentId: string, compoundId: number, payload: AdditiveUpsertPayload) =>
    apiClient
      .put<ChemicalAdditive>(`/experiments/${experimentId}/additives/${compoundId}`, payload)
      .then((r) => r.data),

  /** Delete an additive by experiment string ID + compound ID. */
  deleteAdditive: (experimentId: string, compoundId: number) =>
    apiClient.delete(`/experiments/${experimentId}/additives/${compoundId}`),
}
```

- [ ] **Step 4.2: Check TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: Zero errors

- [ ] **Step 4.3: Commit**

```bash
git add frontend/src/api/chemicals.ts
git commit -m "[#7] Extend chemicals API client with updateCompound and experiment-scoped additive methods"
```

---

## Task 5: Create `CompoundFormModal` shared component

This modal is used by both the Chemicals page (full form) and the additive picker (minimal form — only name required, rest optional).

**Files:**
- Create: `frontend/src/components/CompoundFormModal.tsx`

- [ ] **Step 5.1: Create the component**

```tsx
import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { chemicalsApi, type Compound, type CompoundCreatePayload } from '@/api/chemicals'
import { Modal, Input, Button, useToast } from '@/components/ui'

interface Props {
  open: boolean
  onClose: () => void
  /** Called with the created/updated compound on success. */
  onSuccess: (compound: Compound) => void
  /** If provided, modal is in edit mode. */
  initial?: Compound
  /** Pre-fills the name field (for create-from-picker flow). */
  initialName?: string
  /** Minimal mode: only shows name field. */
  minimal?: boolean
}

const EMPTY_FORM: CompoundCreatePayload = {
  name: '', formula: null, cas_number: null, molecular_weight_g_mol: null,
  density_g_cm3: null, melting_point_c: null, boiling_point_c: null,
  solubility: null, hazard_class: null, supplier: null, catalog_number: null,
  notes: null, preferred_unit: null, elemental_fraction: null, catalyst_formula: null,
}

function toNum(s: string): number | null {
  const n = parseFloat(s)
  return isNaN(n) ? null : n
}

/** Reusable modal for creating or editing a Compound. */
export function CompoundFormModal({ open, onClose, onSuccess, initial, initialName, minimal }: Props) {
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()
  const isEdit = Boolean(initial)

  const [form, setForm] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!open) return
    if (initial) {
      setForm({
        name: initial.name,
        formula: initial.formula ?? '',
        cas_number: initial.cas_number ?? '',
        molecular_weight_g_mol: initial.molecular_weight_g_mol?.toString() ?? '',
        density_g_cm3: initial.density_g_cm3?.toString() ?? '',
        melting_point_c: initial.melting_point_c?.toString() ?? '',
        boiling_point_c: initial.boiling_point_c?.toString() ?? '',
        solubility: initial.solubility ?? '',
        hazard_class: initial.hazard_class ?? '',
        supplier: initial.supplier ?? '',
        catalog_number: initial.catalog_number ?? '',
        notes: initial.notes ?? '',
      })
    } else {
      setForm({ name: initialName ?? '' })
    }
  }, [open, initial, initialName])

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((p) => ({ ...p, [k]: e.target.value }))

  const createMutation = useMutation({
    mutationFn: () => {
      const payload: CompoundCreatePayload = {
        name: form.name.trim(),
        formula: form.formula?.trim() || null,
        cas_number: form.cas_number?.trim() || null,
        molecular_weight_g_mol: form.molecular_weight_g_mol ? toNum(form.molecular_weight_g_mol) : null,
        density_g_cm3: form.density_g_cm3 ? toNum(form.density_g_cm3) : null,
        melting_point_c: form.melting_point_c ? toNum(form.melting_point_c) : null,
        boiling_point_c: form.boiling_point_c ? toNum(form.boiling_point_c) : null,
        solubility: form.solubility?.trim() || null,
        hazard_class: form.hazard_class?.trim() || null,
        supplier: form.supplier?.trim() || null,
        catalog_number: form.catalog_number?.trim() || null,
        notes: form.notes?.trim() || null,
        preferred_unit: null,
        elemental_fraction: null,
        catalyst_formula: null,
      }
      return chemicalsApi.createCompound(payload)
    },
    onSuccess: (compound) => {
      queryClient.invalidateQueries({ queryKey: ['compounds'] })
      success(`Compound "${compound.name}" created`)
      onSuccess(compound)
      onClose()
    },
    onError: (err: Error) => {
      const msg = err.message?.includes('409') ? 'A compound with this name or CAS number already exists' : err.message
      toastError('Failed to create compound', msg)
    },
  })

  const updateMutation = useMutation({
    mutationFn: () => {
      const payload = {
        name: form.name.trim() || undefined,
        formula: form.formula?.trim() || undefined,
        cas_number: form.cas_number?.trim() || undefined,
        molecular_weight_g_mol: form.molecular_weight_g_mol ? toNum(form.molecular_weight_g_mol) : undefined,
        density_g_cm3: form.density_g_cm3 ? toNum(form.density_g_cm3) : undefined,
        melting_point_c: form.melting_point_c ? toNum(form.melting_point_c) : undefined,
        boiling_point_c: form.boiling_point_c ? toNum(form.boiling_point_c) : undefined,
        solubility: form.solubility?.trim() || undefined,
        hazard_class: form.hazard_class?.trim() || undefined,
        supplier: form.supplier?.trim() || undefined,
        catalog_number: form.catalog_number?.trim() || undefined,
        notes: form.notes?.trim() || undefined,
      }
      return chemicalsApi.updateCompound(initial!.id, payload)
    },
    onSuccess: (compound) => {
      queryClient.invalidateQueries({ queryKey: ['compounds'] })
      success(`Compound "${compound.name}" updated`)
      onSuccess(compound)
      onClose()
    },
    onError: (err: Error) => {
      const msg = err.message?.includes('409') ? 'A compound with this name or CAS number already exists' : err.message
      toastError('Failed to update compound', msg)
    },
  })

  const isPending = createMutation.isPending || updateMutation.isPending
  const canSubmit = form.name?.trim().length >= 2

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isEdit ? `Edit: ${initial?.name}` : 'Add Compound'}
    >
      <div className="space-y-3 p-4">
        <Input
          label="Name *"
          value={form.name ?? ''}
          onChange={set('name')}
          placeholder="e.g. Magnesium Hydroxide"
        />

        {!minimal && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Input label="Formula" value={form.formula ?? ''} onChange={set('formula')} placeholder="e.g. Mg(OH)₂" />
              <Input
                label="CAS Number"
                value={form.cas_number ?? ''}
                onChange={set('cas_number')}
                placeholder="e.g. 1309-42-8"
              />
              <Input label="MW (g/mol)" type="number" value={form.molecular_weight_g_mol ?? ''} onChange={set('molecular_weight_g_mol')} />
              <Input label="Density (g/cm³)" type="number" value={form.density_g_cm3 ?? ''} onChange={set('density_g_cm3')} />
              <Input label="Melting Point (°C)" type="number" value={form.melting_point_c ?? ''} onChange={set('melting_point_c')} />
              <Input label="Boiling Point (°C)" type="number" value={form.boiling_point_c ?? ''} onChange={set('boiling_point_c')} />
              <Input label="Solubility" value={form.solubility ?? ''} onChange={set('solubility')} />
              <Input label="Hazard Class" value={form.hazard_class ?? ''} onChange={set('hazard_class')} />
              <Input label="Supplier" value={form.supplier ?? ''} onChange={set('supplier')} />
              <Input label="Catalog #" value={form.catalog_number ?? ''} onChange={set('catalog_number')} />
            </div>
            <div>
              <label className="block text-xs font-medium text-ink-secondary mb-1">Notes</label>
              <textarea
                className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50 resize-none"
                rows={2}
                value={form.notes ?? ''}
                onChange={set('notes')}
              />
            </div>
          </>
        )}

        <div className="flex gap-2 justify-end pt-1">
          <Button variant="ghost" onClick={onClose} disabled={isPending}>Cancel</Button>
          <Button
            variant="primary"
            loading={isPending}
            disabled={!canSubmit}
            onClick={() => isEdit ? updateMutation.mutate() : createMutation.mutate()}
          >
            {isEdit ? 'Save Changes' : 'Create Compound'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
```

- [ ] **Step 5.2: Check TypeScript**

```bash
cd frontend && npx tsc --noEmit
```
Expected: Zero errors

- [ ] **Step 5.3: Commit**

```bash
git add frontend/src/components/CompoundFormModal.tsx
git commit -m "[#7] Add CompoundFormModal shared component"
```

---

## Task 6: Chemicals.tsx — full compound library UI

**Files:**
- Modify: `frontend/src/pages/Chemicals.tsx`

- [ ] **Step 6.1: Replace `frontend/src/pages/Chemicals.tsx`**

```tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { chemicalsApi, type Compound } from '@/api/chemicals'
import { Table, TableHead, TableBody, TableRow, Th, Td, TdValue, Input, PageSpinner, Button } from '@/components/ui'
import { CompoundFormModal } from '@/components/CompoundFormModal'

/** Chemical inventory page: searchable compound table with add and edit actions. */
export function ChemicalsPage() {
  const [search, setSearch] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Compound | null>(null)

  const { data: compounds, isLoading, error } = useQuery({
    queryKey: ['compounds', search],
    queryFn: () => chemicalsApi.listCompounds({ search: search || undefined, limit: 200 }),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-ink-primary">Chemicals</h1>
          <p className="text-xs text-ink-muted mt-0.5">
            {compounds ? `${compounds.length} compounds` : 'Chemical compound inventory'}
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={() => setAddOpen(true)}>
          + Add Compound
        </Button>
      </div>

      <div className="w-64">
        <Input
          placeholder="Search compounds…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          leftIcon={
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <circle cx="5" cy="5" r="4" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M10.5 10.5L8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          }
        />
      </div>

      {isLoading && <PageSpinner />}
      {error && <p className="text-sm text-red-400">Failed to load compounds</p>}

      {compounds && (
        <Table>
          <TableHead>
            <tr>
              <Th>Name</Th>
              <Th>Formula</Th>
              <Th>CAS</Th>
              <Th className="text-right">MW (g/mol)</Th>
              <Th className="text-right">Density (g/cm³)</Th>
              <Th>Preferred Unit</Th>
              <Th>Supplier</Th>
              <Th></Th>
            </tr>
          </TableHead>
          <TableBody>
            {compounds.length === 0 ? (
              <TableRow>
                <Td colSpan={8} className="text-center py-8 text-ink-muted">No compounds found</Td>
              </TableRow>
            ) : (
              compounds.map((c) => (
                <TableRow key={c.id}>
                  <Td className="font-medium text-ink-primary">{c.name}</Td>
                  <Td className="font-mono-data">{c.formula ?? '—'}</Td>
                  <Td className="font-mono-data text-ink-muted">{c.cas_number ?? '—'}</Td>
                  <TdValue>{c.molecular_weight_g_mol?.toFixed(2) ?? '—'}</TdValue>
                  <TdValue>{c.density_g_cm3?.toFixed(3) ?? '—'}</TdValue>
                  <Td className="font-mono-data text-ink-muted">{c.preferred_unit ?? '—'}</Td>
                  <Td className="text-ink-muted">{c.supplier ?? '—'}</Td>
                  <Td>
                    <button
                      onClick={() => setEditTarget(c)}
                      className="text-xs text-ink-muted hover:text-ink-primary transition-colors px-1"
                    >
                      Edit
                    </button>
                  </Td>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      )}

      <CompoundFormModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onSuccess={() => setAddOpen(false)}
      />

      <CompoundFormModal
        open={Boolean(editTarget)}
        onClose={() => setEditTarget(null)}
        onSuccess={() => setEditTarget(null)}
        initial={editTarget ?? undefined}
      />
    </div>
  )
}
```

- [ ] **Step 6.2: Check TypeScript**

```bash
cd frontend && npx tsc --noEmit
```
Expected: Zero errors

- [ ] **Step 6.3: Check ESLint**

```bash
cd frontend && npx eslint src/pages/Chemicals.tsx src/components/CompoundFormModal.tsx --ext .tsx
```
Expected: Zero warnings

- [ ] **Step 6.4: Commit**

```bash
git add frontend/src/pages/Chemicals.tsx
git commit -m "[#7] Add compound library UI with Add and Edit actions"
```

---

## Task 7: Step3Additives.tsx — typeahead + create-inline

**Files:**
- Modify: `frontend/src/pages/NewExperiment/Step3Additives.tsx`

Design decisions:
- Each additive row has its own controlled typeahead text input for compound selection
- The search input shows a dropdown with live results (`queryKey: ['compounds', rowQuery]`)
- If the user types text that doesn't match any existing compound exactly, show "Create '[text]'" at the bottom of the dropdown
- Clicking "Create" opens `CompoundFormModal` in minimal mode with the typed name pre-filled
- On creation success, the new compound is immediately selected for that row
- Adding a row with a compound already in the list replaces the existing row (upsert semantics)

- [ ] **Step 7.1: Replace `frontend/src/pages/NewExperiment/Step3Additives.tsx`**

```tsx
import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { chemicalsApi, type Compound } from '@/api/chemicals'
import { Input, Select, Button } from '@/components/ui'
import { CompoundFormModal } from '@/components/CompoundFormModal'

const AMOUNT_UNITS = ['g', 'mg', 'mL', 'μL', 'mM', 'M', 'ppm', 'mmol', 'mol', '% of Rock', 'wt%']
  .map((u) => ({ value: u, label: u }))

export interface AdditiveRow {
  compound_id: number | null
  compound_name: string
  amount: string
  unit: string
}

interface Props {
  rows: AdditiveRow[]
  onChange: (rows: AdditiveRow[]) => void
  onBack: () => void
  onNext: () => void
}

interface RowEditorProps {
  row: AdditiveRow
  index: number
  onPatch: (patch: Partial<AdditiveRow>) => void
  onRemove: () => void
}

/** Per-row compound typeahead with inline create option. */
function RowEditor({ row, onPatch, onRemove }: RowEditorProps) {
  const queryClient = useQueryClient()
  const [query, setQuery] = useState(row.compound_name)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [createInitialName, setCreateInitialName] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const { data: results = [] } = useQuery({
    queryKey: ['compounds', query],
    queryFn: () => chemicalsApi.listCompounds({ search: query, limit: 10 }),
    enabled: query.length >= 1 && dropdownOpen,
  })

  const hasExactMatch = results.some((c) => c.name.toLowerCase() === query.toLowerCase())

  const selectCompound = (compound: Compound) => {
    setQuery(compound.name)
    setDropdownOpen(false)
    onPatch({ compound_id: compound.id, compound_name: compound.name })
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(e.target.value)
    setDropdownOpen(true)
    if (!e.target.value) {
      onPatch({ compound_id: null, compound_name: '' })
    }
  }

  const openCreate = () => {
    setCreateInitialName(query)
    setDropdownOpen(false)
    setCreateOpen(true)
  }

  const handleCreated = (compound: Compound) => {
    queryClient.invalidateQueries({ queryKey: ['compounds'] })
    selectCompound(compound)
    setCreateOpen(false)
  }

  return (
    <div className="flex items-end gap-2 p-3 bg-surface-raised rounded">
      <div className="flex-1 relative">
        <label className="block text-xs font-medium text-ink-secondary mb-1">Chemical</label>
        <input
          ref={inputRef}
          className="w-full bg-surface-input border border-surface-border rounded px-2 py-1.5 text-sm text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50"
          placeholder="Search compounds…"
          value={query}
          onChange={handleInputChange}
          onFocus={() => setDropdownOpen(true)}
          onBlur={() => setTimeout(() => setDropdownOpen(false), 150)}
          autoComplete="off"
        />
        {dropdownOpen && (query.length >= 1) && (
          <div className="absolute z-10 left-0 right-0 top-full mt-0.5 bg-surface-raised border border-surface-border rounded shadow-lg max-h-48 overflow-y-auto">
            {results.map((c) => (
              <button
                key={c.id}
                type="button"
                className="w-full text-left px-3 py-1.5 text-sm text-ink-primary hover:bg-surface-border/30 flex items-center gap-2"
                onMouseDown={() => selectCompound(c)}
              >
                <span>{c.name}</span>
                {c.formula && <span className="text-xs text-ink-muted font-mono-data">{c.formula}</span>}
              </button>
            ))}
            {!hasExactMatch && query.trim().length >= 2 && (
              <button
                type="button"
                className="w-full text-left px-3 py-1.5 text-sm text-brand-red hover:bg-surface-border/30 border-t border-surface-border/50"
                onMouseDown={openCreate}
              >
                Create "{query.trim()}"
              </button>
            )}
            {results.length === 0 && query.trim().length < 2 && (
              <p className="px-3 py-2 text-xs text-ink-muted">Type to search…</p>
            )}
            {results.length === 0 && query.trim().length >= 2 && hasExactMatch === false && (
              <p className="px-3 py-2 text-xs text-ink-muted">No matches</p>
            )}
          </div>
        )}
      </div>

      <div className="w-28">
        <Input
          label="Amount"
          type="number"
          value={row.amount}
          onChange={(e) => onPatch({ amount: e.target.value })}
        />
      </div>
      <div className="w-28">
        <Select
          label="Unit"
          options={AMOUNT_UNITS}
          value={row.unit}
          onChange={(e) => onPatch({ unit: e.target.value })}
        />
      </div>
      <button
        onClick={onRemove}
        className="mb-0.5 text-ink-muted hover:text-red-400 text-lg leading-none px-1"
        type="button"
      >
        ×
      </button>

      <CompoundFormModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSuccess={handleCreated}
        initialName={createInitialName}
        minimal
      />
    </div>
  )
}

/** Step 3 of new experiment wizard: chemical additives table with compound typeahead picker. */
export function Step3Additives({ rows, onChange, onBack, onNext }: Props) {
  const addRow = () => onChange([...rows, { compound_id: null, compound_name: '', amount: '', unit: 'g' }])

  const removeRow = (i: number) => onChange(rows.filter((_, idx) => idx !== i))

  const patchRow = (i: number, patch: Partial<AdditiveRow>) => {
    const updated = rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r))
    // Upsert semantics: if the patched compound_id already exists in another row, remove the duplicate
    if (patch.compound_id != null) {
      const newCompoundId = patch.compound_id
      const deduped = updated.filter((r, idx) => idx === i || r.compound_id !== newCompoundId)
      onChange(deduped)
    } else {
      onChange(updated)
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-ink-muted">Add chemical additives. Leave empty if none.</p>

      {rows.map((row, i) => (
        <RowEditor
          key={i}
          row={row}
          index={i}
          onPatch={(patch) => patchRow(i, patch)}
          onRemove={() => removeRow(i)}
        />
      ))}

      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={addRow} type="button">+ Add additive</Button>
        {rows.length === 0 && <span className="text-xs text-ink-muted">No additives (valid)</span>}
      </div>

      <div className="flex justify-between pt-2">
        <Button variant="ghost" onClick={onBack} type="button">← Back</Button>
        <Button variant="primary" onClick={onNext} type="button">Next: Review →</Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 7.2: Check TypeScript**

```bash
cd frontend && npx tsc --noEmit
```
Expected: Zero errors

- [ ] **Step 7.3: Check ESLint**

```bash
cd frontend && npx eslint src/pages/NewExperiment/Step3Additives.tsx --ext .tsx
```
Expected: Zero warnings

- [ ] **Step 7.4: Commit**

```bash
git add frontend/src/pages/NewExperiment/Step3Additives.tsx
git commit -m "[#7] Upgrade Step3Additives with per-row typeahead and create-inline compound option"
```

---

## Task 8: ConditionsTab.tsx — delete additive + experiment-based endpoints

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx`

Changes:
- Switch additive list from `chemicalsApi.listAdditives(conditions.id)` to `chemicalsApi.listExperimentAdditives(experimentId)`
- Add delete button per additive row (calls `chemicalsApi.deleteAdditive`)
- Replace "Add" modal with a compound typeahead + `CompoundFormModal` inline create (same pattern as Step 3)
- On additive add: call `chemicalsApi.upsertAdditive(experimentId, compound_id, payload)` instead of `addAdditive`

- [ ] **Step 8.1: Replace `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx` in full**

This is a complete replacement. The key changes from the existing file are:
- Additive list uses `listExperimentAdditives(experimentId)` instead of `listAdditives(conditions.id)`
- New state + queries for compound typeahead picker
- `upsertAdditiveMutation` replaces `addAdditiveMutation`
- New `deleteAdditiveMutation`
- Additive rows show a hover-reveal `×` delete button
- Add Additive modal uses a typeahead input with "Create compound" inline option

```tsx
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { conditionsApi, type ConditionsResponse, type ConditionsPayload } from '@/api/conditions'
import { chemicalsApi, type Compound } from '@/api/chemicals'
import { Button, Input, Select, Modal, useToast } from '@/components/ui'
import { CompoundFormModal } from '@/components/CompoundFormModal'

const FEEDSTOCK_OPTIONS = [
  { value: 'Nitrogen', label: 'Nitrogen' },
  { value: 'Nitrate', label: 'Nitrate' },
  { value: 'Blank', label: 'None / Blank' },
]

const ADDITIVE_UNIT_OPTIONS = [
  { value: 'g', label: 'g' }, { value: 'mg', label: 'mg' },
  { value: 'mM', label: 'mM' }, { value: 'ppm', label: 'ppm' },
  { value: '% of Rock', label: '% of Rock' }, { value: 'mL', label: 'mL' },
  { value: 'μL', label: 'μL' }, { value: 'mol', label: 'mol' },
  { value: 'mmol', label: 'mmol' },
]

interface Props {
  conditions: ConditionsResponse | null
  experimentId: string
}

function Row({ label, value, unit }: { label: string; value: unknown; unit?: string }) {
  if (value == null || value === '') return null
  return (
    <div className="flex items-baseline gap-4 py-1 border-b border-surface-border/50">
      <span className="text-xs text-ink-secondary w-44 shrink-0">{label}</span>
      <span className="text-xs font-mono-data text-ink-primary">
        {String(value)}{unit ? ` ${unit}` : ''}
      </span>
    </div>
  )
}

/** Conditions tab: editable experimental setup parameters and chemical additives. */
export function ConditionsTab({ conditions, experimentId }: Props) {
  const [editOpen, setEditOpen] = useState(false)
  const [form, setForm] = useState<Partial<ConditionsPayload>>({})

  // Add additive modal state
  const [addAdditiveOpen, setAddAdditiveOpen] = useState(false)
  const [selectedCompound, setSelectedCompound] = useState<{ id: number; name: string } | null>(null)
  const [additiveAmount, setAdditiveAmount] = useState('')
  const [additiveUnit, setAdditiveUnit] = useState('g')
  const [compoundQuery, setCompoundQuery] = useState('')
  const [compoundDropdownOpen, setCompoundDropdownOpen] = useState(false)
  const [createCompoundOpen, setCreateCompoundOpen] = useState(false)
  const [createCompoundName, setCreateCompoundName] = useState('')

  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()

  // Additives — keyed by experiment string ID (not conditions integer ID)
  const { data: additives = [] } = useQuery({
    queryKey: ['additives', experimentId],
    queryFn: () => chemicalsApi.listExperimentAdditives(experimentId),
  })

  // Compound search for picker
  const { data: compoundResults = [] } = useQuery({
    queryKey: ['compounds', compoundQuery],
    queryFn: () => chemicalsApi.listCompounds({ search: compoundQuery, limit: 10 }),
    enabled: compoundQuery.length >= 1 && compoundDropdownOpen,
  })

  const upsertAdditiveMutation = useMutation({
    mutationFn: () =>
      chemicalsApi.upsertAdditive(experimentId, selectedCompound!.id, {
        amount: parseFloat(additiveAmount),
        unit: additiveUnit,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['additives', experimentId] })
      success('Additive saved')
      setAddAdditiveOpen(false)
      setSelectedCompound(null)
      setAdditiveAmount('')
      setAdditiveUnit('g')
      setCompoundQuery('')
    },
    onError: (err: Error) => toastError('Failed to save additive', err.message),
  })

  const deleteAdditiveMutation = useMutation({
    mutationFn: (compoundId: number) => chemicalsApi.deleteAdditive(experimentId, compoundId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['additives', experimentId] })
      success('Additive removed')
    },
    onError: (err: Error) => toastError('Failed to remove additive', err.message),
  })

  const patchMutation = useMutation({
    mutationFn: () => conditionsApi.patch(conditions!.id, form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] })
      queryClient.invalidateQueries({ queryKey: ['conditions', experimentId] })
      success('Conditions updated')
      setEditOpen(false)
    },
    onError: (err: Error) => toastError('Update failed', err.message),
  })

  const openEdit = () => {
    setForm({
      temperature_c: conditions?.temperature_c ?? undefined,
      initial_ph: conditions?.initial_ph ?? undefined,
      rock_mass_g: conditions?.rock_mass_g ?? undefined,
      water_volume_mL: conditions?.water_volume_mL ?? undefined,
      feedstock: conditions?.feedstock ?? undefined,
      stir_speed_rpm: conditions?.stir_speed_rpm ?? undefined,
      reactor_number: conditions?.reactor_number ?? undefined,
      initial_conductivity_mS_cm: conditions?.initial_conductivity_mS_cm ?? undefined,
      room_temp_pressure_psi: conditions?.room_temp_pressure_psi ?? undefined,
      rxn_temp_pressure_psi: conditions?.rxn_temp_pressure_psi ?? undefined,
      co2_partial_pressure_MPa: conditions?.co2_partial_pressure_MPa ?? undefined,
      confining_pressure: conditions?.confining_pressure ?? undefined,
      pore_pressure: conditions?.pore_pressure ?? undefined,
      core_height_cm: conditions?.core_height_cm ?? undefined,
      core_width_cm: conditions?.core_width_cm ?? undefined,
    })
    setEditOpen(true)
  }

  const closeAddModal = () => {
    setAddAdditiveOpen(false)
    setSelectedCompound(null)
    setAdditiveAmount('')
    setAdditiveUnit('g')
    setCompoundQuery('')
  }

  if (!conditions) return <p className="text-sm text-ink-muted p-4">No conditions recorded for this experiment.</p>

  const set = (k: keyof ConditionsPayload) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((p) => ({ ...p, [k]: e.target.value === '' ? undefined : (isNaN(Number(e.target.value)) ? e.target.value : Number(e.target.value)) }))

  const hasExactCompoundMatch = compoundResults.some(
    (c: Compound) => c.name.toLowerCase() === compoundQuery.toLowerCase()
  )

  return (
    <>
      <div className="p-4 space-y-1">
        <div className="flex justify-end mb-2">
          <Button variant="ghost" size="xs" onClick={openEdit}>Edit</Button>
        </div>
        <Row label="Type" value={conditions.experiment_type} />
        <Row label="Temperature" value={conditions.temperature_c} unit="°C" />
        <Row label="Initial pH" value={conditions.initial_ph} />
        <Row label="Rock Mass" value={conditions.rock_mass_g} unit="g" />
        <Row label="Water Volume" value={conditions.water_volume_mL} unit="mL" />
        {conditions.water_to_rock_ratio != null && (
          <div className="flex items-baseline gap-4 py-1 border-b border-surface-border/50">
            <span className="text-xs text-ink-secondary font-semibold w-44 shrink-0">Water : Rock Ratio</span>
            <span className="text-xs font-mono-data text-brand-red font-semibold">{conditions.water_to_rock_ratio.toFixed(2)}</span>
          </div>
        )}
        <Row label="Particle Size" value={conditions.particle_size} />
        <Row label="Feedstock" value={conditions.feedstock} />
        <Row label="Reactor" value={conditions.reactor_number} />
        <Row label="Stir Speed" value={conditions.stir_speed_rpm} unit="RPM" />
        <Row label="Initial Conductivity" value={conditions.initial_conductivity_mS_cm} unit="mS/cm" />
        <Row label="Room Temp Pressure" value={conditions.room_temp_pressure_psi} unit="psi" />
        <Row label="Rxn Temp Pressure" value={conditions.rxn_temp_pressure_psi} unit="psi" />
        <Row label="CO₂ Partial Pressure" value={conditions.co2_partial_pressure_MPa} unit="MPa" />
        <Row label="Core Height" value={conditions.core_height_cm} unit="cm" />
        <Row label="Core Width" value={conditions.core_width_cm} unit="cm" />
        <Row label="Confining Pressure" value={conditions.confining_pressure} />
        <Row label="Pore Pressure" value={conditions.pore_pressure} />
      </div>

      {/* Chemical Additives */}
      <div className="px-4 pb-4 border-t border-surface-border mt-2 pt-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-ink-secondary uppercase tracking-wider">Chemical Additives</span>
          <Button variant="ghost" size="xs" onClick={() => setAddAdditiveOpen(true)}>+ Add</Button>
        </div>
        {additives.length === 0 ? (
          <p className="text-xs text-ink-muted">No additives recorded.</p>
        ) : (
          <div className="space-y-1">
            {additives.map((a) => (
              <div key={a.id} className="flex items-baseline gap-4 py-1 border-b border-surface-border/50 group">
                <span className="text-xs text-ink-secondary w-44 shrink-0">{a.compound?.name ?? `Compound #${a.compound_id}`}</span>
                <span className="text-xs font-mono-data text-ink-primary">{a.amount} {a.unit}</span>
                {a.mass_in_grams != null && (
                  <span className="text-xs text-ink-muted">{a.mass_in_grams.toFixed(4)} g</span>
                )}
                <button
                  onClick={() => deleteAdditiveMutation.mutate(a.compound_id)}
                  className="ml-auto text-xs text-ink-muted hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity px-1"
                  type="button"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Edit Conditions Modal */}
      <Modal open={editOpen} onClose={() => setEditOpen(false)} title="Edit Conditions">
        <div className="space-y-3 p-4">
          <div className="grid grid-cols-2 gap-3">
            <Input label="Particle Size" type="text" value={form.particle_size ?? ''} onChange={(e) => setForm((p) => ({ ...p, particle_size: e.target.value || undefined }))} />
            <Input label="Temperature (°C)" type="number" value={form.temperature_c ?? ''} onChange={set('temperature_c')} />
            <Input label="Initial pH" type="number" value={form.initial_ph ?? ''} onChange={set('initial_ph')} />
            <Input label="Rock Mass (g)" type="number" value={form.rock_mass_g ?? ''} onChange={set('rock_mass_g')} />
            <Input label="Water Volume (mL)" type="number" value={form.water_volume_mL ?? ''} onChange={set('water_volume_mL')} />
            <Select label="Feedstock" options={FEEDSTOCK_OPTIONS} value={form.feedstock ?? ''} onChange={set('feedstock')} placeholder="Select…" />
            <Input label="Stir Speed (RPM)" type="number" value={form.stir_speed_rpm ?? ''} onChange={set('stir_speed_rpm')} />
            <Input label="Reactor #" type="number" value={form.reactor_number ?? ''} onChange={set('reactor_number')} />
            <Input label="Initial Conductivity" type="number" value={form.initial_conductivity_mS_cm ?? ''} onChange={set('initial_conductivity_mS_cm')} />
            <Input label="Room Temp Pressure (psi)" type="number" value={form.room_temp_pressure_psi ?? ''} onChange={set('room_temp_pressure_psi')} />
            <Input label="Rxn Temp Pressure (psi)" type="number" value={form.rxn_temp_pressure_psi ?? ''} onChange={set('rxn_temp_pressure_psi')} />
            <Input label="CO₂ Partial Pressure (MPa)" type="number" value={form.co2_partial_pressure_MPa ?? ''} onChange={set('co2_partial_pressure_MPa')} />
            <Input label="Confining Pressure" type="number" value={form.confining_pressure ?? ''} onChange={set('confining_pressure')} />
            <Input label="Pore Pressure" type="number" value={form.pore_pressure ?? ''} onChange={set('pore_pressure')} />
            <Input label="Core Height (cm)" type="number" value={form.core_height_cm ?? ''} onChange={set('core_height_cm')} />
            <Input label="Core Width (cm)" type="number" value={form.core_width_cm ?? ''} onChange={set('core_width_cm')} />
          </div>
          <div className="flex gap-2 justify-end pt-2">
            <Button variant="ghost" onClick={() => setEditOpen(false)}>Cancel</Button>
            <Button variant="primary" loading={patchMutation.isPending} onClick={() => patchMutation.mutate()}>Save</Button>
          </div>
        </div>
      </Modal>

      {/* Add Additive Modal */}
      <Modal open={addAdditiveOpen} onClose={closeAddModal} title="Add Chemical Additive">
        <div className="space-y-3 p-4">
          {/* Compound typeahead */}
          <div className="relative">
            <label className="block text-xs font-medium text-ink-secondary mb-1">Compound</label>
            {selectedCompound ? (
              <div className="flex items-center gap-2">
                <span className="text-sm text-ink-primary font-medium">{selectedCompound.name}</span>
                <button
                  type="button"
                  className="text-xs text-ink-muted hover:text-ink-primary"
                  onClick={() => { setSelectedCompound(null); setCompoundQuery('') }}
                >
                  Change
                </button>
              </div>
            ) : (
              <>
                <input
                  className="w-full bg-surface-input border border-surface-border rounded px-2 py-1.5 text-sm text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50"
                  placeholder="Search compounds…"
                  value={compoundQuery}
                  onChange={(e) => { setCompoundQuery(e.target.value); setCompoundDropdownOpen(true) }}
                  onFocus={() => setCompoundDropdownOpen(true)}
                  onBlur={() => setTimeout(() => setCompoundDropdownOpen(false), 150)}
                  autoComplete="off"
                />
                {compoundDropdownOpen && compoundQuery.length >= 1 && (
                  <div className="absolute z-10 left-0 right-0 top-full mt-0.5 bg-surface-raised border border-surface-border rounded shadow-lg max-h-48 overflow-y-auto">
                    {compoundResults.map((c: Compound) => (
                      <button
                        key={c.id}
                        type="button"
                        className="w-full text-left px-3 py-1.5 text-sm text-ink-primary hover:bg-surface-border/30"
                        onMouseDown={() => {
                          setSelectedCompound({ id: c.id, name: c.name })
                          setCompoundQuery(c.name)
                          setCompoundDropdownOpen(false)
                        }}
                      >
                        {c.name}{c.formula ? ` (${c.formula})` : ''}
                      </button>
                    ))}
                    {!hasExactCompoundMatch && compoundQuery.trim().length >= 2 && (
                      <button
                        type="button"
                        className="w-full text-left px-3 py-1.5 text-sm text-brand-red hover:bg-surface-border/30 border-t border-surface-border/50"
                        onMouseDown={() => {
                          setCreateCompoundName(compoundQuery)
                          setCompoundDropdownOpen(false)
                          setCreateCompoundOpen(true)
                        }}
                      >
                        Create "{compoundQuery.trim()}"
                      </button>
                    )}
                  </div>
                )}
              </>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Amount"
              type="number"
              value={additiveAmount}
              onChange={(e) => setAdditiveAmount(e.target.value)}
            />
            <Select
              label="Unit"
              options={ADDITIVE_UNIT_OPTIONS}
              placeholder="Unit…"
              value={additiveUnit}
              onChange={(e) => setAdditiveUnit(e.target.value)}
            />
          </div>

          <div className="flex gap-2 justify-end pt-2">
            <Button variant="ghost" onClick={closeAddModal}>Cancel</Button>
            <Button
              variant="primary"
              loading={upsertAdditiveMutation.isPending}
              disabled={!selectedCompound || !additiveAmount || !additiveUnit}
              onClick={() => upsertAdditiveMutation.mutate()}
            >
              Save
            </Button>
          </div>
        </div>

        <CompoundFormModal
          open={createCompoundOpen}
          onClose={() => setCreateCompoundOpen(false)}
          onSuccess={(compound) => {
            setSelectedCompound({ id: compound.id, name: compound.name })
            setCompoundQuery(compound.name)
            setCreateCompoundOpen(false)
          }}
          initialName={createCompoundName}
          minimal
        />
      </Modal>
    </>
  )
}
```

- [ ] **Step 8.2: Check TypeScript**

```bash
cd frontend && npx tsc --noEmit
```
Expected: Zero errors

- [ ] **Step 8.3: Check ESLint**

```bash
cd frontend && npx eslint src/pages/ExperimentDetail/ConditionsTab.tsx --ext .tsx
```
Expected: Zero warnings

- [ ] **Step 8.4: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/ConditionsTab.tsx
git commit -m "[#7] Upgrade ConditionsTab additive editor with delete and upsert"
```

---

## Task 9: Final wiring — NewExperiment wizard uses upsertAdditive

**Files:**
- Modify: `frontend/src/pages/NewExperiment/index.tsx`

The wizard currently calls `chemicalsApi.addAdditive(cond.id, ...)` which uses the integer conditions ID. Switch to `chemicalsApi.upsertAdditive(exp.experiment_id, compound_id, ...)` so the new experiment flow is also consistent.

- [ ] **Step 9.1: Update additive submission in `frontend/src/pages/NewExperiment/index.tsx`**

Find and replace the additive creation block. Search for the comment `// 4. Create additives` and replace the entire block:

```tsx
// FIND (the old additive loop):
      // 4. Create additives
      for (const row of additives) {
        if (row.compound_id && row.amount) {
          const cond = await conditionsApi.getByExperiment(exp.experiment_id)
          await chemicalsApi.addAdditive(cond.id, {
            compound_id: row.compound_id,
            amount: parseFloat(row.amount),
            unit: row.unit,
          })
        }
      }

// REPLACE WITH:
      // 4. Create additives (deduped: compound_id is unique in rows after Step 3 upsert logic)
      for (const row of additives) {
        if (row.compound_id && row.amount) {
          await chemicalsApi.upsertAdditive(exp.experiment_id, row.compound_id, {
            amount: parseFloat(row.amount),
            unit: row.unit,
          })
        }
      }
```

Note: `conditionsApi` is still needed for `conditionsApi.create(...)` earlier in the wizard — do not remove that import.

- [ ] **Step 9.2: Check TypeScript**

```bash
cd frontend && npx tsc --noEmit
```
Expected: Zero errors

- [ ] **Step 9.3: Run full ESLint**

```bash
cd frontend && npx eslint src --ext .ts,.tsx
```
Expected: Zero warnings

- [ ] **Step 9.4: Run backend test suite one final time**

```bash
pytest tests/api/ -v
```
Expected: All PASS

- [ ] **Step 9.5: Final commit**

```bash
git add frontend/src/pages/NewExperiment/index.tsx
git commit -m "[#7] Switch wizard additive submission to experiment-scoped upsertAdditive"
```

---

## Acceptance Criteria Checklist

- [ ] A user can create a new compound from `/chemicals` without leaving the app
- [ ] A user can create a compound on-the-fly from the additive picker during experiment creation; it persists to `compounds` table
- [ ] The additive picker is fully wired to the live compound library — no hardcoded options
- [ ] Duplicate compound name (case-insensitive) rejected at API with 409; surfaced in UI via toast
- [ ] Duplicate CAS number rejected at API with 409; surfaced in UI via toast
- [ ] One additive row per compound per conditions row enforced at both API and DB level
- [ ] ESLint zero warnings, TypeScript strict mode zero errors
- [ ] All backend tests pass (`pytest tests/api/ -v`)
