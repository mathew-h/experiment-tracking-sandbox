from __future__ import annotations
from datetime import datetime, timezone
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, case, distinct
from sqlalchemy.orm import Session
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.conditions import ExperimentalConditions
from database.models.results import ExperimentalResults, ScalarResults, ICPResults
from database.models.enums import ExperimentStatus
from database.models.notion_sync import ReactorChangeRequest
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.dashboard import (
    ReactorStatusResponse, ExperimentTimelineResponse, TimelinePoint,
    DashboardResponse, DashboardSummary, SlotOccupancy, ReactorCardData, GanttEntry, ActivityEntry,
)
from backend.services.workdays import workday_window

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Static reactor hardware specs — keyed by reactor_number (int).
# Source: lab hardware inventory (issue #2).
REACTOR_SPECS: dict[int, dict[str, object]] = {
    1:  {"volume_mL": 100, "material": "Hastelloy", "vendor": "Yushen"},
    2:  {"volume_mL": 100, "material": "Hastelloy", "vendor": "Yushen"},
    3:  {"volume_mL": 100, "material": "Hastelloy", "vendor": "Yushen"},
    4:  {"volume_mL": 500, "material": "Titanium",  "vendor": "Yushen"},
    5:  {"volume_mL": 500, "material": "Titanium",  "vendor": "Yushen"},
    6:  {"volume_mL": 500, "material": "Titanium",  "vendor": "Yushen"},
    7:  {"volume_mL": 300, "material": "Titanium",  "vendor": "Tan"},
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

R_SLOT_COUNT = 16    # HPHT vessels R01-R16; must stay in sync with REACTOR_SPECS
CF_SLOT_COUNT = 3    # Core flood rigs CF01-CF03


def _occupancy(cards: list[ReactorCardData], prefix: str, total: int) -> SlotOccupancy:
    """Derive ongoing/queued/empty counts for a fixed slot-label prefix ('R' or 'CF').

    Filters against the valid label set (not just a startswith check) so an
    out-of-range reactor_number (no CHECK constraint exists on that column)
    can never drive `empty` negative.
    """
    valid = {f"{prefix}{i:02d}" for i in range(1, total + 1)}
    relevant = [c for c in cards if c.reactor_label in valid]
    ongoing = sum(1 for c in relevant if c.status == ExperimentStatus.ONGOING)
    queued = sum(1 for c in relevant if c.status == ExperimentStatus.QUEUED)
    return SlotOccupancy(
        total=total,
        ongoing=ongoing,
        queued=queued,
        empty=total - ongoing - queued,
    )


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
            ExperimentalConditions.reactor_slot,
            Experiment.id,
            Experiment.experiment_id,
            Experiment.status,
            Experiment.sample_id,
            Experiment.researcher,
            Experiment.created_at,
            Experiment.date,                          # ← use date (with created_at fallback) for started_at
            ExperimentalConditions.temperature_c,
            ExperimentalConditions.experiment_type,
            note_sq.c.note_text.label("description"),
        )
        .join(Experiment, Experiment.id == ExperimentalConditions.experiment_fk)
        .outerjoin(note_sq, note_sq.c.experiment_fk == Experiment.id)
        .where(
            Experiment.status.in_([ExperimentStatus.ONGOING, ExperimentStatus.QUEUED])
        )
        # reactor_slot is NULL for anything that holds no physical vessel — a
        # non-occupancy type, a missing reactor_number, or reactor_number <= 0.
        # One predicate replaces the number-not-null + type-in pair, and it also
        # excludes the reactor_number = 0 rows the old pair let through
        # (issue #97).
        .where(ExperimentalConditions.reactor_slot.isnot(None))
        .order_by(
            ExperimentalConditions.reactor_number,
            case(
                (Experiment.status == ExperimentStatus.ONGOING, 0),
                (Experiment.status == ExperimentStatus.QUEUED, 1),
                else_=2,
            ),
            Experiment.created_at.desc(),
        )
    ).all()

    seen_labels: set[str] = set()
    reactor_cards: list[ReactorCardData] = []
    for row in reactor_rows:
        rn = row.reactor_number
        exp_type = (
            row.experiment_type.value
            if hasattr(row.experiment_type, "value")
            else str(row.experiment_type)
            if row.experiment_type else None
        )
        # Stored, not re-derived (issue #97). is_cf is still needed below to keep
        # REACTOR_SPECS off the Core Flood cards.
        label = row.reactor_slot
        is_cf = label.startswith("CF")
        if label in seen_labels:
            continue
        seen_labels.add(label)
        start = row.date or row.created_at
        status_val = row.status.value if hasattr(row.status, "value") else str(row.status)
        days = (now - start).days if (start and status_val == "ONGOING") else None
        # REACTOR_SPECS is keyed by bare reactor_number and only covers the R01-R16
        # HPHT vessels. Core Flood rigs reuse the same numbering (CF01-CF03), so
        # this must be skipped for CF or it silently inherits R01-R03's HPHT spec.
        specs = REACTOR_SPECS.get(rn, {}) if not is_cf else {}
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
            started_at=start,
            days_running=days,
            temperature_c=row.temperature_c,
            volume_mL=specs.get("volume_mL"),
            material=specs.get("material"),
            vendor=specs.get("vendor"),
        ))

    # ── 2b. Today's reactor modification per card (issue #72) ─────────────
    # One batched query keyed on (experiment_id, reactor_label) — keeps the
    # "no N+1" contract of this endpoint. "Today" is UTC, matching the
    # pop-out's save path (todayISO() is the UTC date).
    today = now.date()
    card_exp_ids = [c.experiment_id for c in reactor_cards if c.experiment_id]
    if card_exp_ids:
        mod_rows = db.execute(
            select(
                ReactorChangeRequest.experiment_id,
                ReactorChangeRequest.reactor_label,
                ReactorChangeRequest.requested_change,
            ).where(
                ReactorChangeRequest.experiment_id.in_(card_exp_ids),
                ReactorChangeRequest.sync_date == today,
            )
        ).all()
        mods = {(r.experiment_id, r.reactor_label): r.requested_change for r in mod_rows}
        for c in reactor_cards:
            c.todays_modification = mods.get((c.experiment_id, c.reactor_label))

    # ── 2c. Workday-window KPI counts + slot occupancy ─────────────────────
    # ET is used here (not UTC) because "last 7 workdays" is a statement about
    # the lab's week — see design notes in issue #85. This is intentionally
    # NOT the same "today" as section 2b's UTC-based modification lookup.
    wd_first, wd_last, wd_start, wd_end = workday_window(7)

    gc_row = db.execute(
        select(
            func.count(ScalarResults.id).label("measurements"),
            func.count(distinct(ExperimentalResults.experiment_fk)).label("experiments"),
        )
        .join(ExperimentalResults, ExperimentalResults.id == ScalarResults.result_id)
        .where(ScalarResults.gc_run_date >= wd_start)
        .where(ScalarResults.gc_run_date < wd_end)
    ).one()

    serum_start = func.coalesce(Experiment.date, Experiment.created_at)
    serum_row = db.execute(
        select(
            func.count(Experiment.id).label("vials"),
            func.count(distinct(
                func.coalesce(Experiment.base_experiment_id, Experiment.experiment_id)
            )).label("experiments"),
        )
        .join(ExperimentalConditions, ExperimentalConditions.experiment_fk == Experiment.id)
        .where(ExperimentalConditions.experiment_type == "Serum")
        .where(serum_start >= wd_start)
        .where(serum_start < wd_end)
    ).one()

    summary = DashboardSummary(
        reactors=_occupancy(reactor_cards, "R", R_SLOT_COUNT),
        core_floods=_occupancy(reactor_cards, "CF", CF_SLOT_COUNT),
        gc_measurements_7wd=gc_row.measurements,
        gc_experiments_7wd=gc_row.experiments,
        serum_vials_started_7wd=serum_row.vials,
        serum_experiments_7wd=serum_row.experiments,
        workday_window_start=wd_first,
        workday_window_end=wd_last,
    )

    # ── 3. Gantt timeline (all experiments, newest first, limit 100) ──────
    gantt_rows = db.execute(
        select(
            Experiment.id,
            Experiment.experiment_id,
            Experiment.status,
            Experiment.sample_id,
            Experiment.researcher,
            Experiment.created_at,
            Experiment.date,          # ← use date (with created_at fallback) for started_at
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
        start = row.date or row.created_at
        days = None
        if start:
            end = ended_at or now
            days = (end - start).days
        timeline.append(GanttEntry(
            experiment_id=row.experiment_id,
            experiment_db_id=row.id,
            status=status,
            experiment_type=exp_type,
            sample_id=row.sample_id,
            researcher=row.researcher,
            started_at=start,
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
            ExperimentalConditions.reactor_slot,
            Experiment.id,
            Experiment.experiment_id,
            Experiment.status,
            Experiment.created_at,
            Experiment.date,                          # ← use date (with created_at fallback) for started_at
            ExperimentalConditions.temperature_c,
            ExperimentalConditions.experiment_type,
        )
        .join(Experiment, Experiment.id == ExperimentalConditions.experiment_fk)
        # Legacy endpoint: intentionally filters ONGOING only.
        # The reactor cards query (/api/dashboard/reactor-cards) includes QUEUED.
        # Do not change this filter without verifying no downstream callers depend on ONGOING-only behavior.
        .where(Experiment.status == ExperimentStatus.ONGOING)
        # reactor_slot is NULL for anything that holds no physical vessel — a
        # non-occupancy type, a missing reactor_number, or reactor_number <= 0
        # (issue #97).
        .where(ExperimentalConditions.reactor_slot.isnot(None))
        .order_by(ExperimentalConditions.reactor_number, Experiment.created_at.desc())
    ).all()

    # Deduplicate: keep first (most-recent) per label (CF01/R01 are separate slots)
    seen: set[str] = set()
    result: list[ReactorStatusResponse] = []
    for row in rows:
        rn = row.reactor_number
        # No exp_type/is_cf derivation needed here (issue #97): label is read
        # straight from the stored slot, and ReactorStatusResponse.experiment_type
        # is populated from row.experiment_type directly, below.
        label = row.reactor_slot
        if label in seen:
            continue
        seen.add(label)
        start = row.date or row.created_at
        result.append(ReactorStatusResponse(
            reactor_number=rn,
            experiment_id=row.experiment_id,
            status=row.status,
            experiment_db_id=row.id,
            started_at=start,
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
