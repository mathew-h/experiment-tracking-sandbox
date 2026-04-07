# Issue #22 — Edit Additives & Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add edit capability for chemical additives and notes on the Experiment Detail page, with full ModificationsLog audit trail on all write operations.

**Architecture:** Three new backend endpoints (PATCH additive by PK, DELETE additive by PK, PATCH note) live in a new `additives.py` router and an addition to `experiments.py`. All write paths—including the existing upsert PUT and DELETE by compound_id—gain ModificationsLog writes. The frontend adds an edit-pencil affordance per additive row (edit modal) and per note row (inline textarea).

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Pydantic v2, structlog, React 18, TanStack Query v5, Tailwind CSS

---

## What Already Exists (Do Not Duplicate)

- `GET /api/experiments/{id}/additives` — list additives
- `PUT /api/experiments/{id}/additives/{compound_id}` — upsert additive (create or update by compound)
- `DELETE /api/experiments/{id}/additives/{compound_id}` — delete additive by compound PK
- `POST /api/experiments/{id}/notes` — append note
- `ConditionsTab` — "Add" modal with compound typeahead; "×" delete button per row
- `NotesTab` — append-only feed

The "Create compound" inline option in the typeahead satisfies the auto-create-compound requirement from the issue — no new backend logic needed for that case.

---

## File Map

| Status | Path | Purpose |
|--------|------|---------|
| NEW | `backend/api/routers/additives.py` | `/api/additives` router: PATCH + DELETE by additive PK |
| NEW | `tests/api/test_additives.py` | Tests for new additives router |
| NEW | `tests/api/test_notes.py` | Tests for PATCH note endpoint |
| MODIFY | `backend/api/schemas/experiments.py` | Add `NoteUpdate`; add `updated_at` to `NoteResponse` |
| MODIFY | `backend/api/schemas/chemicals.py` | Add `AdditiveUpdate` |
| MODIFY | `backend/api/routers/experiments.py` | Add PATCH note endpoint; add ModificationsLog to existing upsert + delete additive endpoints |
| MODIFY | `backend/api/main.py` | Register `additives` router |
| MODIFY | `frontend/src/api/experiments.ts` | Add `patchNote()` |
| MODIFY | `frontend/src/api/chemicals.ts` | Add `patchAdditive()`, `deleteAdditiveById()` |
| MODIFY | `frontend/src/pages/ExperimentDetail/NotesTab.tsx` | Inline edit UI per note |
| MODIFY | `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx` | Edit-pencil per additive row + edit modal |
| MODIFY | `docs/api/API_REFERENCE.md` | Document new endpoints |

---

## Task 1: Schema additions — NoteUpdate, AdditiveUpdate, NoteResponse.updated_at

**Files:**
- Modify: `backend/api/schemas/experiments.py`
- Modify: `backend/api/schemas/chemicals.py`

No tests needed — schema validation is covered by the endpoint tests in later tasks.

- [ ] **Step 1: Add `NoteUpdate` and `updated_at` to `NoteResponse` in experiments.py**

Open `backend/api/schemas/experiments.py`. Add `Field` to the pydantic imports and add the two classes/modifications:

```python
# At the top, update imports:
from pydantic import BaseModel, ConfigDict, Field

# Add after NoteCreate (line ~85):
class NoteUpdate(BaseModel):
    note_text: str = Field(min_length=1)

# Update NoteResponse to include updated_at:
class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: str
    note_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
```

- [ ] **Step 2: Add `AdditiveUpdate` to chemicals.py**

Open `backend/api/schemas/chemicals.py`. Add after `ChemicalAdditiveUpsert` (after line ~87):

```python
class AdditiveUpdate(BaseModel):
    """Partial update payload for PATCH /api/additives/{id}. All fields optional."""
    compound_id: Optional[int] = None
    amount: Optional[float] = Field(None, gt=0)
    unit: Optional[AmountUnit] = None
    addition_order: Optional[int] = None
    addition_method: Optional[str] = None
    purity: Optional[float] = None
    lot_number: Optional[str] = None
```

- [ ] **Step 3: Commit**

```bash
git add backend/api/schemas/experiments.py backend/api/schemas/chemicals.py
git commit -m "[#22] add NoteUpdate and AdditiveUpdate schemas"
```

---

## Task 2: PATCH note endpoint + tests

**Files:**
- Modify: `backend/api/routers/experiments.py`
- Create: `tests/api/test_notes.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_notes.py`:

```python
from __future__ import annotations
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.enums import ExperimentStatus
from sqlalchemy import select


def _make_experiment_with_note(db, exp_id="NOTE_001", number=7001, text="Initial note text"):
    exp = Experiment(
        experiment_id=exp_id,
        experiment_number=number,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.flush()
    note = ExperimentNotes(experiment_id=exp_id, experiment_fk=exp.id, note_text=text)
    db.add(note)
    db.commit()
    db.refresh(exp)
    db.refresh(note)
    return exp, note


def test_patch_note_happy_path(client, db_session):
    exp, note = _make_experiment_with_note(db_session)
    resp = client.patch(
        f"/api/experiments/{exp.experiment_id}/notes/{note.id}",
        json={"note_text": "Corrected note text"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["note_text"] == "Corrected note text"
    assert body["id"] == note.id
    assert body["updated_at"] is not None


def test_patch_note_wrong_experiment_returns_404(client, db_session):
    exp, note = _make_experiment_with_note(db_session, "NOTE_002", 7002)
    resp = client.patch(
        f"/api/experiments/DOES_NOT_EXIST/notes/{note.id}",
        json={"note_text": "x"},
    )
    assert resp.status_code == 404


def test_patch_note_wrong_note_id_returns_404(client, db_session):
    exp, _ = _make_experiment_with_note(db_session, "NOTE_003", 7003)
    resp = client.patch(
        f"/api/experiments/{exp.experiment_id}/notes/99999",
        json={"note_text": "x"},
    )
    assert resp.status_code == 404


def test_patch_note_empty_text_returns_422(client, db_session):
    exp, note = _make_experiment_with_note(db_session, "NOTE_004", 7004)
    resp = client.patch(
        f"/api/experiments/{exp.experiment_id}/notes/{note.id}",
        json={"note_text": ""},
    )
    assert resp.status_code == 422


def test_patch_condition_note_is_editable(client, db_session):
    """First note (condition note) must be editable — no special read-only treatment."""
    exp, note = _make_experiment_with_note(db_session, "NOTE_005", 7005, text="Original condition note")
    resp = client.patch(
        f"/api/experiments/{exp.experiment_id}/notes/{note.id}",
        json={"note_text": "Fixed condition note"},
    )
    assert resp.status_code == 200
    assert resp.json()["note_text"] == "Fixed condition note"


def test_patch_note_writes_modifications_log(client, db_session):
    exp, note = _make_experiment_with_note(db_session, "NOTE_006", 7006, text="Before")
    client.patch(
        f"/api/experiments/{exp.experiment_id}/notes/{note.id}",
        json={"note_text": "After"},
    )
    log_entry = db_session.execute(
        select(ModificationsLog).where(
            ModificationsLog.experiment_fk == exp.id,
            ModificationsLog.modified_table == "experiment_notes",
        )
    ).scalar_one_or_none()
    assert log_entry is not None
    assert log_entry.modification_type == "update"
    assert log_entry.old_values == {"note_text": "Before"}
    assert log_entry.new_values == {"note_text": "After"}


def test_patch_note_noop_when_text_unchanged(client, db_session):
    """If text matches the stored value exactly, no DB write and no ModificationsLog entry."""
    exp, note = _make_experiment_with_note(db_session, "NOTE_007", 7007, text="Same text")
    resp = client.patch(
        f"/api/experiments/{exp.experiment_id}/notes/{note.id}",
        json={"note_text": "Same text"},
    )
    assert resp.status_code == 200
    assert resp.json()["note_text"] == "Same text"
    # No modifications log entry should exist
    log_count = db_session.execute(
        select(ModificationsLog).where(
            ModificationsLog.experiment_fk == exp.id,
            ModificationsLog.modified_table == "experiment_notes",
        )
    ).scalars().all()
    assert len(log_count) == 0
```

- [ ] **Step 2: Run tests — expect FAIL (endpoint does not exist)**

```bash
cd C:\Users\MathewHearl\Documents\0x_Software\database_sandbox\experiment_tracking_sandbox
.venv/Scripts/pytest tests/api/test_notes.py -v 2>&1 | head -30
```

Expected: `FAILED` with `404` or `AttributeError` on the undefined endpoint.

- [ ] **Step 3: Implement PATCH note endpoint in experiments.py**

In `backend/api/routers/experiments.py`, add `ModificationsLog` to the top-level import and `NoteUpdate` to the schema imports:

```python
# Update line 7:
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog

# Update schema imports (add NoteUpdate after NoteResponse):
from backend.api.schemas.experiments import (
    ExperimentCreate, ExperimentUpdate, ExperimentListItem, ExperimentListResponse,
    ExperimentResponse, ExperimentDetailResponse, ExperimentStatusUpdate, NextIdResponse,
    NoteCreate, NoteResponse, NoteUpdate,
)
```

Add the new endpoint after the `add_note` endpoint (after line ~499):

```python
@router.patch("/{experiment_id}/notes/{note_id}", response_model=NoteResponse)
def patch_note(
    experiment_id: str,
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> NoteResponse:
    """Edit the text of an existing note. No-op if text is unchanged. Writes ModificationsLog."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    note = db.execute(
        select(ExperimentNotes)
        .where(ExperimentNotes.id == note_id)
        .where(ExperimentNotes.experiment_fk == exp.id)
    ).scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    if note.note_text == payload.note_text:
        return NoteResponse.model_validate(note)
    old_text = note.note_text
    note.note_text = payload.note_text
    db.flush()
    db.add(ModificationsLog(
        experiment_id=experiment_id,
        experiment_fk=exp.id,
        modified_by=current_user.email,
        modification_type="update",
        modified_table="experiment_notes",
        old_values={"note_text": old_text},
        new_values={"note_text": payload.note_text},
    ))
    db.commit()
    db.refresh(note)
    log.info("note_updated", experiment_id=experiment_id, note_id=note_id)
    return NoteResponse.model_validate(note)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
.venv/Scripts/pytest tests/api/test_notes.py -v
```

Expected: 7 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/experiments.py tests/api/test_notes.py
git commit -m "[#22] add PATCH note endpoint with ModificationsLog"
```

---

## Task 3: New additives router (PATCH + DELETE by additive PK) + register + tests

**Files:**
- Create: `backend/api/routers/additives.py`
- Modify: `backend/api/main.py`
- Create: `tests/api/test_additives.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_additives.py`:

```python
from __future__ import annotations
from database.models.experiments import Experiment, ModificationsLog
from database.models.conditions import ExperimentalConditions
from database.models.chemicals import Compound, ChemicalAdditive
from database.models.enums import ExperimentStatus
from sqlalchemy import select


def _setup_experiment_with_additive(db, exp_id="ADDTEST_001", number=6001,
                                     compound_name="Iron Oxide", amount=5.0, unit="g"):
    exp = Experiment(experiment_id=exp_id, experiment_number=number, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    cond = ExperimentalConditions(
        experiment_id=exp_id,
        experiment_fk=exp.id,
        rock_mass_g=100.0,
        water_volume_mL=500.0,
    )
    db.add(cond)
    db.flush()
    compound = Compound(name=compound_name, molecular_weight_g_mol=159.69)
    db.add(compound)
    db.flush()
    additive = ChemicalAdditive(
        experiment_id=cond.id,
        compound_id=compound.id,
        amount=amount,
        unit=unit,
    )
    db.add(additive)
    db.commit()
    db.refresh(additive)
    db.refresh(compound)
    db.refresh(exp)
    return exp, cond, compound, additive


# ── PATCH /api/additives/{additive_id} ────────────────────────────────────────

def test_patch_additive_amount(client, db_session):
    exp, cond, compound, additive = _setup_experiment_with_additive(db_session)
    resp = client.patch(f"/api/additives/{additive.id}", json={"amount": 10.0})
    assert resp.status_code == 200
    body = resp.json()
    assert body["amount"] == 10.0
    assert body["unit"] == "g"  # unchanged


def test_patch_additive_unit(client, db_session):
    _, _, _, additive = _setup_experiment_with_additive(db_session, "ADDTEST_002", 6002)
    resp = client.patch(f"/api/additives/{additive.id}", json={"unit": "mg"})
    assert resp.status_code == 200
    assert resp.json()["unit"] == "mg"


def test_patch_additive_compound(client, db_session):
    exp, cond, compound, additive = _setup_experiment_with_additive(db_session, "ADDTEST_003", 6003)
    new_compound = Compound(name="Silica", molecular_weight_g_mol=60.08)
    db_session.add(new_compound)
    db_session.commit()
    resp = client.patch(f"/api/additives/{additive.id}", json={"compound_id": new_compound.id})
    assert resp.status_code == 200
    assert resp.json()["compound_id"] == new_compound.id


def test_patch_additive_invalid_unit_returns_422(client, db_session):
    _, _, _, additive = _setup_experiment_with_additive(db_session, "ADDTEST_004", 6004)
    resp = client.patch(f"/api/additives/{additive.id}", json={"unit": "furlongs"})
    assert resp.status_code == 422


def test_patch_additive_not_found_returns_404(client):
    resp = client.patch("/api/additives/99999", json={"amount": 1.0})
    assert resp.status_code == 404


def test_patch_additive_writes_modifications_log(client, db_session):
    exp, cond, compound, additive = _setup_experiment_with_additive(db_session, "ADDTEST_005", 6005)
    client.patch(f"/api/additives/{additive.id}", json={"amount": 20.0})
    log_entry = db_session.execute(
        select(ModificationsLog).where(
            ModificationsLog.experiment_fk == exp.id,
            ModificationsLog.modified_table == "chemical_additives",
            ModificationsLog.modification_type == "update",
        )
    ).scalar_one_or_none()
    assert log_entry is not None
    assert log_entry.old_values == {"amount": 5.0}
    assert log_entry.new_values == {"amount": 20.0}


def test_patch_additive_recalculates_moles(client, db_session):
    """After changing amount, moles_added must reflect the new amount."""
    _, _, _, additive = _setup_experiment_with_additive(
        db_session, "ADDTEST_006", 6006, compound_name="FeO_calc", amount=159.69, unit="g"
    )
    resp = client.patch(f"/api/additives/{additive.id}", json={"amount": 319.38})
    assert resp.status_code == 200
    # molecular_weight = 159.69 g/mol, amount = 319.38 g → 2.0 mol
    body = resp.json()
    assert body["moles_added"] is not None
    assert abs(body["moles_added"] - 2.0) < 0.01


def test_patch_additive_duplicate_compound_returns_409(client, db_session):
    """Changing compound_id to one already in the experiment violates unique constraint."""
    exp, cond, compound_a, additive_a = _setup_experiment_with_additive(
        db_session, "ADDTEST_007", 6007, compound_name="CompA_409"
    )
    compound_b = Compound(name="CompB_409", molecular_weight_g_mol=50.0)
    db_session.add(compound_b)
    db_session.flush()
    additive_b = ChemicalAdditive(
        experiment_id=cond.id, compound_id=compound_b.id, amount=1.0, unit="g"
    )
    db_session.add(additive_b)
    db_session.commit()
    db_session.refresh(additive_b)
    # Try to change additive_a's compound to compound_b (already in experiment)
    resp = client.patch(f"/api/additives/{additive_a.id}", json={"compound_id": compound_b.id})
    assert resp.status_code == 409


# ── DELETE /api/additives/{additive_id} ───────────────────────────────────────

def test_delete_additive_by_pk(client, db_session):
    _, _, _, additive = _setup_experiment_with_additive(db_session, "ADDTEST_008", 6008)
    additive_id = additive.id
    resp = client.delete(f"/api/additives/{additive_id}")
    assert resp.status_code == 204
    # Verify row is gone
    gone = db_session.get(ChemicalAdditive, additive_id)
    assert gone is None


def test_delete_additive_not_found_returns_404(client):
    resp = client.delete("/api/additives/99999")
    assert resp.status_code == 404


def test_delete_additive_writes_modifications_log(client, db_session):
    exp, cond, compound, additive = _setup_experiment_with_additive(db_session, "ADDTEST_009", 6009)
    additive_id = additive.id
    client.delete(f"/api/additives/{additive_id}")
    log_entry = db_session.execute(
        select(ModificationsLog).where(
            ModificationsLog.experiment_fk == exp.id,
            ModificationsLog.modified_table == "chemical_additives",
            ModificationsLog.modification_type == "delete",
        )
    ).scalar_one_or_none()
    assert log_entry is not None
    assert log_entry.old_values["compound_id"] == compound.id
    assert log_entry.new_values is None
```

- [ ] **Step 2: Run tests — expect FAIL (router not registered)**

```bash
.venv/Scripts/pytest tests/api/test_additives.py -v 2>&1 | head -20
```

Expected: `FAILED` with `404` responses (router not yet registered).

- [ ] **Step 3: Create `backend/api/routers/additives.py`**

```python
from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.models.chemicals import ChemicalAdditive, Compound
from database.models.conditions import ExperimentalConditions
from database.models.experiments import Experiment, ModificationsLog
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.chemicals import AdditiveResponse, AdditiveUpdate
from backend.services.calculations.registry import recalculate

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/additives", tags=["additives"])


@router.patch("/{additive_id}", response_model=AdditiveResponse)
def patch_additive(
    additive_id: int,
    payload: AdditiveUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> AdditiveResponse:
    """Partially update a chemical additive by its PK.

    Accepts any subset of compound_id, amount, unit, addition_order,
    addition_method, purity, lot_number. Recalculates derived fields after
    the write. Writes a ModificationsLog entry with old/new values.
    Returns 404 if the additive does not exist.
    Returns 409 if the new compound_id is already present on this experiment.
    """
    additive = db.get(ChemicalAdditive, additive_id)
    if additive is None:
        raise HTTPException(status_code=404, detail="Additive not found")

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return AdditiveResponse.model_validate(additive)

    # Validate compound exists if changing
    if "compound_id" in update_data:
        if db.get(Compound, update_data["compound_id"]) is None:
            raise HTTPException(status_code=404, detail="Compound not found")

    # Capture old values before mutating (serialize enums to their .value)
    old_vals = {}
    for k in update_data:
        val = getattr(additive, k)
        old_vals[k] = val.value if hasattr(val, "value") else val

    for k, v in update_data.items():
        setattr(additive, k, v)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Compound already added to this experiment",
        )

    recalculate(additive, db)

    # Resolve experiment FK for audit log
    conditions = db.get(ExperimentalConditions, additive.experiment_id)
    exp = db.get(Experiment, conditions.experiment_fk) if conditions else None
    if exp:
        db.add(ModificationsLog(
            experiment_id=exp.experiment_id,
            experiment_fk=exp.id,
            modified_by=current_user.email,
            modification_type="update",
            modified_table="chemical_additives",
            old_values=old_vals,
            new_values=update_data,
        ))

    db.commit()
    db.refresh(additive)
    log.info("additive_patched", additive_id=additive_id, user=current_user.email)
    return AdditiveResponse.model_validate(additive)


@router.delete("/{additive_id}", status_code=204)
def delete_additive_by_pk(
    additive_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> Response:
    """Remove a chemical additive by its PK. Writes a ModificationsLog entry."""
    additive = db.get(ChemicalAdditive, additive_id)
    if additive is None:
        raise HTTPException(status_code=404, detail="Additive not found")

    # Capture values for audit log before deletion
    conditions = db.get(ExperimentalConditions, additive.experiment_id)
    exp = db.get(Experiment, conditions.experiment_fk) if conditions else None
    compound = db.get(Compound, additive.compound_id)

    old_vals = {
        "compound_id": additive.compound_id,
        "compound_name": compound.name if compound else None,
        "amount": additive.amount,
        "unit": additive.unit.value if additive.unit else None,
    }

    db.delete(additive)

    if exp:
        db.add(ModificationsLog(
            experiment_id=exp.experiment_id,
            experiment_fk=exp.id,
            modified_by=current_user.email,
            modification_type="delete",
            modified_table="chemical_additives",
            old_values=old_vals,
            new_values=None,
        ))

    db.commit()
    log.info("additive_deleted_by_pk", additive_id=additive_id, user=current_user.email)
    return Response(status_code=204)
```

- [ ] **Step 4: Register the router in `backend/api/main.py`**

```python
# Update the import block (line 14-17):
from backend.api.routers import (
    experiments, conditions, results, samples,
    chemicals, analysis, dashboard, admin, bulk_uploads, auth, additives,
)

# Add after app.include_router(auth.router) (line ~65):
app.include_router(additives.router)
```

Also add `"additives"` to `openapi_tags` in main.py:

```python
{"name": "additives", "description": "Per-additive edit and delete by PK"},
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
.venv/Scripts/pytest tests/api/test_additives.py -v
```

Expected: all 11 tests PASSED.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/additives.py backend/api/main.py tests/api/test_additives.py
git commit -m "[#22] add PATCH and DELETE additive-by-pk endpoints"
```

---

## Task 4: ModificationsLog in existing additive upsert + delete endpoints

The existing `PUT /api/experiments/{id}/additives/{compound_id}` and
`DELETE /api/experiments/{id}/additives/{compound_id}` in `experiments.py` currently
write no audit trail. This task adds ModificationsLog to both so that all additive
mutations are tracked consistently.

**Files:**
- Modify: `backend/api/routers/experiments.py`

- [ ] **Step 1: Update `upsert_experiment_additive` to write ModificationsLog**

In `backend/api/routers/experiments.py`, replace the `upsert_experiment_additive` function (lines ~253–295) with:

```python
@router.put("/{experiment_id}/additives/{compound_id}", response_model=AdditiveResponse)
def upsert_experiment_additive(
    experiment_id: str,
    compound_id: int,
    payload: ChemicalAdditiveUpsert,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> AdditiveResponse:
    """Upsert a chemical additive for an experiment — create if new, update if exists.

    Accepts experiment string ID and resolves conditions row internally.
    ChemicalAdditive.experiment_id is a FK to experimental_conditions.id (not experiments.id).
    Writes a ModificationsLog entry for create or update.
    """
    conditions = db.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if conditions is None:
        raise HTTPException(status_code=404, detail="Experiment conditions not found")
    compound = db.get(Compound, compound_id)
    if compound is None:
        raise HTTPException(status_code=404, detail="Compound not found")
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()

    existing = db.execute(
        select(ChemicalAdditive)
        .where(ChemicalAdditive.experiment_id == conditions.id)
        .where(ChemicalAdditive.compound_id == compound_id)
    ).scalar_one_or_none()

    if existing:
        old_vals = {
            "amount": existing.amount,
            "unit": existing.unit.value if existing.unit else None,
        }
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(existing, k, v)
        additive = existing
        mod_type = "update"
    else:
        old_vals = None
        additive = ChemicalAdditive(
            experiment_id=conditions.id,
            compound_id=compound_id,
            **payload.model_dump(),
        )
        db.add(additive)
        mod_type = "create"

    db.flush()
    recalculate(additive, db)

    if exp:
        new_vals = {"amount": additive.amount, "unit": additive.unit.value if additive.unit else None}
        db.add(ModificationsLog(
            experiment_id=experiment_id,
            experiment_fk=exp.id,
            modified_by=current_user.email,
            modification_type=mod_type,
            modified_table="chemical_additives",
            old_values=old_vals,
            new_values=new_vals,
        ))

    db.commit()
    db.refresh(additive)
    log.info("additive_upserted", experiment_id=experiment_id, compound_id=compound_id)
    return AdditiveResponse.model_validate(additive)
```

- [ ] **Step 2: Update `delete_experiment_additive` to write ModificationsLog**

Replace the `delete_experiment_additive` function (lines ~298–321) with:

```python
@router.delete("/{experiment_id}/additives/{compound_id}", status_code=204)
def delete_experiment_additive(
    experiment_id: str,
    compound_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> Response:
    """Remove a chemical additive from an experiment. Writes a ModificationsLog entry."""
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

    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    compound = db.get(Compound, compound_id)

    old_vals = {
        "compound_id": compound_id,
        "compound_name": compound.name if compound else None,
        "amount": additive.amount,
        "unit": additive.unit.value if additive.unit else None,
    }

    db.delete(additive)

    if exp:
        db.add(ModificationsLog(
            experiment_id=experiment_id,
            experiment_fk=exp.id,
            modified_by=current_user.email,
            modification_type="delete",
            modified_table="chemical_additives",
            old_values=old_vals,
            new_values=None,
        ))

    db.commit()
    log.info("additive_deleted", experiment_id=experiment_id, compound_id=compound_id)
    return Response(status_code=204)
```

- [ ] **Step 3: Run all existing additive tests to confirm no regressions**

```bash
.venv/Scripts/pytest tests/api/test_experiments.py tests/api/test_additives.py tests/api/test_notes.py -v
```

Expected: all tests PASSED.

- [ ] **Step 4: Commit**

```bash
git add backend/api/routers/experiments.py
git commit -m "[#22] add ModificationsLog to existing additive upsert/delete"
```

---

## Task 5: Frontend API client additions

**Files:**
- Modify: `frontend/src/api/experiments.ts`
- Modify: `frontend/src/api/chemicals.ts`

- [ ] **Step 1: Add `patchNote` to experiments.ts**

Open `frontend/src/api/experiments.ts`. In the `Note` interface (or wherever `NoteResponse` is used), ensure `updated_at` is included. Then add `patchNote` to the `experimentsApi` object:

```typescript
// Add to the Note interface / wherever notes are typed:
interface Note {
  id: number
  experiment_id: string
  note_text: string
  created_at: string
  updated_at: string | null
}

// Add to the experimentsApi object:
patchNote: (experimentId: string, noteId: number, text: string): Promise<Note> =>
  apiClient.patch(`/api/experiments/${experimentId}/notes/${noteId}`, { note_text: text }),
```

- [ ] **Step 2: Add `patchAdditive` and `deleteAdditiveById` to chemicals.ts**

Open `frontend/src/api/chemicals.ts`. Add to the `chemicalsApi` object:

```typescript
// Payload type — add near other interfaces at top of file:
interface AdditiveUpdatePayload {
  compound_id?: number
  amount?: number
  unit?: string
  addition_order?: number
  addition_method?: string
}

// Add to chemicalsApi:
patchAdditive: (additiveId: number, payload: AdditiveUpdatePayload): Promise<ChemicalAdditive> =>
  apiClient.patch(`/api/additives/${additiveId}`, payload),

deleteAdditiveById: (additiveId: number): Promise<void> =>
  apiClient.delete(`/api/additives/${additiveId}`),
```

- [ ] **Step 3: Lint check**

```bash
cd frontend
npx eslint src/api/experiments.ts src/api/chemicals.ts --ext .ts
```

Expected: 0 errors, 0 warnings.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/experiments.ts frontend/src/api/chemicals.ts
git commit -m "[#22] add patchNote, patchAdditive, deleteAdditiveById API clients"
```

---

## Task 6: Frontend — NotesTab inline edit

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/NotesTab.tsx`

Each note gets an edit-pencil icon (visible on hover). Clicking it replaces the note text with an inline `<textarea>` + Save/Cancel buttons. Saving calls `patchNote`. An "(edited)" label appears when `updated_at` differs from `created_at`.

- [ ] **Step 1: Replace `NotesTab.tsx` with the inline-edit version**

```typescript
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { Button, useToast } from '@/components/ui'

interface Note {
  id: number
  note_text: string
  created_at: string
  updated_at: string | null
}
interface Props { experimentId: string; notes: Note[] }

/** Notes tab: chronological lab notes with inline add and inline edit. */
export function NotesTab({ experimentId, notes }: Props) {
  const [text, setText] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editText, setEditText] = useState('')
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

  const editNote = useMutation({
    mutationFn: ({ noteId, newText }: { noteId: number; newText: string }) =>
      experimentsApi.patchNote(experimentId, noteId, newText),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] })
      success('Note updated')
      setEditingId(null)
      setEditText('')
    },
    onError: (err: Error) => toastError('Failed to update note', err.message),
  })

  const startEdit = (note: Note) => {
    setEditingId(note.id)
    setEditText(note.note_text ?? '')
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditText('')
  }

  const isEdited = (note: Note) =>
    note.updated_at != null && note.updated_at !== note.created_at

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
          <div
            key={n.id}
            className={`text-xs border-b border-surface-border pb-3 group ${i === notes.length - 1 ? 'border-b-0' : ''}`}
          >
            <div className="flex items-start justify-between gap-2 mb-0.5">
              <div className="flex items-center gap-1.5 flex-wrap">
                {i === notes.length - 1 && (
                  <span className="inline-block text-[10px] font-semibold uppercase tracking-wider text-brand-red bg-brand-red/10 px-1.5 py-0.5 rounded">
                    Condition Note
                  </span>
                )}
                {isEdited(n) && (
                  <span className="text-[10px] text-ink-muted italic">(edited)</span>
                )}
              </div>
              {editingId !== n.id && (
                <button
                  type="button"
                  className="opacity-0 group-hover:opacity-100 transition-opacity text-ink-muted hover:text-ink-primary p-0.5"
                  onClick={() => startEdit(n)}
                  title="Edit note"
                >
                  {/* Pencil icon (inline SVG to avoid icon library dependency) */}
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round"
                      d="M11.5 2.5a1.414 1.414 0 012 2L5 13H3v-2L11.5 2.5z" />
                  </svg>
                </button>
              )}
            </div>

            {editingId === n.id ? (
              <div className="space-y-1.5 mt-1">
                <textarea
                  className="w-full bg-surface-input border border-surface-border rounded px-2 py-1.5 text-sm text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50 resize-none"
                  rows={3}
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  autoFocus
                />
                <div className="flex gap-2">
                  <Button
                    variant="primary"
                    size="xs"
                    disabled={!editText.trim()}
                    loading={editNote.isPending}
                    onClick={() => editNote.mutate({ noteId: n.id, newText: editText })}
                  >
                    Save
                  </Button>
                  <Button variant="ghost" size="xs" onClick={cancelEdit}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <p className="text-ink-secondary leading-relaxed">{n.note_text}</p>
                <p className="text-ink-muted mt-0.5 font-mono-data">
                  {new Date(n.created_at).toLocaleString()}
                </p>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Lint check**

```bash
npx eslint src/pages/ExperimentDetail/NotesTab.tsx --ext .tsx
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/NotesTab.tsx
git commit -m "[#22] add inline note edit to NotesTab"
```

---

## Task 7: Frontend — ConditionsTab additive edit row

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx`

Each additive row gets an edit-pencil icon alongside the existing × delete button (both visible on hover). The pencil opens a modal pre-populated with the current compound, amount, and unit. Saving calls `patchAdditive(additive.id, {...})`. The delete button is updated to call `deleteAdditiveById(additive.id)` instead of by compound_id.

- [ ] **Step 1: Add edit state + mutations to ConditionsTab.tsx**

Add the following state declarations inside `ConditionsTab` (after the existing `deleteAdditiveMutation`):

```typescript
// Import patchAdditive and deleteAdditiveById — update the chemicals import line:
import { chemicalsApi, type Compound, type ChemicalAdditive } from '@/api/chemicals'

// Add state for edit modal (alongside existing additive state):
const [editAdditiveOpen, setEditAdditiveOpen] = useState(false)
const [editingAdditive, setEditingAdditive] = useState<ChemicalAdditive | null>(null)
const [editCompound, setEditCompound] = useState<{ id: number; name: string } | null>(null)
const [editAmount, setEditAmount] = useState('')
const [editUnit, setEditUnit] = useState('g')
const [editCompoundQuery, setEditCompoundQuery] = useState('')
const [editCompoundDropdownOpen, setEditCompoundDropdownOpen] = useState(false)

// Add compound search query for edit modal:
const { data: editCompoundResults = [] } = useQuery({
  queryKey: ['compounds', editCompoundQuery],
  queryFn: () => chemicalsApi.listCompounds({ search: editCompoundQuery, limit: 10 }),
  enabled: editCompoundQuery.length >= 1 && editCompoundDropdownOpen,
})

// Edit mutation:
const patchAdditiveMutation = useMutation({
  mutationFn: () => {
    if (!editingAdditive) throw new Error('No additive selected')
    return chemicalsApi.patchAdditive(editingAdditive.id, {
      compound_id: editCompound?.id,
      amount: parseFloat(editAmount),
      unit: editUnit,
    })
  },
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['additives', experimentId] })
    success('Additive updated')
    closeEditModal()
  },
  onError: (err: Error) => toastError('Failed to update additive', err.message),
})
```

- [ ] **Step 2: Add `openEditModal` and `closeEditModal` helpers**

```typescript
const openEditModal = (a: ChemicalAdditive) => {
  setEditingAdditive(a)
  setEditCompound(a.compound ? { id: a.compound.id, name: a.compound.name } : null)
  setEditCompoundQuery(a.compound?.name ?? '')
  setEditAmount(String(a.amount))
  setEditUnit(a.unit)
  setEditAdditiveOpen(true)
}

const closeEditModal = () => {
  setEditAdditiveOpen(false)
  setEditingAdditive(null)
  setEditCompound(null)
  setEditCompoundQuery('')
  setEditAmount('')
  setEditUnit('g')
}
```

- [ ] **Step 3: Update the additive row to show pencil + swap delete to by-PK**

In the additive rows render (the `additives.map(...)` block), replace:

```typescript
// OLD delete button:
<button
  onClick={() => deleteAdditiveMutation.mutate(a.compound_id)}
  ...
>
  ×
</button>
```

with:

```typescript
{/* Edit pencil */}
<button
  onClick={() => openEditModal(a)}
  className="ml-auto text-xs text-ink-muted hover:text-ink-primary opacity-0 group-hover:opacity-100 transition-opacity px-1"
  type="button"
  title="Edit additive"
>
  <svg className="w-3 h-3 inline" fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round"
      d="M11.5 2.5a1.414 1.414 0 012 2L5 13H3v-2L11.5 2.5z" />
  </svg>
</button>
{/* Delete × */}
<button
  onClick={() => deleteAdditiveMutation.mutate(a.id)}
  className="text-xs text-ink-muted hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity px-1"
  type="button"
  title="Remove additive"
>
  ×
</button>
```

Also update `deleteAdditiveMutation` to call `deleteAdditiveById` by additive PK:

```typescript
const deleteAdditiveMutation = useMutation({
  mutationFn: (additiveId: number) => chemicalsApi.deleteAdditiveById(additiveId),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['additives', experimentId] })
    success('Additive removed')
  },
  onError: (err: Error) => toastError('Failed to remove additive', err.message),
})
```

- [ ] **Step 4: Add the Edit Additive Modal JSX**

Add inside the return JSX, after the existing `{/* Add Additive Modal */}` block:

```typescript
{/* Edit Additive Modal */}
<Modal open={editAdditiveOpen} onClose={closeEditModal} title="Edit Chemical Additive">
  <div className="space-y-3 p-4">
    {/* Compound typeahead */}
    <div className="relative">
      <label className="block text-xs font-medium text-ink-secondary mb-1">Compound</label>
      {editCompound ? (
        <div className="flex items-center gap-2">
          <span className="text-sm text-ink-primary font-medium">{editCompound.name}</span>
          <button
            type="button"
            className="text-xs text-ink-muted hover:text-ink-primary"
            onClick={() => { setEditCompound(null); setEditCompoundQuery('') }}
          >
            Change
          </button>
        </div>
      ) : (
        <>
          <input
            className="w-full bg-surface-input border border-surface-border rounded px-2 py-1.5 text-sm text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50"
            placeholder="Search compounds…"
            value={editCompoundQuery}
            onChange={(e) => { setEditCompoundQuery(e.target.value); setEditCompoundDropdownOpen(true) }}
            onFocus={() => setEditCompoundDropdownOpen(true)}
            onBlur={() => setTimeout(() => setEditCompoundDropdownOpen(false), 150)}
            autoComplete="off"
          />
          {editCompoundDropdownOpen && editCompoundQuery.length >= 1 && (
            <div className="absolute z-10 left-0 right-0 top-full mt-0.5 bg-surface-raised border border-surface-border rounded shadow-lg max-h-48 overflow-y-auto">
              {editCompoundResults.map((c: Compound) => (
                <button
                  key={c.id}
                  type="button"
                  className="w-full text-left px-3 py-1.5 text-sm text-ink-primary hover:bg-surface-border/30"
                  onMouseDown={() => {
                    setEditCompound({ id: c.id, name: c.name })
                    setEditCompoundQuery(c.name)
                    setEditCompoundDropdownOpen(false)
                  }}
                >
                  {c.name}{c.formula ? ` (${c.formula})` : ''}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>

    <div className="grid grid-cols-2 gap-3">
      <Input
        label="Amount"
        type="number"
        value={editAmount}
        onChange={(e) => setEditAmount(e.target.value)}
      />
      <Select
        label="Unit"
        options={ADDITIVE_UNIT_OPTIONS}
        placeholder="Unit…"
        value={editUnit}
        onChange={(e) => setEditUnit(e.target.value)}
      />
    </div>

    <div className="flex gap-2 justify-end pt-2">
      <Button variant="ghost" onClick={closeEditModal}>Cancel</Button>
      <Button
        variant="primary"
        loading={patchAdditiveMutation.isPending}
        disabled={!editCompound || !editAmount || !editUnit}
        onClick={() => patchAdditiveMutation.mutate()}
      >
        Save
      </Button>
    </div>
  </div>
</Modal>
```

- [ ] **Step 5: Lint check**

```bash
npx eslint src/pages/ExperimentDetail/ConditionsTab.tsx --ext .tsx
```

Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/ConditionsTab.tsx
git commit -m "[#22] add inline additive edit to ConditionsTab"
```

---

## Task 8: Update docs/api/API_REFERENCE.md

**Files:**
- Modify: `docs/api/API_REFERENCE.md`

- [ ] **Step 1: Add new endpoints to the reference**

In the Experiments table, add the PATCH note row:

```markdown
| PATCH | `/api/experiments/{experiment_id}/notes/{note_id}` | Edit note text. Body: `{"note_text": "..."}`. Writes ModificationsLog. No-op if text is unchanged. |
```

Add a new Additives section:

```markdown
## Additives

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/experiments/{experiment_id}/additives` | List chemical additives for an experiment |
| PUT | `/api/experiments/{experiment_id}/additives/{compound_id}` | Upsert additive by compound PK. Body: `AdditiveUpsert`. Triggers recalculation. Writes ModificationsLog. |
| DELETE | `/api/experiments/{experiment_id}/additives/{compound_id}` | Remove additive by compound PK. Writes ModificationsLog. |
| PATCH | `/api/additives/{additive_id}` | Partial update by additive PK. Accepts compound_id, amount, unit, addition_order, addition_method. Triggers recalculation. Writes ModificationsLog. Returns 409 if new compound_id is already in the experiment. |
| DELETE | `/api/additives/{additive_id}` | Remove additive by additive PK. Writes ModificationsLog. |
```

- [ ] **Step 2: Commit**

```bash
git add docs/api/API_REFERENCE.md
git commit -m "[#22] update API_REFERENCE with new note + additive endpoints"
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Task |
|-------------|------|
| Add, edit, remove additives from Conditions tab | Tasks 3, 4, 7 |
| After additive change, derived fields reflect updated values | Tasks 3 + 4 (recalculate) |
| Edit text of any note (including condition note) | Task 2 |
| Every additive mutation writes ModificationsLog | Tasks 3, 4 |
| Every note edit writes ModificationsLog | Task 2 |
| v_experiments.description reflects corrected condition note | No schema change needed — view reads DB directly |
| All new endpoints covered by automated tests | Tasks 2, 3 |
| No regressions on PATCH conditions or New Experiment form | Existing tests unchanged; additive upsert PUT still works |

**Placeholder scan:** None found — every step has exact code or exact commands.

**Type consistency check:**
- `AdditiveUpdate` defined in Task 1, used in Task 3 endpoint and Task 5 API client. ✓
- `NoteUpdate` defined in Task 1, used in Task 2 endpoint. ✓
- `NoteResponse.updated_at` added in Task 1, returned in Task 2, displayed in Task 6. ✓
- `deleteAdditiveMutation.mutate(a.id)` in Task 7 calls `deleteAdditiveById(additiveId: number)` added in Task 5. ✓
- `patchAdditiveMutation` calls `patchAdditive(editingAdditive.id, ...)` using `id: number` from `AdditiveResponse`. ✓
- `editNote.mutate({ noteId, newText })` calls `patchNote(experimentId, noteId, text)` added in Task 5. ✓
