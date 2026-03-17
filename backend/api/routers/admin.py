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
