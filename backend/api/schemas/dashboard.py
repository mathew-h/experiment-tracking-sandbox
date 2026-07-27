from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel
from database.models.enums import ExperimentStatus


class ReactorStatusResponse(BaseModel):
    """Legacy response — kept for backwards-compat with /reactor-status endpoint."""
    reactor_number: int
    experiment_id: Optional[str] = None
    status: Optional[ExperimentStatus] = None
    experiment_db_id: Optional[int] = None
    started_at: Optional[datetime] = None
    temperature_c: Optional[float] = None
    experiment_type: Optional[str] = None


class TimelinePoint(BaseModel):
    result_id: int
    time_post_reaction_days: Optional[float] = None
    time_post_reaction_bucket_days: Optional[float] = None
    is_primary: bool
    has_scalar: bool
    has_icp: bool


class ExperimentTimelineResponse(BaseModel):
    experiment_id: str
    status: Optional[ExperimentStatus] = None
    timepoints: list[TimelinePoint]


# ── M7 full-dashboard schemas ────────────────────────────────────────────────

class SlotOccupancy(BaseModel):
    """Occupancy of a fixed set of physical slots. ongoing + queued + empty == total."""
    total: int
    ongoing: int
    queued: int
    empty: int


class DashboardSummary(BaseModel):
    reactors: SlotOccupancy                  # R01-R16 (HPHT only)
    core_floods: SlotOccupancy               # CF01-CF03
    gc_measurements_7wd: int                 # scalar_results rows with gc_run_date in window
    gc_experiments_7wd: int                  # distinct experiments behind those rows
    serum_vials_started_7wd: int             # Serum experiment rows started in window
    serum_experiments_7wd: int               # distinct base experiments behind those vials
    workday_window_start: date               # first workday in the window (lab-local)
    workday_window_end: date                 # last workday in the window (== today if a workday)


class ReactorCardData(BaseModel):
    reactor_number: int
    reactor_label: str              # "R05" or "CF01"
    experiment_id: Optional[str] = None
    experiment_db_id: Optional[int] = None
    status: Optional[ExperimentStatus] = None
    experiment_type: Optional[str] = None
    sample_id: Optional[str] = None
    description: Optional[str] = None   # first note text
    researcher: Optional[str] = None
    started_at: Optional[datetime] = None
    days_running: Optional[int] = None
    temperature_c: Optional[float] = None
    volume_mL: Optional[int] = None     # reactor hardware spec
    material: Optional[str] = None      # reactor hardware spec
    vendor: Optional[str] = None        # reactor hardware spec
    todays_modification: Optional[str] = None  # requested_change saved today (UTC) for this card; None if none


class GanttEntry(BaseModel):
    experiment_id: str
    experiment_db_id: int
    status: ExperimentStatus
    experiment_type: Optional[str] = None
    sample_id: Optional[str] = None
    researcher: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None   # None for ONGOING
    days_running: Optional[int] = None


class ActivityEntry(BaseModel):
    id: int
    experiment_id: Optional[str] = None
    modified_by: Optional[str] = None
    modification_type: str
    modified_table: str
    created_at: datetime


class DashboardResponse(BaseModel):
    summary: DashboardSummary
    reactors: list[ReactorCardData]      # occupied slots only; frontend fills empties
    timeline: list[GanttEntry]           # all experiments for Gantt, newest first, limit 100
    recent_activity: list[ActivityEntry] # last 20 modification log entries
