from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from database.models.enums import ExperimentStatus


class ExperimentCreate(BaseModel):
    experiment_id: str
    experiment_number: Optional[int] = None   # auto-assigned if omitted
    sample_id: Optional[str] = None
    researcher: Optional[str] = None
    date: Optional[datetime] = None
    status: ExperimentStatus = ExperimentStatus.ONGOING
    base_experiment_id: Optional[str] = None
    parent_experiment_fk: Optional[int] = None


class ExperimentUpdate(BaseModel):
    sample_id: Optional[str] = None
    researcher: Optional[str] = None
    date: Optional[datetime] = None
    status: Optional[ExperimentStatus] = None


class ExperimentStatusUpdate(BaseModel):
    status: ExperimentStatus


class NextIdResponse(BaseModel):
    next_id: str


class ExperimentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: str
    experiment_number: int
    status: Optional[ExperimentStatus] = None
    researcher: Optional[str] = None
    date: Optional[datetime] = None
    sample_id: Optional[str] = None
    created_at: datetime
    # Joined from conditions (may be None if no conditions recorded yet)
    experiment_type: Optional[str] = None
    reactor_number: Optional[int] = None
    # Derived from additives view
    additives_summary: Optional[str] = None
    # First note text
    condition_note: Optional[str] = None


class ExperimentListResponse(BaseModel):
    """Paginated list response."""
    items: list[ExperimentListItem]
    total: int
    skip: int
    limit: int


class ExperimentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: str
    experiment_number: int
    status: Optional[ExperimentStatus] = None
    researcher: Optional[str] = None
    date: Optional[datetime] = None
    sample_id: Optional[str] = None
    base_experiment_id: Optional[str] = None
    parent_experiment_fk: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ExperimentDetailResponse(ExperimentResponse):
    """Full detail including nested conditions, notes, modifications."""
    conditions: Optional[dict] = None
    notes: list[dict] = []
    modifications: list[dict] = []


class NoteCreate(BaseModel):
    note_text: str


class NoteUpdate(BaseModel):
    note_text: str = Field(min_length=1)


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: str
    note_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
