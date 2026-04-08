"""Sync orchestrator — runs full import + export cycle.

Also provides make_scheduler() to configure APScheduler for the daily job.
"""
from __future__ import annotations

import structlog
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from sqlalchemy.orm import Session

from .client import NotionSyncClient
from .import_ import run_import
from .export import run_export

log = structlog.get_logger(__name__)


@dataclass
class SyncResult:
    imported: int = 0
    exported: int = 0
    carried_forward: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "imported": self.imported,
            "exported": self.exported,
            "carried_forward": self.carried_forward,
            "errors": self.errors,
        }


def run_sync(
    client: NotionSyncClient,
    db: Session,
    sync_date: date | None = None,
) -> SyncResult:
    """Run one full sync cycle: import then export.

    Args:
        client: Notion client wrapper.
        db: SQLAlchemy session. Import step commits; export step is read-only.
        sync_date: Date for this sync cycle. Defaults to today.
    """
    try:
        pages = client.query_all_rows()
    except Exception as exc:
        log.error("notion_sync_query_failed", error=str(exc))
        return SyncResult(errors=[f"Notion API error: {exc}"])

    effective_sync_date = sync_date or date.today()
    import_result = run_import(client, db, pages, effective_sync_date)
    export_result = run_export(client, db, pages, import_result.cleared_page_ids)

    # Stamp sync metadata on all pages: Last Synced (heartbeat) on every page,
    # Working Date on pages with active change requests (cleared on others).
    last_synced_iso = datetime.now(timezone.utc).isoformat()
    working_date_iso = effective_sync_date.isoformat()
    metadata_errors: list[str] = []
    for page in pages:
        page_id = page["id"]
        has_active_cr = page_id in import_result.active_cr_page_ids
        try:
            client.stamp_sync_metadata(
                page_id=page_id,
                last_synced_iso=last_synced_iso,
                working_date_iso=working_date_iso if has_active_cr else None,
            )
        except Exception as exc:
            metadata_errors.append(f"sync metadata stamp failed for {page_id}: {exc}")
            log.warning("notion_stamp_metadata_error", page_id=page_id, error=str(exc))

    result = SyncResult(
        imported=import_result.imported,
        exported=export_result.exported,
        carried_forward=import_result.carried_forward,
        errors=import_result.errors + export_result.errors + metadata_errors,
    )
    log.info(
        "notion_sync_complete",
        imported=result.imported,
        exported=result.exported,
        carried_forward=result.carried_forward,
        errors=result.errors,
    )
    return result


def make_scheduler(notion_sync_hour: int) -> AsyncIOScheduler:
    """Build an AsyncIOScheduler with the daily notion sync job.

    The scheduler is returned un-started; call scheduler.start() in the
    FastAPI lifespan and scheduler.shutdown() on teardown.
    """
    tz = pytz.timezone("America/New_York")
    scheduler = AsyncIOScheduler()

    def _job() -> None:
        """APScheduler entry point — creates its own DB session."""
        from database.database import SessionLocal
        from backend.config.settings import get_settings

        settings = get_settings()
        notion_client = NotionSyncClient(
            token=settings.notion_token,
            database_id=settings.notion_database_id,
        )
        db = SessionLocal()
        try:
            run_sync(notion_client, db)
        except Exception as exc:
            log.error("notion_sync_job_unhandled_error", error=str(exc))
        finally:
            db.close()

    scheduler.add_job(
        _job,
        CronTrigger(hour=notion_sync_hour, timezone=tz),
        id="notion_sync",
        replace_existing=True,
        misfire_grace_time=300,
    )
    return scheduler
