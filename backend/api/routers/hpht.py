"""HPHT run endpoints (issue #149), read-only.

Sample writes go through POST/PATCH /api/experiments/{experiment_id}/results (#146).
"""
from __future__ import annotations

from typing import Callable, Literal, Optional, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.api.dependencies.db import get_db
from backend.api.schemas.hpht import HphtRun, HphtRunListItem
from backend.api.schemas.results import IcpRow
from backend.auth.firebase_auth import FirebaseUser, verify_firebase_token
from backend.services import hpht_service as svc

router = APIRouter(prefix="/api/hpht", tags=["hpht"])

T = TypeVar("T")


def _translate(fn: Callable[[], T]) -> T:
    """Run fn, mapping HphtRunNotFound to 404."""
    try:
        return fn()
    except svc.HphtRunNotFound as exc:
        raise HTTPException(status_code=404, detail=f"No HPHT run with base ID {exc}")


@router.get("", response_model=list[HphtRunListItem])
def list_hpht_runs(
    scope: Literal["active", "all"] = "active",
    q: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[HphtRunListItem]:
    """HPHT runs, active (any ONGOING segment) first. `q` matches the base ID,
    any segment ID or the run description (case-insensitive)."""
    return svc.list_runs(db, scope=scope, q=q)


@router.get("/{base_id}/icp", response_model=list[IcpRow])
def get_hpht_run_icp(
    base_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[IcpRow]:
    """ICP-OES readings (ppm) for the run's samples, in view order."""
    return _translate(lambda: svc.get_run_icp(db, base_id))


@router.get("/{base_id}", response_model=HphtRun)
def get_hpht_run(
    base_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> HphtRun:
    """One run: segments, latest setup, view-derived samples with notes, warnings."""
    return _translate(lambda: svc.get_run(db, base_id))
