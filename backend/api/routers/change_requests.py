from __future__ import annotations

from datetime import date

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.notion_sync import ChangeRequestResponse, RecentChangeRequestsResponse
from database.models.notion_sync import ReactorChangeRequest

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/change-requests", tags=["change-requests"])


@router.get("/reactor/{reactor_label}/recent", response_model=RecentChangeRequestsResponse)
def get_recent_for_reactor(
    reactor_label: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> RecentChangeRequestsResponse:
    """Return today's and the most recent prior-day change request for a reactor.

    Both fields are nullable — returns nulls if no records exist for that label.
    Does not 404 on unknown reactor_label; absence is represented by null.
    """
    today = date.today()

    today_row = db.execute(
        select(ReactorChangeRequest).where(
            ReactorChangeRequest.reactor_label == reactor_label,
            ReactorChangeRequest.sync_date == today,
        )
    ).scalar_one_or_none()

    previous_row = db.execute(
        select(ReactorChangeRequest)
        .where(
            ReactorChangeRequest.reactor_label == reactor_label,
            ReactorChangeRequest.sync_date < today,
        )
        .order_by(ReactorChangeRequest.sync_date.desc())
        .limit(1)
    ).scalar_one_or_none()

    return RecentChangeRequestsResponse(
        today=ChangeRequestResponse.model_validate(today_row) if today_row else None,
        previous=ChangeRequestResponse.model_validate(previous_row) if previous_row else None,
    )
