from __future__ import annotations
from typing import Literal, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.api.dependencies.db import get_db
from backend.api.schemas.core_floods import CoreFloodRun, CoreFloodRunListItem
from backend.auth.firebase_auth import FirebaseUser, verify_firebase_token
from backend.services import core_flood_service as svc

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/core-floods", tags=["core-floods"])


@router.get("", response_model=list[CoreFloodRunListItem])
def list_core_flood_runs(
    scope: Literal["active", "all"] = "active",
    q: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[CoreFloodRunListItem]:
    """Core flood runs, active (any ONGOING segment) first."""
    return svc.list_runs(db, scope=scope, q=q)


@router.get("/{base_id}", response_model=CoreFloodRun)
def get_core_flood_run(
    base_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> CoreFloodRun:
    """One run: segments, view-derived samples and data-quality warnings."""
    try:
        return svc.get_run(db, base_id)
    except svc.CoreFloodNotFound:
        raise HTTPException(status_code=404, detail="Core flood run not found")
