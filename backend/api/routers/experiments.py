from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from database.models.experiments import Experiment, ExperimentNotes
from database.models.enums import ExperimentStatus
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.experiments import (
    ExperimentCreate, ExperimentUpdate, ExperimentListItem, ExperimentListResponse,
    ExperimentResponse, ExperimentStatusUpdate, NextIdResponse,
    NoteCreate, NoteResponse,
)

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/experiments", tags=["experiments"])

# Prefix mapping for next-id endpoint
_TYPE_PREFIX: dict[str, str] = {
    "HPHT": "HPHT",
    "Serum": "SERUM",
    "Autoclave": "AUTOCLAVE",
    "Core Flood": "CF",
}


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
    """List experiments with optional filters, joins for conditions/additives, and pagination."""
    from database.models.conditions import ExperimentalConditions

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
        # Join conditions for experiment_type and reactor_number
        cond = db.execute(
            select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
        ).scalar_one_or_none()
        item_data["experiment_type"] = cond.experiment_type if cond else None
        item_data["reactor_number"] = cond.reactor_number if cond else None
        # In-memory filter for type/reactor (acceptable for < 500 experiments)
        # TODO: replace with proper JOIN query when lab data grows
        if experiment_type and item_data["experiment_type"] != experiment_type:
            total -= 1
            continue
        if reactor_number is not None and item_data["reactor_number"] != reactor_number:
            total -= 1
            continue
        # Additives summary — inline query avoids view dependency
        additive_row = db.execute(
            text("""
                SELECT string_agg(c.name || ' ' || CAST(a.amount AS TEXT) || ' ' || a.unit, '; ')
                FROM chemical_additives a
                JOIN experimental_conditions ec ON ec.id = a.experiment_id
                JOIN compounds c ON c.id = a.compound_id
                WHERE ec.experiment_fk = :exp_fk
            """),
            {"exp_fk": exp.id},
        ).fetchone()
        item_data["additives_summary"] = additive_row[0] if additive_row else None
        # First note as condition note
        first_note = db.execute(
            select(ExperimentNotes)
            .where(ExperimentNotes.experiment_fk == exp.id)
            .order_by(ExperimentNotes.id.asc())
            .limit(1)
        ).scalar_one_or_none()
        item_data["condition_note"] = first_note.note_text if first_note else None
        items.append(ExperimentListItem.model_validate(item_data))

    return ExperimentListResponse(items=items, total=total, skip=skip, limit=limit)


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


@router.get("/{experiment_id}/results")
def get_experiment_results(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
):
    """Placeholder — implemented in B4."""
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.patch("/{experiment_id}/status", response_model=ExperimentResponse)
def update_experiment_status(
    experiment_id: str,
    payload: ExperimentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentResponse:
    """Inline status update without full patch."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    exp.status = payload.status
    db.commit()
    db.refresh(exp)
    return ExperimentResponse.model_validate(exp)


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


@router.post("", response_model=ExperimentResponse, status_code=201)
def create_experiment(
    payload: ExperimentCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentResponse:
    """Create a new experiment."""
    data = payload.model_dump()
    if data.get("experiment_number") is None:
        max_num = db.execute(select(func.max(Experiment.experiment_number))).scalar() or 0
        data["experiment_number"] = max_num + 1
    exp = Experiment(**data)
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
