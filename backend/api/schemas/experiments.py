from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
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
    experiment_id: Optional[str] = Field(None, min_length=1, max_length=100)
    sample_id: Optional[str] = None
    researcher: Optional[str] = None
    date: Optional[datetime] = None
    status: Optional[ExperimentStatus] = None
    is_outlier: Optional[bool] = None

    @field_validator("is_outlier")
    @classmethod
    def _is_outlier_not_null(cls, v: Optional[bool]) -> bool:
        if v is None:
            raise ValueError("is_outlier cannot be null; send true or false, or omit the field")
        return v


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
    base_experiment_id: Optional[str] = None
    parent_experiment_fk: Optional[int] = None
    replicate_label: Optional[str] = None
    is_outlier: bool = False
    id_timepoint_days: Optional[float] = None
    # Joined from conditions (may be None if no conditions recorded yet)
    experiment_type: Optional[str] = None
    reactor_number: Optional[int] = None
    # Derived from additives view
    additives_summary: Optional[str] = None
    # First note text
    condition_note: Optional[str] = None
    # Grouped-list mode only (group_replicates=true): lettered children of this
    # group parent, ordered by replicate_label. None in flat mode / for non-parents.
    replicates: Optional[list["ExperimentListItem"]] = None


ExperimentListItem.model_rebuild()


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
    replicate_label: Optional[str] = None
    is_outlier: bool = False
    id_timepoint_days: Optional[float] = None
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


class ReplicateGroupMember(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    experiment_id: str
    replicate_label: Optional[str] = None
    status: Optional[ExperimentStatus] = None
    is_outlier: bool = False


class ReplicateGroupResponse(BaseModel):
    base_experiment_id: str
    parent: Optional[ReplicateGroupMember] = None
    members: list[ReplicateGroupMember] = []


class ReplicateCreateRequest(BaseModel):
    base_experiment_id: str
    count: int = Field(3, ge=1, le=25)


class ReplicateCreateResponse(BaseModel):
    created: list[ExperimentResponse]
    skipped: list[str] = []
