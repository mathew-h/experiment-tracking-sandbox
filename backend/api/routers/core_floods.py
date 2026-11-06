from __future__ import annotations
from typing import Callable, Literal, Optional, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.api.dependencies.db import get_db
from backend.api.schemas.core_floods import (
    CoreFloodRun, CoreFloodRunListItem, CoreFloodSample, CoreFloodSampleCreate,
    CoreFloodSampleUpdate,
)
from backend.auth.firebase_auth import FirebaseUser, verify_firebase_token
from backend.services import core_flood_service as svc

router = APIRouter(prefix="/api/core-floods", tags=["core-floods"])

T = TypeVar("T")


def _translate(fn: Callable[[], T]) -> T:
    """Run fn, mapping the CoreFloodError hierarchy to HTTP statuses."""
    try:
        return fn()
    except svc.CoreFloodError as exc:
        code = 404 if isinstance(exc, svc.CoreFloodNotFound) else 422
        raise HTTPException(status_code=code, detail=str(exc))


@router.get("", response_model=list[CoreFloodRunListItem])
def list_core_flood_runs(
    scope: Literal["active", "all"] = "active",
    q: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[CoreFloodRunListItem]:
    """Core flood runs, active (any ONGOING segment) first."""
    return _translate(lambda: svc.list_runs(db, scope=scope, q=q))


@router.patch("/samples/{result_id}", response_model=CoreFloodSample)
def update_core_flood_sample(
    result_id: int,
    payload: CoreFloodSampleUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> CoreFloodSample:
    """Edit one sample; only changed fields are written and audited."""
    # update_sample rejects missing and non-primary results before it writes anything.
    _translate(lambda: svc.update_sample(db, result_id, payload, current_user.email))
    db.commit()
    rows = svc.fetch_samples(db, result_id=result_id)
    # Effectively unreachable: update_sample already rejected non-primary and
    # non-Core-Flood results. This guards against v_core_flood_samples and the
    # Python Core Flood rule (is_core_flood) diverging.
    if not rows:
        raise HTTPException(status_code=404, detail="Sample is not a primary timepoint")
    return CoreFloodSample(**svc.attach_notes(db, rows)[0])


@router.get("/{base_id}", response_model=CoreFloodRun)
def get_core_flood_run(
    base_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> CoreFloodRun:
    """One run: segments, view-derived samples and data-quality warnings."""
    return _translate(lambda: svc.get_run(db, base_id))


@router.post(
    "/{experiment_id}/samples",
    response_model=CoreFloodSample,
    status_code=status.HTTP_201_CREATED,
)
def create_core_flood_sample(
    experiment_id: str,
    payload: CoreFloodSampleCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> CoreFloodSample:
    """Add one sample (result + scalar rows) to a Core Flood experiment."""
    # create_sample validates before it writes, so a rejection leaves nothing to undo.
    rid = _translate(
        lambda: svc.create_sample(db, experiment_id, payload, current_user.email))
    db.commit()
    rows = svc.attach_notes(db, svc.fetch_samples(db, result_id=rid))
    return CoreFloodSample(**rows[0])
