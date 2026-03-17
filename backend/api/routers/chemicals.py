from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from database.models.chemicals import Compound, ChemicalAdditive
from database.models.conditions import ExperimentalConditions
import backend.services.calculations  # noqa: F401 — registers @register decorators
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
