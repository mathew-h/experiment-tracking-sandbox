"""Export step — write occupied reactor slot data to Notion.

Only writes for ONGOING experiments with a reactor_number assigned.
Idle slots are skipped entirely (no Notion calls).
"""
from __future__ import annotations

import structlog
from dataclasses import dataclass, field

from sqlalchemy.orm import Session, joinedload

from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus
from database.models.experiments import Experiment
from .client import (
    NotionSyncClient,
    extract_reactor_label,
)

log = structlog.get_logger(__name__)


@dataclass
class ExportResult:
    exported: int = 0
    errors: list[str] = field(default_factory=list)


def _reactor_label_for(reactor_number: int, experiment_type: str | None) -> str:
    """Map DB reactor_number + experiment_type to Notion label e.g. 'R05' or 'CF01'.

    Handles both string values and enum instances for experiment_type,
    matching the same defensive pattern used in the dashboard router.
    """
    if experiment_type is None:
        return f"R{reactor_number:02d}"
    # Defensive: handle both plain string and enum instance
    etype = experiment_type.value if hasattr(experiment_type, "value") else str(experiment_type)
    return f"CF{reactor_number:02d}" if etype == "Core Flood" else f"R{reactor_number:02d}"


def run_export(
    client: NotionSyncClient,
    db: Session,
    pages: list[dict],
    cleared_page_ids: set[str],
) -> ExportResult:
    """Write experiment info to Notion for every occupied ONGOING reactor slot.

    Args:
        client: Notion client wrapper.
        db: SQLAlchemy session (read-only in this step).
        pages: All 18 Notion reactor pages (already fetched by orchestrator).
        cleared_page_ids: Page IDs whose Change Request was cleared in the import step.
            Only these pages get their status reset to Pending.
    """
    result = ExportResult()

    # Build lookup: reactor_label → page_id (with dashes, for Notion API calls)
    notion_rows: dict[str, str] = {
        extract_reactor_label(page): page["id"] for page in pages
    }

    # Query occupied slots: ONGOING experiments with a reactor assigned.
    # Note: Experiment.description is a @property, not a column — fetch the
    # full Experiment object so we can access it after the query.
    rows = (
        db.query(Experiment, ExperimentalConditions)
        .options(joinedload(Experiment.notes))
        .join(ExperimentalConditions, ExperimentalConditions.experiment_fk == Experiment.id)
        .filter(
            Experiment.status == ExperimentStatus.ONGOING,
            ExperimentalConditions.reactor_number.isnot(None),
        )
        .all()
    )

    occupied_page_ids: set[str] = set()

    for exp, cond in rows:
        label = _reactor_label_for(cond.reactor_number, cond.experiment_type)
        page_id = notion_rows.get(label)
        if page_id is None:
            log.warning("notion_export_no_page_for_reactor", reactor=label)
            continue

        occupied_page_ids.add(page_id)
        date_started = exp.date.strftime("%Y-%m-%d") if exp.date else None

        try:
            client.write_experiment_info(
                page_id=page_id,
                experiment_id=exp.experiment_id,
                description=exp.description or "",
                date_started=date_started,
            )
            # Re-confirm Pending status only for rows cleared in this cycle
            if page_id in cleared_page_ids:
                client.set_status_pending(page_id)
            result.exported += 1
        except Exception as exc:
            result.errors.append(f"{label}: export error — {exc}")
            log.error("notion_export_error", reactor=label, error=str(exc))

    # Clear experiment info from idle reactor slots so stale data doesn't persist
    for label, page_id in notion_rows.items():
        if page_id in occupied_page_ids:
            continue
        try:
            client.clear_experiment_info(page_id)
        except Exception as exc:
            result.errors.append(f"{label}: clear idle error — {exc}")
            log.error("notion_clear_idle_error", reactor=label, error=str(exc))

    log.info("notion_export_done", exported=result.exported, errors=result.errors)
    return result
