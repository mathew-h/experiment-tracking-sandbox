# M3 FastAPI Backend Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete FastAPI API layer — 9 routers, Pydantic schemas, Firebase auth middleware, calculation engine wiring on all writes, and bulk upload endpoint wrappers.

**Architecture:** Settings via `pydantic-settings`. DB session as a module-level singleton in `backend/api/dependencies/db.py`. Firebase Admin SDK initialized directly in `backend/auth/firebase_auth.py` (do NOT import `auth.firebase_config` — it imports `streamlit` at module load and will crash the API). Every write endpoint: `db.add(obj)` → `db.flush()` → `registry.recalculate(obj, db)` → `db.commit()` → `db.refresh(obj)`.

**Tech Stack:** FastAPI 0.115, SQLAlchemy 2.x (sync), Pydantic v2 + pydantic-settings 2.6, firebase-admin 6.7, structlog 24.4, httpx 0.28 (tests). **use context7** for FastAPI, SQLAlchemy 2.x, Pydantic v2.

**Critical constraint:** `auth/firebase_config.py` is locked and imports `streamlit` — never import it from the FastAPI backend. Firebase is initialized independently in `backend/auth/firebase_auth.py`.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `backend/config/__init__.py` | Package marker |
| Create | `backend/config/settings.py` | pydantic-settings: DB URL, Firebase creds, CORS |
| Create | `backend/api/dependencies/db.py` | `get_db` generator (module-level engine) |
| Create | `backend/auth/firebase_auth.py` | `FirebaseUser` model + `verify_firebase_token` dep |
| Create | `tests/api/__init__.py` | Package marker |
| Create | `tests/api/conftest.py` | TestClient, test DB session, auth override |
| Create | `backend/api/schemas/experiments.py` | Experiment request/response schemas |
| Create | `backend/api/schemas/conditions.py` | Conditions + additive schemas |
| Create | `backend/api/schemas/results.py` | ExperimentalResults, Scalar, ICP schemas |
| Create | `backend/api/schemas/samples.py` | SampleInfo schemas |
| Create | `backend/api/schemas/chemicals.py` | Compound schemas |
| Create | `backend/api/schemas/analysis.py` | ExternalAnalysis, XRDPhase, pXRF schemas |
| Create | `backend/api/schemas/dashboard.py` | ReactorStatus, ExperimentTimeline schemas |
| Create | `backend/api/schemas/bulk_upload.py` | UploadResponse schema |
| Create | `backend/api/routers/experiments.py` | GET list/detail, POST, PATCH, DELETE |
| Create | `backend/api/routers/conditions.py` | GET, POST, PATCH |
| Create | `backend/api/routers/results.py` | GET by experiment, POST scalar, POST ICP |
| Create | `backend/api/routers/samples.py` | GET list/detail, POST, PATCH |
| Create | `backend/api/routers/chemicals.py` | GET/POST compounds, GET/POST additives |
| Create | `backend/api/routers/analysis.py` | GET XRD/pXRF/elemental |
| Create | `backend/api/routers/dashboard.py` | GET reactor status, GET experiment timeline |
| Create | `backend/api/routers/admin.py` | POST recalculate |
| Create | `backend/api/routers/bulk_uploads.py` | POST per upload type |
| Modify | `backend/api/main.py` | Mount all routers + static file serving |
| Create | `docs/api/API_REFERENCE.md` | Endpoint reference |

---

## Chunk 1: Infrastructure

### Task 1: Settings Module

**Files:**
- Create: `backend/config/__init__.py`
- Create: `backend/config/settings.py`
- Test: `tests/test_settings.py`

- [ ] **Write the failing test**

```python
# tests/test_settings.py
from backend.config.settings import Settings

def test_settings_loads_database_url():
    s = Settings(database_url="postgresql://u:p@localhost/test")
    assert s.database_url == "postgresql://u:p@localhost/test"

def test_settings_cors_origins_list():
    s = Settings(cors_origins="http://localhost:5173,http://localhost:8000")
    assert "http://localhost:5173" in s.cors_origins_list
    assert "http://localhost:8000" in s.cors_origins_list
```

- [ ] **Run to verify FAIL**

```bash
pytest tests/test_settings.py -v
```
Expected: `ModuleNotFoundError: No module named 'backend.config.settings'`

- [ ] **Implement**

```python
# backend/config/__init__.py
```

```python
# backend/config/settings.py
from __future__ import annotations
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql://experiments_user:password@localhost:5432/experiments"

    # Firebase — read from FIREBASE_* env vars
    firebase_project_id: str = ""
    firebase_private_key: str = ""
    firebase_client_email: str = ""
    firebase_client_id: str = ""
    firebase_client_cert_url: str = ""

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:8000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def firebase_cred_dict(self) -> dict:
        return {
            "type": "service_account",
            "project_id": self.firebase_project_id,
            "private_key": self.firebase_private_key.replace("\\n", "\n"),
            "client_email": self.firebase_client_email,
            "client_id": self.firebase_client_id,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": self.firebase_client_cert_url,
        }


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance. Override in tests via dependency injection."""
    return Settings()
```

- [ ] **Run to verify PASS**

```bash
pytest tests/test_settings.py -v
```
Expected: `2 passed`

- [ ] **Commit**

```bash
git add backend/config/__init__.py backend/config/settings.py tests/test_settings.py
git commit -m "[M3] Add pydantic-settings config module"
```

---

### Task 2: DB Dependency

**Files:**
- Create: `backend/api/dependencies/db.py`
- Test: `tests/api/test_db_dependency.py`

- [ ] **Write the failing test**

```python
# tests/api/test_db_dependency.py
from sqlalchemy.orm import Session
from backend.api.dependencies.db import get_db

def test_get_db_yields_session():
    gen = get_db()
    db = next(gen)
    assert isinstance(db, Session)
    try:
        next(gen)
    except StopIteration:
        pass
```

- [ ] **Run to verify FAIL**

```bash
pytest tests/api/test_db_dependency.py -v
```

- [ ] **Implement**

```python
# backend/api/dependencies/db.py
from __future__ import annotations
from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from backend.config.settings import get_settings

_settings = get_settings()
_engine = create_engine(_settings.database_url, pool_pre_ping=True)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a database session, close on exit."""
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

Update `backend/api/dependencies/__init__.py`:
```python
from backend.api.dependencies.db import get_db

__all__ = ["get_db"]
```

- [ ] **Run to verify PASS**

```bash
pytest tests/api/test_db_dependency.py -v
```

- [ ] **Commit**

```bash
git add backend/api/dependencies/db.py backend/api/dependencies/__init__.py tests/api/test_db_dependency.py
git commit -m "[M3] Add get_db session dependency"
```

---

### Task 3: Firebase Auth Dependency

**Files:**
- Create: `backend/auth/firebase_auth.py`
- Test: `tests/api/test_firebase_auth.py`

- [ ] **Write the failing test**

```python
# tests/api/test_firebase_auth.py
import pytest
from fastapi import HTTPException
from unittest.mock import patch, MagicMock
from backend.auth.firebase_auth import FirebaseUser, _decode_token


def test_decode_token_returns_firebase_user():
    mock_decoded = {"uid": "abc123", "email": "user@addisenergy.com", "name": "Test User"}
    with patch("backend.auth.firebase_auth._verify_id_token", return_value=mock_decoded):
        user = _decode_token("fake-token")
    assert user.uid == "abc123"
    assert user.email == "user@addisenergy.com"


def test_decode_token_raises_401_on_invalid():
    with patch("backend.auth.firebase_auth._verify_id_token", side_effect=Exception("bad")):
        with pytest.raises(HTTPException) as exc:
            _decode_token("bad-token")
    assert exc.value.status_code == 401
```

- [ ] **Run to verify FAIL**

```bash
pytest tests/api/test_firebase_auth.py -v
```

- [ ] **Implement**

```python
# backend/auth/firebase_auth.py
from __future__ import annotations
from typing import Optional
import structlog
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth_module
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from backend.config.settings import get_settings

log = structlog.get_logger(__name__)
_bearer = HTTPBearer(auto_error=False)
_firebase_initialized = False


def _ensure_firebase_initialized() -> None:
    """Initialize Firebase Admin SDK once from settings. No-op if already done."""
    global _firebase_initialized
    if _firebase_initialized or firebase_admin._apps:
        _firebase_initialized = True
        return
    settings = get_settings()
    if not settings.firebase_project_id:
        log.warning("firebase_project_id_not_set_skipping_init")
        return
    cred = credentials.Certificate(settings.firebase_cred_dict)
    firebase_admin.initialize_app(cred)
    _firebase_initialized = True
    log.info("firebase_admin_initialized", project=settings.firebase_project_id)


def _verify_id_token(token: str) -> dict:
    """Thin wrapper around firebase_auth.verify_id_token — patched in tests."""
    _ensure_firebase_initialized()
    return firebase_auth_module.verify_id_token(token, check_revoked=False)


class FirebaseUser(BaseModel):
    uid: str
    email: str
    display_name: str = ""


def _decode_token(token: str) -> FirebaseUser:
    """Verify token and return FirebaseUser. Raises HTTP 401 on failure."""
    try:
        decoded = _verify_id_token(token)
    except Exception as exc:
        log.warning("token_verification_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc
    return FirebaseUser(
        uid=decoded.get("uid", decoded.get("user_id", "")),
        email=decoded.get("email", ""),
        display_name=decoded.get("name", ""),
    )


def verify_firebase_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> FirebaseUser:
    """FastAPI dependency: extract Bearer token and return authenticated user."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
        )
    return _decode_token(credentials.credentials)
```

- [ ] **Run to verify PASS**

```bash
pytest tests/api/test_firebase_auth.py -v
```
Expected: `2 passed`

- [ ] **Commit**

```bash
git add backend/auth/firebase_auth.py tests/api/test_firebase_auth.py
git commit -m "[M3] Add Firebase auth dependency with isolated init"
```

---

### Task 4: Test Infrastructure (conftest)

**Files:**
- Create: `tests/api/__init__.py`
- Create: `tests/api/conftest.py`

Pre-requisite: create the test database once:
```bash
psql -U postgres -c "CREATE DATABASE experiments_test OWNER experiments_user;" 2>/dev/null || echo "already exists"
```

- [ ] **Implement conftest**

```python
# tests/api/__init__.py
```

```python
# tests/api/conftest.py
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Import Base via database package (triggers model registration)
from database import Base  # noqa: F401 — side-effect: registers all models
from backend.api.main import app
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"
_test_engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    """Create all tables once per test session, drop after."""
    Base.metadata.create_all(bind=_test_engine)
    yield
    Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture()
def db_session(create_test_tables) -> Session:
    """Per-test DB session wrapped in a savepoint; rolls back after each test."""
    connection = _test_engine.connect()
    transaction = connection.begin()
    session = _TestSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


_FAKE_USER = FirebaseUser(uid="test-uid", email="test@addisenergy.com", display_name="Test User")


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    """TestClient with DB and auth overrides applied."""

    def override_get_db():
        yield db_session

    def override_verify_token():
        return _FAKE_USER

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_firebase_token] = override_verify_token
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

- [ ] **Verify conftest imports cleanly**

```bash
pytest tests/api/ --collect-only 2>&1 | head -20
```
Expected: no import errors

- [ ] **Commit**

```bash
git add tests/api/__init__.py tests/api/conftest.py
git commit -m "[M3] Add test infrastructure: test DB, client fixture, auth override"
```

---

## Chunk 2: Pydantic Schemas

### Task 5: Experiment + Conditions Schemas

**Files:**
- Create: `backend/api/schemas/experiments.py`
- Create: `backend/api/schemas/conditions.py`
- Test: `tests/api/test_schemas.py` (add incrementally)

- [ ] **Write failing test**

```python
# tests/api/test_schemas.py
from backend.api.schemas.experiments import ExperimentCreate, ExperimentResponse
from backend.api.schemas.conditions import ConditionsCreate, ConditionsResponse

def test_experiment_create_requires_experiment_id():
    from pydantic import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        ExperimentCreate()  # missing experiment_id

def test_experiment_create_valid():
    e = ExperimentCreate(experiment_id="Serum_MH_001", experiment_number=1)
    assert e.experiment_id == "Serum_MH_001"

def test_conditions_create_valid():
    c = ConditionsCreate(experiment_fk=1, experiment_id="Serum_MH_001")
    assert c.experiment_fk == 1
```

- [ ] **Run to verify FAIL**

```bash
pytest tests/api/test_schemas.py -v
```

- [ ] **Implement experiments.py**

```python
# backend/api/schemas/experiments.py
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from database.models.enums import ExperimentStatus


class ExperimentCreate(BaseModel):
    experiment_id: str
    experiment_number: int
    sample_id: Optional[str] = None
    researcher: Optional[str] = None
    date: Optional[datetime] = None
    status: ExperimentStatus = ExperimentStatus.ONGOING
    base_experiment_id: Optional[str] = None
    parent_experiment_fk: Optional[int] = None


class ExperimentUpdate(BaseModel):
    sample_id: Optional[str] = None
    researcher: Optional[str] = None
    date: Optional[datetime] = None
    status: Optional[ExperimentStatus] = None


class ExperimentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: str
    experiment_number: int
    status: Optional[ExperimentStatus] = None
    researcher: Optional[str] = None
    date: Optional[datetime] = None
    sample_id: Optional[str] = None
    created_at: datetime


class ExperimentResponse(ExperimentListItem):
    base_experiment_id: Optional[str] = None
    parent_experiment_fk: Optional[int] = None
    updated_at: Optional[datetime] = None


class NoteCreate(BaseModel):
    note_text: str


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: str
    note_text: Optional[str] = None
    created_at: datetime
```

- [ ] **Implement conditions.py**

```python
# backend/api/schemas/conditions.py
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ConditionsCreate(BaseModel):
    experiment_fk: int
    experiment_id: str
    temperature_c: Optional[float] = None
    initial_ph: Optional[float] = None
    rock_mass_g: Optional[float] = None
    water_volume_mL: Optional[float] = None
    experiment_type: Optional[str] = None
    reactor_number: Optional[int] = None
    feedstock: Optional[str] = None
    particle_size: Optional[str] = None
    stir_speed_rpm: Optional[float] = None
    room_temp_pressure_psi: Optional[float] = None
    rxn_temp_pressure_psi: Optional[float] = None
    initial_conductivity_mS_cm: Optional[float] = None
    co2_partial_pressure_MPa: Optional[float] = None
    confining_pressure: Optional[float] = None
    pore_pressure: Optional[float] = None
    flow_rate: Optional[float] = None
    initial_nitrate_concentration: Optional[float] = None
    initial_dissolved_oxygen: Optional[float] = None
    initial_alkalinity: Optional[float] = None
    core_height_cm: Optional[float] = None
    core_width_cm: Optional[float] = None
    core_volume_cm3: Optional[float] = None


class ConditionsUpdate(BaseModel):
    temperature_c: Optional[float] = None
    initial_ph: Optional[float] = None
    rock_mass_g: Optional[float] = None
    water_volume_mL: Optional[float] = None
    experiment_type: Optional[str] = None
    reactor_number: Optional[int] = None
    feedstock: Optional[str] = None
    stir_speed_rpm: Optional[float] = None
    co2_partial_pressure_MPa: Optional[float] = None
    initial_alkalinity: Optional[float] = None


class ConditionsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_fk: int
    experiment_id: str
    temperature_c: Optional[float] = None
    initial_ph: Optional[float] = None
    rock_mass_g: Optional[float] = None
    water_volume_mL: Optional[float] = None
    water_to_rock_ratio: Optional[float] = None
    experiment_type: Optional[str] = None
    reactor_number: Optional[int] = None
    feedstock: Optional[str] = None
    particle_size: Optional[str] = None
    stir_speed_rpm: Optional[float] = None
    room_temp_pressure_psi: Optional[float] = None
    rxn_temp_pressure_psi: Optional[float] = None
    initial_conductivity_mS_cm: Optional[float] = None
    co2_partial_pressure_MPa: Optional[float] = None
    initial_nitrate_concentration: Optional[float] = None
    initial_dissolved_oxygen: Optional[float] = None
    initial_alkalinity: Optional[float] = None
    created_at: datetime
```

- [ ] **Run to verify PASS**

```bash
pytest tests/api/test_schemas.py -v
```

- [ ] **Commit**

```bash
git add backend/api/schemas/experiments.py backend/api/schemas/conditions.py tests/api/test_schemas.py
git commit -m "[M3] Add experiment and conditions Pydantic schemas"
```

---

### Task 6: Results + Chemicals Schemas

**Files:**
- Create: `backend/api/schemas/results.py`
- Create: `backend/api/schemas/chemicals.py`

- [ ] **Add failing tests** (append to `tests/api/test_schemas.py`)

```python
from backend.api.schemas.results import ScalarCreate, ResultResponse
from backend.api.schemas.chemicals import CompoundResponse, AdditiveCreate

def test_scalar_create_valid():
    s = ScalarCreate(result_id=1, final_ph=7.2)
    assert s.final_ph == 7.2

def test_compound_response_from_orm():
    from types import SimpleNamespace
    obj = SimpleNamespace(id=1, name="NaCl", formula="NaCl", cas_number=None,
                          molecular_weight_g_mol=58.44, created_at=None, updated_at=None,
                          preferred_unit=None, catalyst_formula=None, elemental_fraction=None,
                          density_g_cm3=None, supplier=None, notes=None,
                          melting_point_c=None, boiling_point_c=None, solubility=None,
                          hazard_class=None, catalog_number=None)
    r = CompoundResponse.model_validate(obj)
    assert r.name == "NaCl"
```

- [ ] **Run to verify FAIL**

```bash
pytest tests/api/test_schemas.py -v
```

- [ ] **Implement results.py**

```python
# backend/api/schemas/results.py
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from database.models.enums import AmmoniumQuantMethod


class ResultCreate(BaseModel):
    experiment_fk: int
    time_post_reaction_days: Optional[float] = None
    time_post_reaction_bucket_days: Optional[float] = None
    cumulative_time_post_reaction_days: Optional[float] = None
    is_primary_timepoint_result: bool = True
    description: str


class ResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_fk: int
    time_post_reaction_days: Optional[float] = None
    time_post_reaction_bucket_days: Optional[float] = None
    cumulative_time_post_reaction_days: Optional[float] = None
    is_primary_timepoint_result: bool
    description: str
    created_at: datetime


class ScalarCreate(BaseModel):
    result_id: int
    final_ph: Optional[float] = None
    final_conductivity_mS_cm: Optional[float] = None
    final_dissolved_oxygen_mg_L: Optional[float] = None
    final_nitrate_concentration_mM: Optional[float] = None
    final_alkalinity_mg_L: Optional[float] = None
    gross_ammonium_concentration_mM: Optional[float] = None
    background_ammonium_concentration_mM: Optional[float] = None
    ammonium_quant_method: Optional[AmmoniumQuantMethod] = None
    ferrous_iron_yield: Optional[float] = None
    sampling_volume_mL: Optional[float] = None
    measurement_date: Optional[datetime] = None
    h2_concentration: Optional[float] = None
    h2_concentration_unit: Optional[str] = "ppm"
    gas_sampling_volume_ml: Optional[float] = None
    gas_sampling_pressure_MPa: Optional[float] = None
    background_experiment_fk: Optional[int] = None
    co2_partial_pressure_MPa: Optional[float] = None


class ScalarUpdate(BaseModel):
    final_ph: Optional[float] = None
    gross_ammonium_concentration_mM: Optional[float] = None
    background_ammonium_concentration_mM: Optional[float] = None
    h2_concentration: Optional[float] = None
    gas_sampling_volume_ml: Optional[float] = None
    gas_sampling_pressure_MPa: Optional[float] = None
    sampling_volume_mL: Optional[float] = None
    ferrous_iron_yield: Optional[float] = None
    measurement_date: Optional[datetime] = None


class ScalarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    result_id: int
    final_ph: Optional[float] = None
    final_conductivity_mS_cm: Optional[float] = None
    final_dissolved_oxygen_mg_L: Optional[float] = None
    final_nitrate_concentration_mM: Optional[float] = None
    final_alkalinity_mg_L: Optional[float] = None
    gross_ammonium_concentration_mM: Optional[float] = None
    background_ammonium_concentration_mM: Optional[float] = None
    grams_per_ton_yield: Optional[float] = None
    ammonium_quant_method: Optional[AmmoniumQuantMethod] = None
    ferrous_iron_yield: Optional[float] = None
    sampling_volume_mL: Optional[float] = None
    measurement_date: Optional[datetime] = None
    h2_concentration: Optional[float] = None
    h2_concentration_unit: Optional[str] = None
    gas_sampling_volume_ml: Optional[float] = None
    gas_sampling_pressure_MPa: Optional[float] = None
    h2_micromoles: Optional[float] = None
    h2_mass_ug: Optional[float] = None
    h2_grams_per_ton_yield: Optional[float] = None
    co2_partial_pressure_MPa: Optional[float] = None
    background_experiment_fk: Optional[int] = None


ICP_ELEMENTS = ["fe","si","mg","ca","ni","cu","mo","zn","mn","cr","co","al",
                "sr","y","nb","sb","cs","ba","nd","gd","pt","rh","ir","pd","ru","os","tl"]


class ICPCreate(BaseModel):
    result_id: int
    dilution_factor: Optional[float] = None
    instrument_used: Optional[str] = None
    raw_label: Optional[str] = None
    measurement_date: Optional[datetime] = None
    sample_date: Optional[datetime] = None
    all_elements: Optional[dict] = None
    # fixed element columns — all optional
    fe: Optional[float] = None
    si: Optional[float] = None
    mg: Optional[float] = None
    ca: Optional[float] = None
    ni: Optional[float] = None
    cu: Optional[float] = None
    mo: Optional[float] = None
    zn: Optional[float] = None
    mn: Optional[float] = None
    cr: Optional[float] = None
    co: Optional[float] = None
    al: Optional[float] = None
    sr: Optional[float] = None
    y:  Optional[float] = None
    nb: Optional[float] = None
    sb: Optional[float] = None
    cs: Optional[float] = None
    ba: Optional[float] = None
    nd: Optional[float] = None
    gd: Optional[float] = None
    pt: Optional[float] = None
    rh: Optional[float] = None
    ir: Optional[float] = None
    pd: Optional[float] = None
    ru: Optional[float] = None
    os: Optional[float] = None
    tl: Optional[float] = None


class ICPResponse(ICPCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
```

- [ ] **Implement chemicals.py**

```python
# backend/api/schemas/chemicals.py
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from database.models.enums import AmountUnit


class CompoundCreate(BaseModel):
    name: str
    formula: Optional[str] = None
    cas_number: Optional[str] = None
    molecular_weight_g_mol: Optional[float] = None
    density_g_cm3: Optional[float] = None
    supplier: Optional[str] = None
    notes: Optional[str] = None
    elemental_fraction: Optional[float] = None
    catalyst_formula: Optional[str] = None
    preferred_unit: Optional[AmountUnit] = None


class CompoundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    formula: Optional[str] = None
    cas_number: Optional[str] = None
    molecular_weight_g_mol: Optional[float] = None
    density_g_cm3: Optional[float] = None
    elemental_fraction: Optional[float] = None
    catalyst_formula: Optional[str] = None
    preferred_unit: Optional[AmountUnit] = None
    supplier: Optional[str] = None
    notes: Optional[str] = None


class AdditiveCreate(BaseModel):
    compound_id: int
    amount: float
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

- [ ] **Run to verify PASS**

```bash
pytest tests/api/test_schemas.py -v
```

- [ ] **Commit**

```bash
git add backend/api/schemas/results.py backend/api/schemas/chemicals.py tests/api/test_schemas.py
git commit -m "[M3] Add results and chemicals Pydantic schemas"
```

---

### Task 7: Remaining Schemas

**Files:**
- Create: `backend/api/schemas/samples.py`
- Create: `backend/api/schemas/analysis.py`
- Create: `backend/api/schemas/dashboard.py`
- Create: `backend/api/schemas/bulk_upload.py`
- Create: `backend/api/schemas/__init__.py`

- [ ] **Implement samples.py**

```python
# backend/api/schemas/samples.py
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


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
```

- [ ] **Implement analysis.py**

```python
# backend/api/schemas/analysis.py
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class XRDPhaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mineral_name: str
    amount: Optional[float] = None
    time_post_reaction_days: Optional[float] = None
    measurement_date: Optional[datetime] = None
    rwp: Optional[float] = None


class PXRFResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reading_no: str
    fe: Optional[float] = None
    mg: Optional[float] = None
    ni: Optional[float] = None
    cu: Optional[float] = None
    si: Optional[float] = None
    co: Optional[float] = None
    mo: Optional[float] = None
    al: Optional[float] = None
    ca: Optional[float] = None
    zn: Optional[float] = None
    ingested_at: datetime


class ExternalAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sample_id: Optional[str] = None
    experiment_id: Optional[str] = None
    analysis_type: Optional[str] = None
    analysis_date: Optional[datetime] = None
    laboratory: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime
```

- [ ] **Implement dashboard.py**

```python
# backend/api/schemas/dashboard.py
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from database.models.enums import ExperimentStatus


class ReactorStatusResponse(BaseModel):
    reactor_number: int
    experiment_id: Optional[str] = None
    status: Optional[ExperimentStatus] = None
    experiment_db_id: Optional[int] = None
    started_at: Optional[datetime] = None
    temperature_c: Optional[float] = None
    experiment_type: Optional[str] = None


class TimelinePoint(BaseModel):
    result_id: int
    time_post_reaction_days: Optional[float] = None
    time_post_reaction_bucket_days: Optional[float] = None
    is_primary: bool
    has_scalar: bool
    has_icp: bool


class ExperimentTimelineResponse(BaseModel):
    experiment_id: str
    status: Optional[ExperimentStatus] = None
    timepoints: list[TimelinePoint]
```

- [ ] **Implement bulk_upload.py**

```python
# backend/api/schemas/bulk_upload.py
from __future__ import annotations
from pydantic import BaseModel


class UploadResponse(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]
    message: str
```

- [ ] **Implement schemas `__init__.py`**

```python
# backend/api/schemas/__init__.py
from backend.api.schemas.experiments import (
    ExperimentCreate, ExperimentUpdate, ExperimentResponse, ExperimentListItem, NoteCreate, NoteResponse,
)
from backend.api.schemas.conditions import ConditionsCreate, ConditionsUpdate, ConditionsResponse
from backend.api.schemas.results import (
    ResultCreate, ResultResponse, ScalarCreate, ScalarUpdate,
    ScalarResponse, ICPCreate, ICPResponse,
)
from backend.api.schemas.chemicals import CompoundCreate, CompoundResponse, AdditiveCreate, AdditiveResponse
from backend.api.schemas.samples import SampleCreate, SampleUpdate, SampleResponse
from backend.api.schemas.analysis import XRDPhaseResponse, PXRFResponse, ExternalAnalysisResponse
from backend.api.schemas.dashboard import ReactorStatusResponse, ExperimentTimelineResponse
from backend.api.schemas.bulk_upload import UploadResponse
```

- [ ] **Run existing schema tests**

```bash
pytest tests/api/test_schemas.py -v
```
Expected: all pass

- [ ] **Commit**

```bash
git add backend/api/schemas/
git commit -m "[M3] Add remaining schemas: samples, analysis, dashboard, bulk_upload"
```

---

## Chunk 3: Read Routers

### Task 8: Experiments Router (Read)

**Files:**
- Create: `backend/api/routers/experiments.py` (read endpoints only for now)
- Create: `tests/api/test_experiments.py`

- [ ] **Write failing tests**

```python
# tests/api/test_experiments.py
from database.models.experiments import Experiment
from database.models.enums import ExperimentStatus


def _make_experiment(db, experiment_id="TEST_001", number=9001):
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=number,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def test_list_experiments_empty(client):
    resp = client.get("/api/experiments")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_experiments_returns_items(client, db_session):
    _make_experiment(db_session)
    resp = client.get("/api/experiments")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_get_experiment_not_found(client):
    resp = client.get("/api/experiments/DOES_NOT_EXIST")
    assert resp.status_code == 404


def test_get_experiment_by_id(client, db_session):
    exp = _make_experiment(db_session, "READABLE_001", 9002)
    resp = client.get(f"/api/experiments/{exp.experiment_id}")
    assert resp.status_code == 200
    assert resp.json()["experiment_id"] == "READABLE_001"
```

- [ ] **Run to verify FAIL**

```bash
pytest tests/api/test_experiments.py -v 2>&1 | head -30
```

- [ ] **Implement experiments.py (read endpoints)**

```python
# backend/api/routers/experiments.py
from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from database.models.experiments import Experiment
from database.models.enums import ExperimentStatus
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.experiments import ExperimentListItem, ExperimentResponse

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/experiments", tags=["experiments"])


@router.get("", response_model=list[ExperimentListItem])
def list_experiments(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    status: ExperimentStatus | None = None,
    researcher: str | None = None,
    sample_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[ExperimentListItem]:
    """List experiments with optional filters and pagination."""
    stmt = select(Experiment).order_by(Experiment.experiment_number.desc())
    if status:
        stmt = stmt.where(Experiment.status == status)
    if researcher:
        stmt = stmt.where(Experiment.researcher == researcher)
    if sample_id:
        stmt = stmt.where(Experiment.sample_id == sample_id)
    stmt = stmt.offset(skip).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [ExperimentListItem.model_validate(r) for r in rows]


@router.get("/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentResponse:
    """Get a single experiment by its string identifier."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return ExperimentResponse.model_validate(exp)
```

- [ ] **Wire router into main.py temporarily and run tests**

Add to `backend/api/main.py` (top of file, after existing imports):
```python
from backend.api.routers import experiments as experiments_router
app.include_router(experiments_router.router)
```

- [ ] **Run to verify PASS**

```bash
pytest tests/api/test_experiments.py -v
```
Expected: `4 passed`

- [ ] **Commit**

```bash
git add backend/api/routers/experiments.py tests/api/test_experiments.py backend/api/main.py
git commit -m "[M3] Add experiments read endpoints (GET list, GET detail)"
```

---

### Task 9: Samples Router

**Files:**
- Create: `backend/api/routers/samples.py`
- Create: `tests/api/test_samples.py`

- [ ] **Write failing tests**

```python
# tests/api/test_samples.py
from database.models.samples import SampleInfo


def _make_sample(db, sample_id="ROCK_T01"):
    s = SampleInfo(sample_id=sample_id, rock_classification="Peridotite")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_list_samples_empty(client):
    resp = client.get("/api/samples")
    assert resp.status_code == 200


def test_get_sample_not_found(client):
    resp = client.get("/api/samples/NOPE")
    assert resp.status_code == 404


def test_get_sample_found(client, db_session):
    _make_sample(db_session, "ROCK_TEST_01")
    resp = client.get("/api/samples/ROCK_TEST_01")
    assert resp.status_code == 200
    assert resp.json()["rock_classification"] == "Peridotite"


def test_create_sample(client):
    payload = {"sample_id": "ROCK_NEW_01", "rock_classification": "Dunite", "country": "USA"}
    resp = client.post("/api/samples", json=payload)
    assert resp.status_code == 201
    assert resp.json()["sample_id"] == "ROCK_NEW_01"


def test_patch_sample(client, db_session):
    _make_sample(db_session, "ROCK_PATCH_01")
    resp = client.patch("/api/samples/ROCK_PATCH_01", json={"country": "Canada"})
    assert resp.status_code == 200
    assert resp.json()["country"] == "Canada"
```

- [ ] **Run to verify FAIL**

```bash
pytest tests/api/test_samples.py -v 2>&1 | head -20
```

- [ ] **Implement**

```python
# backend/api/routers/samples.py
from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from database.models.samples import SampleInfo
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.samples import SampleCreate, SampleUpdate, SampleResponse

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/samples", tags=["samples"])


@router.get("", response_model=list[SampleResponse])
def list_samples(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    country: str | None = None,
    rock_classification: str | None = None,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[SampleResponse]:
    stmt = select(SampleInfo).order_by(SampleInfo.sample_id)
    if country:
        stmt = stmt.where(SampleInfo.country == country)
    if rock_classification:
        stmt = stmt.where(SampleInfo.rock_classification == rock_classification)
    stmt = stmt.offset(skip).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [SampleResponse.model_validate(r) for r in rows]


@router.get("/{sample_id}", response_model=SampleResponse)
def get_sample(
    sample_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> SampleResponse:
    sample = db.execute(
        select(SampleInfo).where(SampleInfo.sample_id == sample_id)
    ).scalar_one_or_none()
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return SampleResponse.model_validate(sample)


@router.post("", response_model=SampleResponse, status_code=201)
def create_sample(
    payload: SampleCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> SampleResponse:
    sample = SampleInfo(**payload.model_dump())
    db.add(sample)
    db.commit()
    db.refresh(sample)
    log.info("sample_created", sample_id=sample.sample_id, user=current_user.email)
    return SampleResponse.model_validate(sample)


@router.patch("/{sample_id}", response_model=SampleResponse)
def update_sample(
    sample_id: str,
    payload: SampleUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> SampleResponse:
    sample = db.execute(
        select(SampleInfo).where(SampleInfo.sample_id == sample_id)
    ).scalar_one_or_none()
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(sample, field, value)
    db.commit()
    db.refresh(sample)
    return SampleResponse.model_validate(sample)
```

- [ ] **Add router to main.py**, run tests, commit

```bash
pytest tests/api/test_samples.py -v
```
Expected: `5 passed`

```bash
git add backend/api/routers/samples.py tests/api/test_samples.py backend/api/main.py
git commit -m "[M3] Add samples router (GET list/detail, POST, PATCH)"
```

---

### Task 10: Chemicals Router (Read + Write)

**Files:**
- Create: `backend/api/routers/chemicals.py`
- Create: `tests/api/test_chemicals.py`

- [ ] **Write failing tests**

```python
# tests/api/test_chemicals.py
from database.models.chemicals import Compound


def _make_compound(db, name="TestCompound"):
    c = Compound(name=name, formula="TestF", molecular_weight_g_mol=100.0)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_list_compounds_empty(client):
    resp = client.get("/api/chemicals/compounds")
    assert resp.status_code == 200


def test_create_compound(client):
    resp = client.post("/api/chemicals/compounds", json={
        "name": "Magnesium Hydroxide", "formula": "Mg(OH)2", "molecular_weight_g_mol": 58.32
    })
    assert resp.status_code == 201
    assert resp.json()["name"] == "Magnesium Hydroxide"


def test_get_compound_not_found(client):
    resp = client.get("/api/chemicals/compounds/99999")
    assert resp.status_code == 404


def test_get_compound(client, db_session):
    c = _make_compound(db_session, "IronChloride")
    resp = client.get(f"/api/chemicals/compounds/{c.id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "IronChloride"
```

- [ ] **Run to verify FAIL**

```bash
pytest tests/api/test_chemicals.py -v 2>&1 | head -20
```

- [ ] **Implement**

```python
# backend/api/routers/chemicals.py
from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from database.models.chemicals import Compound, ChemicalAdditive
from database.models.conditions import ExperimentalConditions
import backend.services.calculations as _calcs  # noqa: F401 — registers @register decorators
from backend.services.calculations.registry import recalculate
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.chemicals import (
    CompoundCreate, CompoundResponse, AdditiveCreate, AdditiveResponse,
)

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/chemicals", tags=["chemicals"])


@router.get("/compounds", response_model=list[CompoundResponse])
def list_compounds(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[CompoundResponse]:
    rows = db.execute(select(Compound).order_by(Compound.name).offset(skip).limit(limit)).scalars().all()
    return [CompoundResponse.model_validate(r) for r in rows]


@router.get("/compounds/{compound_id}", response_model=CompoundResponse)
def get_compound(
    compound_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> CompoundResponse:
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
    compound = Compound(**payload.model_dump())
    db.add(compound)
    db.commit()
    db.refresh(compound)
    return CompoundResponse.model_validate(compound)


@router.get("/additives/{conditions_id}", response_model=list[AdditiveResponse])
def list_additives(
    conditions_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[AdditiveResponse]:
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

- [ ] **Add router to main.py**, run tests, commit

```bash
pytest tests/api/test_chemicals.py -v
git add backend/api/routers/chemicals.py tests/api/test_chemicals.py backend/api/main.py
git commit -m "[M3] Add chemicals router: compounds CRUD, additives with calc engine"
```

---

### Task 11: Analysis Router (Read)

**Files:**
- Create: `backend/api/routers/analysis.py`
- Create: `tests/api/test_analysis.py`

- [ ] **Write failing tests**

```python
# tests/api/test_analysis.py
from database.models.analysis import PXRFReading
from database.models.xrd import XRDPhase


def test_list_pxrf_empty(client):
    resp = client.get("/api/analysis/pxrf")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_xrd_phases_by_experiment(client):
    resp = client.get("/api/analysis/xrd/NONEXISTENT_EXP")
    assert resp.status_code == 200
    assert resp.json() == []
```

- [ ] **Run to verify FAIL**, then implement:

```python
# backend/api/routers/analysis.py
from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from database.models.analysis import PXRFReading, ExternalAnalysis
from database.models.xrd import XRDPhase
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.analysis import XRDPhaseResponse, PXRFResponse, ExternalAnalysisResponse

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/xrd/{experiment_id}", response_model=list[XRDPhaseResponse])
def get_xrd_phases(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[XRDPhaseResponse]:
    rows = db.execute(
        select(XRDPhase)
        .where(XRDPhase.experiment_id == experiment_id)
        .order_by(XRDPhase.time_post_reaction_days, XRDPhase.mineral_name)
    ).scalars().all()
    return [XRDPhaseResponse.model_validate(r) for r in rows]


@router.get("/pxrf", response_model=list[PXRFResponse])
def list_pxrf(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[PXRFResponse]:
    rows = db.execute(
        select(PXRFReading).order_by(PXRFReading.reading_no).offset(skip).limit(limit)
    ).scalars().all()
    return [PXRFResponse.model_validate(r) for r in rows]


@router.get("/external/{experiment_id}", response_model=list[ExternalAnalysisResponse])
def get_external_analyses(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[ExternalAnalysisResponse]:
    rows = db.execute(
        select(ExternalAnalysis)
        .where(ExternalAnalysis.experiment_id == experiment_id)
        .order_by(ExternalAnalysis.analysis_date)
    ).scalars().all()
    return [ExternalAnalysisResponse.model_validate(r) for r in rows]
```

- [ ] **Add router, run tests, commit**

```bash
pytest tests/api/test_analysis.py -v
git add backend/api/routers/analysis.py tests/api/test_analysis.py backend/api/main.py
git commit -m "[M3] Add analysis read endpoints (XRD, pXRF, external analyses)"
```

---

## Chunk 4: Write Routers

### Task 12: Experiments Write + Conditions Router

**Files:**
- Modify: `backend/api/routers/experiments.py` (add POST, PATCH, DELETE, notes)
- Create: `backend/api/routers/conditions.py`
- Modify/Create: tests

- [ ] **Add failing tests** (append to `tests/api/test_experiments.py`)

```python
def test_create_experiment(client):
    payload = {
        "experiment_id": "CREATE_TEST_001",
        "experiment_number": 8001,
        "status": "ONGOING",
    }
    resp = client.post("/api/experiments", json=payload)
    assert resp.status_code == 201
    assert resp.json()["experiment_id"] == "CREATE_TEST_001"


def test_create_experiment_duplicate_id_fails(client, db_session):
    _make_experiment(db_session, "DUP_001", 8002)
    payload = {"experiment_id": "DUP_001", "experiment_number": 8003}
    resp = client.post("/api/experiments", json=payload)
    assert resp.status_code == 409


def test_patch_experiment(client, db_session):
    _make_experiment(db_session, "PATCH_ME_001", 8004)
    resp = client.patch("/api/experiments/PATCH_ME_001", json={"status": "COMPLETED"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"


def test_delete_experiment(client, db_session):
    _make_experiment(db_session, "DELETE_ME_001", 8005)
    resp = client.delete("/api/experiments/DELETE_ME_001")
    assert resp.status_code == 204
    assert client.get("/api/experiments/DELETE_ME_001").status_code == 404
```

- [ ] **Run to verify FAIL**

```bash
pytest tests/api/test_experiments.py -v 2>&1 | grep FAILED
```

- [ ] **Add write endpoints to experiments.py**

```python
# Append to backend/api/routers/experiments.py
from backend.api.schemas.experiments import ExperimentCreate, ExperimentUpdate, NoteCreate, NoteResponse
from database.models.experiments import ExperimentNotes
from sqlalchemy.exc import IntegrityError
from fastapi import Response

@router.post("", response_model=ExperimentResponse, status_code=201)
def create_experiment(
    payload: ExperimentCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentResponse:
    """Create a new experiment."""
    exp = Experiment(**payload.model_dump())
    db.add(exp)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Experiment ID already exists")
    db.refresh(exp)
    log.info("experiment_created", experiment_id=exp.experiment_id, user=current_user.email)
    return ExperimentResponse.model_validate(exp)


@router.patch("/{experiment_id}", response_model=ExperimentResponse)
def update_experiment(
    experiment_id: str,
    payload: ExperimentUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentResponse:
    """Update mutable fields on an experiment."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(exp, field, value)
    db.commit()
    db.refresh(exp)
    return ExperimentResponse.model_validate(exp)


@router.delete("/{experiment_id}", status_code=204)
def delete_experiment(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> Response:
    """Delete an experiment and all cascaded records."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    db.delete(exp)
    db.commit()
    log.info("experiment_deleted", experiment_id=experiment_id, user=current_user.email)
    return Response(status_code=204)


@router.post("/{experiment_id}/notes", response_model=NoteResponse, status_code=201)
def add_note(
    experiment_id: str,
    payload: NoteCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> NoteResponse:
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    note = ExperimentNotes(
        experiment_id=experiment_id,
        experiment_fk=exp.id,
        note_text=payload.note_text,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return NoteResponse.model_validate(note)
```

- [ ] **Write failing test for conditions** (new file)

```python
# tests/api/test_conditions.py
from database.models.experiments import Experiment
from database.models.enums import ExperimentStatus


def _make_experiment(db, eid="COND_EXP_001", num=7001):
    exp = Experiment(experiment_id=eid, experiment_number=num, status=ExperimentStatus.ONGOING)
    db.add(exp); db.commit(); db.refresh(exp)
    return exp


def test_create_conditions_triggers_calculation(client, db_session):
    exp = _make_experiment(db_session)
    payload = {
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "rock_mass_g": 10.0,
        "water_volume_mL": 50.0,
    }
    resp = client.post("/api/conditions", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["water_to_rock_ratio"] == 5.0  # 50/10


def test_get_conditions(client, db_session):
    exp = _make_experiment(db_session, "COND_EXP_002", 7002)
    payload = {"experiment_fk": exp.id, "experiment_id": exp.experiment_id, "temperature_c": 180.0}
    created = client.post("/api/conditions", json=payload).json()
    resp = client.get(f"/api/conditions/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["temperature_c"] == 180.0
```

- [ ] **Implement conditions.py**

```python
# backend/api/routers/conditions.py
from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
import backend.services.calculations as _calcs  # noqa: F401
from backend.services.calculations.registry import recalculate
from database.models.conditions import ExperimentalConditions
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.conditions import ConditionsCreate, ConditionsUpdate, ConditionsResponse

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/conditions", tags=["conditions"])


@router.get("/{conditions_id}", response_model=ConditionsResponse)
def get_conditions(
    conditions_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ConditionsResponse:
    cond = db.get(ExperimentalConditions, conditions_id)
    if cond is None:
        raise HTTPException(status_code=404, detail="Conditions not found")
    return ConditionsResponse.model_validate(cond)


@router.get("/by-experiment/{experiment_id}", response_model=ConditionsResponse)
def get_conditions_by_experiment(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ConditionsResponse:
    cond = db.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if cond is None:
        raise HTTPException(status_code=404, detail="Conditions not found for this experiment")
    return ConditionsResponse.model_validate(cond)


@router.post("", response_model=ConditionsResponse, status_code=201)
def create_conditions(
    payload: ConditionsCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ConditionsResponse:
    """Create conditions and compute derived fields (water_to_rock_ratio)."""
    cond = ExperimentalConditions(**payload.model_dump())
    db.add(cond)
    db.flush()
    recalculate(cond, db)
    db.commit()
    db.refresh(cond)
    log.info("conditions_created", experiment_id=cond.experiment_id)
    return ConditionsResponse.model_validate(cond)


@router.patch("/{conditions_id}", response_model=ConditionsResponse)
def update_conditions(
    conditions_id: int,
    payload: ConditionsUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ConditionsResponse:
    """Update conditions and recompute derived fields."""
    cond = db.get(ExperimentalConditions, conditions_id)
    if cond is None:
        raise HTTPException(status_code=404, detail="Conditions not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(cond, field, value)
    db.flush()
    recalculate(cond, db)
    db.commit()
    db.refresh(cond)
    return ConditionsResponse.model_validate(cond)
```

- [ ] **Add both routers to main.py**, run tests, commit

```bash
pytest tests/api/test_experiments.py tests/api/test_conditions.py -v
git add backend/api/routers/experiments.py backend/api/routers/conditions.py \
        tests/api/test_experiments.py tests/api/test_conditions.py backend/api/main.py
git commit -m "[M3] Add experiment write endpoints and conditions router with calc engine"
```

---

### Task 13: Results Router

**Files:**
- Create: `backend/api/routers/results.py`
- Create: `tests/api/test_results.py`

- [ ] **Write failing tests**

```python
# tests/api/test_results.py
from database.models.experiments import Experiment
from database.models.results import ExperimentalResults
from database.models.enums import ExperimentStatus


def _seed(db):
    exp = Experiment(experiment_id="RES_EXP_001", experiment_number=6001, status=ExperimentStatus.ONGOING)
    db.add(exp); db.flush()
    result = ExperimentalResults(experiment_fk=exp.id, description="T0", is_primary_timepoint_result=True,
                                  time_post_reaction_days=0.0, time_post_reaction_bucket_days=0.0)
    db.add(result); db.commit(); db.refresh(result)
    return exp, result


def test_list_results_by_experiment(client, db_session):
    exp, _ = _seed(db_session)
    resp = client.get(f"/api/results/{exp.experiment_id}")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_create_result(client, db_session):
    exp, _ = _seed(db_session)
    payload = {
        "experiment_fk": exp.id,
        "description": "Day 7",
        "time_post_reaction_days": 7.0,
        "time_post_reaction_bucket_days": 7.0,
        "is_primary_timepoint_result": False,
    }
    resp = client.post("/api/results", json=payload)
    assert resp.status_code == 201
    assert resp.json()["description"] == "Day 7"


def test_create_scalar_triggers_calculation(client, db_session):
    exp, result = _seed(db_session)
    payload = {
        "result_id": result.id,
        "gross_ammonium_concentration_mM": 1.0,
        "h2_concentration": 500.0,
        "gas_sampling_volume_ml": 10.0,
        "gas_sampling_pressure_MPa": 0.1,
    }
    resp = client.post("/api/results/scalar", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    # H2 calc should have run
    assert data["h2_micromoles"] is not None
    assert data["h2_micromoles"] > 0
```

- [ ] **Run to verify FAIL**

```bash
pytest tests/api/test_results.py -v 2>&1 | head -20
```

- [ ] **Implement results.py**

```python
# backend/api/routers/results.py
from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
import backend.services.calculations as _calcs  # noqa: F401
from backend.services.calculations.registry import recalculate
from database.models.experiments import Experiment
from database.models.results import ExperimentalResults, ScalarResults, ICPResults
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.results import (
    ResultCreate, ResultResponse, ScalarCreate, ScalarUpdate,
    ScalarResponse, ICPCreate, ICPResponse,
)

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/results", tags=["results"])


@router.get("/{experiment_id}", response_model=list[ResultResponse])
def list_results(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[ResultResponse]:
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    rows = db.execute(
        select(ExperimentalResults)
        .where(ExperimentalResults.experiment_fk == exp.id)
        .order_by(ExperimentalResults.time_post_reaction_days)
    ).scalars().all()
    return [ResultResponse.model_validate(r) for r in rows]


@router.post("", response_model=ResultResponse, status_code=201)
def create_result(
    payload: ResultCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ResultResponse:
    result = ExperimentalResults(**payload.model_dump())
    db.add(result)
    db.commit()
    db.refresh(result)
    return ResultResponse.model_validate(result)


@router.post("/scalar", response_model=ScalarResponse, status_code=201)
def create_scalar(
    payload: ScalarCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ScalarResponse:
    """Create scalar results and trigger H2 + ammonium yield calculations."""
    result_entry = db.get(ExperimentalResults, payload.result_id)
    if result_entry is None:
        raise HTTPException(status_code=404, detail="Result entry not found")
    scalar = ScalarResults(**payload.model_dump())
    db.add(scalar)
    db.flush()
    recalculate(scalar, db)
    db.commit()
    db.refresh(scalar)
    log.info("scalar_created", result_id=scalar.result_id)
    return ScalarResponse.model_validate(scalar)


@router.patch("/scalar/{scalar_id}", response_model=ScalarResponse)
def update_scalar(
    scalar_id: int,
    payload: ScalarUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ScalarResponse:
    scalar = db.get(ScalarResults, scalar_id)
    if scalar is None:
        raise HTTPException(status_code=404, detail="Scalar result not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(scalar, field, value)
    db.flush()
    recalculate(scalar, db)
    db.commit()
    db.refresh(scalar)
    return ScalarResponse.model_validate(scalar)


@router.get("/scalar/{result_id}", response_model=ScalarResponse)
def get_scalar(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ScalarResponse:
    scalar = db.execute(
        select(ScalarResults).where(ScalarResults.result_id == result_id)
    ).scalar_one_or_none()
    if scalar is None:
        raise HTTPException(status_code=404, detail="Scalar result not found")
    return ScalarResponse.model_validate(scalar)


@router.post("/icp", response_model=ICPResponse, status_code=201)
def create_icp(
    payload: ICPCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ICPResponse:
    result_entry = db.get(ExperimentalResults, payload.result_id)
    if result_entry is None:
        raise HTTPException(status_code=404, detail="Result entry not found")
    icp = ICPResults(**payload.model_dump())
    db.add(icp)
    db.commit()
    db.refresh(icp)
    return ICPResponse.model_validate(icp)


@router.get("/icp/{result_id}", response_model=ICPResponse)
def get_icp(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ICPResponse:
    icp = db.execute(
        select(ICPResults).where(ICPResults.result_id == result_id)
    ).scalar_one_or_none()
    if icp is None:
        raise HTTPException(status_code=404, detail="ICP result not found")
    return ICPResponse.model_validate(icp)
```

- [ ] **Add router to main.py**, run tests, commit

```bash
pytest tests/api/test_results.py -v
git add backend/api/routers/results.py tests/api/test_results.py backend/api/main.py
git commit -m "[M3] Add results router: ExperimentalResults, ScalarResults (calc wired), ICP"
```

---

## Chunk 5: Specialized Routers + Final Wiring

### Task 14: Dashboard Router

**Files:**
- Create: `backend/api/routers/dashboard.py`
- Create: `tests/api/test_dashboard.py`

- [ ] **Write failing tests**

```python
# tests/api/test_dashboard.py
from database.models.experiments import Experiment
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus


def _seed_reactor(db, reactor_num=1, exp_id="DASH_EXP_001", num=5001):
    exp = Experiment(experiment_id=exp_id, experiment_number=num, status=ExperimentStatus.ONGOING)
    db.add(exp); db.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id, experiment_id=exp_id, reactor_number=reactor_num
    )
    db.add(cond); db.commit(); db.refresh(exp)
    return exp


def test_reactor_status_empty(client):
    resp = client.get("/api/dashboard/reactor-status")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_reactor_status_returns_ongoing(client, db_session):
    _seed_reactor(db_session, reactor_num=3, exp_id="DASH_R3_001", num=5002)
    resp = client.get("/api/dashboard/reactor-status")
    assert resp.status_code == 200
    reactor_nums = [r["reactor_number"] for r in resp.json()]
    assert 3 in reactor_nums


def test_experiment_timeline(client, db_session):
    exp = _seed_reactor(db_session, reactor_num=4, exp_id="DASH_TL_001", num=5003)
    resp = client.get(f"/api/dashboard/timeline/{exp.experiment_id}")
    assert resp.status_code == 200
    assert resp.json()["experiment_id"] == exp.experiment_id
```

- [ ] **Run to verify FAIL**

```bash
pytest tests/api/test_dashboard.py -v 2>&1 | head -20
```

- [ ] **Implement**

```python
# backend/api/routers/dashboard.py
from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from database.models.experiments import Experiment
from database.models.conditions import ExperimentalConditions
from database.models.results import ExperimentalResults, ScalarResults, ICPResults
from database.models.enums import ExperimentStatus
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.dashboard import (
    ReactorStatusResponse, ExperimentTimelineResponse, TimelinePoint,
)

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/reactor-status", response_model=list[ReactorStatusResponse])
def get_reactor_status(
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[ReactorStatusResponse]:
    """Single query: all reactors with their current ONGOING experiment. No N+1."""
    rows = db.execute(
        select(
            ExperimentalConditions.reactor_number,
            Experiment.id,
            Experiment.experiment_id,
            Experiment.status,
            Experiment.created_at,
            ExperimentalConditions.temperature_c,
            ExperimentalConditions.experiment_type,
        )
        .join(Experiment, Experiment.id == ExperimentalConditions.experiment_fk)
        .where(Experiment.status == ExperimentStatus.ONGOING)
        .where(ExperimentalConditions.reactor_number.isnot(None))
        .order_by(ExperimentalConditions.reactor_number, Experiment.created_at.desc())
    ).all()

    # Deduplicate: keep first (most-recent) per reactor_number
    seen: set[int] = set()
    result: list[ReactorStatusResponse] = []
    for row in rows:
        rn = row.reactor_number
        if rn in seen:
            continue
        seen.add(rn)
        result.append(ReactorStatusResponse(
            reactor_number=rn,
            experiment_id=row.experiment_id,
            status=row.status,
            experiment_db_id=row.id,
            started_at=row.created_at,
            temperature_c=row.temperature_c,
            experiment_type=row.experiment_type,
        ))
    return result


@router.get("/timeline/{experiment_id}", response_model=ExperimentTimelineResponse)
def get_experiment_timeline(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentTimelineResponse:
    """Return all result timepoints for an experiment with data-presence flags."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    results = db.execute(
        select(ExperimentalResults)
        .where(ExperimentalResults.experiment_fk == exp.id)
        .order_by(ExperimentalResults.time_post_reaction_days)
    ).scalars().all()

    # Check scalar/ICP presence in bulk (avoid N+1)
    result_ids = [r.id for r in results]
    scalar_ids = set(
        db.execute(select(ScalarResults.result_id).where(ScalarResults.result_id.in_(result_ids)))
        .scalars().all()
    )
    icp_ids = set(
        db.execute(select(ICPResults.result_id).where(ICPResults.result_id.in_(result_ids)))
        .scalars().all()
    )

    timepoints = [
        TimelinePoint(
            result_id=r.id,
            time_post_reaction_days=r.time_post_reaction_days,
            time_post_reaction_bucket_days=r.time_post_reaction_bucket_days,
            is_primary=r.is_primary_timepoint_result,
            has_scalar=r.id in scalar_ids,
            has_icp=r.id in icp_ids,
        )
        for r in results
    ]

    return ExperimentTimelineResponse(
        experiment_id=experiment_id,
        status=exp.status,
        timepoints=timepoints,
    )
```

- [ ] **Add router, run tests, commit**

```bash
pytest tests/api/test_dashboard.py -v
git add backend/api/routers/dashboard.py tests/api/test_dashboard.py backend/api/main.py
git commit -m "[M3] Add dashboard router: reactor status (no N+1), experiment timeline"
```

---

### Task 15: Admin Router

**Files:**
- Create: `backend/api/routers/admin.py`
- Create: `tests/api/test_admin.py`

- [ ] **Write failing tests**

```python
# tests/api/test_admin.py
from database.models.conditions import ExperimentalConditions
from database.models.experiments import Experiment
from database.models.enums import ExperimentStatus


def test_recalculate_conditions(client, db_session):
    exp = Experiment(experiment_id="ADMIN_EXP_001", experiment_number=4001, status=ExperimentStatus.ONGOING)
    db_session.add(exp); db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id, experiment_id=exp.experiment_id,
        rock_mass_g=20.0, water_volume_mL=100.0, water_to_rock_ratio=None,
    )
    db_session.add(cond); db_session.commit(); db_session.refresh(cond)
    # water_to_rock_ratio is None; trigger recalculate via admin endpoint
    resp = client.post(f"/api/admin/recalculate/conditions/{cond.id}")
    assert resp.status_code == 200
    assert resp.json()["water_to_rock_ratio"] == 5.0


def test_recalculate_unknown_model(client):
    resp = client.post("/api/admin/recalculate/unknown_model/1")
    assert resp.status_code == 422
```

- [ ] **Run to verify FAIL**, then implement:

```python
# backend/api/routers/admin.py
from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import backend.services.calculations as _calcs  # noqa: F401
from backend.services.calculations.registry import recalculate
from database.models.conditions import ExperimentalConditions
from database.models.results import ScalarResults
from database.models.chemicals import ChemicalAdditive
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.conditions import ConditionsResponse
from backend.api.schemas.results import ScalarResponse
from backend.api.schemas.chemicals import AdditiveResponse

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])

_MODEL_MAP = {
    "conditions": (ExperimentalConditions, ConditionsResponse),
    "scalar": (ScalarResults, ScalarResponse),
    "additive": (ChemicalAdditive, AdditiveResponse),
}


@router.post("/recalculate/{model_type}/{record_id}")
def recalculate_record(
    model_type: str,
    record_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> dict:
    """Re-run the calculation engine for any single record by type and ID."""
    if model_type not in _MODEL_MAP:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown model_type '{model_type}'. Valid: {list(_MODEL_MAP.keys())}",
        )
    model_class, response_schema = _MODEL_MAP[model_type]
    instance = db.get(model_class, record_id)
    if instance is None:
        raise HTTPException(status_code=404, detail=f"{model_type} record {record_id} not found")
    db.flush()
    recalculate(instance, db)
    db.commit()
    db.refresh(instance)
    log.info("recalculate_triggered", model=model_type, id=record_id, user=current_user.email)
    return response_schema.model_validate(instance).model_dump()
```

- [ ] **Add router, run tests, commit**

```bash
pytest tests/api/test_admin.py -v
git add backend/api/routers/admin.py tests/api/test_admin.py backend/api/main.py
git commit -m "[M3] Add admin recalculate endpoint"
```

---

### Task 16: Bulk Uploads Router

**Files:**
- Create: `backend/api/routers/bulk_uploads.py`
- Create: `tests/api/test_bulk_uploads.py`

**Note:** Parsers are locked. This task wraps them in FastAPI endpoints only. Do not modify any file in `backend/services/bulk_uploads/`.

- [ ] **Write failing tests**

```python
# tests/api/test_bulk_uploads.py
import io
from unittest.mock import patch


def test_upload_scalar_returns_upload_response_shape(client):
    """Endpoint exists and returns correct response shape (mock parser)."""
    mock_result = (0, 0, 0, ["No data in file"], [])
    with patch(
        "backend.api.routers.bulk_uploads.ScalarResultsUploadService.bulk_upsert_from_excel_ex",
        return_value=mock_result,
    ):
        resp = client.post(
            "/api/bulk-uploads/scalar-results",
            files={"file": ("test.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "created" in body
    assert "errors" in body


def test_upload_requires_file(client):
    resp = client.post("/api/bulk-uploads/scalar-results")
    assert resp.status_code == 422
```

- [ ] **Run to verify FAIL**, then implement:

```python
# backend/api/routers/bulk_uploads.py
from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.bulk_upload import UploadResponse
from backend.services.bulk_uploads.scalar_results import ScalarResultsUploadService
from backend.services.bulk_uploads.new_experiments import NewExperimentsUploadService
from backend.services.bulk_uploads.pxrf_data import PXRFDataService
from backend.services.bulk_uploads.aeris_xrd import AerisXRDUploadService

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/bulk-uploads", tags=["bulk-uploads"])


@router.post("/scalar-results", response_model=UploadResponse)
async def upload_scalar_results(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload a Solution Chemistry Excel file and upsert scalar results."""
    file_bytes = await file.read()
    created, updated, skipped, errors, _ = ScalarResultsUploadService.bulk_upsert_from_excel_ex(
        db, file_bytes
    )
    log.info("scalar_upload", created=created, updated=updated, user=current_user.email)
    return UploadResponse(
        created=created, updated=updated, skipped=skipped, errors=errors,
        message=f"Processed: {created} created, {updated} updated, {skipped} skipped",
    )


@router.post("/new-experiments", response_model=UploadResponse)
async def upload_new_experiments(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload a New Experiments Excel file."""
    file_bytes = await file.read()
    try:
        result = NewExperimentsUploadService.bulk_upload_from_excel(db, file_bytes)
        created = getattr(result, "created", 0) if not isinstance(result, tuple) else result[0]
        errors: list[str] = getattr(result, "errors", []) if not isinstance(result, tuple) else (result[3] if len(result) > 3 else [])
    except Exception as exc:
        log.error("new_experiments_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(created=created, updated=0, skipped=0, errors=errors,
                          message=f"{created} experiments created")


@router.post("/pxrf", response_model=UploadResponse)
async def upload_pxrf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload a pXRF CSV/Excel file."""
    file_bytes = await file.read()
    try:
        created, updated, skipped, errors = PXRFDataService.bulk_upsert_from_file(db, file_bytes)
    except Exception as exc:
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(created=created, updated=updated, skipped=skipped, errors=errors,
                          message=f"pXRF: {created} created, {updated} updated")


@router.post("/aeris-xrd", response_model=UploadResponse)
async def upload_aeris_xrd(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload an Aeris XRD file (time-series mineral phases)."""
    file_bytes = await file.read()
    try:
        created, updated, skipped, errors = AerisXRDUploadService.bulk_upsert_from_file(db, file_bytes)
    except Exception as exc:
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(created=created, updated=updated, skipped=skipped, errors=errors,
                          message=f"XRD: {created} created, {updated} updated")
```

**Note on bulk upload service signatures:** The parsers in `backend/services/bulk_uploads/` have varying return signatures. If a service method doesn't match the expected signature above, adapt the wrapper (not the parser). Check the actual parser signature before calling — use `bulk_upsert_from_excel_ex` for scalar (already confirmed), and inspect `new_experiments.py` / `pxrf_data.py` / `aeris_xrd.py` before wiring.

- [ ] **Add router, run tests, commit**

```bash
pytest tests/api/test_bulk_uploads.py -v
git add backend/api/routers/bulk_uploads.py tests/api/test_bulk_uploads.py backend/api/main.py
git commit -m "[M3] Add bulk uploads router wrapping existing parsers"
```

---

### Task 17: Wire main.py + Static File Serving

**Files:**
- Modify: `backend/api/main.py` (complete rewrite — consolidate all router mounts)

- [ ] **Write test for router registration**

```python
# tests/api/test_main.py
from fastapi.testclient import TestClient
from backend.api.main import app


def test_health_check():
    with TestClient(app) as c:
        resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_openapi_schema_has_all_tags():
    with TestClient(app) as c:
        schema = c.get("/openapi.json").json()
    tag_names = {t["name"] for t in schema.get("tags", [])}
    for expected in ["experiments", "conditions", "results", "samples",
                     "chemicals", "analysis", "dashboard", "admin", "bulk-uploads"]:
        assert expected in tag_names, f"Missing tag: {expected}"
```

- [ ] **Run to verify FAIL** (tags not declared yet)

- [ ] **Implement full main.py**

```python
# backend/api/main.py
"""FastAPI application entry point."""
from __future__ import annotations
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

from backend.config.settings import get_settings
from backend.api.routers import (
    experiments, conditions, results, samples,
    chemicals, analysis, dashboard, admin, bulk_uploads,
)

settings = get_settings()

app = FastAPI(
    title="Experiment Tracking System API",
    description="Backend API for laboratory experiment tracking",
    version="1.0.0",
    openapi_tags=[
        {"name": "experiments", "description": "Experiment CRUD and notes"},
        {"name": "conditions", "description": "Experimental conditions and calculation engine"},
        {"name": "results", "description": "Scalar, ICP, and file results"},
        {"name": "samples", "description": "Sample inventory"},
        {"name": "chemicals", "description": "Compound library and chemical additives"},
        {"name": "analysis", "description": "XRD, pXRF, and external analyses"},
        {"name": "dashboard", "description": "Reactor status and experiment timelines"},
        {"name": "admin", "description": "Recalculation and maintenance endpoints"},
        {"name": "bulk-uploads", "description": "Bulk data upload via Excel/CSV"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all API routers
app.include_router(experiments.router)
app.include_router(conditions.router)
app.include_router(results.router)
app.include_router(samples.router)
app.include_router(chemicals.router)
app.include_router(analysis.router)
app.include_router(dashboard.router)
app.include_router(admin.router)
app.include_router(bulk_uploads.router)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "service": "experiment_tracking_api"}


# Serve React app from frontend/dist/ if built
_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        """Serve React SPA — all non-API routes return index.html."""
        index = _DIST / "index.html"
        return FileResponse(index)


# Create routers __init__.py for clean imports
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.api.main:app", host="0.0.0.0", port=8000, reload=True)
```

Create `backend/api/routers/__init__.py`:
```python
# backend/api/routers/__init__.py
```

- [ ] **Run all API tests**

```bash
pytest tests/api/ -v --tb=short
```
Expected: all tests pass (or clear failures to fix before proceeding)

- [ ] **Run full test suite** (verify M2 tests still pass)

```bash
pytest tests/ -v --tb=short 2>&1 | tail -20
```

- [ ] **Commit**

```bash
git add backend/api/main.py backend/api/routers/__init__.py tests/api/test_main.py
git commit -m "[M3] Wire all routers into main.py; add static file serving for React build"
```

---

## Chunk 6: Documentation + Completion

### Task 18: API Reference Doc + plan.md update

**Files:**
- Create: `docs/api/API_REFERENCE.md`
- Modify: `docs/working/plan.md`

- [ ] **Create docs/api/ directory and API_REFERENCE.md**

```bash
mkdir -p docs/api
```

```markdown
# API Reference

Base URL: `http://localhost:8000`
Auth: All endpoints require `Authorization: Bearer <firebase-id-token>` header.

## Experiments

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/experiments` | List experiments. Query: `skip`, `limit`, `status`, `researcher`, `sample_id` |
| GET | `/api/experiments/{experiment_id}` | Get single experiment by string ID |
| POST | `/api/experiments` | Create experiment |
| PATCH | `/api/experiments/{experiment_id}` | Update status, researcher, date, sample_id |
| DELETE | `/api/experiments/{experiment_id}` | Delete experiment (cascades all related data) |
| POST | `/api/experiments/{experiment_id}/notes` | Add a note |

## Conditions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/conditions/{id}` | Get conditions by PK |
| GET | `/api/conditions/by-experiment/{experiment_id}` | Get conditions by experiment string ID |
| POST | `/api/conditions` | Create conditions (triggers `water_to_rock_ratio` calc) |
| PATCH | `/api/conditions/{id}` | Update conditions (recalculates derived fields) |

## Results

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/results/{experiment_id}` | List all result timepoints for an experiment |
| POST | `/api/results` | Create result entry |
| GET | `/api/results/scalar/{result_id}` | Get scalar result |
| POST | `/api/results/scalar` | Create scalar (triggers H2 + ammonium yield calc) |
| PATCH | `/api/results/scalar/{scalar_id}` | Update scalar (recalculates) |
| GET | `/api/results/icp/{result_id}` | Get ICP result |
| POST | `/api/results/icp` | Create ICP result |

## Samples

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/samples` | List samples. Query: `country`, `rock_classification`, `skip`, `limit` |
| GET | `/api/samples/{sample_id}` | Get sample |
| POST | `/api/samples` | Create sample |
| PATCH | `/api/samples/{sample_id}` | Update sample |

## Chemicals

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/chemicals/compounds` | List all compounds |
| GET | `/api/chemicals/compounds/{id}` | Get compound |
| POST | `/api/chemicals/compounds` | Create compound |
| GET | `/api/chemicals/additives/{conditions_id}` | List additives for a conditions record |
| POST | `/api/chemicals/additives/{conditions_id}` | Add additive (triggers full additive calc) |

## Analysis

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/analysis/xrd/{experiment_id}` | XRD phases for an experiment |
| GET | `/api/analysis/pxrf` | List pXRF readings. Query: `skip`, `limit` |
| GET | `/api/analysis/external/{experiment_id}` | External analyses for an experiment |

## Dashboard

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dashboard/reactor-status` | All reactors with current ONGOING experiment |
| GET | `/api/dashboard/timeline/{experiment_id}` | All timepoints with scalar/ICP presence flags |

## Admin

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/admin/recalculate/{model_type}/{id}` | Re-run calc engine. model_type: `conditions`, `scalar`, `additive` |

## Bulk Uploads

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/bulk-uploads/scalar-results` | Solution Chemistry Excel upload |
| POST | `/api/bulk-uploads/new-experiments` | New Experiments Excel upload |
| POST | `/api/bulk-uploads/pxrf` | pXRF data file upload |
| POST | `/api/bulk-uploads/aeris-xrd` | Aeris XRD file upload |

All bulk upload endpoints return:
```json
{"created": 5, "updated": 2, "skipped": 0, "errors": [], "message": "..."}
```

## Interactive Docs

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
```

- [ ] **Update plan.md M3 section**

In `docs/working/plan.md`, under M3 pending tasks, mark completed items and note what was implemented.

- [ ] **Commit**

```bash
git add docs/api/API_REFERENCE.md docs/working/plan.md
git commit -m "[M3] Add API_REFERENCE.md; update plan.md"
```

---

## Final Verification

- [ ] **Run full test suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -30
```
Expected: all M2 tests still pass; all M3 tests pass.

- [ ] **Start server and verify /docs loads**

```bash
uvicorn backend.api.main:app --reload --port 8000
# In a second terminal:
curl http://localhost:8000/health
curl http://localhost:8000/openapi.json | python -m json.tool | grep '"tags"' | head -5
```

- [ ] **Verify calc engine fires on a real write**

```bash
curl -X POST http://localhost:8000/api/conditions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"experiment_fk": 1, "experiment_id": "test", "rock_mass_g": 10, "water_volume_mL": 50}'
# Response should include: "water_to_rock_ratio": 5.0
```

- [ ] **Final commit + plan complete**

```bash
git add .
git commit -m "[M3] M3 FastAPI Backend complete — all endpoints, auth, calc engine, tests"
```
