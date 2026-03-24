# M9 Sample Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate and improve the full sample management workflow from legacy Streamlit into the React + FastAPI stack, adding map view, characterized auto-evaluation, photo gallery, and pXRF analysis linkage.

**Architecture:** New `backend/services/samples.py` handles `evaluate_characterized` and `normalize_pxrf_reading_no` business logic. The existing samples router is extended with photo upload, analysis CRUD, geo, and delete endpoints. Frontend replaces the Samples stub with a full inventory page (table + map toggle), New Sample Modal, four-tab detail page, and a reusable SampleSelector component.

**Tech Stack:** FastAPI + SQLAlchemy + PostgreSQL (backend), React 18 + React Query + Tailwind (frontend), react-leaflet + leaflet + react-leaflet-markercluster (map), pytest FastAPI TestClient (all tests).

**Testing strategy:** pytest API tests in `tests/api/test_samples.py` and service unit tests in `tests/services/test_samples_service.py`. No Playwright E2E — validate through the API and unit tests only.

---

## File Map

**Create:**
- `backend/services/samples.py` — `normalize_pxrf_reading_no`, `evaluate_characterized`, `log_sample_modification`
- `tests/services/test_samples_service.py` — unit tests for service functions (no DB)
- `frontend/src/pages/SampleDetail/index.tsx` — four-tab detail page entry
- `frontend/src/pages/SampleDetail/OverviewTab.tsx`
- `frontend/src/pages/SampleDetail/PhotosTab.tsx`
- `frontend/src/pages/SampleDetail/AnalysesTab.tsx`
- `frontend/src/pages/SampleDetail/ActivityTab.tsx`
- `frontend/src/pages/SampleDetail/NewSampleModal.tsx` — create form modal
- `frontend/src/components/ui/SampleSelector.tsx` — combobox with chip + create-new
- `frontend/src/components/map/MapView.tsx` — leaflet map with clustering

**Modify:**
- `database/models/experiments.py` — add `sample_id` nullable String to `ModificationsLog`
- `alembic/versions/` — new migration for ModificationsLog.sample_id
- `backend/config/settings.py` — add `sample_photos_dir` setting
- `backend/api/schemas/samples.py` — add SampleListItem, SampleDetail, SampleGeoItem, photo/analysis schemas
- `backend/api/routers/samples.py` — extend with all new endpoints
- `backend/api/main.py` — add static mount for `sample_photos/` if needed
- `tests/api/test_samples.py` — extend with all new endpoint tests
- `frontend/src/api/samples.ts` — all new types + API methods
- `frontend/src/pages/Samples.tsx` — replace stub with full inventory page
- `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx` — replace inline combobox with SampleSelector
- `frontend/src/components/ui/index.ts` — export SampleSelector
- `frontend/src/App.tsx` (or router file) — add `/samples/:sample_id` route
- `docs/api/API_REFERENCE.md` — new sample endpoints
- `docs/user_guide/SAMPLES.md` — new
- `docs/developer/SAMPLE_CHARACTERIZED_LOGIC.md` — new

---

## Task 1: Service Layer — pXRF Normalization

**Files:**
- Create: `backend/services/samples.py`
- Create: `tests/services/test_samples_service.py`

- [ ] **Step 1: Write failing unit tests for normalize_pxrf_reading_no**

```python
# tests/services/test_samples_service.py
from backend.services.samples import normalize_pxrf_reading_no

def test_normalize_strips_whitespace():
    assert normalize_pxrf_reading_no("  42  ") == "42"

def test_normalize_integer_float():
    assert normalize_pxrf_reading_no("1.0") == "1"
    assert normalize_pxrf_reading_no("12.00") == "12"

def test_normalize_non_float_unchanged():
    assert normalize_pxrf_reading_no("ABC-01") == "ABC-01"

def test_normalize_plain_int():
    assert normalize_pxrf_reading_no("7") == "7"
```

- [ ] **Step 2: Run — expect ImportError/AttributeError**

```
pytest tests/services/test_samples_service.py -v
```

- [ ] **Step 3: Create backend/services/samples.py with normalize function**

```python
# backend/services/samples.py
from __future__ import annotations
import re
import structlog
from sqlalchemy.orm import Session

log = structlog.get_logger(__name__)


def normalize_pxrf_reading_no(raw: str) -> str:
    """Normalize a pXRF reading number for consistent storage and lookup.

    Strips surrounding whitespace and converts integer-like floats
    (e.g. '1.0', '12.00') to plain integers to match legacy
    split_normalized_pxrf_readings behaviour.
    """
    v = raw.strip()
    if re.fullmatch(r"\d+\.0+", v):
        v = str(int(float(v)))
    return v
```

- [ ] **Step 4: Run — expect PASS**

```
pytest tests/services/test_samples_service.py -v
```

- [ ] **Step 5: Commit**

```
git add backend/services/samples.py tests/services/test_samples_service.py
git commit -m "[M9] Task 1: normalize_pxrf_reading_no service + tests"
```

---

## Task 2: Service Layer — evaluate_characterized

**Files:**
- Modify: `backend/services/samples.py`
- Modify: `tests/services/test_samples_service.py`

- [ ] **Step 1: Write failing tests for evaluate_characterized**

These tests use the real test DB (need `db_session` fixture from `tests/api/conftest.py`).
Add a `conftest.py` in `tests/services/` that re-exports the `db_session` fixture:

```python
# tests/services/conftest.py
from tests.api.conftest import db_session, create_test_tables  # noqa: F401
```

Then add tests:

```python
# tests/services/test_samples_service.py  (append)
import pytest
from database.models.samples import SampleInfo
from database.models.analysis import ExternalAnalysis, PXRFReading
from database.models.xrd import XRDAnalysis
from database.models.characterization import ElementalAnalysis, Analyte
from backend.services.samples import evaluate_characterized


def _sample(db, sid="CHAR_S01"):
    s = SampleInfo(sample_id=sid)
    db.add(s)
    db.flush()
    return s


def test_evaluate_no_analyses_returns_false(db_session):
    _sample(db_session)
    assert evaluate_characterized(db_session, "CHAR_S01") is False


def test_evaluate_xrd_with_analysis_returns_true(db_session):
    s = _sample(db_session, "CHAR_S02")
    ea = ExternalAnalysis(sample_id=s.sample_id, analysis_type="XRD")
    db_session.add(ea)
    db_session.flush()
    xrd = XRDAnalysis(external_analysis_id=ea.id, mineral_phases={})
    db_session.add(xrd)
    db_session.flush()
    assert evaluate_characterized(db_session, "CHAR_S02") is True


def test_evaluate_xrd_without_xrd_analysis_returns_false(db_session):
    s = _sample(db_session, "CHAR_S03")
    db_session.add(ExternalAnalysis(sample_id=s.sample_id, analysis_type="XRD"))
    db_session.flush()
    assert evaluate_characterized(db_session, "CHAR_S03") is False


def test_evaluate_elemental_with_rows_returns_true(db_session):
    s = _sample(db_session, "CHAR_S04")
    ea = ExternalAnalysis(sample_id=s.sample_id, analysis_type="Elemental")
    db_session.add(ea)
    db_session.flush()
    analyte = Analyte(analyte_symbol="SiO2", unit="%")
    db_session.add(analyte)
    db_session.flush()
    db_session.add(ElementalAnalysis(
        external_analysis_id=ea.id, sample_id=s.sample_id,
        analyte_id=analyte.id, analyte_composition=45.0,
    ))
    db_session.flush()
    assert evaluate_characterized(db_session, "CHAR_S04") is True


def test_evaluate_pxrf_with_existing_reading_returns_true(db_session):
    s = _sample(db_session, "CHAR_S05")
    db_session.add(PXRFReading(reading_no="99"))
    ea = ExternalAnalysis(
        sample_id=s.sample_id, analysis_type="pXRF", pxrf_reading_no="99"
    )
    db_session.add(ea)
    db_session.flush()
    assert evaluate_characterized(db_session, "CHAR_S05") is True


def test_evaluate_pxrf_with_missing_reading_returns_false(db_session):
    s = _sample(db_session, "CHAR_S06")
    db_session.add(ExternalAnalysis(
        sample_id=s.sample_id, analysis_type="pXRF", pxrf_reading_no="9999"
    ))
    db_session.flush()
    assert evaluate_characterized(db_session, "CHAR_S06") is False
```

- [ ] **Step 2: Run — expect FAIL (function not yet implemented)**

```
pytest tests/services/test_samples_service.py::test_evaluate_no_analyses_returns_false -v
```

- [ ] **Step 3: Implement evaluate_characterized and log_sample_modification**

```python
# backend/services/samples.py  (append below normalize_pxrf_reading_no)

def evaluate_characterized(db: Session, sample_id: str) -> bool:
    """Return True if the sample meets at least one characterization criterion."""
    from sqlalchemy import select
    from database.models.analysis import ExternalAnalysis, PXRFReading
    from database.models.characterization import ElementalAnalysis
    from database.models.xrd import XRDAnalysis

    # 1. XRD type with a linked XRDAnalysis record
    has_xrd = db.execute(
        select(ExternalAnalysis.id)
        .join(XRDAnalysis, XRDAnalysis.external_analysis_id == ExternalAnalysis.id)
        .where(
            ExternalAnalysis.sample_id == sample_id,
            ExternalAnalysis.analysis_type == "XRD",
        )
        .limit(1)
    ).first() is not None
    if has_xrd:
        return True

    # 2. Elemental or Titration with at least one ElementalAnalysis row
    has_elemental = db.execute(
        select(ExternalAnalysis.id)
        .join(ElementalAnalysis, ElementalAnalysis.external_analysis_id == ExternalAnalysis.id)
        .where(
            ExternalAnalysis.sample_id == sample_id,
            ExternalAnalysis.analysis_type.in_(["Elemental", "Titration"]),
        )
        .limit(1)
    ).first() is not None
    if has_elemental:
        return True

    # 3. pXRF linked to an existing PXRFReading row
    pxrf_readings = db.execute(
        select(ExternalAnalysis.pxrf_reading_no)
        .where(
            ExternalAnalysis.sample_id == sample_id,
            ExternalAnalysis.analysis_type == "pXRF",
            ExternalAnalysis.pxrf_reading_no.isnot(None),
        )
    ).scalars().all()
    for readings_str in pxrf_readings:
        for raw in readings_str.split(","):
            normalized = normalize_pxrf_reading_no(raw)
            if normalized and db.get(PXRFReading, normalized) is not None:
                return True

    return False


def log_sample_modification(
    db: Session,
    *,
    sample_id: str,
    modified_by: str,
    modification_type: str,
    modified_table: str,
    old_values: dict | None = None,
    new_values: dict | None = None,
) -> None:
    """Write a ModificationsLog entry for a sample-related change."""
    from database.models.experiments import ModificationsLog

    db.add(ModificationsLog(
        sample_id=sample_id,
        modified_by=modified_by,
        modification_type=modification_type,
        modified_table=modified_table,
        old_values=old_values or {},
        new_values=new_values or {},
    ))
```

- [ ] **Step 4: Run all service tests — expect PASS**

```
pytest tests/services/test_samples_service.py -v
```

- [ ] **Step 5: Commit**

```
git add backend/services/samples.py tests/services/test_samples_service.py tests/services/conftest.py
git commit -m "[M9] Task 2: evaluate_characterized + log_sample_modification + tests"
```

---

## Task 3: ModificationsLog Migration — sample_id Column

**Files:**
- Modify: `database/models/experiments.py` — add `sample_id` to ModificationsLog
- Create: `alembic/versions/<hash>_add_sample_id_to_modifications_log.py`

- [ ] **Step 1: Add column to model**

In `database/models/experiments.py`, find `class ModificationsLog` and add one line after `experiment_fk`:

```python
sample_id = Column(String, nullable=True, index=True)  # sample-related modifications
```

- [ ] **Step 2: Generate migration**

```
.venv/Scripts/alembic revision --autogenerate -m "add sample_id to modifications_log"
```

Review the generated file — confirm it only adds the column and index.

- [ ] **Step 3: Apply migration**

```
.venv/Scripts/alembic upgrade head
```

- [ ] **Step 4: Verify downgrade**

```
.venv/Scripts/alembic downgrade -1
.venv/Scripts/alembic upgrade head
```

Both should complete without error.

- [ ] **Step 5: Add sample_photos_dir to settings**

In `backend/config/settings.py`, add inside `class Settings`:

```python
# File storage
sample_photos_dir: str = "sample_photos"
```

- [ ] **Step 6: Commit**

```
git add database/models/experiments.py alembic/versions/ backend/config/settings.py
git commit -m "[M9] Task 3: add sample_id to ModificationsLog + settings.sample_photos_dir"
```

---

## Task 4: Pydantic Schema Extensions

**Files:**
- Modify: `backend/api/schemas/samples.py`

- [ ] **Step 1: Replace the file contents**

```python
# backend/api/schemas/samples.py
from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict


# ── Core sample schemas ────────────────────────────────────────────────────

class SampleCreate(BaseModel):
    sample_id: str
    rock_classification: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None


class SampleUpdate(BaseModel):
    rock_classification: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    characterized: Optional[bool] = None


class SampleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sample_id: str
    rock_classification: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    characterized: bool
    created_at: datetime


# ── List view (no nested objects) ─────────────────────────────────────────

class SampleListItem(BaseModel):
    """Flat projection for the inventory table — no nested objects."""
    sample_id: str
    rock_classification: Optional[str] = None
    locality: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    characterized: bool
    experiment_count: int = 0
    has_pxrf: bool = False
    has_xrd: bool = False
    has_elemental: bool = False
    created_at: datetime


class SampleListResponse(BaseModel):
    items: list[SampleListItem]
    total: int
    skip: int
    limit: int


# ── Geo view (map markers) ────────────────────────────────────────────────

class SampleGeoItem(BaseModel):
    sample_id: str
    latitude: float
    longitude: float
    rock_classification: Optional[str] = None
    characterized: bool


# ── Photo schemas ─────────────────────────────────────────────────────────

class SamplePhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sample_id: str
    file_name: Optional[str] = None
    file_path: str
    file_type: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime


# ── Analysis schemas ──────────────────────────────────────────────────────

ANALYSIS_TYPE = Literal["pXRF", "XRD", "Elemental", "Titration", "Magnetic Susceptibility", "Other"]

class ExternalAnalysisCreate(BaseModel):
    analysis_type: ANALYSIS_TYPE  # validated against known types
    analysis_date: Optional[datetime] = None
    laboratory: Optional[str] = None
    analyst: Optional[str] = None
    pxrf_reading_no: Optional[str] = None  # comma-separated reading numbers
    description: Optional[str] = None
    magnetic_susceptibility: Optional[str] = None


class AnalysisFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_analysis_id: int
    file_name: Optional[str] = None
    file_path: str
    file_type: Optional[str] = None
    created_at: datetime


class ExternalAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sample_id: Optional[str] = None
    analysis_type: Optional[str] = None
    analysis_date: Optional[datetime] = None
    laboratory: Optional[str] = None
    analyst: Optional[str] = None
    pxrf_reading_no: Optional[str] = None
    description: Optional[str] = None
    magnetic_susceptibility: Optional[str] = None
    created_at: datetime
    analysis_files: list[AnalysisFileResponse] = []


class ExternalAnalysisWithWarnings(BaseModel):
    analysis: ExternalAnalysisResponse
    warnings: list[str] = []


# ── Detail view (full nested) ─────────────────────────────────────────────

class LinkedExperiment(BaseModel):
    experiment_id: str
    experiment_type: Optional[str] = None  # from ExperimentalConditions.experiment_type
    status: Optional[str] = None
    date: Optional[datetime] = None


class ElementalAnalysisItem(BaseModel):
    """One analyte row from ElementalAnalysis, for the Analyses tab elemental group."""
    analyte_symbol: str
    unit: str
    analyte_composition: Optional[float] = None


class SampleDetail(BaseModel):
    sample_id: str
    rock_classification: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    characterized: bool
    created_at: datetime
    photos: list[SamplePhotoResponse] = []
    analyses: list[ExternalAnalysisResponse] = []
    elemental_results: list[ElementalAnalysisItem] = []
    experiments: list[LinkedExperiment] = []
```

- [ ] **Step 2: Run existing schema tests (if any)**

```
pytest tests/api/test_samples.py -v
```

All 5 existing tests should still pass (SampleResponse is unchanged).

- [ ] **Step 3: Commit**

```
git add backend/api/schemas/samples.py
git commit -m "[M9] Task 4: extend Pydantic schemas for list/detail/geo/photo/analysis"
```

---

## Task 5: Backend — Extend List + Detail + Delete + Geo Endpoints

**Files:**
- Modify: `backend/api/routers/samples.py`
- Modify: `tests/api/test_samples.py`

- [ ] **Step 1: Write failing tests for new endpoints**

Append to `tests/api/test_samples.py`:

```python
from database.models.analysis import ExternalAnalysis, PXRFReading
from database.models.experiments import Experiment, ModificationsLog
from database.models.enums import ExperimentStatus


def _make_experiment(db, sample_id="ROCK_T01", experiment_id="HPHT_001"):
    from database.models.experiments import Experiment
    from database.models.enums import ExperimentStatus
    e = Experiment(
        experiment_id=experiment_id,
        experiment_number=9001,
        sample_id=sample_id,
        status=ExperimentStatus.ONGOING,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


# --- List endpoint (SampleListItem) ---

def test_list_samples_returns_list_items(client, db_session):
    _make_sample(db_session, "LIST_S01")
    resp = client.get("/api/samples")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    item = next(i for i in data["items"] if i["sample_id"] == "LIST_S01")
    assert "experiment_count" in item
    assert "has_pxrf" in item
    assert "has_xrd" in item
    assert "has_elemental" in item


def test_list_samples_filter_characterized(client, db_session):
    s = _make_sample(db_session, "LIST_S02")
    s.characterized = True
    db_session.commit()
    resp = client.get("/api/samples", params={"characterized": "true"})
    assert resp.status_code == 200
    ids = [i["sample_id"] for i in resp.json()["items"]]
    assert "LIST_S02" in ids


def test_list_samples_search(client, db_session):
    _make_sample(db_session, "SEARCH_UNIQUE_XYZ")
    resp = client.get("/api/samples", params={"search": "SEARCH_UNIQUE"})
    assert resp.status_code == 200
    ids = [i["sample_id"] for i in resp.json()["items"]]
    assert "SEARCH_UNIQUE_XYZ" in ids


# --- Geo endpoint ---

def test_get_geo_returns_only_samples_with_coords(client, db_session):
    s1 = _make_sample(db_session, "GEO_S01")
    s1.latitude = 40.0
    s1.longitude = -74.0
    _make_sample(db_session, "GEO_S02")  # no coords
    db_session.commit()
    resp = client.get("/api/samples/geo")
    assert resp.status_code == 200
    ids = [i["sample_id"] for i in resp.json()]
    assert "GEO_S01" in ids
    assert "GEO_S02" not in ids


# --- Delete endpoint ---

def test_delete_sample_no_experiments(client, db_session):
    _make_sample(db_session, "DEL_S01")
    resp = client.delete("/api/samples/DEL_S01")
    assert resp.status_code == 204
    assert client.get("/api/samples/DEL_S01").status_code == 404


def test_delete_sample_with_experiments_returns_409(client, db_session):
    _make_sample(db_session, "DEL_S02")
    _make_experiment(db_session, sample_id="DEL_S02", experiment_id="DEL_EXP_001")
    resp = client.delete("/api/samples/DEL_S02")
    assert resp.status_code == 409


# --- Detail endpoint (SampleDetail) ---

def test_get_sample_detail_structure(client, db_session):
    _make_sample(db_session, "DETAIL_S01")
    resp = client.get("/api/samples/DETAIL_S01")
    assert resp.status_code == 200
    data = resp.json()
    assert "photos" in data
    assert "analyses" in data
    assert "experiments" in data
```

- [ ] **Step 2: Run — expect FAIL**

```
pytest tests/api/test_samples.py -v 2>&1 | tail -30
```

- [ ] **Step 3: Rewrite samples.py router with all endpoints**

```python
# backend/api/routers/samples.py
from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, case
from sqlalchemy.orm import Session, selectinload
from database.models.samples import SampleInfo, SamplePhotos
from database.models.analysis import ExternalAnalysis
from database.models.experiments import Experiment
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.samples import (
    SampleCreate, SampleUpdate, SampleResponse,
    SampleListItem, SampleListResponse, SampleGeoItem, SampleDetail,
    LinkedExperiment, SamplePhotoResponse,
)
from backend.services.samples import evaluate_characterized, log_sample_modification

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/samples", tags=["samples"])


# ── GET /api/samples/geo  (must come before /{sample_id}) ─────────────────
@router.get("/geo", response_model=list[SampleGeoItem])
def list_samples_geo(
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[SampleGeoItem]:
    rows = db.execute(
        select(SampleInfo)
        .where(SampleInfo.latitude.isnot(None), SampleInfo.longitude.isnot(None))
        .order_by(SampleInfo.sample_id)
    ).scalars().all()
    return [
        SampleGeoItem(
            sample_id=r.sample_id,
            latitude=r.latitude,
            longitude=r.longitude,
            rock_classification=r.rock_classification,
            characterized=r.characterized,
        )
        for r in rows
    ]


# ── GET /api/samples ───────────────────────────────────────────────────────
@router.get("", response_model=SampleListResponse)
def list_samples(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    country: str | None = None,
    rock_classification: str | None = None,
    locality: str | None = None,
    characterized: bool | None = None,
    search: str | None = None,
    has_pxrf: bool | None = None,
    has_xrd: bool | None = None,
    has_elemental: bool | None = None,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> SampleListResponse:
    # Subquery counts
    exp_count_sq = (
        select(func.count(Experiment.id))
        .where(Experiment.sample_id == SampleInfo.sample_id)
        .correlate(SampleInfo)
        .scalar_subquery()
    )
    pxrf_count_sq = (
        select(func.count(ExternalAnalysis.id))
        .where(
            ExternalAnalysis.sample_id == SampleInfo.sample_id,
            ExternalAnalysis.analysis_type == "pXRF",
        )
        .correlate(SampleInfo)
        .scalar_subquery()
    )
    xrd_count_sq = (
        select(func.count(ExternalAnalysis.id))
        .where(
            ExternalAnalysis.sample_id == SampleInfo.sample_id,
            ExternalAnalysis.analysis_type == "XRD",
        )
        .correlate(SampleInfo)
        .scalar_subquery()
    )
    elemental_count_sq = (
        select(func.count(ExternalAnalysis.id))
        .where(
            ExternalAnalysis.sample_id == SampleInfo.sample_id,
            ExternalAnalysis.analysis_type.in_(["Elemental", "Titration"]),
        )
        .correlate(SampleInfo)
        .scalar_subquery()
    )

    stmt = select(
        SampleInfo,
        exp_count_sq.label("experiment_count"),
        pxrf_count_sq.label("pxrf_count"),
        xrd_count_sq.label("xrd_count"),
        elemental_count_sq.label("elemental_count"),
    ).order_by(SampleInfo.sample_id)

    if country:
        stmt = stmt.where(SampleInfo.country == country)
    if rock_classification:
        stmt = stmt.where(SampleInfo.rock_classification == rock_classification)
    if locality:
        stmt = stmt.where(SampleInfo.locality.ilike(f"%{locality}%"))
    if characterized is not None:
        stmt = stmt.where(SampleInfo.characterized == characterized)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            SampleInfo.sample_id.ilike(pattern) | SampleInfo.description.ilike(pattern)
        )
    if has_pxrf is True:
        stmt = stmt.where(pxrf_count_sq > 0)
    if has_xrd is True:
        stmt = stmt.where(xrd_count_sq > 0)
    if has_elemental is True:
        stmt = stmt.where(elemental_count_sq > 0)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.offset(skip).limit(limit)).all()

    items = [
        SampleListItem(
            sample_id=r.SampleInfo.sample_id,
            rock_classification=r.SampleInfo.rock_classification,
            locality=r.SampleInfo.locality,
            state=r.SampleInfo.state,
            country=r.SampleInfo.country,
            characterized=r.SampleInfo.characterized,
            created_at=r.SampleInfo.created_at,
            experiment_count=r.experiment_count,
            has_pxrf=r.pxrf_count > 0,
            has_xrd=r.xrd_count > 0,
            has_elemental=r.elemental_count > 0,
        )
        for r in rows
    ]
    return SampleListResponse(items=items, total=total, skip=skip, limit=limit)


# ── GET /api/samples/{sample_id} ──────────────────────────────────────────
@router.get("/{sample_id}", response_model=SampleDetail)
def get_sample(
    sample_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> SampleDetail:
    from database.models.conditions import ExperimentalConditions
    from database.models.characterization import ElementalAnalysis

    sample = db.execute(
        select(SampleInfo)
        .where(SampleInfo.sample_id == sample_id)
        .options(
            selectinload(SampleInfo.photos),
            selectinload(SampleInfo.external_analyses).selectinload(ExternalAnalysis.analysis_files),
            selectinload(SampleInfo.experiments).selectinload(Experiment.conditions),
            selectinload(SampleInfo.elemental_results).selectinload(ElementalAnalysis.analyte),
        )
    ).scalar_one_or_none()
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")

    from backend.api.schemas.samples import ElementalAnalysisItem

    return SampleDetail(
        sample_id=sample.sample_id,
        rock_classification=sample.rock_classification,
        state=sample.state,
        country=sample.country,
        locality=sample.locality,
        latitude=sample.latitude,
        longitude=sample.longitude,
        description=sample.description,
        characterized=sample.characterized,
        created_at=sample.created_at,
        photos=[SamplePhotoResponse.model_validate(p) for p in sample.photos],
        analyses=[_to_analysis_response(a) for a in sample.external_analyses],
        elemental_results=[
            ElementalAnalysisItem(
                analyte_symbol=r.analyte.analyte_symbol,
                unit=r.analyte.unit,
                analyte_composition=r.analyte_composition,
            )
            for r in sample.elemental_results
            if r.analyte
        ],
        experiments=[
            LinkedExperiment(
                experiment_id=e.experiment_id,
                experiment_type=(
                    e.conditions.experiment_type.value
                    if e.conditions and e.conditions.experiment_type else None
                ),
                status=e.status.value if e.status else None,
                date=e.date,
            )
            for e in sample.experiments
        ],
    )


def _to_analysis_response(a: ExternalAnalysis):
    from backend.api.schemas.samples import ExternalAnalysisResponse, AnalysisFileResponse
    return ExternalAnalysisResponse(
        id=a.id,
        sample_id=a.sample_id,
        analysis_type=a.analysis_type,
        analysis_date=a.analysis_date,
        laboratory=a.laboratory,
        analyst=a.analyst,
        pxrf_reading_no=a.pxrf_reading_no,
        description=a.description,
        magnetic_susceptibility=a.magnetic_susceptibility,
        created_at=a.created_at,
        analysis_files=[AnalysisFileResponse.model_validate(f) for f in a.analysis_files],
    )


# ── POST /api/samples ─────────────────────────────────────────────────────
@router.post("", response_model=SampleResponse, status_code=201)
def create_sample(
    payload: SampleCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> SampleResponse:
    existing = db.get(SampleInfo, payload.sample_id)
    if existing:
        raise HTTPException(status_code=409, detail="Sample ID already exists")
    sample = SampleInfo(**payload.model_dump(), characterized=False)
    db.add(sample)
    db.flush()
    log_sample_modification(
        db, sample_id=sample.sample_id, modified_by=current_user.email,
        modification_type="create", modified_table="sample_info",
        new_values=payload.model_dump(),
    )
    db.commit()
    db.refresh(sample)
    log.info("sample_created", sample_id=sample.sample_id, user=current_user.email)
    return SampleResponse.model_validate(sample)


# ── PATCH /api/samples/{sample_id} ────────────────────────────────────────
@router.patch("/{sample_id}", response_model=SampleResponse)
def update_sample(
    sample_id: str,
    payload: SampleUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> SampleResponse:
    sample = db.get(SampleInfo, sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")

    old_values = {k: getattr(sample, k) for k in payload.model_fields}
    updates = payload.model_dump(exclude_unset=True)
    manual_characterized = "characterized" in updates

    for field, value in updates.items():
        setattr(sample, field, value)

    # Auto-evaluate characterized unless manually set
    if not manual_characterized:
        sample.characterized = evaluate_characterized(db, sample_id)

    log_sample_modification(
        db, sample_id=sample_id, modified_by=current_user.email,
        modification_type="update", modified_table="sample_info",
        old_values=old_values, new_values=updates,
    )
    db.commit()
    db.refresh(sample)
    return SampleResponse.model_validate(sample)


# ── DELETE /api/samples/{sample_id} ───────────────────────────────────────
@router.delete("/{sample_id}", status_code=204)
def delete_sample(
    sample_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> None:
    sample = db.get(SampleInfo, sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")

    linked = db.execute(
        select(func.count(Experiment.id))
        .where(Experiment.sample_id == sample_id)
    ).scalar_one()
    if linked > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Sample has {linked} linked experiment(s) and cannot be deleted",
        )

    log_sample_modification(
        db, sample_id=sample_id, modified_by=current_user.email,
        modification_type="delete", modified_table="sample_info",
    )
    db.delete(sample)
    db.commit()
    log.info("sample_deleted", sample_id=sample_id, user=current_user.email)
```

- [ ] **Step 4: Run tests**

```
pytest tests/api/test_samples.py -v
```

Expected: all passing.

- [ ] **Step 5: Commit**

```
git add backend/api/routers/samples.py tests/api/test_samples.py
git commit -m "[M9] Task 5: list/detail/delete/geo endpoints + tests"
```

---

## Task 6: Photo Upload Endpoints

**Files:**
- Modify: `backend/api/routers/samples.py`
- Modify: `tests/api/test_samples.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_samples.py  (append)
import io

def test_upload_photo_returns_201(client, db_session, tmp_path, monkeypatch):
    _make_sample(db_session, "PHOTO_S01")
    monkeypatch.setattr(
        "backend.api.routers.samples.get_settings",
        lambda: type("S", (), {"sample_photos_dir": str(tmp_path)})(),
    )
    content = b"fake image bytes"
    resp = client.post(
        "/api/samples/PHOTO_S01/photos",
        files={"file": ("shot.jpg", io.BytesIO(content), "image/jpeg")},
        data={"description": "Rock face"},
    )
    assert resp.status_code == 201
    assert resp.json()["file_name"] == "shot.jpg"


def test_upload_photo_rejects_bad_mime(client, db_session, tmp_path, monkeypatch):
    _make_sample(db_session, "PHOTO_S02")
    monkeypatch.setattr(
        "backend.api.routers.samples.get_settings",
        lambda: type("S", (), {"sample_photos_dir": str(tmp_path)})(),
    )
    resp = client.post(
        "/api/samples/PHOTO_S02/photos",
        files={"file": ("doc.pdf", io.BytesIO(b"pdf"), "application/pdf")},
    )
    assert resp.status_code == 415


def test_delete_photo(client, db_session, tmp_path, monkeypatch):
    from database.models.samples import SamplePhotos
    _make_sample(db_session, "PHOTO_S03")
    photo = SamplePhotos(
        sample_id="PHOTO_S03", file_path=str(tmp_path / "x.jpg"),
        file_name="x.jpg", file_type="image/jpeg",
    )
    db_session.add(photo)
    db_session.commit()
    db_session.refresh(photo)
    resp = client.delete(f"/api/samples/PHOTO_S03/photos/{photo.id}")
    assert resp.status_code == 204
```

- [ ] **Step 2: Run — expect FAIL**

```
pytest tests/api/test_samples.py::test_upload_photo_returns_201 -v
```

- [ ] **Step 3: Add photo endpoints to router**

Append to `backend/api/routers/samples.py`:

```python
import os
import uuid
from pathlib import Path
from fastapi import File, Form, UploadFile
from backend.config.settings import get_settings

PHOTO_ALLOWED_TYPES = {"image/jpeg", "image/png"}
MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB


@router.post("/{sample_id}/photos", response_model=SamplePhotoResponse, status_code=201)
async def upload_photo(
    sample_id: str,
    file: UploadFile = File(...),
    description: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> SamplePhotoResponse:
    if db.get(SampleInfo, sample_id) is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    if file.content_type not in PHOTO_ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Photo must be image/jpeg or image/png; got {file.content_type}",
        )
    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=422, detail="File exceeds 20 MB limit")

    settings = get_settings()
    dest_dir = Path(settings.sample_photos_dir) / sample_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(file.filename or "photo").stem
    ext = Path(file.filename or "photo").suffix or ".jpg"
    filename = f"{stem}_{uuid.uuid4().hex[:8]}{ext}"
    dest = dest_dir / filename
    dest.write_bytes(content)

    photo = SamplePhotos(
        sample_id=sample_id,
        file_path=str(dest),
        file_name=file.filename,
        file_type=file.content_type,
        description=description,
    )
    db.add(photo)
    log_sample_modification(
        db, sample_id=sample_id, modified_by=current_user.email,
        modification_type="create", modified_table="sample_photos",
        new_values={"file_name": file.filename},
    )
    db.commit()
    db.refresh(photo)
    return SamplePhotoResponse.model_validate(photo)


@router.delete("/{sample_id}/photos/{photo_id}", status_code=204)
def delete_photo(
    sample_id: str,
    photo_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> None:
    photo = db.execute(
        select(SamplePhotos)
        .where(SamplePhotos.id == photo_id, SamplePhotos.sample_id == sample_id)
    ).scalar_one_or_none()
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    file_path = Path(photo.file_path)
    if file_path.exists():
        file_path.unlink()

    log_sample_modification(
        db, sample_id=sample_id, modified_by=current_user.email,
        modification_type="delete", modified_table="sample_photos",
        old_values={"file_name": photo.file_name},
    )
    db.delete(photo)
    db.commit()
```

- [ ] **Step 4: Run photo tests**

```
pytest tests/api/test_samples.py -k "photo" -v
```

- [ ] **Step 5: Commit**

```
git add backend/api/routers/samples.py tests/api/test_samples.py
git commit -m "[M9] Task 6: photo upload/delete endpoints + tests"
```

---

## Task 7: Analysis CRUD Endpoints

**Files:**
- Modify: `backend/api/routers/samples.py`
- Modify: `tests/api/test_samples.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_samples.py  (append)

def test_create_analysis_pxrf_warn_missing_reading(client, db_session):
    _make_sample(db_session, "ANA_S01")
    payload = {
        "analysis_type": "pXRF",
        "pxrf_reading_no": "9876",
        "description": "Handheld scan",
    }
    resp = client.post("/api/samples/ANA_S01/analyses", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["analysis"]["analysis_type"] == "pXRF"
    assert any("9876" in w for w in body["warnings"])


def test_create_analysis_pxrf_no_warn_when_reading_exists(client, db_session):
    _make_sample(db_session, "ANA_S02")
    db_session.add(PXRFReading(reading_no="42"))
    db_session.commit()
    payload = {"analysis_type": "pXRF", "pxrf_reading_no": "42"}
    resp = client.post("/api/samples/ANA_S02/analyses", json=payload)
    assert resp.status_code == 201
    assert resp.json()["warnings"] == []


def test_create_analysis_updates_characterized(client, db_session):
    from database.models.xrd import XRDAnalysis
    _make_sample(db_session, "ANA_S03")
    payload = {"analysis_type": "XRD", "description": "Diffraction"}
    resp = client.post("/api/samples/ANA_S03/analyses", json=payload)
    assert resp.status_code == 201
    ea_id = resp.json()["analysis"]["id"]
    # Add XRDAnalysis row to trigger characterized
    xrd = XRDAnalysis(external_analysis_id=ea_id, mineral_phases={})
    db_session.add(xrd)
    db_session.commit()
    # Patch sample to re-trigger evaluation
    resp2 = client.patch("/api/samples/ANA_S03", json={"country": "USA"})
    assert resp2.json()["characterized"] is True


def test_list_analyses_by_sample(client, db_session):
    _make_sample(db_session, "ANA_S04")
    db_session.add(ExternalAnalysis(sample_id="ANA_S04", analysis_type="XRD"))
    db_session.add(ExternalAnalysis(sample_id="ANA_S04", analysis_type="pXRF"))
    db_session.commit()
    resp = client.get("/api/samples/ANA_S04/analyses")
    assert resp.status_code == 200
    types = [a["analysis_type"] for a in resp.json()]
    assert "XRD" in types
    assert "pXRF" in types


def test_delete_analysis(client, db_session):
    _make_sample(db_session, "ANA_S05")
    ea = ExternalAnalysis(sample_id="ANA_S05", analysis_type="XRD")
    db_session.add(ea)
    db_session.commit()
    db_session.refresh(ea)
    resp = client.delete(f"/api/samples/ANA_S05/analyses/{ea.id}")
    assert resp.status_code == 204


def test_get_activity_returns_modifications(client, db_session):
    _make_sample(db_session, "ACT_S01")
    # Patch triggers a ModificationsLog entry via log_sample_modification
    client.patch("/api/samples/ACT_S01", json={"country": "Australia"})
    resp = client.get("/api/samples/ACT_S01/activity")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["modified_table"] == "sample_info"
```

- [ ] **Step 2: Run — expect FAIL**

```
pytest tests/api/test_samples.py -k "ana" -v
```

- [ ] **Step 3: Add analysis endpoints to router**

Append to `backend/api/routers/samples.py`:

```python
from backend.api.schemas.samples import (
    ExternalAnalysisCreate, ExternalAnalysisResponse,
    ExternalAnalysisWithWarnings,
)


@router.post("/{sample_id}/analyses", response_model=ExternalAnalysisWithWarnings, status_code=201)
def create_analysis(
    sample_id: str,
    payload: ExternalAnalysisCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExternalAnalysisWithWarnings:
    from database.models.analysis import ExternalAnalysis, PXRFReading

    if db.get(SampleInfo, sample_id) is None:
        raise HTTPException(status_code=404, detail="Sample not found")

    warnings: list[str] = []

    # Normalize pXRF reading numbers and warn on missing
    normalized_readings: list[str] = []
    if payload.pxrf_reading_no:
        for raw in payload.pxrf_reading_no.split(","):
            normed = normalize_pxrf_reading_no(raw)
            if normed:
                normalized_readings.append(normed)
                if db.get(PXRFReading, normed) is None:
                    warnings.append(
                        f"pXRF reading '{normed}' not found in database — "
                        "it may be uploaded later via bulk upload"
                    )

    ea_data = payload.model_dump()
    if normalized_readings:
        ea_data["pxrf_reading_no"] = ",".join(normalized_readings)

    ea = ExternalAnalysis(sample_id=sample_id, **ea_data)
    db.add(ea)
    db.flush()

    # Re-evaluate characterized.
    # NOTE: For XRD analyses, evaluate_characterized checks for a linked XRDAnalysis row
    # which does not exist at this point — so the XRD branch will return False here.
    # characterized will be re-evaluated to True on the next PATCH to the sample
    # after the client has created the XRDAnalysis child record separately.
    sample = db.get(SampleInfo, sample_id)
    sample.characterized = evaluate_characterized(db, sample_id)

    log_sample_modification(
        db, sample_id=sample_id, modified_by=current_user.email,
        modification_type="create", modified_table="external_analyses",
        new_values={**ea_data, "id": ea.id},
    )
    db.commit()
    db.refresh(ea)
    return ExternalAnalysisWithWarnings(
        analysis=_to_analysis_response(ea), warnings=warnings
    )


@router.get("/{sample_id}/analyses", response_model=list[ExternalAnalysisResponse])
def list_analyses(
    sample_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[ExternalAnalysisResponse]:
    from database.models.analysis import ExternalAnalysis
    from sqlalchemy.orm import selectinload as sl

    rows = db.execute(
        select(ExternalAnalysis)
        .where(ExternalAnalysis.sample_id == sample_id)
        .options(sl(ExternalAnalysis.analysis_files))
        .order_by(ExternalAnalysis.analysis_date)
    ).scalars().all()
    return [_to_analysis_response(r) for r in rows]


@router.delete("/{sample_id}/analyses/{analysis_id}", status_code=204)
def delete_analysis(
    sample_id: str,
    analysis_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> None:
    from database.models.analysis import ExternalAnalysis

    from sqlalchemy.orm import selectinload as sl

    ea = db.execute(
        select(ExternalAnalysis)
        .where(
            ExternalAnalysis.id == analysis_id,
            ExternalAnalysis.sample_id == sample_id,
        )
        .options(sl(ExternalAnalysis.analysis_files))
    ).scalar_one_or_none()
    if ea is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Delete physical analysis files
    for af in ea.analysis_files:
        p = Path(af.file_path)
        if p.exists():
            p.unlink()

    log_sample_modification(
        db, sample_id=sample_id, modified_by=current_user.email,
        modification_type="delete", modified_table="external_analyses",
        old_values={"id": ea.id, "analysis_type": ea.analysis_type},
    )
    db.delete(ea)

    # Re-evaluate characterized after deletion
    sample = db.get(SampleInfo, sample_id)
    if sample:
        sample.characterized = evaluate_characterized(db, sample_id)

    db.commit()
```

- [ ] **Step 4: Run all sample tests**

```
pytest tests/api/test_samples.py -v
```

Target: all passing.

- [ ] **Step 5: Run full test suite**

```
pytest tests/ -v --tb=short 2>&1 | tail -20
```

- [ ] **Step 6: Commit**

```
git add backend/api/routers/samples.py tests/api/test_samples.py
git commit -m "[M9] Task 7: analysis CRUD endpoints + pXRF normalization + characterized trigger + tests"
```

---

## Task 8: Frontend API Client

**Files:**
- Modify: `frontend/src/api/samples.ts`

- [ ] **Step 1: Replace samples.ts**

```typescript
// frontend/src/api/samples.ts
import { apiClient } from './client'

// ── Core types ──────────────────────────────────────────────────────────

export interface Sample {
  sample_id: string
  rock_classification: string | null
  state: string | null
  country: string | null
  locality: string | null
  latitude: number | null
  longitude: number | null
  description: string | null
  characterized: boolean
  created_at: string
}

export interface SampleListItem {
  sample_id: string
  rock_classification: string | null
  locality: string | null
  state: string | null
  country: string | null
  characterized: boolean
  experiment_count: number
  has_pxrf: boolean
  has_xrd: boolean
  has_elemental: boolean
  created_at: string
}

export interface SampleListResponse {
  items: SampleListItem[]
  total: number
  skip: number
  limit: number
}

export interface SampleGeoItem {
  sample_id: string
  latitude: number
  longitude: number
  rock_classification: string | null
  characterized: boolean
}

export interface SamplePhoto {
  id: number
  sample_id: string
  file_name: string | null
  file_path: string
  file_type: string | null
  description: string | null
  created_at: string
}

export interface ExternalAnalysis {
  id: number
  sample_id: string | null
  analysis_type: string | null
  analysis_date: string | null
  laboratory: string | null
  analyst: string | null
  pxrf_reading_no: string | null
  description: string | null
  magnetic_susceptibility: string | null
  created_at: string
  analysis_files: AnalysisFile[]
}

export interface AnalysisFile {
  id: number
  external_analysis_id: number
  file_name: string | null
  file_path: string
  file_type: string | null
  created_at: string
}

export interface ActivityEntry {
  id: number
  modification_type: string
  modified_table: string
  modified_by: string
  old_values: Record<string, unknown>
  new_values: Record<string, unknown>
  created_at: string
}

export interface ElementalAnalysisItem {
  analyte_symbol: string
  unit: string
  analyte_composition: number | null
}

export interface LinkedExperiment {
  experiment_id: string
  experiment_type: string | null
  status: string | null
  date: string | null
}

export interface SampleDetail extends Sample {
  photos: SamplePhoto[]
  analyses: ExternalAnalysis[]
  elemental_results: ElementalAnalysisItem[]
  experiments: LinkedExperiment[]
}

export interface ExternalAnalysisCreate {
  analysis_type: string
  analysis_date?: string | null
  laboratory?: string | null
  analyst?: string | null
  pxrf_reading_no?: string | null
  description?: string | null
  magnetic_susceptibility?: string | null
}

export interface AnalysisWithWarnings {
  analysis: ExternalAnalysis
  warnings: string[]
}

// ── List filter params ──────────────────────────────────────────────────

export interface SampleListParams {
  skip?: number
  limit?: number
  country?: string
  rock_classification?: string
  locality?: string
  characterized?: boolean
  search?: string
  has_pxrf?: boolean
  has_xrd?: boolean
  has_elemental?: boolean
}

// ── API client ──────────────────────────────────────────────────────────

export const samplesApi = {
  list: (params?: SampleListParams) =>
    apiClient.get<SampleListResponse>('/samples', { params }).then((r) => r.data),

  listGeo: () =>
    apiClient.get<SampleGeoItem[]>('/samples/geo').then((r) => r.data),

  get: (id: string) =>
    apiClient.get<SampleDetail>(`/samples/${id}`).then((r) => r.data),

  create: (payload: Partial<Sample>) =>
    apiClient.post<Sample>('/samples', payload).then((r) => r.data),

  patch: (id: string, payload: Partial<Sample>) =>
    apiClient.patch<Sample>(`/samples/${id}`, payload).then((r) => r.data),

  delete: (id: string) =>
    apiClient.delete(`/samples/${id}`),

  uploadPhoto: (id: string, file: File, description?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (description) form.append('description', description)
    return apiClient.post<SamplePhoto>(`/samples/${id}/photos`, form).then((r) => r.data)
  },

  deletePhoto: (sampleId: string, photoId: number) =>
    apiClient.delete(`/samples/${sampleId}/photos/${photoId}`),

  listAnalyses: (id: string) =>
    apiClient.get<ExternalAnalysis[]>(`/samples/${id}/analyses`).then((r) => r.data),

  createAnalysis: (id: string, payload: ExternalAnalysisCreate) =>
    apiClient.post<AnalysisWithWarnings>(`/samples/${id}/analyses`, payload).then((r) => r.data),

  deleteAnalysis: (sampleId: string, analysisId: number) =>
    apiClient.delete(`/samples/${sampleId}/analyses/${analysisId}`),

  listActivity: (sampleId: string) =>
    apiClient.get<ActivityEntry[]>(`/samples/${sampleId}/activity`).then((r) => r.data),
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```
git add frontend/src/api/samples.ts
git commit -m "[M9] Task 8: extend samples API client with all M9 types"
```

---

## Task 9: Install Map Packages

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install react-leaflet packages**

```
cd frontend && npm install leaflet react-leaflet
npm install --save-dev @types/leaflet
```

> `react-leaflet-markercluster` has poor React 18 compatibility. Use `react-leaflet-cluster` instead (React 18 compatible, maintained):

```
npm install react-leaflet-cluster
```

- [ ] **Step 2: Verify build**

```
npm run build 2>&1 | tail -10
```

Expected: clean build.

- [ ] **Step 3: Commit**

```
git add frontend/package.json frontend/package-lock.json
git commit -m "[M9] Task 9: install leaflet + react-leaflet + react-leaflet-cluster"
```

---

## Task 10: MapView Component

**Files:**
- Create: `frontend/src/components/map/MapView.tsx`

- [ ] **Step 1: Create MapView component**

```tsx
// frontend/src/components/map/MapView.tsx
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import { Link } from 'react-router-dom'
import type { SampleGeoItem } from '@/api/samples'

// Fix leaflet default icon paths broken by webpack/vite bundling
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
})

const characterizedIcon = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
})

interface Props {
  samples: SampleGeoItem[]
}

export function MapView({ samples }: Props) {
  const center: [number, number] = samples.length
    ? [samples[0].latitude, samples[0].longitude]
    : [20, 0]

  return (
    <MapContainer center={center} zoom={3} className="h-96 w-full rounded-lg border border-surface-border">
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      />
      <MarkerClusterGroup>
        {samples.map((s) => (
          <Marker
            key={s.sample_id}
            position={[s.latitude, s.longitude]}
            icon={s.characterized ? characterizedIcon : new L.Icon.Default()}
          >
            <Popup>
              <div className="text-sm space-y-1">
                <p className="font-semibold font-mono-data">{s.sample_id}</p>
                {s.rock_classification && <p className="text-ink-muted">{s.rock_classification}</p>}
                <Link to={`/samples/${s.sample_id}`} className="text-brand-red underline text-xs">
                  View detail →
                </Link>
              </div>
            </Popup>
          </Marker>
        ))}
      </MarkerClusterGroup>
    </MapContainer>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```
git add frontend/src/components/map/
git commit -m "[M9] Task 10: MapView component with leaflet clustering"
```

---

## Task 11: Samples Inventory Page

**Files:**
- Modify: `frontend/src/pages/Samples.tsx`

Replace the stub with a full implementation:

- [ ] **Step 1: Rewrite Samples.tsx**

```tsx
// frontend/src/pages/Samples.tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { samplesApi, type SampleListParams } from '@/api/samples'
import {
  Table, TableHead, TableBody, TableRow, Th, Td,
  Badge, StatusBadge, Button, Input, Select, Modal, PageSpinner, useToast,
} from '@/components/ui'
import { MapView } from '@/components/map/MapView'
import { NewSampleModal } from './SampleDetail/NewSampleModal'

type ViewMode = 'table' | 'map'

export function SamplesPage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [view, setView] = useState<ViewMode>('table')
  const [search, setSearch] = useState('')
  const [country, setCountry] = useState('')
  const [characterized, setCharacterized] = useState<boolean | undefined>()
  const [hasPxrf, setHasPxrf] = useState(false)
  const [hasXrd, setHasXrd] = useState(false)
  const [hasElemental, setHasElemental] = useState(false)
  const [skip, setSkip] = useState(0)
  const [limit] = useState(50)
  const [showNewModal, setShowNewModal] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  const params: SampleListParams = {
    skip, limit,
    ...(search && { search }),
    ...(country && { country }),
    ...(characterized !== undefined && { characterized }),
    ...(hasPxrf && { has_pxrf: true }),
    ...(hasXrd && { has_xrd: true }),
    ...(hasElemental && { has_elemental: true }),
  }

  const { data, isLoading } = useQuery({
    queryKey: ['samples', params],
    queryFn: () => samplesApi.list(params),
  })

  const { data: geoData } = useQuery({
    queryKey: ['samples-geo'],
    queryFn: () => samplesApi.listGeo(),
    enabled: view === 'map',
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => samplesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['samples'] })
      toast({ title: 'Sample deleted', variant: 'success' })
      setDeleteTarget(null)
    },
    onError: (err: unknown) => {
      const msg = (err as { message?: string }).message ?? 'Delete failed'
      toast({ title: msg, variant: 'error' })
      setDeleteTarget(null)
    },
  })

  const totalPages = data ? Math.ceil(data.total / limit) : 0
  const currentPage = Math.floor(skip / limit) + 1

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-ink-primary">Samples</h1>
          <p className="text-xs text-ink-muted mt-0.5">
            {data ? `${data.total} samples` : 'Geological sample inventory'}
          </p>
        </div>
        <Button variant="primary" onClick={() => setShowNewModal(true)}>+ New Sample</Button>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap gap-2 items-center">
        <Input
          placeholder="Search by ID or description…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setSkip(0) }}
          className="w-64"
        />
        <Input
          placeholder="Country"
          value={country}
          onChange={(e) => { setCountry(e.target.value); setSkip(0) }}
          className="w-36"
        />
        <Select
          options={[
            { value: '', label: 'All' },
            { value: 'true', label: 'Characterized' },
            { value: 'false', label: 'Uncharacterized' },
          ]}
          value={characterized === undefined ? '' : String(characterized)}
          onChange={(e) => {
            setCharacterized(e.target.value === '' ? undefined : e.target.value === 'true')
            setSkip(0)
          }}
          className="w-40"
        />
        {(['pXRF', 'XRD', 'Elemental'] as const).map((label) => {
          const active = label === 'pXRF' ? hasPxrf : label === 'XRD' ? hasXrd : hasElemental
          const setter = label === 'pXRF' ? setHasPxrf : label === 'XRD' ? setHasXrd : setHasElemental
          return (
            <button
              key={label}
              onClick={() => { setter(!active); setSkip(0) }}
              className={`px-3 py-1 rounded text-xs font-medium border transition-colors ${
                active
                  ? 'bg-brand-red/10 border-brand-red text-brand-red'
                  : 'border-surface-border text-ink-muted hover:border-ink-muted'
              }`}
            >
              {label}
            </button>
          )
        })}
        <div className="ml-auto flex gap-1">
          {(['table', 'map'] as ViewMode[]).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`px-3 py-1 rounded text-xs capitalize border transition-colors ${
                view === v ? 'bg-surface-raised border-surface-border' : 'border-transparent text-ink-muted'
              }`}
            >
              {v}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <PageSpinner />}

      {/* Map view */}
      {view === 'map' && geoData && data && (
        <div className="space-y-4">
          {geoData.length > 0
            ? <MapView samples={geoData} />
            : <p className="text-sm text-ink-muted text-center py-4">No samples with coordinates</p>
          }
          {/* Samples without coordinates */}
          {(() => {
            const geoIds = new Set(geoData.map((g) => g.sample_id))
            const noCoords = data.items.filter((s) => !geoIds.has(s.sample_id))
            if (noCoords.length === 0) return null
            return (
              <div>
                <h2 className="text-sm font-medium text-ink-secondary mb-2">No Coordinates ({noCoords.length})</h2>
                <div className="space-y-1">
                  {noCoords.map((s) => (
                    <div
                      key={s.sample_id}
                      onClick={() => navigate(`/samples/${s.sample_id}`)}
                      className="flex items-center gap-3 px-3 py-2 rounded hover:bg-surface-overlay cursor-pointer text-sm"
                    >
                      <span className="font-mono-data text-ink-primary">{s.sample_id}</span>
                      <span className="text-ink-muted">{s.rock_classification ?? '—'}</span>
                    </div>
                  ))}
                </div>
              </div>
            )
          })()}
        </div>
      )}

      {/* Table view */}
      {view === 'table' && data && (
        <>
          <Table>
            <TableHead>
              <tr>
                <Th>Sample ID</Th>
                <Th>Classification</Th>
                <Th>Location</Th>
                <Th>Characterized</Th>
                <Th>Analyses</Th>
                <Th>Experiments</Th>
                <Th></Th>
              </tr>
            </TableHead>
            <TableBody>
              {data.items.length === 0 ? (
                <TableRow>
                  <Td colSpan={7} className="text-center py-8 text-ink-muted">No samples found</Td>
                </TableRow>
              ) : (
                data.items.map((s) => (
                  <TableRow
                    key={s.sample_id}
                    onClick={() => navigate(`/samples/${s.sample_id}`)}
                    className="cursor-pointer"
                  >
                    <Td className="font-mono-data text-ink-primary">{s.sample_id}</Td>
                    <Td>{s.rock_classification ?? <span className="text-ink-muted">—</span>}</Td>
                    <Td className="text-ink-muted">
                      {[s.locality, s.state, s.country].filter(Boolean).join(', ') || '—'}
                    </Td>
                    <Td>
                      <StatusBadge variant={s.characterized ? 'success' : 'neutral'}>
                        {s.characterized ? 'Yes' : 'No'}
                      </StatusBadge>
                    </Td>
                    <Td>
                      <div className="flex gap-1">
                        {s.has_pxrf && <Badge variant="default">pXRF</Badge>}
                        {s.has_xrd && <Badge variant="default">XRD</Badge>}
                        {s.has_elemental && <Badge variant="default">Elem</Badge>}
                      </div>
                    </Td>
                    <Td className="tabular-nums">{s.experiment_count}</Td>
                    <Td onClick={(e) => e.stopPropagation()}>
                      <button
                        className="text-xs text-red-400 hover:text-red-300"
                        onClick={() => setDeleteTarget(s.sample_id)}
                      >
                        Delete
                      </button>
                    </Td>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between text-sm text-ink-muted">
              <span>Page {currentPage} of {totalPages}</span>
              <div className="flex gap-2">
                <Button variant="ghost" disabled={skip === 0} onClick={() => setSkip(skip - limit)}>
                  ← Prev
                </Button>
                <Button variant="ghost" disabled={currentPage >= totalPages} onClick={() => setSkip(skip + limit)}>
                  Next →
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      {/* New Sample Modal */}
      {showNewModal && (
        <NewSampleModal
          onClose={() => setShowNewModal(false)}
          onCreated={(id) => {
            queryClient.invalidateQueries({ queryKey: ['samples'] })
            setShowNewModal(false)
            navigate(`/samples/${id}`)
          }}
        />
      )}

      {/* Delete confirmation */}
      {deleteTarget && (
        <Modal
          title="Delete Sample"
          onClose={() => setDeleteTarget(null)}
          footer={
            <>
              <Button variant="ghost" onClick={() => setDeleteTarget(null)}>Cancel</Button>
              <Button
                variant="danger"
                onClick={() => deleteMutation.mutate(deleteTarget)}
                disabled={deleteMutation.isPending}
              >
                Delete
              </Button>
            </>
          }
        >
          <p className="text-sm text-ink-secondary">
            Delete <span className="font-mono-data">{deleteTarget}</span>? This cannot be undone.
          </p>
        </Modal>
      )}
    </div>
  )
}
```

- [ ] **Step 2: TypeScript check**

```
cd frontend && npx tsc --noEmit
```

Fix any type errors before committing.

- [ ] **Step 3: Commit**

```
git add frontend/src/pages/Samples.tsx
git commit -m "[M9] Task 11: replace Samples stub with full inventory page + map toggle"
```

---

## Task 12: New Sample Modal

**Files:**
- Create: `frontend/src/pages/SampleDetail/NewSampleModal.tsx`

- [ ] **Step 1: Create the modal**

```tsx
// frontend/src/pages/SampleDetail/NewSampleModal.tsx
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { samplesApi } from '@/api/samples'
import { Modal, Input, Button, useToast } from '@/components/ui'

interface Props {
  onClose: () => void
  onCreated: (sampleId: string) => void
}

interface FormData {
  sample_id: string
  rock_classification: string
  locality: string
  state: string
  country: string
  latitude: string
  longitude: string
  description: string
  pxrf_reading_no: string
  magnetic_susceptibility: string
}

const EMPTY: FormData = {
  sample_id: '', rock_classification: '', locality: '', state: '',
  country: '', latitude: '', longitude: '', description: '',
  pxrf_reading_no: '', magnetic_susceptibility: '',
}

export function NewSampleModal({ onClose, onCreated }: Props) {
  const { toast } = useToast()
  const [form, setForm] = useState<FormData>(EMPTY)
  const [photo, setPhoto] = useState<File | null>(null)
  const [photoDesc, setPhotoDesc] = useState('')
  const [step, setStep] = useState<'idle' | 'creating' | 'uploading' | 'done'>('idle')
  const [warnings, setWarnings] = useState<string[]>([])

  const set = (k: keyof FormData) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  const handleSubmit = async () => {
    if (!form.sample_id.trim()) return
    setStep('creating')
    setWarnings([])
    try {
      const sample = await samplesApi.create({
        sample_id: form.sample_id.trim(),
        rock_classification: form.rock_classification || undefined,
        locality: form.locality || undefined,
        state: form.state || undefined,
        country: form.country || undefined,
        latitude: form.latitude ? parseFloat(form.latitude) : undefined,
        longitude: form.longitude ? parseFloat(form.longitude) : undefined,
        description: form.description || undefined,
      })

      setStep('uploading')

      if (photo) {
        await samplesApi.uploadPhoto(sample.sample_id, photo, photoDesc || undefined)
      }

      const w: string[] = []
      if (form.pxrf_reading_no) {
        const result = await samplesApi.createAnalysis(sample.sample_id, {
          analysis_type: 'pXRF',
          pxrf_reading_no: form.pxrf_reading_no,
        })
        w.push(...result.warnings)
      }
      if (form.magnetic_susceptibility) {
        await samplesApi.createAnalysis(sample.sample_id, {
          analysis_type: 'Magnetic Susceptibility',
          magnetic_susceptibility: form.magnetic_susceptibility,
        })
      }

      setWarnings(w)
      setStep('done')
      toast({ title: `Sample ${sample.sample_id} created`, variant: 'success' })
      onCreated(sample.sample_id)
    } catch (err) {
      const msg = (err as { message?: string }).message ?? 'Failed to create sample'
      toast({ title: msg, variant: 'error' })
      setStep('idle')
    }
  }

  const busy = step === 'creating' || step === 'uploading'

  return (
    <Modal
      title="New Sample"
      size="lg"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="primary" onClick={handleSubmit} disabled={busy || !form.sample_id.trim()}>
            {step === 'creating' ? 'Creating…' : step === 'uploading' ? 'Uploading…' : 'Create Sample'}
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-4">
        {/* Left column */}
        <div className="space-y-3">
          <Input label="Sample ID *" value={form.sample_id} onChange={set('sample_id')} />
          <Input label="Rock Classification" value={form.rock_classification} onChange={set('rock_classification')} />
          <Input label="Locality" value={form.locality} onChange={set('locality')} />
          <Input label="State / Province" value={form.state} onChange={set('state')} />
          <Input label="Country" value={form.country} onChange={set('country')} />
          <div className="grid grid-cols-2 gap-2">
            <Input label="Latitude" type="number" value={form.latitude} onChange={set('latitude')} />
            <Input label="Longitude" type="number" value={form.longitude} onChange={set('longitude')} />
          </div>
          <div>
            <label className="block text-xs font-medium text-ink-secondary mb-1">Description</label>
            <textarea
              className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary placeholder-ink-muted focus:outline-none focus:ring-1 focus:ring-brand-red/50 resize-none"
              rows={3}
              value={form.description}
              onChange={set('description')}
            />
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-3">
          <Input
            label="pXRF Reading No (optional)"
            value={form.pxrf_reading_no}
            onChange={set('pxrf_reading_no')}
            hint="Comma-separated: 1, 2, 3"
          />
          <Input
            label="Magnetic Susceptibility (optional)"
            value={form.magnetic_susceptibility}
            onChange={set('magnetic_susceptibility')}
            hint="Units: 1×10⁻³"
          />
          <div>
            <label className="block text-xs font-medium text-ink-secondary mb-1">
              Sample Photo (optional)
            </label>
            <input
              type="file"
              accept="image/jpeg,image/png"
              onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
              className="text-sm text-ink-primary"
            />
            {photo && (
              <Input
                label="Photo description"
                value={photoDesc}
                onChange={(e) => setPhotoDesc(e.target.value)}
                className="mt-2"
              />
            )}
          </div>
          {warnings.length > 0 && (
            <div className="rounded border border-yellow-500/30 bg-yellow-500/10 p-3 text-xs text-yellow-300 space-y-1">
              {warnings.map((w, i) => <p key={i}>{w}</p>)}
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}
```

- [ ] **Step 2: TypeScript check**

```
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```
git add frontend/src/pages/SampleDetail/NewSampleModal.tsx
git commit -m "[M9] Task 12: NewSampleModal — create + photo + analysis in one flow"
```

---

## Task 13: Sample Detail Page

**Files:**
- Create: `frontend/src/pages/SampleDetail/index.tsx`
- Create: `frontend/src/pages/SampleDetail/OverviewTab.tsx`
- Create: `frontend/src/pages/SampleDetail/PhotosTab.tsx`
- Create: `frontend/src/pages/SampleDetail/AnalysesTab.tsx`
- Create: `frontend/src/pages/SampleDetail/ActivityTab.tsx`
- Modify: router file (App.tsx or routes file)

- [ ] **Step 1: Find the router file**

```
grep -r "Route" frontend/src/App.tsx | head -5
```

- [ ] **Step 2: Create SampleDetail/index.tsx**

```tsx
// frontend/src/pages/SampleDetail/index.tsx
import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { samplesApi } from '@/api/samples'
import { PageSpinner, Button } from '@/components/ui'
import { OverviewTab } from './OverviewTab'
import { PhotosTab } from './PhotosTab'
import { AnalysesTab } from './AnalysesTab'
import { ActivityTab } from './ActivityTab'

type Tab = 'overview' | 'photos' | 'analyses' | 'activity'

export function SampleDetailPage() {
  const { sampleId } = useParams<{ sampleId: string }>()
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('overview')

  const { data: sample, isLoading, error } = useQuery({
    queryKey: ['sample', sampleId],
    queryFn: () => samplesApi.get(sampleId!),
    enabled: Boolean(sampleId),
  })

  if (isLoading) return <PageSpinner />
  if (error || !sample) return (
    <div className="text-sm text-ink-muted p-8 text-center">
      Sample not found. <button onClick={() => navigate('/samples')} className="text-brand-red underline">Back to inventory</button>
    </div>
  )

  const TABS: { id: Tab; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'photos', label: `Photos (${sample.photos.length})` },
    { id: 'analyses', label: `Analyses (${sample.analyses.length})` },
    { id: 'activity', label: 'Activity' },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/samples')} className="text-ink-muted hover:text-ink-primary text-sm">
          ← Samples
        </button>
        <h1 className="text-lg font-semibold font-mono-data text-ink-primary">{sample.sample_id}</h1>
        {sample.rock_classification && (
          <span className="text-sm text-ink-muted">{sample.rock_classification}</span>
        )}
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-surface-border">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
              tab === t.id
                ? 'border-brand-red text-ink-primary'
                : 'border-transparent text-ink-muted hover:text-ink-primary'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'overview' && <OverviewTab sample={sample} />}
      {tab === 'photos' && <PhotosTab sample={sample} />}
      {tab === 'analyses' && <AnalysesTab sample={sample} />}
      {tab === 'activity' && <ActivityTab sampleId={sample.sample_id} />}
    </div>
  )
}
```

- [ ] **Step 3: Create OverviewTab.tsx**

```tsx
// frontend/src/pages/SampleDetail/OverviewTab.tsx
import { useState } from 'react'
import { useQueryClient, useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { samplesApi, type SampleDetail } from '@/api/samples'
import { Card, CardBody, CardHeader, StatusBadge, Button, Input, useToast } from '@/components/ui'

interface Props { sample: SampleDetail }

export function OverviewTab({ sample }: Props) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({
    rock_classification: sample.rock_classification ?? '',
    locality: sample.locality ?? '',
    state: sample.state ?? '',
    country: sample.country ?? '',
    latitude: sample.latitude?.toString() ?? '',
    longitude: sample.longitude?.toString() ?? '',
    description: sample.description ?? '',
  })

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  const saveMutation = useMutation({
    mutationFn: () => samplesApi.patch(sample.sample_id, {
      rock_classification: form.rock_classification || undefined,
      locality: form.locality || undefined,
      state: form.state || undefined,
      country: form.country || undefined,
      latitude: form.latitude ? parseFloat(form.latitude) : undefined,
      longitude: form.longitude ? parseFloat(form.longitude) : undefined,
      description: form.description || undefined,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sample', sample.sample_id] })
      toast({ title: 'Sample updated', variant: 'success' })
      setEditing(false)
    },
    onError: () => toast({ title: 'Update failed', variant: 'error' }),
  })

  const charLabel = sample.characterized ? 'Characterized' : 'Uncharacterized'

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex items-center justify-between">
          <span className="text-sm font-medium text-ink-primary">Sample Details</span>
          {!editing && <Button variant="ghost" onClick={() => setEditing(true)}>Edit</Button>}
        </CardHeader>
        <CardBody>
          {!editing ? (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
              {[
                ['Rock Classification', sample.rock_classification],
                ['Locality', sample.locality],
                ['State', sample.state],
                ['Country', sample.country],
                ['Latitude', sample.latitude],
                ['Longitude', sample.longitude],
              ].map(([label, val]) => (
                <div key={String(label)}>
                  <dt className="text-xs text-ink-muted">{label}</dt>
                  <dd className="text-ink-primary font-mono-data">{val ?? '—'}</dd>
                </div>
              ))}
              <div className="col-span-2">
                <dt className="text-xs text-ink-muted">Description</dt>
                <dd className="text-ink-secondary">{sample.description ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-xs text-ink-muted">Characterized</dt>
                <dd><StatusBadge variant={sample.characterized ? 'success' : 'neutral'}>{charLabel}</StatusBadge></dd>
              </div>
            </dl>
          ) : (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <Input label="Rock Classification" value={form.rock_classification} onChange={set('rock_classification')} />
                <Input label="Locality" value={form.locality} onChange={set('locality')} />
                <Input label="State" value={form.state} onChange={set('state')} />
                <Input label="Country" value={form.country} onChange={set('country')} />
                <Input label="Latitude" type="number" value={form.latitude} onChange={set('latitude')} />
                <Input label="Longitude" type="number" value={form.longitude} onChange={set('longitude')} />
              </div>
              <div>
                <label className="block text-xs font-medium text-ink-secondary mb-1">Description</label>
                <textarea
                  className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary resize-none focus:outline-none focus:ring-1 focus:ring-brand-red/50"
                  rows={3}
                  value={form.description}
                  onChange={set('description')}
                />
              </div>
              <div className="flex gap-2 justify-end">
                <Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
                <Button variant="primary" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
                  {saveMutation.isPending ? 'Saving…' : 'Save'}
                </Button>
              </div>
            </div>
          )}
        </CardBody>
      </Card>

      {/* Linked experiments */}
      {sample.experiments.length > 0 && (
        <Card>
          <CardHeader><span className="text-sm font-medium text-ink-primary">Linked Experiments</span></CardHeader>
          <CardBody>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-ink-muted border-b border-surface-border">
                  <th className="pb-2 pr-4">Experiment ID</th>
                  <th className="pb-2 pr-4">Type</th>
                  <th className="pb-2 pr-4">Status</th>
                  <th className="pb-2">Start Date</th>
                </tr>
              </thead>
              <tbody>
                {sample.experiments.map((e) => (
                  <tr
                    key={e.experiment_id}
                    onClick={() => navigate(`/experiments/${e.experiment_id}`)}
                    className="cursor-pointer hover:bg-surface-overlay/50 border-b border-surface-border/50"
                  >
                    <td className="py-2 pr-4 font-mono-data text-ink-primary">{e.experiment_id}</td>
                    <td className="py-2 pr-4 text-ink-muted">{e.experiment_type ?? '—'}</td>
                    <td className="py-2 pr-4 text-ink-muted">{e.status ?? '—'}</td>
                    <td className="py-2 text-ink-muted">{e.date ? new Date(e.date).toLocaleDateString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Create PhotosTab.tsx**

```tsx
// frontend/src/pages/SampleDetail/PhotosTab.tsx
import { useQueryClient, useMutation } from '@tanstack/react-query'
import { samplesApi, type SampleDetail } from '@/api/samples'
import { Card, CardBody, Button, useToast } from '@/components/ui'
import { useState } from 'react'

interface Props { sample: SampleDetail }

export function PhotosTab({ sample }: Props) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [file, setFile] = useState<File | null>(null)
  const [desc, setDesc] = useState('')

  const uploadMutation = useMutation({
    mutationFn: () => samplesApi.uploadPhoto(sample.sample_id, file!, desc || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sample', sample.sample_id] })
      toast({ title: 'Photo uploaded', variant: 'success' })
      setFile(null)
      setDesc('')
    },
    onError: () => toast({ title: 'Upload failed', variant: 'error' }),
  })

  const deleteMutation = useMutation({
    mutationFn: (photoId: number) => samplesApi.deletePhoto(sample.sample_id, photoId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sample', sample.sample_id] })
      toast({ title: 'Photo deleted', variant: 'success' })
    },
  })

  return (
    <div className="space-y-4">
      {/* Upload zone */}
      <Card>
        <CardBody>
          <div className="space-y-2">
            <label className="block text-xs font-medium text-ink-secondary">Upload Photo (JPG / PNG)</label>
            <input type="file" accept="image/jpeg,image/png" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm" />
            {file && (
              <>
                <input
                  type="text"
                  placeholder="Description (optional)"
                  value={desc}
                  onChange={(e) => setDesc(e.target.value)}
                  className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary focus:outline-none"
                />
                <Button variant="primary" onClick={() => uploadMutation.mutate()} disabled={uploadMutation.isPending}>
                  {uploadMutation.isPending ? 'Uploading…' : 'Upload'}
                </Button>
              </>
            )}
          </div>
        </CardBody>
      </Card>

      {/* Gallery */}
      {sample.photos.length === 0 ? (
        <p className="text-sm text-ink-muted text-center py-8">No photos yet. Upload the first one.</p>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {sample.photos.map((p) => (
            <Card key={p.id}>
              <CardBody className="space-y-2">
                <div className="h-36 bg-surface-overlay rounded overflow-hidden flex items-center justify-center">
                  <span className="text-xs text-ink-muted font-mono-data">{p.file_name}</span>
                </div>
                {p.description && <p className="text-xs text-ink-muted">{p.description}</p>}
                <p className="text-xs text-ink-muted">{new Date(p.created_at).toLocaleDateString()}</p>
                <button
                  className="text-xs text-red-400 hover:text-red-300"
                  onClick={() => deleteMutation.mutate(p.id)}
                >
                  Delete
                </button>
              </CardBody>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Create AnalysesTab.tsx**

```tsx
// frontend/src/pages/SampleDetail/AnalysesTab.tsx
import { useState } from 'react'
import { useQueryClient, useMutation } from '@tanstack/react-query'
import { samplesApi, type SampleDetail, type ExternalAnalysisCreate } from '@/api/samples'
import { Card, CardBody, CardHeader, Button, Input, Select, useToast } from '@/components/ui'

interface Props { sample: SampleDetail }

const ANALYSIS_TYPES = [
  'pXRF', 'XRD', 'Elemental', 'Titration', 'Magnetic Susceptibility', 'Other',
].map((v) => ({ value: v, label: v }))

export function AnalysesTab({ sample }: Props) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<ExternalAnalysisCreate>({ analysis_type: 'pXRF' })
  const [warnings, setWarnings] = useState<string[]>([])

  const createMutation = useMutation({
    mutationFn: () => samplesApi.createAnalysis(sample.sample_id, form),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['sample', sample.sample_id] })
      setWarnings(data.warnings)
      if (data.warnings.length === 0) {
        toast({ title: 'Analysis added', variant: 'success' })
        setShowForm(false)
      }
    },
    onError: () => toast({ title: 'Failed to add analysis', variant: 'error' }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => samplesApi.deleteAnalysis(sample.sample_id, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sample', sample.sample_id] })
      toast({ title: 'Analysis deleted', variant: 'success' })
    },
  })

  // Group by type
  const groups = sample.analyses.reduce<Record<string, typeof sample.analyses>>((acc, a) => {
    const t = a.analysis_type ?? 'Other'
    ;(acc[t] ??= []).push(a)
    return acc
  }, {})

  return (
    <div className="space-y-4">
      {Object.entries(groups).map(([type, items]) => (
        <Card key={type}>
          <CardHeader>
            <span className="text-sm font-medium text-ink-primary">{type}</span>
          </CardHeader>
          <CardBody>
            <table className="w-full text-sm">
              <tbody>
                {items.map((a) => (
                  <tr key={a.id} className="border-b border-surface-border/50">
                    <td className="py-2 pr-4 text-ink-muted font-mono-data">
                      {a.pxrf_reading_no ?? a.magnetic_susceptibility ?? a.description ?? '—'}
                    </td>
                    <td className="py-2 pr-4 text-ink-muted">
                      {a.analysis_date ? new Date(a.analysis_date).toLocaleDateString() : '—'}
                    </td>
                    <td className="py-2 pr-4 text-ink-muted">{a.laboratory ?? '—'}</td>
                    <td className="py-2">
                      <button
                        className="text-xs text-red-400 hover:text-red-300"
                        onClick={() => deleteMutation.mutate(a.id)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>
      ))}

      {sample.analyses.length === 0 && !showForm && (
        <p className="text-sm text-ink-muted text-center py-8">No analyses recorded.</p>
      )}

      {/* Add analysis form */}
      {!showForm ? (
        <Button variant="ghost" onClick={() => setShowForm(true)}>+ Add Analysis</Button>
      ) : (
        <Card>
          <CardBody className="space-y-3">
            <Select
              label="Type"
              options={ANALYSIS_TYPES}
              value={form.analysis_type}
              onChange={(e) => setForm((f) => ({ ...f, analysis_type: e.target.value }))}
            />
            {form.analysis_type === 'pXRF' && (
              <Input
                label="Reading Numbers (comma-separated)"
                value={form.pxrf_reading_no ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, pxrf_reading_no: e.target.value }))}
              />
            )}
            {form.analysis_type === 'Magnetic Susceptibility' && (
              <Input
                label="Value (×10⁻³)"
                value={form.magnetic_susceptibility ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, magnetic_susceptibility: e.target.value }))}
              />
            )}
            <Input
              label="Description"
              value={form.description ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
            {warnings.length > 0 && (
              <div className="text-xs text-yellow-300 space-y-1">
                {warnings.map((w, i) => <p key={i}>{w}</p>)}
              </div>
            )}
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setShowForm(false)}>Cancel</Button>
              <Button variant="primary" onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Saving…' : 'Add'}
              </Button>
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  )
}
```

- [ ] **Step 6: Create ActivityTab.tsx**

```tsx
// frontend/src/pages/SampleDetail/ActivityTab.tsx
import { useQuery } from '@tanstack/react-query'
import { samplesApi } from '@/api/samples'
import { Card, CardBody, PageSpinner } from '@/components/ui'

interface Props { sampleId: string }

export function ActivityTab({ sampleId }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ['sample-activity', sampleId],
    queryFn: () => samplesApi.listActivity(sampleId),
  })

  if (isLoading) return <PageSpinner />

  return (
    <div className="space-y-2">
      {(!data || data.length === 0) ? (
        <p className="text-sm text-ink-muted text-center py-8">No activity recorded.</p>
      ) : (
        data.map((entry) => (
          <Card key={entry.id}>
            <CardBody className="flex items-start gap-3">
              <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                entry.modification_type === 'create' ? 'bg-green-500/10 text-green-400' :
                entry.modification_type === 'delete' ? 'bg-red-500/10 text-red-400' :
                'bg-blue-500/10 text-blue-400'
              }`}>
                {entry.modification_type}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-xs text-ink-secondary">
                  <span className="font-medium">{entry.modified_table}</span>
                  {' · '}
                  {entry.modified_by}
                </p>
                <p className="text-xs text-ink-muted mt-0.5">
                  {new Date(entry.created_at).toLocaleString()}
                </p>
              </div>
            </CardBody>
          </Card>
        ))
      )}
    </div>
  )
}
```

- [ ] **Step 7: Add GET /samples/{id}/activity endpoint**

Append to `backend/api/routers/samples.py`:

```python
@router.get("/{sample_id}/activity")
def get_activity(
    sample_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[dict]:
    from database.models.experiments import ModificationsLog
    rows = db.execute(
        select(ModificationsLog)
        .where(
            ModificationsLog.sample_id == sample_id,
            ModificationsLog.modified_table.in_(
                ["sample_info", "sample_photos", "external_analyses"]
            ),
        )
        .order_by(ModificationsLog.created_at.desc())
        .limit(100)
    ).scalars().all()
    return [
        {
            "id": r.id,
            "modification_type": r.modification_type,
            "modified_table": r.modified_table,
            "modified_by": r.modified_by,
            "old_values": r.old_values or {},
            "new_values": r.new_values or {},
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
```

- [ ] **Step 8: Wire SampleDetail route in App.tsx**

Find the router config (likely `frontend/src/App.tsx`) and add:

```tsx
import { SampleDetailPage } from '@/pages/SampleDetail'
// Inside <Routes>:
<Route path="/samples/:sampleId" element={<SampleDetailPage />} />
```

- [ ] **Step 9: TypeScript check**

```
cd frontend && npx tsc --noEmit
```

- [ ] **Step 10: Commit**

```
git add frontend/src/pages/SampleDetail/ backend/api/routers/samples.py frontend/src/App.tsx
git commit -m "[M9] Task 13: SampleDetail page — Overview/Photos/Analyses/Activity tabs + activity endpoint"
```

---

## Task 14: SampleSelector Component

**Files:**
- Create: `frontend/src/components/ui/SampleSelector.tsx`
- Modify: `frontend/src/components/ui/index.ts`
- Modify: `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx`

- [ ] **Step 1: Create SampleSelector.tsx**

```tsx
// frontend/src/components/ui/SampleSelector.tsx
import { useEffect, useId, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { samplesApi } from '@/api/samples'
import { StatusBadge } from './Badge'

interface Props {
  value: string
  onChange: (sampleId: string) => void
  onCreateNew?: () => void
}

export function SampleSelector({ value, onChange, onCreateNew }: Props) {
  const inputId = useId()
  const [query, setQuery] = useState(value)
  const [debouncedQuery, setDebouncedQuery] = useState(value)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Debounce: wait 300 ms after the user stops typing before querying the server
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), 300)
    return () => clearTimeout(t)
  }, [query])

  const { data: samples } = useQuery({
    queryKey: ['samples-selector', debouncedQuery],
    queryFn: () => samplesApi.list({ search: debouncedQuery || undefined, limit: 30 }),
    enabled: open,
  })

  const options = samples?.items ?? []

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  useEffect(() => { setQuery(value) }, [value])

  const handleSelect = (sampleId: string) => {
    onChange(sampleId)
    setQuery(sampleId)
    setOpen(false)
  }

  const handleClear = () => {
    onChange('')
    setQuery('')
  }

  return (
    <div ref={ref} className="relative">
      <label htmlFor={inputId} className="block text-xs font-medium text-ink-secondary mb-1">
        Sample
      </label>
      {value ? (
        // Show chip when a value is selected
        <div className="flex items-center gap-2 px-3 py-2 bg-surface-input border border-surface-border rounded text-sm">
          <span className="font-mono-data text-ink-primary">{value}</span>
          <button
            onClick={handleClear}
            className="ml-auto text-ink-muted hover:text-ink-primary text-xs"
            aria-label="Clear selection"
          >
            ✕
          </button>
        </div>
      ) : (
        <input
          id={inputId}
          type="text"
          autoComplete="off"
          placeholder="Search by sample ID or locality…"
          value={query}
          onFocus={() => setOpen(true)}
          onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
          className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary placeholder-ink-muted focus:outline-none focus:ring-1 focus:ring-brand-red/50"
        />
      )}

      {open && !value && (
        <ul className="absolute z-20 mt-1 w-full max-h-56 overflow-y-auto bg-surface-raised border border-surface-border rounded shadow-lg">
          {options.slice(0, 30).map((s) => (
            <li
              key={s.sample_id}
              onMouseDown={() => handleSelect(s.sample_id)}
              className="px-3 py-2 text-sm text-ink-primary hover:bg-surface-overlay cursor-pointer flex items-center justify-between"
            >
              <span>
                <span className="font-mono-data">{s.sample_id}</span>
                {s.rock_classification && (
                  <span className="text-ink-muted ml-2">{s.rock_classification}</span>
                )}
              </span>
              <StatusBadge variant={s.characterized ? 'success' : 'neutral'} className="text-xs">
                {s.characterized ? 'Char.' : 'Unch.'}
              </StatusBadge>
            </li>
          ))}
          {onCreateNew && (
            <li
              onMouseDown={onCreateNew}
              className="px-3 py-2 text-sm text-brand-red hover:bg-surface-overlay cursor-pointer border-t border-surface-border"
            >
              + Create new sample…
            </li>
          )}
          {options.length === 0 && !onCreateNew && (
            <li className="px-3 py-2 text-sm text-ink-muted">No matches</li>
          )}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Export from ui/index.ts**

```typescript
// Add to frontend/src/components/ui/index.ts:
export { SampleSelector } from './SampleSelector'
```

- [ ] **Step 3: Replace inline combobox in Step1BasicInfo.tsx**

In `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx`, remove the inline sample combobox (lines 37–137 approximately) and replace with:

```tsx
import { SampleSelector } from '@/components/ui'

// Inside Step1BasicInfo component, replace the combobox div with:
<SampleSelector
  value={data.sampleId}
  onChange={(id) => onChange({ sampleId: id })}
/>
```

Also remove unused imports: `useRef`, `sampleRef`, `sampleOptions`, `filtered`, `showSuggestions`, `sampleInputId`, and the `useEffect` for outside-click.

- [ ] **Step 4: TypeScript check**

```
cd frontend && npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```
git add frontend/src/components/ui/SampleSelector.tsx frontend/src/components/ui/index.ts frontend/src/pages/NewExperiment/Step1BasicInfo.tsx
git commit -m "[M9] Task 14: SampleSelector component + wire into NewExperiment Step1"
```

---

## Task 15: Run Full Test Suite + Fix Failures

- [ ] **Step 1: Run all API tests**

```
pytest tests/api/ -v --tb=short 2>&1 | tail -40
```

- [ ] **Step 2: Run all service tests**

```
pytest tests/services/ -v --tb=short
```

- [ ] **Step 3: Run full suite**

```
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Fix any failures before proceeding. Target: all passing.

- [ ] **Step 4: TypeScript and lint check**

```
cd frontend && npx tsc --noEmit && npx eslint src --ext .ts,.tsx
```

Fix zero-tolerance ESLint errors.

- [ ] **Step 5: Commit any fixes**

```
git add -p
git commit -m "[M9] Task 15: fix test/lint failures from full suite run"
```

---

## Task 16: Documentation

**Files:**
- Create: `docs/user_guide/SAMPLES.md`
- Create: `docs/developer/SAMPLE_CHARACTERIZED_LOGIC.md`
- Modify: `docs/api/API_REFERENCE.md`
- Modify: `docs/working/plan.md`
- Modify: `docs/milestones/MILESTONE_INDEX.md`

- [ ] **Step 1: Write SAMPLES.md** — researcher-facing guide covering creating samples, uploading photos, adding analyses, reading the map view, understanding Characterized status.

- [ ] **Step 2: Write SAMPLE_CHARACTERIZED_LOGIC.md** — developer guide explaining the three conditions, `evaluate_characterized` function, when it's called, manual override behavior.

- [ ] **Step 3: Update API_REFERENCE.md** — add all 11 new sample endpoints with parameters, request/response shapes, and error codes.

- [ ] **Step 4: Update plan.md** — mark M9 complete.

- [ ] **Step 5: Update MILESTONE_INDEX.md** — set M9 status to Complete.

- [ ] **Step 6: Commit**

```
git add docs/
git commit -m "[M9] Task 16: documentation — SAMPLES.md, CHARACTERIZED_LOGIC.md, API_REFERENCE.md, plan.md"
```

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-03-23-m9-sample-management.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — Fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans

**Which approach?**
