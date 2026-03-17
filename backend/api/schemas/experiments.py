from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from database.models.enums import ExperimentStatus


class ExperimentCreate(BaseModel):
    experiment_id: str
    experiment_number: int
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


class ExperimentResponse(ExperimentListItem):
    base_experiment_id: Optional[str] = None
    parent_experiment_fk: Optional[int] = None
    updated_at: Optional[datetime] = None


class NoteCreate(BaseModel):
    note_text: str


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: str
    note_text: Optional[str] = None
    created_at: datetime
