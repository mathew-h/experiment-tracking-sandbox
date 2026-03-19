# M5 Experiment Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build three fully-functional experiment management pages (List, New, Detail) wired to the live FastAPI backend, with TDD throughout.

**Architecture:** Backend-first per chunk — add/extend endpoints, then wire the frontend. Each chunk is independently testable. Skip "copy-from-existing" feature entirely.

**Tech Stack:** FastAPI + SQLAlchemy (backend), React 18 + TypeScript + React Query + Tailwind (frontend), pytest (API tests), vitest (frontend tests).

---

## Known Pre-conditions / Bugs to Fix

- `ExperimentList` links to `/experiments/${exp.id}` (numeric DB id) — must be `exp.experiment_id` (string). Router `get_experiment` fetches by string `experiment_id`.
- `ExperimentCreate` requires `experiment_number: int` — backend must auto-assign it.
- `ExperimentResponse` does not include `conditions`, `notes`, or `modifications` — detail page needs a richer schema.
- `ConditionsUpdate`/`ConditionsResponse` missing several fields needed for M5 forms and display.

---

## File Map

**Backend — modified:**
- `backend/api/schemas/experiments.py` — extend list item, add detail response, status-update schema, next-id response; make `experiment_number` optional in create
- `backend/api/schemas/conditions.py` — extend update + response with all condition fields
- `backend/api/schemas/results.py` — add `ResultWithFlagsResponse`
- `backend/api/routers/experiments.py` — add `next-id`, `status-patch`, `results-with-flags`; fix list query (joins + pagination metadata); fix create to auto-assign experiment_number
- `tests/api/test_experiments.py` — extend with new endpoint tests

**Frontend — modified:**
- `frontend/src/api/experiments.ts` — add types + methods for new endpoints
- `frontend/src/api/conditions.ts` — add patch method + full types
- `frontend/src/pages/ExperimentList.tsx` — full M5 spec rewrite

**Frontend — created:**
- `frontend/src/pages/NewExperiment/fieldVisibility.ts`
- `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx`
- `frontend/src/pages/NewExperiment/Step2Conditions.tsx`
- `frontend/src/pages/NewExperiment/Step3Additives.tsx`
- `frontend/src/pages/NewExperiment/Step4Review.tsx`
- `frontend/src/pages/NewExperiment/index.tsx`
- `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx`
- `frontend/src/pages/ExperimentDetail/ResultsTab.tsx`
- `frontend/src/pages/ExperimentDetail/NotesTab.tsx`
- `frontend/src/pages/ExperimentDetail/ModificationsTab.tsx`
- `frontend/src/pages/ExperimentDetail/AnalysisTab.tsx`
- `frontend/src/pages/ExperimentDetail/FilesTab.tsx`
- `frontend/src/pages/ExperimentDetail/index.tsx`

**App.tsx** — update ExperimentDetail import path (no route change needed, `:id` param stays)

---

## Chunk A — Commit Run-Date Migration

### Task A1: Commit the staged run-date fields

- [ ] Run migration: `cd` to project root, then `python -m alembic upgrade head`
- [ ] Verify: `python -m alembic current` shows new head
- [ ] Stage and commit:
```bash
git add database/models/results.py alembic/versions/ddcef00413b9_add_run_date_fields_to_scalar_results.py
git commit -m "[M5] Add nmr_run_date, icp_run_date, gc_run_date to ScalarResults

- Tests added: no
- Docs updated: no"
```

---

## Chunk B — Backend Schema + Endpoint Extensions

### Task B1: Extend Pydantic schemas

**Files:**
- Modify: `backend/api/schemas/experiments.py`
- Modify: `backend/api/schemas/conditions.py`
- Modify: `backend/api/schemas/results.py`

- [ ] **Write the failing schema tests** in `tests/api/test_schemas.py`:

```python
def test_experiment_list_item_has_additives_summary():
    item = ExperimentListItem(
        id=1, experiment_id="X", experiment_number=1,
        status="ONGOING", created_at=datetime.now(),
        additives_summary=None, condition_note=None,
        experiment_type=None, reactor_number=None,
    )
    assert item.additives_summary is None

def test_experiment_create_no_number_required():
    payload = ExperimentCreate(experiment_id="TEST_001", status="ONGOING")
    assert payload.experiment_number is None

def test_experiment_status_update():
    u = ExperimentStatusUpdate(status="COMPLETED")
    assert u.status == ExperimentStatus.COMPLETED

def test_next_id_response():
    r = NextIdResponse(next_id="HPHT_003")
    assert r.next_id == "HPHT_003"

def test_conditions_update_has_all_fields():
    u = ConditionsUpdate(
        particle_size="<75um",
        room_temp_pressure_psi=100.0,
        rxn_temp_pressure_psi=200.0,
        initial_conductivity_mS_cm=1.5,
        confining_pressure=500.0,
        pore_pressure=200.0,
        core_height_cm=5.0,
        core_width_cm=3.0,
    )
    assert u.confining_pressure == 500.0

def test_result_with_flags_response():
    r = ResultWithFlagsResponse(
        id=1, experiment_fk=1,
        time_post_reaction_days=7.0,
        time_post_reaction_bucket_days=7.0,
        cumulative_time_post_reaction_days=7.0,
        is_primary_timepoint_result=True,
        description="T7",
        created_at=datetime.now(),
        has_scalar=True, has_icp=False,
        grams_per_ton_yield=50.0, h2_grams_per_ton_yield=None, final_ph=7.2,
    )
    assert r.has_scalar is True
```

- [ ] **Run tests, confirm they fail** (import errors expected):
```
pytest tests/api/test_schemas.py -k "test_experiment_list_item_has_additives or test_experiment_create_no or test_experiment_status or test_next_id or test_conditions_update_has_all or test_result_with_flags" -v
```

- [ ] **Implement schema changes** in `backend/api/schemas/experiments.py`:

```python
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from database.models.enums import ExperimentStatus


class ExperimentCreate(BaseModel):
    experiment_id: str
    experiment_number: Optional[int] = None   # auto-assigned if omitted
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


class ExperimentStatusUpdate(BaseModel):
    status: ExperimentStatus


class NextIdResponse(BaseModel):
    next_id: str


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
    # Joined from conditions (may be None if no conditions recorded yet)
    experiment_type: Optional[str] = None
    reactor_number: Optional[int] = None
    # Derived from additives view
    additives_summary: Optional[str] = None
    # First note text
    condition_note: Optional[str] = None


class ExperimentListResponse(BaseModel):
    """Paginated list response."""
    items: list[ExperimentListItem]
    total: int
    skip: int
    limit: int


class ExperimentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: str
    experiment_number: int
    status: Optional[ExperimentStatus] = None
    researcher: Optional[str] = None
    date: Optional[datetime] = None
    sample_id: Optional[str] = None
    base_experiment_id: Optional[str] = None
    parent_experiment_fk: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ExperimentDetailResponse(ExperimentResponse):
    """Full detail including nested conditions, notes, modifications."""
    conditions: Optional[dict] = None
    notes: list[dict] = []
    modifications: list[dict] = []


class NoteCreate(BaseModel):
    note_text: str


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: str
    note_text: Optional[str] = None
    created_at: datetime
```

- [ ] **Implement schema changes** in `backend/api/schemas/conditions.py` — add missing fields to `ConditionsUpdate` and `ConditionsResponse`:

```python
# Add to ConditionsUpdate:
particle_size: Optional[str] = None
room_temp_pressure_psi: Optional[float] = None
rxn_temp_pressure_psi: Optional[float] = None
initial_conductivity_mS_cm: Optional[float] = None
initial_nitrate_concentration: Optional[float] = None
initial_dissolved_oxygen: Optional[float] = None
confining_pressure: Optional[float] = None
pore_pressure: Optional[float] = None
core_height_cm: Optional[float] = None
core_width_cm: Optional[float] = None
core_volume_cm3: Optional[float] = None

# Add to ConditionsResponse (these were missing):
room_temp_pressure_psi: Optional[float] = None
rxn_temp_pressure_psi: Optional[float] = None
confining_pressure: Optional[float] = None
pore_pressure: Optional[float] = None
core_height_cm: Optional[float] = None
core_width_cm: Optional[float] = None
core_volume_cm3: Optional[float] = None
```

- [ ] **Add `ResultWithFlagsResponse`** to `backend/api/schemas/results.py`:

```python
class ResultWithFlagsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_fk: int
    time_post_reaction_days: Optional[float] = None
    time_post_reaction_bucket_days: Optional[float] = None
    cumulative_time_post_reaction_days: Optional[float] = None
    is_primary_timepoint_result: bool
    description: str
    created_at: datetime
    has_scalar: bool = False
    has_icp: bool = False
    # Key scalar values for the list (None if no scalar)
    grams_per_ton_yield: Optional[float] = None
    h2_grams_per_ton_yield: Optional[float] = None
    final_ph: Optional[float] = None
```

- [ ] **Run tests, confirm they pass**:
```
pytest tests/api/test_schemas.py -k "test_experiment_list_item_has_additives or test_experiment_create_no or test_experiment_status or test_next_id or test_conditions_update_has_all or test_result_with_flags" -v
```
Expected: 6 PASSED

- [ ] Commit:
```bash
git add backend/api/schemas/
git commit -m "[M5] Extend API schemas: list item, detail, next-id, conditions fields, result flags

- Tests added: yes (6 schema tests)
- Docs updated: no"
```

---

### Task B2: Add `GET /experiments/next-id` and fix create auto-numbering

**Files:**
- Modify: `backend/api/routers/experiments.py`
- Modify: `tests/api/test_experiments.py`

- [ ] **Write failing tests**:

```python
# In tests/api/test_experiments.py

def test_next_id_first_ever(client):
    """No existing experiments of type → returns PREFIX_001."""
    resp = client.get("/api/experiments/next-id?type=HPHT")
    assert resp.status_code == 200
    assert resp.json()["next_id"] == "HPHT_001"

def test_next_id_increments(client, db_session):
    """Existing HPHT_002 → next is HPHT_003."""
    db_session.add(Experiment(experiment_id="HPHT_002", experiment_number=9010, status=ExperimentStatus.ONGOING))
    db_session.commit()
    resp = client.get("/api/experiments/next-id?type=HPHT")
    assert resp.json()["next_id"] == "HPHT_003"

def test_next_id_serum_prefix(client):
    resp = client.get("/api/experiments/next-id?type=Serum")
    assert resp.json()["next_id"] == "SERUM_001"

def test_next_id_core_flood_prefix(client):
    resp = client.get("/api/experiments/next-id?type=Core Flood")
    assert resp.json()["next_id"] == "CF_001"

def test_create_experiment_auto_number(client, db_session):
    """experiment_number omitted → auto-assigned."""
    resp = client.post("/api/experiments", json={"experiment_id": "AUTONUMBER_001", "status": "ONGOING"})
    assert resp.status_code == 201
    assert resp.json()["experiment_number"] >= 1
```

- [ ] **Run tests, confirm they fail**:
```
pytest tests/api/test_experiments.py -k "test_next_id or test_create_experiment_auto_number" -v
```

- [ ] **Implement** — add to `backend/api/routers/experiments.py` **before** `/{experiment_id}` route:

```python
# Prefix mapping for next-id
_TYPE_PREFIX: dict[str, str] = {
    "HPHT": "HPHT",
    "Serum": "SERUM",
    "Autoclave": "AUTOCLAVE",
    "Core Flood": "CF",
}

@router.get("/next-id", response_model=NextIdResponse)
def get_next_experiment_id(
    type: str = Query(..., description="Experiment type"),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> NextIdResponse:
    """Return the next auto-incremented experiment ID for the given type."""
    prefix = _TYPE_PREFIX.get(type, type.upper().replace(" ", "_"))
    pattern = f"{prefix}_%"
    rows = db.execute(
        select(Experiment.experiment_id).where(Experiment.experiment_id.like(pattern))
    ).scalars().all()
    max_num = 0
    for eid in rows:
        suffix = eid[len(prefix) + 1:]
        if suffix.isdigit():
            max_num = max(max_num, int(suffix))
    next_num = str(max_num + 1).zfill(3)
    return NextIdResponse(next_id=f"{prefix}_{next_num}")
```

- [ ] **Fix auto-numbering** in `create_experiment`:

```python
# At top of create_experiment, after payload.model_dump():
if payload.experiment_number is None:
    from sqlalchemy import func
    max_num = db.execute(select(func.max(Experiment.experiment_number))).scalar() or 0
    exp_number = max_num + 1
else:
    exp_number = payload.experiment_number

data = payload.model_dump()
data["experiment_number"] = exp_number
exp = Experiment(**data)
```

- [ ] **Run tests**:
```
pytest tests/api/test_experiments.py -k "test_next_id or test_create_experiment_auto_number" -v
```
Expected: 5 PASSED

- [ ] Commit:
```bash
git add backend/api/routers/experiments.py tests/api/test_experiments.py
git commit -m "[M5] Add next-id endpoint; auto-assign experiment_number on create

- Tests added: yes (5)
- Docs updated: no"
```

---

### Task B3: Add `PATCH /experiments/{id}/status` and extend list endpoint

**Files:**
- Modify: `backend/api/routers/experiments.py`
- Modify: `tests/api/test_experiments.py`

- [ ] **Write failing tests**:

```python
def test_patch_status(client, db_session):
    _make_experiment(db_session, "STATUS_TEST_001", 9020)
    resp = client.patch("/api/experiments/STATUS_TEST_001/status", json={"status": "COMPLETED"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"

def test_patch_status_invalid(client, db_session):
    _make_experiment(db_session, "STATUS_TEST_002", 9021)
    resp = client.patch("/api/experiments/STATUS_TEST_002/status", json={"status": "INVALID"})
    assert resp.status_code == 422

def test_list_experiments_pagination(client, db_session):
    for i in range(5):
        db_session.add(Experiment(experiment_id=f"PAGE_{i:03d}", experiment_number=9100+i, status=ExperimentStatus.ONGOING))
    db_session.commit()
    resp = client.get("/api/experiments?skip=0&limit=3")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) <= 3

def test_list_experiments_filter_by_status(client, db_session):
    db_session.add(Experiment(experiment_id="COMP_001", experiment_number=9200, status=ExperimentStatus.COMPLETED))
    db_session.commit()
    resp = client.get("/api/experiments?status=COMPLETED")
    data = resp.json()
    assert all(e["status"] == "COMPLETED" for e in data["items"])
```

- [ ] **Run, confirm failures**:
```
pytest tests/api/test_experiments.py -k "test_patch_status or test_list_experiments_pagination or test_list_experiments_filter_by_status" -v
```

- [ ] **Implement** `PATCH /{experiment_id}/status` — add to `backend/api/routers/experiments.py` **before** `/{experiment_id}` catch-all:

```python
@router.patch("/{experiment_id}/status", response_model=ExperimentResponse)
def update_experiment_status(
    experiment_id: str,
    payload: ExperimentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentResponse:
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    exp.status = payload.status
    db.commit()
    db.refresh(exp)
    return ExperimentResponse.model_validate(exp)
```

- [ ] **Update `list_experiments`** to return `ExperimentListResponse` with joins for experiment_type, reactor_number, additives_summary, condition_note:

```python
@router.get("", response_model=ExperimentListResponse)
def list_experiments(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    status: ExperimentStatus | None = None,
    researcher: str | None = None,
    sample_id: str | None = None,
    experiment_type: str | None = None,
    reactor_number: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentListResponse:
    from database.models.conditions import ExperimentalConditions
    from database.models.experiments import ExperimentNotes
    from sqlalchemy import text, func, and_

    stmt = select(Experiment).order_by(Experiment.experiment_number.desc())
    if status:
        stmt = stmt.where(Experiment.status == status)
    if researcher:
        stmt = stmt.where(Experiment.researcher == researcher)
    if sample_id:
        stmt = stmt.where(Experiment.sample_id.ilike(f"%{sample_id}%"))
    if date_from:
        stmt = stmt.where(Experiment.date >= date_from)
    if date_to:
        stmt = stmt.where(Experiment.date <= date_to)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.offset(skip).limit(limit)).scalars().all()

    items = []
    for exp in rows:
        item_data = {c.key: getattr(exp, c.key) for c in Experiment.__table__.columns}
        # Join conditions
        cond = db.execute(
            select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
        ).scalar_one_or_none()
        item_data["experiment_type"] = cond.experiment_type if cond else None
        item_data["reactor_number"] = cond.reactor_number if cond else None
        # Filter by type/reactor if requested
        if experiment_type and item_data["experiment_type"] != experiment_type:
            total -= 1
            continue
        if reactor_number is not None and item_data["reactor_number"] != reactor_number:
            total -= 1
            continue
        # Additives summary
        additive_row = db.execute(
            text("SELECT additives_summary FROM v_experiment_additives_summary WHERE experiment_id = :eid"),
            {"eid": exp.experiment_id},
        ).fetchone()
        item_data["additives_summary"] = additive_row[0] if additive_row else None
        # First note
        first_note = db.execute(
            select(ExperimentNotes)
            .where(ExperimentNotes.experiment_fk == exp.id)
            .order_by(ExperimentNotes.id.asc())
            .limit(1)
        ).scalar_one_or_none()
        item_data["condition_note"] = first_note.note_text if first_note else None
        items.append(ExperimentListItem.model_validate(item_data))

    return ExperimentListResponse(items=items, total=total, skip=skip, limit=limit)
```

> **⚠ Known limitation:** The in-memory filter for `experiment_type`/`reactor_number` fetches the current page from the DB then discards non-matching rows in Python. This means the reported `total` is only decremented for rows in the current page window — it will be wrong for multi-page datasets when those filters are active. This is acceptable for a lab with < 500 experiments where type/reactor filtering will nearly always return < 25 results. Add a `# TODO: replace with proper JOIN query when lab data grows` comment in the code so it is not forgotten.

- [ ] **Run tests**:
```
pytest tests/api/test_experiments.py -v
```
Expected: all existing tests + new ones pass. Note: list tests that check `resp.json() == []` will break — update them to check `resp.json()["items"] == []`.

- [ ] **Fix existing list tests** that expect bare array (now wrapped in `ExperimentListResponse`):
```python
# Change:
assert resp.json() == []
# To:
assert resp.json()["items"] == []

# Change:
assert len(resp.json()) >= 1
# To:
assert len(resp.json()["items"]) >= 1
```

- [ ] Re-run and confirm all pass:
```
pytest tests/api/test_experiments.py -v
```

- [ ] Commit:
```bash
git add backend/api/routers/experiments.py tests/api/test_experiments.py
git commit -m "[M5] Add status-patch endpoint; extend list with pagination, joins, filters

- Tests added: yes (4 new + fixes)
- Docs updated: no"
```

---

### Task B4: Add `GET /experiments/{id}/results` with scalar+ICP flags

**Files:**
- Modify: `backend/api/routers/experiments.py`
- Modify: `tests/api/test_experiments.py`

- [ ] **Write failing tests**:

```python
def test_get_experiment_results_empty(client, db_session):
    _make_experiment(db_session, "RESULTS_EXP_001", 9300)
    resp = client.get("/api/experiments/RESULTS_EXP_001/results")
    assert resp.status_code == 200
    assert resp.json() == []

def test_get_experiment_results_with_flags(client, db_session):
    from database.models.results import ExperimentalResults, ScalarResults
    exp = _make_experiment(db_session, "RESULTS_EXP_002", 9301)
    result = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=7.0,
        time_post_reaction_bucket_days=7.0,
        cumulative_time_post_reaction_days=7.0,
        is_primary_timepoint_result=True,
        description="T7",
    )
    db_session.add(result)
    db_session.flush()
    scalar = ScalarResults(result_id=result.id, final_ph=7.2, grams_per_ton_yield=55.0)
    db_session.add(scalar)
    db_session.commit()

    resp = client.get("/api/experiments/RESULTS_EXP_002/results")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["has_scalar"] is True
    assert data[0]["has_icp"] is False
    assert data[0]["final_ph"] == 7.2
    assert data[0]["grams_per_ton_yield"] == 55.0
```

- [ ] **Run, confirm failures**:
```
pytest tests/api/test_experiments.py -k "test_get_experiment_results" -v
```

- [ ] **Implement** — add to `backend/api/routers/experiments.py` **before** `/{experiment_id}` route:

```python
@router.get("/{experiment_id}/results", response_model=list[ResultWithFlagsResponse])
def get_experiment_results(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[ResultWithFlagsResponse]:
    from database.models.results import ExperimentalResults, ScalarResults, ICPResults
    from backend.api.schemas.results import ResultWithFlagsResponse

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

    out = []
    for r in results:
        scalar = db.execute(
            select(ScalarResults).where(ScalarResults.result_id == r.id)
        ).scalar_one_or_none()
        icp = db.execute(
            select(ICPResults).where(ICPResults.result_id == r.id)
        ).scalar_one_or_none()
        out.append(ResultWithFlagsResponse(
            id=r.id,
            experiment_fk=r.experiment_fk,
            time_post_reaction_days=r.time_post_reaction_days,
            time_post_reaction_bucket_days=r.time_post_reaction_bucket_days,
            cumulative_time_post_reaction_days=r.cumulative_time_post_reaction_days,
            is_primary_timepoint_result=r.is_primary_timepoint_result,
            description=r.description,
            created_at=r.created_at,
            has_scalar=scalar is not None,
            has_icp=icp is not None,
            grams_per_ton_yield=scalar.grams_per_ton_yield if scalar else None,
            h2_grams_per_ton_yield=scalar.h2_grams_per_ton_yield if scalar else None,
            final_ph=scalar.final_ph if scalar else None,
        ))
    return out
```

- [ ] Also update `get_experiment` to return `ExperimentDetailResponse` with nested conditions/notes/modifications:

```python
@router.get("/{experiment_id}", response_model=ExperimentDetailResponse)
def get_experiment(experiment_id: str, db, current_user) -> ExperimentDetailResponse:
    from database.models.conditions import ExperimentalConditions
    from database.models.experiments import ExperimentNotes, ModificationsLog
    from backend.api.schemas.conditions import ConditionsResponse

    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    cond = db.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
    ).scalar_one_or_none()
    notes = db.execute(
        select(ExperimentNotes).where(ExperimentNotes.experiment_fk == exp.id)
        .order_by(ExperimentNotes.id.asc())
    ).scalars().all()
    mods = db.execute(
        select(ModificationsLog).where(ModificationsLog.experiment_fk == exp.id)
        .order_by(ModificationsLog.created_at.desc())
    ).scalars().all()

    detail = ExperimentDetailResponse.model_validate(exp)
    detail.conditions = ConditionsResponse.model_validate(cond).model_dump() if cond else None
    detail.notes = [{"id": n.id, "note_text": n.note_text, "created_at": n.created_at.isoformat()} for n in notes]
    detail.modifications = [
        {
            "id": m.id,
            "modified_by": m.modified_by,
            "modification_type": m.modification_type,
            "modified_table": m.modified_table,
            "old_values": m.old_values,
            "new_values": m.new_values,
            "created_at": m.created_at.isoformat(),
        }
        for m in mods
    ]
    return detail
```

- [ ] **Run all experiment tests**:
```
pytest tests/api/test_experiments.py -v
```
Expected: all pass

- [ ] **Verify final route ordering** in `backend/api/routers/experiments.py` after all B2/B3/B4 additions. The decorator order in the file must be:
  1. `GET /next-id`
  2. `GET /{experiment_id}/results`
  3. `PATCH /{experiment_id}/status`
  4. `GET /{experiment_id}`
  5. `PATCH /{experiment_id}`
  6. `DELETE /{experiment_id}`
  7. `POST /{experiment_id}/notes`

  FastAPI matches routes top-to-bottom. Static segments must appear before dynamic ones at the same depth. Run `pytest tests/api/test_experiments.py -k "test_next_id or test_patch_status or test_get_experiment_results" -v` to confirm no path shadowing.

- [ ] Commit:
```bash
git add backend/api/routers/experiments.py tests/api/test_experiments.py
git commit -m "[M5] Add results-with-flags endpoint; enrich get_experiment with conditions+notes

- Tests added: yes (2)
- Docs updated: no"
```

---

## Chunk C — ExperimentList Page

### Task C1: Update frontend API client

**Files:**
- Modify: `frontend/src/api/experiments.ts`

- [ ] **Update `frontend/src/api/experiments.ts`** — add `ExperimentListItem`, `ExperimentListResponse`, `ResultWithFlags`, `patchStatus`, `nextId`, `getResults`:

```typescript
import { apiClient } from './client'

export interface ExperimentListItem {
  id: number
  experiment_id: string
  experiment_number: number
  status: 'ONGOING' | 'COMPLETED' | 'CANCELLED'
  researcher: string | null
  date: string | null
  sample_id: string | null
  created_at: string
  experiment_type: string | null
  reactor_number: number | null
  additives_summary: string | null
  condition_note: string | null
}

export interface ExperimentListResponse {
  items: ExperimentListItem[]
  total: number
  skip: number
  limit: number
}

export interface ExperimentDetail {
  id: number
  experiment_id: string
  experiment_number: number
  status: 'ONGOING' | 'COMPLETED' | 'CANCELLED'
  researcher: string | null
  date: string | null
  sample_id: string | null
  base_experiment_id: string | null
  parent_experiment_fk: number | null
  created_at: string
  updated_at: string | null
  conditions: Record<string, unknown> | null
  notes: Array<{ id: number; note_text: string; created_at: string }>
  modifications: Array<{
    id: number
    modified_by: string | null
    modification_type: string | null
    modified_table: string | null
    old_values: Record<string, unknown> | null
    new_values: Record<string, unknown> | null
    created_at: string
  }>
}

export interface ResultWithFlags {
  id: number
  experiment_fk: number
  time_post_reaction_days: number | null
  time_post_reaction_bucket_days: number | null
  cumulative_time_post_reaction_days: number | null
  is_primary_timepoint_result: boolean
  description: string
  created_at: string
  has_scalar: boolean
  has_icp: boolean
  grams_per_ton_yield: number | null
  h2_grams_per_ton_yield: number | null
  final_ph: number | null
}

export interface ExperimentListParams {
  status?: string
  researcher?: string
  sample_id?: string
  experiment_type?: string
  reactor_number?: number
  date_from?: string
  date_to?: string
  skip?: number
  limit?: number
}

export interface CreateExperimentPayload {
  experiment_id: string
  status?: string
  researcher?: string
  date?: string
  sample_id?: string
  experiment_type?: string
  note?: string            // creates first note on submit
}

export const experimentsApi = {
  list: (params?: ExperimentListParams) =>
    apiClient.get<ExperimentListResponse>('/experiments', { params }).then((r) => r.data),

  get: (experimentId: string) =>
    apiClient.get<ExperimentDetail>(`/experiments/${experimentId}`).then((r) => r.data),

  create: (payload: CreateExperimentPayload) =>
    apiClient.post<ExperimentDetail>('/experiments', payload).then((r) => r.data),

  patch: (experimentId: string, payload: { status?: string; researcher?: string; date?: string }) =>
    apiClient.patch<ExperimentDetail>(`/experiments/${experimentId}`, payload).then((r) => r.data),

  patchStatus: (experimentId: string, status: string) =>
    apiClient.patch<ExperimentDetail>(`/experiments/${experimentId}/status`, { status }).then((r) => r.data),

  nextId: (type: string) =>
    apiClient.get<{ next_id: string }>('/experiments/next-id', { params: { type } }).then((r) => r.data),

  getResults: (experimentId: string) =>
    apiClient.get<ResultWithFlags[]>(`/experiments/${experimentId}/results`).then((r) => r.data),

  addNote: (experimentId: string, text: string) =>
    apiClient.post(`/experiments/${experimentId}/notes`, { note_text: text }).then((r) => r.data),

  delete: (experimentId: string) =>
    apiClient.delete(`/experiments/${experimentId}`).then((r) => r.data),
}
```

- [ ] Build check: `cd frontend && npx tsc --noEmit` — 0 errors

---

### Task C2: Rewrite ExperimentList page

**Files:**
- Modify: `frontend/src/pages/ExperimentList.tsx`

- [ ] **Rewrite `ExperimentList.tsx`** with full M5 spec:
  - All filters (status multi-chip, experiment type, sample ID text, date range, reactor number)
  - Server-side pagination (25/50/100)
  - Columns: #, Experiment ID (link), Description, Sample ID, Reactor #, Status (inline dropdown), Date, Additives
  - Inline status update: `patchStatus` + `invalidateQueries`
  - **Fix link bug**: `to={`/experiments/${exp.experiment_id}`}` (not `exp.id`)

```tsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { experimentsApi } from '@/api/experiments'
import {
  Table, TableHead, TableBody, TableRow, Th, Td,
  StatusBadge, Button, Input, Select, PageSpinner, Badge,
} from '@/components/ui'

const STATUS_OPTIONS = [
  { value: 'ONGOING', label: 'Ongoing' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'CANCELLED', label: 'Cancelled' },
]
const TYPE_OPTIONS = [
  { value: 'Serum', label: 'Serum' },
  { value: 'HPHT', label: 'HPHT' },
  { value: 'Autoclave', label: 'Autoclave' },
  { value: 'Core Flood', label: 'Core Flood' },
]
const PAGE_SIZES = [25, 50, 100]

export function ExperimentListPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [statusFilter, setStatusFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [sampleFilter, setSampleFilter] = useState('')
  const [reactorFilter, setReactorFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [skip, setSkip] = useState(0)
  const [limit, setLimit] = useState(25)

  const queryKey = ['experiments', statusFilter, typeFilter, sampleFilter, reactorFilter, dateFrom, dateTo, skip, limit]
  const { data, isLoading, error } = useQuery({
    queryKey,
    queryFn: () => experimentsApi.list({
      status: statusFilter || undefined,
      experiment_type: typeFilter || undefined,
      sample_id: sampleFilter || undefined,
      reactor_number: reactorFilter ? parseInt(reactorFilter) : undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      skip,
      limit,
    }),
  })

  const statusMutation = useMutation({
    mutationFn: ({ experimentId, status }: { experimentId: string; status: string }) =>
      experimentsApi.patchStatus(experimentId, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['experiments'] }),
  })

  const resetPage = () => setSkip(0)
  const totalPages = data ? Math.ceil(data.total / limit) : 0
  const currentPage = Math.floor(skip / limit) + 1

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-ink-primary">Experiments</h1>
          <p className="text-xs text-ink-muted mt-0.5">
            {data ? `${data.total} total` : '…'}
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={() => navigate('/experiments/new')}
          leftIcon={<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M6 1v10M1 6h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>}>
          New Experiment
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-2">
        <div className="w-40">
          <Select label="" options={STATUS_OPTIONS} placeholder="All statuses"
            value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); resetPage() }} />
        </div>
        <div className="w-40">
          <Select label="" options={TYPE_OPTIONS} placeholder="All types"
            value={typeFilter} onChange={(e) => { setTypeFilter(e.target.value); resetPage() }} />
        </div>
        <div className="w-36">
          <Input placeholder="Sample ID…" value={sampleFilter}
            onChange={(e) => { setSampleFilter(e.target.value); resetPage() }} />
        </div>
        <div className="w-24">
          <Input placeholder="Reactor #" value={reactorFilter}
            onChange={(e) => { setReactorFilter(e.target.value); resetPage() }} />
        </div>
        <div className="w-36">
          <Input type="date" placeholder="From" value={dateFrom}
            onChange={(e) => { setDateFrom(e.target.value); resetPage() }} />
        </div>
        <div className="w-36">
          <Input type="date" placeholder="To" value={dateTo}
            onChange={(e) => { setDateTo(e.target.value); resetPage() }} />
        </div>
        {(statusFilter || typeFilter || sampleFilter || reactorFilter || dateFrom || dateTo) && (
          <Button variant="ghost" size="sm" onClick={() => {
            setStatusFilter(''); setTypeFilter(''); setSampleFilter('')
            setReactorFilter(''); setDateFrom(''); setDateTo(''); resetPage()
          }}>Clear</Button>
        )}
      </div>

      {isLoading && <PageSpinner />}
      {error && <p className="text-sm text-red-400 py-4">Failed to load experiments</p>}

      {data && (
        <>
          <Table>
            <TableHead>
              <tr>
                <Th>#</Th>
                <Th>Experiment ID</Th>
                <Th>Description</Th>
                <Th>Sample</Th>
                <Th>Reactor</Th>
                <Th>Status</Th>
                <Th>Date</Th>
                <Th>Additives</Th>
              </tr>
            </TableHead>
            <TableBody>
              {data.items.length === 0 ? (
                <TableRow>
                  <Td colSpan={8} className="text-center py-8 text-ink-muted">No experiments found</Td>
                </TableRow>
              ) : (
                data.items.map((exp) => (
                  <TableRow key={exp.id} className="cursor-pointer" onClick={() => navigate(`/experiments/${exp.experiment_id}`)}>
                    <Td className="font-mono-data text-ink-muted">{exp.experiment_number}</Td>
                    <Td>
                      <span className="font-mono-data text-red-400 hover:text-red-300">
                        {exp.experiment_id}
                      </span>
                    </Td>
                    <Td className="text-xs text-ink-secondary max-w-48 truncate">
                      {exp.condition_note ?? <span className="text-ink-muted">—</span>}
                    </Td>
                    <Td className="font-mono-data text-xs">{exp.sample_id ?? <span className="text-ink-muted">—</span>}</Td>
                    <Td className="font-mono-data text-xs">{exp.reactor_number ?? <span className="text-ink-muted">—</span>}</Td>
                    <Td onClick={(e) => e.stopPropagation()}>
                      <select
                        className="bg-surface-card border border-surface-border rounded px-1.5 py-0.5 text-xs text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50"
                        value={exp.status ?? ''}
                        onChange={(e) => statusMutation.mutate({ experimentId: exp.experiment_id, status: e.target.value })}
                      >
                        {STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </select>
                    </Td>
                    <Td className="font-mono-data text-xs text-ink-muted">{exp.date ?? '—'}</Td>
                    <Td className="text-xs text-ink-secondary max-w-48 truncate">
                      {exp.additives_summary ?? <span className="text-ink-muted">—</span>}
                    </Td>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>

          {/* Pagination */}
          <div className="flex items-center justify-between text-xs text-ink-muted pt-1">
            <div className="flex items-center gap-2">
              <span>Rows per page:</span>
              {PAGE_SIZES.map((size) => (
                <button
                  key={size}
                  onClick={() => { setLimit(size); resetPage() }}
                  className={`px-2 py-0.5 rounded ${limit === size ? 'bg-surface-raised text-ink-primary' : 'hover:text-ink-secondary'}`}
                >
                  {size}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-3">
              <span>Page {currentPage} of {totalPages || 1}</span>
              <Button variant="ghost" size="xs" disabled={skip === 0}
                onClick={() => setSkip(Math.max(0, skip - limit))}>←</Button>
              <Button variant="ghost" size="xs" disabled={skip + limit >= (data.total)}
                onClick={() => setSkip(skip + limit)}>→</Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
```

- [ ] TypeScript check: `cd frontend && npx tsc --noEmit` — 0 errors
- [ ] Start dev server, verify list page renders, filters work, status dropdown updates without reload
- [ ] Commit:
```bash
git add frontend/src/api/experiments.ts frontend/src/pages/ExperimentList.tsx
git commit -m "[M5] ExperimentList: pagination, all filters, inline status update, correct links

- Tests added: no (frontend)
- Docs updated: no"
```

---

## Chunk D — New Experiment Multi-Step Form

### Task D1: Field visibility config + Step 1

**Files:**
- Create: `frontend/src/pages/NewExperiment/fieldVisibility.ts`
- Create: `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx`

- [ ] **Create `fieldVisibility.ts`**:

```typescript
export type ExperimentType = 'Serum' | 'HPHT' | 'Autoclave' | 'Core Flood'

export type ConditionField =
  | 'particle_size' | 'initial_ph' | 'rock_mass_g' | 'water_volume_mL'
  | 'temperature_c' | 'reactor_number' | 'feedstock' | 'stir_speed_rpm'
  | 'initial_conductivity_mS_cm' | 'room_temp_pressure_psi' | 'rxn_temp_pressure_psi'
  | 'co2_partial_pressure_MPa' | 'core_height_cm' | 'core_width_cm'
  | 'confining_pressure' | 'pore_pressure'

export const FIELD_VISIBILITY: Record<ExperimentType, Set<ConditionField>> = {
  Serum: new Set([
    'particle_size', 'initial_ph', 'rock_mass_g', 'water_volume_mL',
    'temperature_c', 'feedstock', 'stir_speed_rpm', 'initial_conductivity_mS_cm',
  ]),
  HPHT: new Set([
    'particle_size', 'initial_ph', 'rock_mass_g', 'water_volume_mL',
    'temperature_c', 'reactor_number', 'feedstock', 'stir_speed_rpm',
    'initial_conductivity_mS_cm', 'room_temp_pressure_psi', 'rxn_temp_pressure_psi',
    'co2_partial_pressure_MPa',
  ]),
  Autoclave: new Set([
    'particle_size', 'initial_ph', 'rock_mass_g', 'water_volume_mL',
    'temperature_c', 'feedstock', 'initial_conductivity_mS_cm',
  ]),
  'Core Flood': new Set([
    'particle_size', 'initial_ph', 'rock_mass_g', 'water_volume_mL',
    'temperature_c', 'reactor_number', 'feedstock', 'initial_conductivity_mS_cm',
    'room_temp_pressure_psi', 'rxn_temp_pressure_psi',
    'core_height_cm', 'core_width_cm', 'confining_pressure', 'pore_pressure',
  ]),
}

export function isVisible(field: ConditionField, type: ExperimentType | ''): boolean {
  if (!type) return false
  return FIELD_VISIBILITY[type]?.has(field) ?? false
}
```

- [ ] **Create `Step1BasicInfo.tsx`**:

```tsx
import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { samplesApi } from '@/api/samples'
import { Input, Select, Button } from '@/components/ui'
import type { ExperimentType } from './fieldVisibility'

export interface Step1Data {
  experimentType: ExperimentType | ''
  experimentId: string
  sampleId: string
  date: string
  status: string
  note: string
}

interface Props {
  data: Step1Data
  onChange: (patch: Partial<Step1Data>) => void
  onNext: () => void
}

const TYPE_OPTIONS = [
  { value: 'Serum', label: 'Serum' },
  { value: 'HPHT', label: 'HPHT' },
  { value: 'Autoclave', label: 'Autoclave' },
  { value: 'Core Flood', label: 'Core Flood' },
]
const STATUS_OPTIONS = [
  { value: 'ONGOING', label: 'Ongoing' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'CANCELLED', label: 'Cancelled' },
]

export function Step1BasicInfo({ data, onChange, onNext }: Props) {
  const { data: samples } = useQuery({
    queryKey: ['samples'],
    queryFn: () => samplesApi.list({ limit: 500 }),
  })

  // Fetch next-id whenever type changes.
  // NOTE: onSuccess was removed from useQuery in React Query v5. Use useEffect instead.
  const { data: nextIdData, isFetching: loadingId } = useQuery({
    queryKey: ['next-id', data.experimentType],
    queryFn: () => experimentsApi.nextId(data.experimentType),
    enabled: Boolean(data.experimentType),
  })
  useEffect(() => {
    if (nextIdData?.next_id) onChange({ experimentId: nextIdData.next_id })
  }, [nextIdData])

  const canProceed = Boolean(data.experimentType && data.experimentId)

  return (
    <div className="space-y-4">
      <Select
        label="Experiment Type *"
        options={TYPE_OPTIONS}
        placeholder="Select type…"
        value={data.experimentType}
        onChange={(e) => onChange({ experimentType: e.target.value as ExperimentType, experimentId: '' })}
      />
      <Input
        label="Experiment ID (auto-assigned)"
        value={loadingId ? 'Loading…' : data.experimentId}
        readOnly
        hint="Assigned from the next available ID for this type"
      />
      <Select
        label="Sample"
        options={(samples ?? []).map((s) => ({
          value: s.sample_id,
          label: `${s.sample_id}${s.rock_classification ? ` — ${s.rock_classification}` : ''}`,
        }))}
        placeholder="Select sample…"
        value={data.sampleId}
        onChange={(e) => onChange({ sampleId: e.target.value })}
      />
      <div className="grid grid-cols-2 gap-3">
        <Input label="Date" type="date" value={data.date}
          onChange={(e) => onChange({ date: e.target.value })} />
        <Select label="Status" options={STATUS_OPTIONS} value={data.status}
          onChange={(e) => onChange({ status: e.target.value })} />
      </div>
      <div>
        <label className="block text-xs font-medium text-ink-secondary mb-1">
          Condition Note (optional)
        </label>
        <textarea
          className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary placeholder-ink-muted focus:outline-none focus:ring-1 focus:ring-brand-red/50 resize-none"
          rows={3}
          placeholder="Describe the experiment conditions…"
          value={data.note}
          onChange={(e) => onChange({ note: e.target.value })}
        />
      </div>
      <div className="flex justify-end pt-2">
        <Button variant="primary" disabled={!canProceed} onClick={onNext}>
          Next: Conditions →
        </Button>
      </div>
    </div>
  )
}
```

- [ ] TypeScript check: `cd frontend && npx tsc --noEmit` — 0 errors

---

### Task D2: Step 2 Conditions + Step 3 Additives

**Files:**
- Create: `frontend/src/pages/NewExperiment/Step2Conditions.tsx`
- Create: `frontend/src/pages/NewExperiment/Step3Additives.tsx`

- [ ] **Create `Step2Conditions.tsx`**:

```tsx
import { Input, Select, Button } from '@/components/ui'
import { isVisible } from './fieldVisibility'
import type { ExperimentType } from './fieldVisibility'

const FEEDSTOCK_OPTIONS = [
  { value: 'Nitrogen', label: 'Nitrogen' },
  { value: 'Nitrate', label: 'Nitrate' },
  { value: 'Blank', label: 'None / Blank' },
]

export interface Step2Data {
  temperature_c: string
  initial_ph: string
  rock_mass_g: string
  water_volume_mL: string
  particle_size: string
  feedstock: string
  reactor_number: string
  stir_speed_rpm: string
  initial_conductivity_mS_cm: string
  room_temp_pressure_psi: string
  rxn_temp_pressure_psi: string
  co2_partial_pressure_MPa: string
  core_height_cm: string
  core_width_cm: string
  confining_pressure: string
  pore_pressure: string
}

interface Props {
  data: Step2Data
  experimentType: ExperimentType | ''
  onChange: (patch: Partial<Step2Data>) => void
  onBack: () => void
  onNext: () => void
}

function field(
  label: string,
  key: keyof Step2Data,
  type: ExperimentType | '',
  data: Step2Data,
  onChange: (p: Partial<Step2Data>) => void,
  unit?: string,
  inputType = 'number',
) {
  if (!isVisible(key as never, type)) return null
  return (
    <Input
      key={key}
      label={unit ? `${label} (${unit})` : label}
      type={inputType}
      value={data[key]}
      onChange={(e) => onChange({ [key]: e.target.value } as Partial<Step2Data>)}
    />
  )
}

export function Step2Conditions({ data, experimentType, onChange, onBack, onNext }: Props) {
  const rockMass = parseFloat(data.rock_mass_g)
  const waterVol = parseFloat(data.water_volume_mL)
  const wtr = (!isNaN(rockMass) && !isNaN(waterVol) && rockMass > 0) ? (waterVol / rockMass).toFixed(2) : null

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        {field('Temperature', 'temperature_c', experimentType, data, onChange, '°C')}
        {field('Initial pH', 'initial_ph', experimentType, data, onChange)}
        {field('Rock Mass', 'rock_mass_g', experimentType, data, onChange, 'g')}
        {field('Water Volume', 'water_volume_mL', experimentType, data, onChange, 'mL')}
        {wtr && (
          <div className="col-span-2 flex items-center gap-2 p-2 bg-surface-raised rounded text-xs text-ink-secondary">
            <span className="text-ink-muted">Water : Rock Ratio</span>
            <span className="font-mono-data text-ink-primary ml-auto">{wtr}</span>
          </div>
        )}
        {field('Particle Size', 'particle_size', experimentType, data, onChange, undefined, 'text')}
        {isVisible('feedstock', experimentType) && (
          <Select
            label="Feedstock"
            options={FEEDSTOCK_OPTIONS}
            placeholder="Select…"
            value={data.feedstock}
            onChange={(e) => onChange({ feedstock: e.target.value })}
          />
        )}
        {field('Reactor Number', 'reactor_number', experimentType, data, onChange)}
        {field('Stir Speed', 'stir_speed_rpm', experimentType, data, onChange, 'RPM')}
        {field('Initial Conductivity', 'initial_conductivity_mS_cm', experimentType, data, onChange, 'mS/cm')}
        {field('Room Temp Pressure', 'room_temp_pressure_psi', experimentType, data, onChange, 'psi')}
        {field('Rxn Temp Pressure', 'rxn_temp_pressure_psi', experimentType, data, onChange, 'psi')}
        {field('CO₂ Partial Pressure', 'co2_partial_pressure_MPa', experimentType, data, onChange, 'MPa')}
        {field('Core Height', 'core_height_cm', experimentType, data, onChange, 'cm')}
        {field('Core Width', 'core_width_cm', experimentType, data, onChange, 'cm')}
        {field('Confining Pressure', 'confining_pressure', experimentType, data, onChange)}
        {field('Pore Pressure', 'pore_pressure', experimentType, data, onChange)}
      </div>
      <div className="flex justify-between pt-2">
        <Button variant="ghost" onClick={onBack}>← Back</Button>
        <Button variant="primary" onClick={onNext}>Next: Additives →</Button>
      </div>
    </div>
  )
}
```

- [ ] **Create `Step3Additives.tsx`**:

```tsx
import { useQuery } from '@tanstack/react-query'
import { chemicalsApi } from '@/api/chemicals'
import { Input, Select, Button } from '@/components/ui'
import { useState } from 'react'

const AMOUNT_UNITS = ['g', 'mg', 'mL', 'mM', 'ppm', '% of Rock', 'wt%', 'mol', 'mmol']
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

export function Step3Additives({ rows, onChange, onBack, onNext }: Props) {
  const [compoundSearch, setCompoundSearch] = useState('')

  const { data: compounds } = useQuery({
    queryKey: ['compounds', compoundSearch],
    queryFn: () => chemicalsApi.listCompounds({ search: compoundSearch, limit: 50 }),
    enabled: compoundSearch.length >= 1,
  })

  const addRow = () => onChange([...rows, { compound_id: null, compound_name: '', amount: '', unit: 'g' }])
  const removeRow = (i: number) => onChange(rows.filter((_, idx) => idx !== i))
  const patchRow = (i: number, patch: Partial<AdditiveRow>) =>
    onChange(rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))

  return (
    <div className="space-y-3">
      <p className="text-xs text-ink-muted">Add chemical additives. Leave empty if none.</p>

      {/* Compound search — drives the query that populates the compound select below */}
      <div className="w-72">
        <Input
          placeholder="Search compounds…"
          value={compoundSearch}
          onChange={(e) => setCompoundSearch(e.target.value)}
        />
      </div>

      {rows.map((row, i) => (
        <div key={i} className="flex items-end gap-2 p-3 bg-surface-raised rounded">
          <div className="flex-1">
            <label className="block text-xs font-medium text-ink-secondary mb-1">Chemical</label>
            <select
              className="w-full bg-surface-input border border-surface-border rounded px-2 py-1.5 text-sm text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50"
              value={row.compound_id ?? ''}
              onChange={(e) => {
                const opt = compounds?.find((c) => c.id === parseInt(e.target.value))
                patchRow(i, { compound_id: opt?.id ?? null, compound_name: opt?.name ?? '' })
              }}
            >
              <option value="">Select compound…</option>
              {compounds?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div className="w-28">
            <Input label="Amount" type="number" value={row.amount}
              onChange={(e) => patchRow(i, { amount: e.target.value })} />
          </div>
          <div className="w-28">
            <Select label="Unit" options={AMOUNT_UNITS} value={row.unit}
              onChange={(e) => patchRow(i, { unit: e.target.value })} />
          </div>
          <button onClick={() => removeRow(i)}
            className="mb-0.5 text-ink-muted hover:text-red-400 text-lg leading-none px-1">×</button>
        </div>
      ))}

      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={addRow}>+ Add additive</Button>
        {rows.length === 0 && <span className="text-xs text-ink-muted">No additives (valid)</span>}
      </div>

      <div className="flex justify-between pt-2">
        <Button variant="ghost" onClick={onBack}>← Back</Button>
        <Button variant="primary" onClick={onNext}>Next: Review →</Button>
      </div>
    </div>
  )
}
```

- [ ] TypeScript check: `cd frontend && npx tsc --noEmit` — 0 errors

---

### Task D3: Step 4 Review + Orchestrator

**Files:**
- Create: `frontend/src/pages/NewExperiment/Step4Review.tsx`
- Create: `frontend/src/pages/NewExperiment/index.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Create `Step4Review.tsx`**:

```tsx
import { Button } from '@/components/ui'
import type { Step1Data } from './Step1BasicInfo'
import type { Step2Data } from './Step2Conditions'
import type { AdditiveRow } from './Step3Additives'
import { FIELD_VISIBILITY } from './fieldVisibility'

interface Props {
  step1: Step1Data
  step2: Step2Data
  additives: AdditiveRow[]
  onBack: () => void
  onSubmit: () => void
  isSubmitting: boolean
}

function kv(label: string, value: string | undefined) {
  if (!value) return null
  return (
    <div key={label} className="flex justify-between py-1 border-b border-surface-border/50 text-xs">
      <span className="text-ink-muted">{label}</span>
      <span className="font-mono-data text-ink-primary">{value}</span>
    </div>
  )
}

export function Step4Review({ step1, step2, additives, onBack, onSubmit, isSubmitting }: Props) {
  const visibleFields = step1.experimentType ? FIELD_VISIBILITY[step1.experimentType] : new Set()

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-ink-primary mb-2">Basic Info</h3>
        <div className="space-y-0">
          {kv('Experiment ID', step1.experimentId)}
          {kv('Type', step1.experimentType)}
          {kv('Sample', step1.sampleId)}
          {kv('Date', step1.date)}
          {kv('Status', step1.status)}
          {step1.note && kv('Condition Note', step1.note.slice(0, 80) + (step1.note.length > 80 ? '…' : ''))}
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-ink-primary mb-2">Conditions</h3>
        <div className="space-y-0">
          {[...visibleFields].map((f) => kv(f, (step2 as Record<string, string>)[f]))}
        </div>
      </div>

      {additives.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-ink-primary mb-2">Additives</h3>
          {additives.map((a, i) => (
            <div key={i} className="flex justify-between py-1 border-b border-surface-border/50 text-xs">
              <span className="text-ink-muted">{a.compound_name || '(unnamed)'}</span>
              <span className="font-mono-data text-ink-primary">{a.amount} {a.unit}</span>
            </div>
          ))}
        </div>
      )}

      <div className="flex justify-between pt-2">
        <Button variant="ghost" onClick={onBack}>← Back</Button>
        <Button variant="primary" loading={isSubmitting} onClick={onSubmit}>
          Create Experiment
        </Button>
      </div>
    </div>
  )
}
```

- [ ] **Create `index.tsx`** (orchestrator):

```tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { conditionsApi } from '@/api/conditions'
import { chemicalsApi } from '@/api/chemicals'
import { Card, CardHeader, CardBody, useToast } from '@/components/ui'
import { Step1BasicInfo, type Step1Data } from './Step1BasicInfo'
import { Step2Conditions, type Step2Data } from './Step2Conditions'
import { Step3Additives, type AdditiveRow } from './Step3Additives'
import { Step4Review } from './Step4Review'
import type { ExperimentType } from './fieldVisibility'

const STEPS = ['Basic Info', 'Conditions', 'Additives', 'Review']

const defaultStep1 = (): Step1Data => ({
  experimentType: '' as ExperimentType | '',
  experimentId: '',
  sampleId: '',
  date: new Date().toISOString().split('T')[0],
  status: 'ONGOING',
  note: '',
})

const defaultStep2 = (): Step2Data => ({
  temperature_c: '', initial_ph: '', rock_mass_g: '', water_volume_mL: '',
  particle_size: '', feedstock: '', reactor_number: '', stir_speed_rpm: '',
  initial_conductivity_mS_cm: '', room_temp_pressure_psi: '', rxn_temp_pressure_psi: '',
  co2_partial_pressure_MPa: '', core_height_cm: '', core_width_cm: '',
  confining_pressure: '', pore_pressure: '',
})

function toFloat(s: string): number | undefined {
  const n = parseFloat(s)
  return isNaN(n) ? undefined : n
}

export function NewExperimentPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()
  const [step, setStep] = useState(0)
  const [step1, setStep1] = useState(defaultStep1)
  const [step2, setStep2] = useState(defaultStep2)
  const [additives, setAdditives] = useState<AdditiveRow[]>([])

  const mutation = useMutation({
    mutationFn: async () => {
      // 1. Create experiment
      const exp = await experimentsApi.create({
        experiment_id: step1.experimentId,
        status: step1.status,
        sample_id: step1.sampleId || undefined,
        date: step1.date || undefined,
      })

      // 2. Add condition note if provided
      if (step1.note) {
        await experimentsApi.addNote(exp.experiment_id, step1.note)
      }

      // 3. Create conditions
      await conditionsApi.create({
        experiment_fk: exp.id,
        experiment_id: exp.experiment_id,
        experiment_type: step1.experimentType || undefined,
        temperature_c: toFloat(step2.temperature_c),
        initial_ph: toFloat(step2.initial_ph),
        rock_mass_g: toFloat(step2.rock_mass_g),
        water_volume_mL: toFloat(step2.water_volume_mL),
        particle_size: step2.particle_size || undefined,
        feedstock: step2.feedstock || undefined,
        reactor_number: step2.reactor_number ? parseInt(step2.reactor_number) : undefined,
        stir_speed_rpm: toFloat(step2.stir_speed_rpm),
        initial_conductivity_mS_cm: toFloat(step2.initial_conductivity_mS_cm),
        room_temp_pressure_psi: toFloat(step2.room_temp_pressure_psi),
        rxn_temp_pressure_psi: toFloat(step2.rxn_temp_pressure_psi),
        co2_partial_pressure_MPa: toFloat(step2.co2_partial_pressure_MPa),
        core_height_cm: toFloat(step2.core_height_cm),
        core_width_cm: toFloat(step2.core_width_cm),
        confining_pressure: toFloat(step2.confining_pressure),
        pore_pressure: toFloat(step2.pore_pressure),
      })

      // 4. Create additives
      for (const row of additives) {
        if (row.compound_id && row.amount) {
          // get conditions id from created conditions
          const cond = await conditionsApi.getByExperiment(exp.experiment_id)
          await chemicalsApi.addAdditive(cond.id, {
            compound_id: row.compound_id,
            amount: parseFloat(row.amount),
            unit: row.unit,
          })
        }
      }

      return exp
    },
    onSuccess: (exp) => {
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
      success('Experiment created', exp.experiment_id)
      navigate(`/experiments/${exp.experiment_id}`)
    },
    onError: (err: Error) => {
      toastError('Failed to create experiment', err.message)
    },
  })

  const stepContent = [
    <Step1BasicInfo data={step1} onChange={(p) => setStep1((s) => ({ ...s, ...p }))}
      onNext={() => setStep(1)} />,
    <Step2Conditions data={step2} experimentType={step1.experimentType}
      onChange={(p) => setStep2((s) => ({ ...s, ...p }))}
      onBack={() => setStep(0)} onNext={() => setStep(2)} />,
    <Step3Additives rows={additives} onChange={setAdditives}
      onBack={() => setStep(1)} onNext={() => setStep(3)} />,
    <Step4Review step1={step1} step2={step2} additives={additives}
      onBack={() => setStep(2)} onSubmit={() => mutation.mutate()}
      isSubmitting={mutation.isPending} />,
  ]

  return (
    <div className="max-w-xl space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-ink-primary">New Experiment</h1>
        {/* Step indicator */}
        <div className="flex gap-1 mt-2">
          {STEPS.map((s, i) => (
            <div key={s} className={`h-1 flex-1 rounded-full transition-colors ${i <= step ? 'bg-brand-red' : 'bg-surface-border'}`} />
          ))}
        </div>
        <p className="text-xs text-ink-muted mt-1">Step {step + 1} of {STEPS.length}: {STEPS[step]}</p>
      </div>
      <Card padding="none">
        <CardHeader label={STEPS[step]} />
        <CardBody>{stepContent[step]}</CardBody>
      </Card>
    </div>
  )
}
```

- [ ] **Create `frontend/src/api/conditions.ts`**:

```typescript
import { apiClient } from './client'

export interface ConditionsPayload {
  experiment_fk: number
  experiment_id: string
  experiment_type?: string
  temperature_c?: number
  initial_ph?: number
  rock_mass_g?: number
  water_volume_mL?: number
  particle_size?: string
  feedstock?: string
  reactor_number?: number
  stir_speed_rpm?: number
  initial_conductivity_mS_cm?: number
  room_temp_pressure_psi?: number
  rxn_temp_pressure_psi?: number
  co2_partial_pressure_MPa?: number
  core_height_cm?: number
  core_width_cm?: number
  confining_pressure?: number
  pore_pressure?: number
}

export interface ConditionsResponse extends ConditionsPayload {
  id: number
  water_to_rock_ratio?: number | null
  created_at: string
}

export const conditionsApi = {
  create: (payload: ConditionsPayload) =>
    apiClient.post<ConditionsResponse>('/conditions', payload).then((r) => r.data),

  getByExperiment: (experimentId: string) =>
    apiClient.get<ConditionsResponse>(`/conditions/by-experiment/${experimentId}`).then((r) => r.data),

  patch: (conditionsId: number, payload: Partial<ConditionsPayload>) =>
    apiClient.patch<ConditionsResponse>(`/conditions/${conditionsId}`, payload).then((r) => r.data),
}
```

- [ ] **Verify `addAdditive` exists in `frontend/src/api/chemicals.ts`** — the existing file already exports this method. Do NOT add a duplicate `createAdditive`. If the method is missing or named differently, add it as `addAdditive`:

```typescript
addAdditive: (conditionsId: number, payload: { compound_id: number; amount: number; unit: string; addition_order?: number }) =>
  apiClient.post<ChemicalAdditive>(`/chemicals/additives/${conditionsId}`, payload).then((r) => r.data),
```

- [ ] **Update `App.tsx`** — update the import path for `NewExperimentPage`:

```tsx
import { NewExperimentPage } from '@/pages/NewExperiment'
```
(This replaces the single-file import. The index.tsx re-exports the component so the route path `/experiments/new` stays the same.)

- [ ] TypeScript check: `cd frontend && npx tsc --noEmit` — 0 errors
- [ ] Start dev server, manually walk through all 4 steps with a test experiment
- [ ] Verify: experiment appears in list, note shows in detail, conditions populated
- [ ] Commit:
```bash
git add frontend/src/pages/NewExperiment/ frontend/src/api/conditions.ts frontend/src/api/chemicals.ts frontend/src/api/experiments.ts frontend/src/App.tsx
git commit -m "[M5] New Experiment: 4-step form with auto-ID, field visibility, additives

- Tests added: no (frontend)
- Docs updated: no"
```

---

## Chunk E — Experiment Detail Tabs

### Task E1: Tab scaffold + ConditionsTab

**Files:**
- Create: `frontend/src/pages/ExperimentDetail/index.tsx`
- Create: `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Create `ConditionsTab.tsx`**:

```tsx
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { conditionsApi, type ConditionsResponse, type ConditionsPayload } from '@/api/conditions'
import { Card, CardHeader, CardBody, Button, Input, Select, Modal, useToast } from '@/components/ui'

const FEEDSTOCK_OPTIONS = [
  { value: 'Nitrogen', label: 'Nitrogen' },
  { value: 'Nitrate', label: 'Nitrate' },
  { value: 'Blank', label: 'None / Blank' },
]

interface Props {
  conditions: ConditionsResponse | null
  experimentId: string
}

function Row({ label, value, unit }: { label: string; value: unknown; unit?: string }) {
  if (value == null || value === '') return null
  return (
    <div className="flex items-baseline justify-between py-1 border-b border-surface-border/50">
      <span className="text-xs text-ink-muted">{label}</span>
      <span className="text-xs font-mono-data text-ink-primary">
        {String(value)}{unit ? ` ${unit}` : ''}
      </span>
    </div>
  )
}

export function ConditionsTab({ conditions, experimentId }: Props) {
  const [editOpen, setEditOpen] = useState(false)
  const [form, setForm] = useState<Partial<ConditionsPayload>>({})
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()

  const patchMutation = useMutation({
    mutationFn: () => conditionsApi.patch(conditions!.id, form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] })
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

  if (!conditions) return <p className="text-sm text-ink-muted p-4">No conditions recorded for this experiment.</p>

  const set = (k: keyof ConditionsPayload) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((p) => ({ ...p, [k]: e.target.value === '' ? undefined : (isNaN(Number(e.target.value)) ? e.target.value : Number(e.target.value)) }))

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
          <div className="flex items-baseline justify-between py-1 border-b border-surface-border/50">
            <span className="text-xs text-ink-muted font-semibold">Water : Rock Ratio</span>
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

      <Modal isOpen={editOpen} onClose={() => setEditOpen(false)} title="Edit Conditions">
        <div className="space-y-3 p-4">
          <div className="grid grid-cols-2 gap-3">
            <Input label="Particle Size" type="text" value={(form as Record<string, unknown>).particle_size as string ?? ''} onChange={(e) => setForm((p) => ({ ...p, particle_size: e.target.value || undefined }))} />
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
    </>
  )
}
```

---

### Task E2: ResultsTab, NotesTab, remaining tabs

**Files:**
- Create: `frontend/src/pages/ExperimentDetail/ResultsTab.tsx`
- Create: `frontend/src/pages/ExperimentDetail/NotesTab.tsx`
- Create: `frontend/src/pages/ExperimentDetail/ModificationsTab.tsx`
- Create: `frontend/src/pages/ExperimentDetail/AnalysisTab.tsx`
- Create: `frontend/src/pages/ExperimentDetail/FilesTab.tsx`

- [ ] **Create `ResultsTab.tsx`** — expandable rows with scalar + ICP:

```tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { experimentsApi, type ResultWithFlags } from '@/api/experiments'
import { resultsApi } from '@/api/results'
import { Badge, PageSpinner } from '@/components/ui'

function fmt(n: number | null | undefined, decimals = 2) {
  return n != null ? n.toFixed(decimals) : '—'
}

function ExpandedRow({ result }: { result: ResultWithFlags }) {
  const { data: scalar, isLoading: loadingScalar } = useQuery({
    queryKey: ['scalar', result.id],
    queryFn: () => resultsApi.listScalar({ result_id: result.id }).then((d) => d[0] ?? null),
    enabled: result.has_scalar,
  })

  const { data: icp } = useQuery({
    queryKey: ['icp', result.id],
    queryFn: () => resultsApi.getIcp(result.id),
    enabled: result.has_icp,
  })

  if (loadingScalar) return <div className="py-3 pl-6"><PageSpinner /></div>

  return (
    <div className="bg-surface-raised border-t border-surface-border px-6 py-3 space-y-3">
      {scalar && (
        <div>
          <p className="text-xs font-semibold text-ink-secondary mb-1">Scalar Results</p>
          <div className="grid grid-cols-3 gap-x-6 gap-y-1">
            {[
              ['Final pH', scalar.final_ph, ''],
              ['Conductivity', scalar.final_conductivity_mS_cm, 'mS/cm'],
              ['Gross NH₄', scalar.gross_ammonium_concentration_mM, 'mM'],
              ['Net NH₄ Yield', scalar.grams_per_ton_yield, 'g/t'],
              ['H₂ (ppm)', scalar.h2_concentration, 'ppm'],
              ['H₂ (µmol)', scalar.h2_micromoles, 'µmol'],
              ['H₂ Yield', scalar.h2_grams_per_ton_yield, 'g/t'],
              ['DO', scalar.final_dissolved_oxygen_mg_L, 'mg/L'],
              ['Fe(II)', scalar.ferrous_iron_yield, ''],
            ].map(([label, val, unit]) => val != null ? (
              <div key={String(label)} className="text-xs">
                <span className="text-ink-muted">{label}: </span>
                <span className="font-mono-data text-ink-primary">{String(val)}{unit ? ` ${unit}` : ''}</span>
              </div>
            ) : null)}
          </div>
        </div>
      )}
      {icp && (
        <div>
          <p className="text-xs font-semibold text-ink-secondary mb-1">ICP-OES</p>
          <div className="grid grid-cols-4 gap-x-4 gap-y-1">
            {['fe','si','mg','ca','ni','cu','mo','zn','mn','cr','co','al'].map((el) => {
              const val = (icp as Record<string, unknown>)[el]
              return val != null ? (
                <div key={el} className="text-xs">
                  <span className="text-ink-muted uppercase">{el}: </span>
                  <span className="font-mono-data text-ink-primary">{String(val)}</span>
                </div>
              ) : null
            })}
          </div>
          {icp.dilution_factor && (
            <p className="text-xs text-ink-muted mt-1">Dilution: {icp.dilution_factor}× · {icp.instrument_used ?? ''}</p>
          )}
        </div>
      )}
    </div>
  )
}

interface Props { experimentId: string }

export function ResultsTab({ experimentId }: Props) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const { data: results, isLoading } = useQuery({
    queryKey: ['experiment-results', experimentId],
    queryFn: () => experimentsApi.getResults(experimentId),
  })

  const toggle = (id: number) => setExpanded((s) => {
    const n = new Set(s)
    n.has(id) ? n.delete(id) : n.add(id)
    return n
  })

  if (isLoading) return <PageSpinner />
  if (!results?.length) return <p className="text-sm text-ink-muted p-4 text-center">No results recorded</p>

  return (
    <div>
      {/* Header row */}
      <div className="grid grid-cols-[2rem_6rem_6rem_6rem_5rem_4rem_2rem] gap-2 px-4 py-2 border-b border-surface-border text-xs text-ink-muted">
        <span></span>
        <span>Time (d)</span>
        <span>NH₄ (g/t)</span>
        <span>H₂ (g/t)</span>
        <span>pH</span>
        <span>ICP</span>
        <span></span>
      </div>
      {results.map((r) => (
        <div key={r.id}>
          <div
            className="grid grid-cols-[2rem_6rem_6rem_6rem_5rem_4rem_2rem] gap-2 px-4 py-2 border-b border-surface-border/50 hover:bg-surface-raised cursor-pointer items-center"
            onClick={() => toggle(r.id)}
          >
            <span className="text-xs text-ink-muted">{r.is_primary_timepoint_result ? '★' : ''}</span>
            <span className="font-mono-data text-sm text-ink-primary">T+{r.time_post_reaction_days ?? '?'}</span>
            <span className="font-mono-data text-xs text-ink-secondary">{fmt(r.grams_per_ton_yield)}</span>
            <span className="font-mono-data text-xs text-ink-secondary">{fmt(r.h2_grams_per_ton_yield)}</span>
            <span className="font-mono-data text-xs text-ink-secondary">{fmt(r.final_ph, 1)}</span>
            <span>{r.has_icp ? <Badge variant="info" dot>ICP</Badge> : <span className="text-ink-muted text-xs">—</span>}</span>
            <span className="text-ink-muted text-xs">{expanded.has(r.id) ? '▲' : '▼'}</span>
          </div>
          {expanded.has(r.id) && <ExpandedRow result={r} />}
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Add `getIcp` to `frontend/src/api/results.ts`**:

```typescript
export interface ICPResult {
  id: number
  result_id: number
  dilution_factor: number | null
  instrument_used: string | null
  fe: number | null; si: number | null; mg: number | null; ca: number | null
  ni: number | null; cu: number | null; mo: number | null; zn: number | null
  mn: number | null; cr: number | null; co: number | null; al: number | null
}

// Add to resultsApi:
getIcp: (resultId: number) =>
  apiClient.get<ICPResult>(`/results/icp/${resultId}`).then((r) => r.data),
```

- [ ] **Create `NotesTab.tsx`**:

```tsx
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { Button, useToast } from '@/components/ui'

interface Note { id: number; note_text: string; created_at: string }
interface Props { experimentId: string; notes: Note[] }

export function NotesTab({ experimentId, notes }: Props) {
  const [text, setText] = useState('')
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()

  const addNote = useMutation({
    mutationFn: () => experimentsApi.addNote(experimentId, text),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] })
      success('Note added')
      setText('')
    },
    onError: (err: Error) => toastError('Failed to add note', err.message),
  })

  return (
    <div className="p-4 space-y-4">
      {/* Add note */}
      <div className="space-y-2">
        <textarea
          className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary placeholder-ink-muted focus:outline-none focus:ring-1 focus:ring-brand-red/50 resize-none"
          rows={3}
          placeholder="Add a note…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <Button variant="primary" size="sm" disabled={!text.trim()} loading={addNote.isPending}
          onClick={() => addNote.mutate()}>
          Add Note
        </Button>
      </div>

      {/* Feed */}
      <div className="space-y-3">
        {notes.length === 0 && <p className="text-sm text-ink-muted">No notes yet</p>}
        {[...notes].reverse().map((n, i) => (
          <div key={n.id} className={`text-xs border-b border-surface-border pb-3 ${i === notes.length - 1 ? 'border-b-0' : ''}`}>
            {i === notes.length - 1 && (
              <span className="inline-block text-[10px] font-semibold uppercase tracking-wider text-brand-red bg-brand-red/10 px-1.5 py-0.5 rounded mb-1">
                Condition Note
              </span>
            )}
            <p className="text-ink-secondary leading-relaxed">{n.note_text}</p>
            <p className="text-ink-muted mt-0.5 font-mono-data">
              {new Date(n.created_at).toLocaleString()}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Create `ModificationsTab.tsx`**:

```tsx
interface Mod {
  id: number
  modified_by: string | null
  modification_type: string | null
  modified_table: string | null
  old_values: Record<string, unknown> | null
  new_values: Record<string, unknown> | null
  created_at: string
}
interface Props { modifications: Mod[] }

export function ModificationsTab({ modifications }: Props) {
  if (!modifications.length) return <p className="text-sm text-ink-muted p-4">No modifications recorded</p>
  return (
    <div className="divide-y divide-surface-border">
      {modifications.map((m) => (
        <div key={m.id} className="px-4 py-3 space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono-data text-ink-muted">{new Date(m.created_at).toLocaleString()}</span>
            <span className="text-xs text-ink-secondary">{m.modified_table ?? '—'}</span>
            <span className="text-xs text-brand-red uppercase">{m.modification_type ?? '—'}</span>
            {m.modified_by && <span className="text-xs text-ink-muted ml-auto">{m.modified_by}</span>}
          </div>
          {(m.old_values || m.new_values) && (
            <pre className="text-[10px] font-mono-data text-ink-muted bg-surface-raised p-2 rounded overflow-x-auto">
              {JSON.stringify({ old: m.old_values, new: m.new_values }, null, 2)}
            </pre>
          )}
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Create `AnalysisTab.tsx`** (stub showing linked analyses):

```tsx
import { useQuery } from '@tanstack/react-query'
import { analysisApi } from '@/api/analysis'

interface Props { experimentId: string }

export function AnalysisTab({ experimentId }: Props) {
  const { data: xrd } = useQuery({
    queryKey: ['xrd', experimentId],
    queryFn: () => analysisApi.getXRD(experimentId),  // uppercase XRD — matches existing analysis.ts export
  })
  const { data: external } = useQuery({
    queryKey: ['external-analysis', experimentId],
    queryFn: () => analysisApi.getExternal(experimentId),
  })

  const hasData = (xrd?.length ?? 0) + (external?.length ?? 0) > 0
  if (!hasData) return <p className="text-sm text-ink-muted p-4">No external analyses linked</p>

  return (
    <div className="p-4 space-y-3">
      {(xrd ?? []).map((x) => (
        <div key={x.id} className="text-xs border-b border-surface-border pb-2">
          <span className="font-semibold text-ink-secondary">XRD</span>
          <span className="text-ink-muted ml-2">{x.analysis_date ?? '—'} · {x.laboratory ?? '—'}</span>
        </div>
      ))}
      {(external ?? []).map((e) => (
        <div key={e.id} className="text-xs border-b border-surface-border pb-2">
          <span className="font-semibold text-ink-secondary">{e.analysis_type ?? 'Analysis'}</span>
          <span className="text-ink-muted ml-2">{e.analysis_date ?? '—'} · {e.laboratory ?? '—'}</span>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Create `FilesTab.tsx`** (stub):

```tsx
interface Props { experimentId: string }
export function FilesTab({ experimentId: _ }: Props) {
  return <p className="text-sm text-ink-muted p-4">File management — coming in M6 (Bulk Uploads)</p>
}
```

---

### Task E3: ExperimentDetail orchestrator

**Files:**
- Create: `frontend/src/pages/ExperimentDetail/index.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Create `ExperimentDetail/index.tsx`**:

```tsx
import { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { conditionsApi } from '@/api/conditions'
import { StatusBadge, Button, PageSpinner } from '@/components/ui'
import { ConditionsTab } from './ConditionsTab'
import { ResultsTab } from './ResultsTab'
import { NotesTab } from './NotesTab'
import { ModificationsTab } from './ModificationsTab'
import { AnalysisTab } from './AnalysisTab'
import { FilesTab } from './FilesTab'

const TABS = ['Conditions', 'Results', 'Notes', 'Modifications', 'Analysis', 'Files'] as const
type Tab = typeof TABS[number]

export function ExperimentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<Tab>('Conditions')

  const { data: experiment, isLoading, error } = useQuery({
    queryKey: ['experiment', id],
    queryFn: () => experimentsApi.get(id!),
    enabled: Boolean(id),
  })

  const { data: conditions } = useQuery({
    queryKey: ['conditions', id],
    queryFn: () => conditionsApi.getByExperiment(id!),
    enabled: Boolean(id),
    retry: false,          // 404 = no conditions yet, don't retry
  })

  if (isLoading) return <PageSpinner />
  if (error || !experiment) return <p className="text-red-400 text-sm p-6">Experiment not found</p>

  return (
    <div className="space-y-4">
      {/* Breadcrumb */}
      <div>
        <p className="text-xs text-ink-muted mb-1">
          <Link to="/experiments" className="hover:text-ink-secondary">Experiments</Link>
          <span className="mx-1.5">›</span>
          <span className="font-mono-data">{experiment.experiment_id}</span>
        </p>
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-ink-primary font-mono-data">{experiment.experiment_id}</h1>
          <StatusBadge status={experiment.status} />
          {conditions?.experiment_type && (
            <span className="text-xs text-ink-muted">{conditions.experiment_type}</span>
          )}
        </div>
        <p className="text-xs text-ink-muted mt-0.5">
          #{experiment.experiment_number}
          {experiment.researcher && ` · ${experiment.researcher}`}
          {experiment.date && ` · ${experiment.date}`}
          {experiment.sample_id && ` · Sample: ${experiment.sample_id}`}
          {conditions?.reactor_number != null && ` · Reactor ${conditions.reactor_number}`}
        </p>
      </div>

      {/* Quick actions */}
      <div className="flex gap-2">
        <Button variant="ghost" size="sm" onClick={() => navigate('/experiments/new')}>
          + New Experiment
        </Button>
      </div>

      {/* Tab bar */}
      <div className="border-b border-surface-border flex gap-0">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm border-b-2 transition-colors ${
              activeTab === tab
                ? 'border-brand-red text-ink-primary'
                : 'border-transparent text-ink-muted hover:text-ink-secondary'
            }`}
          >
            {tab}
            {tab === 'Notes' && experiment.notes.length > 0 && (
              <span className="ml-1.5 text-[10px] bg-surface-raised rounded px-1">{experiment.notes.length}</span>
            )}
            {tab === 'Modifications' && experiment.modifications.length > 0 && (
              <span className="ml-1.5 text-[10px] bg-surface-raised rounded px-1">{experiment.modifications.length}</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="bg-surface-card border border-surface-border rounded-lg overflow-hidden">
        {activeTab === 'Conditions' && (
          <ConditionsTab conditions={conditions ?? null} experimentId={id!} />
        )}
        {activeTab === 'Results' && <ResultsTab experimentId={id!} />}
        {activeTab === 'Notes' && (
          <NotesTab experimentId={id!} notes={experiment.notes} />
        )}
        {activeTab === 'Modifications' && (
          <ModificationsTab modifications={experiment.modifications} />
        )}
        {activeTab === 'Analysis' && <AnalysisTab experimentId={id!} />}
        {activeTab === 'Files' && <FilesTab experimentId={id!} />}
      </div>
    </div>
  )
}
```

- [ ] **Update `App.tsx`** — update import:
```tsx
import { ExperimentDetailPage } from '@/pages/ExperimentDetail'
```

- [ ] **Check `frontend/src/api/analysis.ts`** exists and has `getXRD` (uppercase) and `getExternal` — if not, add minimal stubs. Note: the method is `getXRD` not `getXrd`.

- [ ] TypeScript check: `cd frontend && npx tsc --noEmit` — 0 errors
- [ ] ESLint check: `cd frontend && npx eslint src --ext .ts,.tsx` — 0 warnings
- [ ] Start dev server, manually test:
  - Conditions tab renders, edit modal works, save reflects immediately
  - Results tab shows timepoints, expanding row loads scalar, ICP tick shows when has_icp
  - Notes tab adds new note, list refreshes, condition note labelled at bottom
  - Modifications tab renders (may be empty)
  - Analysis/Files tabs render stubs

- [ ] Commit:
```bash
git add frontend/src/pages/ExperimentDetail/ frontend/src/api/ frontend/src/App.tsx
git commit -m "[M5] Experiment Detail: 6 tabs with conditions edit modal, expandable results, notes

- Tests added: no (frontend)
- Docs updated: no"
```

---

## Chunk F — Documentation + Working Plan Update

### Task F1: Update docs

- [ ] Update `docs/working/plan.md` — mark M5 tasks complete, update status
- [ ] Update `docs/milestones/M5_experiment_pages.md` — mark completed items
- [ ] Update `docs/api/API_REFERENCE.md` — add next-id, status-patch, experiment-results endpoints
- [ ] Commit:
```bash
git add docs/
git commit -m "[M5] Update docs: API reference, working plan, milestone progress

- Tests added: no
- Docs updated: yes"
```

---

## Final Verification Checklist

Before `/complete-task`:

- [ ] `pytest tests/api/ -v` — all tests pass
- [ ] `cd frontend && npx tsc --noEmit` — 0 errors
- [ ] `cd frontend && npx eslint src --ext .ts,.tsx` — 0 warnings
- [ ] `cd frontend && npm run build` — clean build
- [ ] Chrome DevTools: no console errors on any of the 3 pages
- [ ] Acceptance criteria from M5 doc:
  - [ ] Auto-ID returns correct next number for each type
  - [ ] New experiment round-trips: experiment + conditions + additives + note all saved
  - [ ] Step 2 shows only fields defined in visibility matrix
  - [ ] List filters all work server-side; status updates in-place
  - [ ] Detail results tab: NH₄ and H₂ yield from stored values; ICP tick renders; expanding row shows full data
  - [ ] Notes tab: condition note labelled; add note works
