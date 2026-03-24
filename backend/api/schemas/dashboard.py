from __future__ import annotations
from datetime import datetime
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

class DashboardSummary(BaseModel):
    active_experiments: int
    reactors_in_use: int
    completed_this_month: int
    pending_results: int  # ONGOING experiments with no result recorded in the last 7 days


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
