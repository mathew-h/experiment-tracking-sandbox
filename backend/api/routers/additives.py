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
import backend.services.calculations  # noqa: F401 — registers @register decorators
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

    # Serialize enums in new_values so they are JSON-storable
    new_vals = {
        k: (v.value if hasattr(v, "value") else v)
        for k, v in update_data.items()
    }

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
            new_values=new_vals,
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
