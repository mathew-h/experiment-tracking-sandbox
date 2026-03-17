from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from database.models.enums import ExperimentStatus


class ReactorStatusResponse(BaseModel):
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
