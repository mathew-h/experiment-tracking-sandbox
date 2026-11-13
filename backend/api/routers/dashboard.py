from __future__ import annotations
from datetime import date, datetime, timezone
import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, case, distinct
from sqlalchemy.orm import Session
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.conditions import ExperimentalConditions
from database.models.results import ExperimentalResults, ScalarResults
from database.models.enums import ExperimentStatus, NoteType
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.dashboard import (
    DashboardResponse, DashboardSummary, SlotOccupancy, ReactorCardData, GanttEntry, ActivityEntry,
    LatestModification, ReactorSpec,
)
from backend.services.workdays import workday_window, LAB_TZ
from backend.services import run_service
from backend.services.result_entry_service import _aware

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

def _type_text(experiment_type: object) -> str | None:
    """A stored experiment_type as plain text: an enum's value, else str(), else None."""
    if hasattr(experiment_type, "value"):
        return experiment_type.value
    return str(experiment_type) if experiment_type else None


# Static reactor hardware specs, keyed by slot label (issue #147). The single
# source of truth: the dashboard payload carries this table (`reactor_specs`),
# so the frontend no longer keeps a copy. Core Flood labels have no entry.
# Source: lab hardware inventory (issue #2); Parr specs confirmed by Mat
# 2026-11-06 (all six 75 mL Hastelloy).
REACTOR_SPECS: dict[str, dict[str, object]] = {
    "R01": {"volume_mL": 100, "material": "Hastelloy", "vendor": "Yushen"},
    "R02": {"volume_mL": 100, "material": "Hastelloy", "vendor": "Yushen"},
    "R03": {"volume_mL": 100, "material": "Hastelloy", "vendor": "Yushen"},
    "R04": {"volume_mL": 500, "material": "Titanium",  "vendor": "Yushen"},
    "R05": {"volume_mL": 500, "material": "Titanium",  "vendor": "Yushen"},
    "R06": {"volume_mL": 500, "material": "Titanium",  "vendor": "Yushen"},
    "R07": {"volume_mL": 300, "material": "Titanium",  "vendor": "Tan"},
    "R08": {"volume_mL": 100, "material": "Titanium",  "vendor": "Tan"},
    "R09": {"volume_mL": 100, "material": "Titanium",  "vendor": "Tan"},
    "R10": {"volume_mL": 100, "material": "Titanium",  "vendor": "Yushen"},
    "R11": {"volume_mL": 100, "material": "Titanium",  "vendor": "Yushen"},
    "R12": {"volume_mL": 100, "material": "Titanium",  "vendor": "Yushen"},
    "R13": {"volume_mL": 100, "material": "Titanium",  "vendor": "Yushen"},
    "R14": {"volume_mL": 100, "material": "Titanium",  "vendor": "Yushen"},
    "R15": {"volume_mL": 100, "material": "Titanium",  "vendor": "Yushen"},
    "R16": {"volume_mL": 100, "material": "Titanium",  "vendor": "Yushen"},
    "P01": {"volume_mL": 75,  "material": "Hastelloy", "vendor": "Parr"},
    "P02": {"volume_mL": 75,  "material": "Hastelloy", "vendor": "Parr"},
    "P03": {"volume_mL": 75,  "material": "Hastelloy", "vendor": "Parr"},
    "P04": {"volume_mL": 75,  "material": "Hastelloy", "vendor": "Parr"},
    "P05": {"volume_mL": 75,  "material": "Hastelloy", "vendor": "Parr"},
    "P06": {"volume_mL": 75,  "material": "Hastelloy", "vendor": "Parr"},
}

R_SLOT_COUNT = 16    # Yushen/Tan HPHT vessels R01-R16
P_SLOT_COUNT = 6     # Parr HPHT vessels P01-P06
CF_SLOT_COUNT = 3    # Core flood rigs CF01-CF03


def _occupancy(cards: list[ReactorCardData], prefix: str, total: int) -> SlotOccupancy:
    """Derive ongoing/queued/empty counts for a fixed slot-label prefix ('R', 'P' or 'CF').

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


def _samples_view(label: str) -> str:
    """The run samples view a slot's card reads (issue #165): CF rigs read
    v_core_flood_samples, R and P vessels v_hpht_samples."""
    return "v_core_flood_samples" if label.startswith("CF") else "v_hpht_samples"


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
    # The description is the note typed 'description' (Experiment.description
    # hybrid, issue #118 PR3) -- the same expression the experiments list and
    # v_experiments use, so the three can no longer disagree.

    reactor_rows = db.execute(
        select(
            ExperimentalConditions.reactor_number,
            ExperimentalConditions.reactor_slot,
            Experiment.id,
            Experiment.experiment_id,
            Experiment.base_experiment_id,
            Experiment.status,
            Experiment.sample_id,
            Experiment.researcher,
            Experiment.created_at,
            Experiment.date,                          # ← use date (with created_at fallback) for started_at
            ExperimentalConditions.temperature_c,
            ExperimentalConditions.experiment_type,
            Experiment.description.label("description"),
        )
        .join(Experiment, Experiment.id == ExperimentalConditions.experiment_fk)
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
        exp_type = _type_text(row.experiment_type)
        # Stored, not re-derived (issue #97).
        label = row.reactor_slot
        if label in seen_labels:
            continue
        seen_labels.add(label)
        start = row.date or row.created_at
        status_val = row.status.value if hasattr(row.status, "value") else str(row.status)
        days = (now - start).days if (start and status_val == "ONGOING") else None
        # Keyed by label, so CF01 and P01 can never inherit R01's spec (#147).
        specs = REACTOR_SPECS.get(label, {})
        reactor_cards.append(ReactorCardData(
            reactor_number=rn,
            reactor_label=label,
            experiment_id=row.experiment_id,
            experiment_db_id=row.id,
            base_experiment_id=row.base_experiment_id,
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

    # ── 2b. Reactor modifications per card (issue #72, re-sourced by #122 PR-B) ─
    # A reactor modification is a 'modification' note anchored to an event_date
    # (dashboard saves, the 021 backfill) or to a result (Add Results). One
    # batched query over the cards' experiments keeps this endpoint's "no N+1"
    # contract; the reduction to "today's" and "latest" happens here. "Today" is
    # the lab's calendar day (America/New_York, `LAB_TZ`), matching the card's
    # date input default and the KPI window in 2c — Mat's ruling 2026-10-05,
    # reversing the spec's "UTC, unchanged".
    today = now.astimezone(LAB_TZ).date()
    card_fks = [c.experiment_db_id for c in reactor_cards if c.experiment_db_id]
    if card_fks:
        mod_rows = db.execute(
            select(
                ExperimentNotes.experiment_fk,
                ExperimentNotes.id,
                ExperimentNotes.note_text,
                ExperimentNotes.event_date,
                ExperimentNotes.created_at,
            )
            .where(
                ExperimentNotes.experiment_fk.in_(card_fks),
                ExperimentNotes.note_type == NoteType.modification,
            )
            .order_by(ExperimentNotes.experiment_fk, ExperimentNotes.id)
        ).all()
        todays: dict[int, list[str]] = {}
        latest: dict[int, tuple] = {}   # experiment_fk -> ((anchor_date, id), row)
        for r in mod_rows:
            if r.event_date == today:
                todays.setdefault(r.experiment_fk, []).append(r.note_text or "")
            anchor = (r.event_date or (r.created_at.astimezone(LAB_TZ).date() if r.created_at else date.min), r.id)
            if r.experiment_fk not in latest or anchor > latest[r.experiment_fk][0]:
                latest[r.experiment_fk] = (anchor, r)
        for c in reactor_cards:
            if not c.experiment_db_id:
                continue
            texts = todays.get(c.experiment_db_id)
            c.todays_modification = "; ".join(texts) if texts else None
            hit = latest.get(c.experiment_db_id)
            if hit is not None:
                _, r = hit
                c.latest_modification = LatestModification(
                    note_text=r.note_text or "", event_date=r.event_date, created_at=r.created_at,
                )

    # ── 2d. Run H2 to date and last sampled date per card (issue #165) ────
    # A card's run is every segment sharing its base ID. CF cards read
    # v_core_flood_samples, R/P cards v_hpht_samples: one fetch per view, so at
    # most two queries for any number of cards. Both values come from the run's
    # last non-variant sample in view order (cumulative time NULLS LAST); the
    # date is that sample's sample_date as a lab-local calendar date, with no
    # fallback to an earlier dated sample. This deliberately differs from
    # hpht_service.list_runs' "max dated sample" (Mat, 2026-11-10).
    bases_by_view: dict[str, set[str]] = {}
    for c in reactor_cards:
        if c.base_experiment_id:
            view = _samples_view(c.reactor_label)
            bases_by_view.setdefault(view, set()).add(c.base_experiment_id)
    latest_by_view = {
        view: run_service.latest_sample_by_base(
            run_service.fetch_samples(db, view, base_ids=sorted(bases)))
        for view, bases in bases_by_view.items()
    }
    for c in reactor_cards:
        if not c.base_experiment_id:
            continue
        view = _samples_view(c.reactor_label)
        last = latest_by_view.get(view, {}).get(c.base_experiment_id)
        if last is None:
            continue
        c.cumulative_h2_grams_per_ton = last["cumulative_h2_grams_per_ton"]
        if last["sample_date"] is not None:
            c.last_sampled_date = _aware(last["sample_date"]).astimezone(LAB_TZ).date()

    # ── 2c. Workday-window KPI counts + slot occupancy ─────────────────────
    # ET is used here (not UTC) because "last 7 workdays" is a statement about
    # the lab's week — see design notes in issue #85. This is now the SAME
    # "today" as section 2b's modification lookup (both use LAB_TZ).
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
        parr=_occupancy(reactor_cards, "P", P_SLOT_COUNT),
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
        exp_type = _type_text(row.experiment_type)
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
        reactor_specs={label: ReactorSpec(**spec) for label, spec in REACTOR_SPECS.items()},
        timeline=timeline,
        recent_activity=recent_activity,
    )
