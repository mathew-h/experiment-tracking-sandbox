from __future__ import annotations
from datetime import datetime, timedelta, timezone
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, case, distinct
from sqlalchemy.orm import Session
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.conditions import ExperimentalConditions
from database.models.results import ExperimentalResults, ScalarResults, ICPResults
from database.models.enums import ExperimentStatus
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.dashboard import (
    ReactorStatusResponse, ExperimentTimelineResponse, TimelinePoint,
    DashboardResponse, DashboardSummary, ReactorCardData, GanttEntry, ActivityEntry,
)

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Static reactor hardware specs — keyed by reactor_number (int).
# Source: lab hardware inventory (issue #2).
REACTOR_SPECS: dict[int, dict[str, object]] = {
    1:  {"volume_mL": 100, "material": "Hastelloy", "vendor": "Yushen"},
    2:  {"volume_mL": 100, "material": "Hastelloy", "vendor": "Yushen"},
    3:  {"volume_mL": 100, "material": "Hastelloy", "vendor": "Yushen"},
    4:  {"volume_mL": 300, "material": "Titanium",  "vendor": "Tan"},
    5:  {"volume_mL": 500, "material": "Titanium",  "vendor": "Yushen"},
    6:  {"volume_mL": 500, "material": "Titanium",  "vendor": "Yushen"},
    7:  {"volume_mL": 500, "material": "Titanium",  "vendor": "Yushen"},
    8:  {"volume_mL": 100, "material": "Titanium",  "vendor": "Tan"},
    9:  {"volume_mL": 100, "material": "Titanium",  "vendor": "Tan"},
    10: {"volume_mL": 100, "material": "Titanium",  "vendor": "Yushen"},
    11: {"volume_mL": 100, "material": "Titanium",  "vendor": "Yushen"},
    12: {"volume_mL": 100, "material": "Titanium",  "vendor": "Yushen"},
    13: {"volume_mL": 100, "material": "Titanium",  "vendor": "Yushen"},
    14: {"volume_mL": 100, "material": "Titanium",  "vendor": "Yushen"},
    15: {"volume_mL": 100, "material": "Titanium",  "vendor": "Yushen"},
    16: {"volume_mL": 100, "material": "Titanium",  "vendor": "Yushen"},
}


@router.get("/", response_model=DashboardResponse)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> DashboardResponse:
    """
    Single call returning all dashboard data.
    Four focused queries — no N+1. Target: <500ms with 500 experiments.
    """
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = now - timedelta(days=7)

    # ── 1. Summary stats ──────────────────────────────────────────────────
    summary_row = db.execute(
        select(
            func.count(case((Experiment.status == ExperimentStatus.ONGOING, 1))).label("active"),
            func.count(
                distinct(case((
                    (Experiment.status == ExperimentStatus.ONGOING) &
                    ExperimentalConditions.reactor_number.isnot(None),
                    ExperimentalConditions.reactor_number,
                )))
            ).label("reactors_in_use"),
            func.count(
                case((
                    (Experiment.status == ExperimentStatus.COMPLETED) &
                    (Experiment.updated_at >= month_start),
                    1,
                ))
            ).label("completed_month"),
        )
        .outerjoin(ExperimentalConditions, ExperimentalConditions.experiment_fk == Experiment.id)
    ).one()

    # Pending results: ONGOING experiments with no result in the last 7 days
    ongoing_with_recent_result = set(
        db.execute(
            select(ExperimentalResults.experiment_fk)
            .where(ExperimentalResults.created_at >= seven_days_ago)
        ).scalars().all()
    )
    ongoing_ids = set(
        db.execute(
            select(Experiment.id).where(Experiment.status == ExperimentStatus.ONGOING)
        ).scalars().all()
    )
    pending_results = len(ongoing_ids - ongoing_with_recent_result)

    summary = DashboardSummary(
        active_experiments=summary_row.active,
        reactors_in_use=summary_row.reactors_in_use,
        completed_this_month=summary_row.completed_month,
        pending_results=pending_results,
    )

    # ── 2. Reactor cards (ONGOING experiments with a reactor assigned) ────
    # Subquery: pick the oldest note per experiment (the "description" note)
    first_note_sq = (
        select(
            ExperimentNotes.experiment_fk,
            func.min(ExperimentNotes.id).label("min_note_id"),
        )
        .group_by(ExperimentNotes.experiment_fk)
        .subquery()
    )
    note_sq = (
        select(ExperimentNotes.experiment_fk, ExperimentNotes.note_text)
        .join(first_note_sq, ExperimentNotes.id == first_note_sq.c.min_note_id)
        .subquery()
    )

    reactor_rows = db.execute(
        select(
            ExperimentalConditions.reactor_number,
            Experiment.id,
            Experiment.experiment_id,
            Experiment.status,
            Experiment.sample_id,
            Experiment.researcher,
            Experiment.created_at,
            ExperimentalConditions.temperature_c,
            ExperimentalConditions.experiment_type,
            note_sq.c.note_text.label("description"),
        )
        .join(Experiment, Experiment.id == ExperimentalConditions.experiment_fk)
        .outerjoin(note_sq, note_sq.c.experiment_fk == Experiment.id)
        .where(Experiment.status == ExperimentStatus.ONGOING)
        .where(ExperimentalConditions.reactor_number.isnot(None))
        .order_by(ExperimentalConditions.reactor_number, Experiment.created_at.desc())
    ).all()

    seen_reactors: set[int] = set()
    reactor_cards: list[ReactorCardData] = []
    for row in reactor_rows:
        rn = row.reactor_number
        if rn in seen_reactors:
            continue
        seen_reactors.add(rn)
        exp_type = (
            row.experiment_type.value
            if hasattr(row.experiment_type, "value")
            else str(row.experiment_type)
            if row.experiment_type else None
        )
        is_cf = exp_type == "Core Flood" if exp_type else False
        label = f"CF{rn:02d}" if is_cf else f"R{rn:02d}"
        days = (now - row.created_at).days if row.created_at else None
        specs = REACTOR_SPECS.get(rn, {})
        reactor_cards.append(ReactorCardData(
            reactor_number=rn,
            reactor_label=label,
            experiment_id=row.experiment_id,
            experiment_db_id=row.id,
            status=row.status,
            experiment_type=exp_type,
            sample_id=row.sample_id,
            description=row.description,
            researcher=row.researcher,
            started_at=row.created_at,
            days_running=days,
            temperature_c=row.temperature_c,
            volume_mL=specs.get("volume_mL"),
            material=specs.get("material"),
            vendor=specs.get("vendor"),
        ))

    # ── 3. Gantt timeline (all experiments, newest first, limit 100) ──────
    gantt_rows = db.execute(
        select(
            Experiment.id,
            Experiment.experiment_id,
            Experiment.status,
            Experiment.sample_id,
            Experiment.researcher,
            Experiment.created_at,
            Experiment.updated_at,
            ExperimentalConditions.experiment_type,
        )
        .outerjoin(ExperimentalConditions, ExperimentalConditions.experiment_fk == Experiment.id)
        .order_by(Experiment.created_at.desc())
        .limit(100)
    ).all()

    timeline: list[GanttEntry] = []
    for row in gantt_rows:
        status = row.status
        exp_type = (
            row.experiment_type.value
            if hasattr(row.experiment_type, "value")
            else str(row.experiment_type)
            if row.experiment_type else None
        )
        ended_at = row.updated_at if status != ExperimentStatus.ONGOING else None
        days = None
        if row.created_at:
            end = ended_at or now
            days = (end - row.created_at).days
        timeline.append(GanttEntry(
            experiment_id=row.experiment_id,
            experiment_db_id=row.id,
            status=status,
            experiment_type=exp_type,
            sample_id=row.sample_id,
            researcher=row.researcher,
            started_at=row.created_at,
            ended_at=ended_at,
            days_running=days,
        ))

    # ── 4. Recent activity (last 20 ModificationsLog entries) ─────────────
    activity_rows = db.execute(
        select(
            ModificationsLog.id,
            ModificationsLog.experiment_id,
            ModificationsLog.modified_by,
            ModificationsLog.modification_type,
            ModificationsLog.modified_table,
            ModificationsLog.created_at,
        )
        .order_by(ModificationsLog.created_at.desc())
        .limit(20)
    ).all()

    recent_activity = [
        ActivityEntry(
            id=row.id,
            experiment_id=row.experiment_id,
            modified_by=row.modified_by,
            modification_type=row.modification_type,
            modified_table=row.modified_table,
            created_at=row.created_at,
        )
        for row in activity_rows
    ]

    return DashboardResponse(
        summary=summary,
        reactors=reactor_cards,
        timeline=timeline,
        recent_activity=recent_activity,
    )


@router.get("/reactor-status", response_model=list[ReactorStatusResponse])
def get_reactor_status(
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[ReactorStatusResponse]:
    """Single query: all reactors with their current ONGOING experiment. No N+1."""
    rows = db.execute(
        select(
            ExperimentalConditions.reactor_number,
            Experiment.id,
            Experiment.experiment_id,
            Experiment.status,
            Experiment.created_at,
            ExperimentalConditions.temperature_c,
            ExperimentalConditions.experiment_type,
        )
        .join(Experiment, Experiment.id == ExperimentalConditions.experiment_fk)
        .where(Experiment.status == ExperimentStatus.ONGOING)
        .where(ExperimentalConditions.reactor_number.isnot(None))
        .order_by(ExperimentalConditions.reactor_number, Experiment.created_at.desc())
    ).all()

    # Deduplicate: keep first (most-recent) per reactor_number
    seen: set[int] = set()
    result: list[ReactorStatusResponse] = []
    for row in rows:
        rn = row.reactor_number
        if rn in seen:
            continue
        seen.add(rn)
        result.append(ReactorStatusResponse(
            reactor_number=rn,
            experiment_id=row.experiment_id,
            status=row.status,
            experiment_db_id=row.id,
            started_at=row.created_at,
            temperature_c=row.temperature_c,
            experiment_type=row.experiment_type,
        ))
    return result


@router.get("/timeline/{experiment_id}", response_model=ExperimentTimelineResponse)
def get_experiment_timeline(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentTimelineResponse:
    """Return all result timepoints for an experiment with data-presence flags."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    results = db.execute(
        select(ExperimentalResults)
        .where(ExperimentalResults.experiment_fk == exp.id)
        .order_by(ExperimentalResults.time_post_reaction_days)
    ).scalars().all()

    # Check scalar/ICP presence in bulk (avoid N+1)
    result_ids = [r.id for r in results]
    scalar_ids = set(
        db.execute(select(ScalarResults.result_id).where(ScalarResults.result_id.in_(result_ids)))
        .scalars().all()
    )
    icp_ids = set(
        db.execute(select(ICPResults.result_id).where(ICPResults.result_id.in_(result_ids)))
        .scalars().all()
    )

    timepoints = [
        TimelinePoint(
            result_id=r.id,
            time_post_reaction_days=r.time_post_reaction_days,
            time_post_reaction_bucket_days=r.time_post_reaction_bucket_days,
            is_primary=r.is_primary_timepoint_result,
            has_scalar=r.id in scalar_ids,
            has_icp=r.id in icp_ids,
        )
        for r in results
    ]

    return ExperimentTimelineResponse(
        experiment_id=experiment_id,
        status=exp.status,
        timepoints=timepoints,
    )
