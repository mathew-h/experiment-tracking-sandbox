"""Admin endpoints for on-demand Notion sync."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import FirebaseUser, verify_firebase_token
from backend.config.settings import get_settings
from backend.services.notion_sync.client import NotionSyncClient
from backend.services.notion_sync.sync import run_sync

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/admin/notion-sync", tags=["admin"])


@router.post("/trigger")
def trigger_notion_sync(
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> dict:
    """Run a full Notion sync cycle on demand.

    Returns a summary dict with imported, exported, carried_forward, and errors counts.
    Sync errors are returned in the payload rather than raising HTTP 500 so callers
    can inspect partial results.
    """
    settings = get_settings()
    if not settings.notion_token:
        raise HTTPException(status_code=503, detail="NOTION_TOKEN not configured")

    notion_client = NotionSyncClient(
        token=settings.notion_token,
        database_id=settings.notion_database_id,
    )
    result = run_sync(notion_client, db)
    log.info(
        "notion_sync_triggered",
        user=current_user.email,
        **result.to_dict(),
    )
    return result.to_dict()
