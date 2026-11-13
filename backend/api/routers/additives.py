from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.models.chemicals import ChemicalAdditive, Compound
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.chemicals import AdditiveResponse, AdditiveUpdate
from backend.services import additive_service

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

    try:
        additive_service.patch_additive(db, additive, update_data, current_user.email)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Compound already added to this experiment",
        )

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

    additive_service.delete_additive(
        db, additive, additive_service.owning_experiment(db, additive), current_user.email)
    db.commit()
    log.info("additive_deleted_by_pk", additive_id=additive_id, user=current_user.email)
    return Response(status_code=204)
