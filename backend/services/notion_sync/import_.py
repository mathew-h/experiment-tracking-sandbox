"""Import step — read Change Requests from Notion, upsert to DB, then clear Notion.

The Notion clear is deliberately called AFTER db.commit() so that a DB failure
never causes Notion data to be lost without a DB record.
"""
from __future__ import annotations

import structlog
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus
from database.models.experiments import Experiment
from database.models.notion_sync import ReactorChangeRequest
from .client import (
    NotionSyncClient,
    extract_change_request,
    extract_change_status,
    extract_reactor_label,
    STATUS_IN_PROGRESS,
    STATUS_COMPLETED,
    STATUS_PENDING,
)

log = structlog.get_logger(__name__)


@dataclass
class ImportResult:
    imported: int = 0
    skipped: int = 0
    carried_forward: int = 0
    errors: list[str] = field(default_factory=list)
    cleared_page_ids: set[str] = field(default_factory=set)
    active_cr_page_ids: set[str] = field(default_factory=set)


def _resolve_experiment_id(db: Session, reactor_label: str) -> str | None:
    """Find the ONGOING experiment occupying a reactor slot, if any."""
    label_upper = reactor_label.upper()
    try:
        if label_upper.startswith("CF"):
            reactor_number = int(label_upper[2:])
            type_filter = ExperimentalConditions.experiment_type == "Core Flood"
        elif label_upper.startswith("R"):
            reactor_number = int(label_upper[1:])
            type_filter = ExperimentalConditions.experiment_type != "Core Flood"
        else:
            return None
    except ValueError:
        return None

    row = db.execute(
        select(Experiment.experiment_id)
        .join(ExperimentalConditions, ExperimentalConditions.experiment_fk == Experiment.id)
        .where(
            Experiment.status == ExperimentStatus.ONGOING,
            ExperimentalConditions.reactor_number == reactor_number,
            type_filter,
        )
        .limit(1)
    ).scalar_one_or_none()
    return row


def run_import(
    client: NotionSyncClient,
    db: Session,
    pages: list[dict],
    sync_date: date,
) -> ImportResult:
    """Import change requests from Notion pages into the DB for sync_date.

    For each page:
    - Empty Change Request → skip
    - In Progress → upsert DB with carried_forward=True; do NOT clear Notion
    - Completed / Pending with content → upsert DB; THEN clear Notion after commit
    - Unknown status → log warning and skip

    Returns ImportResult with counts and the set of page IDs that were cleared.
    """
    result = ImportResult()
    pages_to_clear: list[str] = []  # collected before commit; cleared after

    for page in pages:
        page_id_raw: str = page["id"]
        reactor_label: str = extract_reactor_label(page)
        change_request: str = extract_change_request(page)
        status: str = extract_change_status(page)

        if not change_request:
            result.skipped += 1
            continue

        # Unknown/legacy statuses (e.g. removed "Carried Forward") are skipped
        known_statuses = (STATUS_IN_PROGRESS, STATUS_COMPLETED, STATUS_PENDING)
        if status not in known_statuses:
            log.warning("notion_import_unknown_status", reactor=reactor_label, status=status)
            result.skipped += 1
            continue

        carried_forward = status == STATUS_IN_PROGRESS
        should_clear = status != STATUS_IN_PROGRESS

        try:
            resolved_exp_id = _resolve_experiment_id(db, reactor_label)
            stmt = (
                pg_insert(ReactorChangeRequest)
                .values(
                    reactor_label=reactor_label,
                    experiment_id=resolved_exp_id,
                    requested_change=change_request,
                    notion_status=status,
                    carried_forward=carried_forward,
                    sync_date=sync_date,
                    notion_page_id=page_id_raw.replace("-", ""),
                )
                .on_conflict_do_update(
                    index_elements=["reactor_label", "sync_date"],
                    set_=dict(
                        experiment_id=resolved_exp_id,
                        requested_change=change_request,
                        notion_status=status,
                        carried_forward=carried_forward,
                        notion_page_id=page_id_raw.replace("-", ""),
                    ),
                )
            )
            db.execute(stmt)
        except Exception as exc:
            result.errors.append(f"{reactor_label}: DB error — {exc}")
            log.error("notion_import_db_error", reactor=reactor_label, error=str(exc))
            continue

        if carried_forward:
            result.carried_forward += 1
        result.imported += 1
        result.active_cr_page_ids.add(page_id_raw)

        if should_clear:
            pages_to_clear.append(page_id_raw)

    # Commit ALL upserts BEFORE touching Notion — protects against partial failures.
    try:
        db.commit()
    except Exception as exc:
        result.errors.append(f"DB commit failed: {exc}")
        log.error("notion_import_commit_error", error=str(exc))
        return result

    # Now clear Notion rows safely; DB is already committed.
    for page_id in pages_to_clear:
        try:
            client.clear_change_request(page_id)
            result.cleared_page_ids.add(page_id)
        except Exception as exc:
            result.errors.append(f"Notion clear failed for {page_id}: {exc}")
            log.warning("notion_clear_failed", page_id=page_id, error=str(exc))

    log.info(
        "notion_import_done",
        imported=result.imported,
        skipped=result.skipped,
        carried_forward=result.carried_forward,
        errors=result.errors,
    )
    return result
