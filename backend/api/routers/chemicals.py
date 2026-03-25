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
