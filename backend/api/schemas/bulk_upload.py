from __future__ import annotations
from typing import Any, Literal, Optional
from pydantic import BaseModel


class PlanCreate(BaseModel):
    row: int
    experiment_id: str
    parent_id: Optional[str] = None
    copied_from: Optional[str] = None


class PlanRename(BaseModel):
    row: int
    from_id: str
    to_id: str


class PlanFieldChange(BaseModel):
    field: str
    old: Any = None
    new: Any = None


class PlanOverwrite(BaseModel):
    row: int
    experiment_id: str
    fields_changed: list[PlanFieldChange] = []


class PlanSkip(BaseModel):
    row: int
    experiment_id: Optional[str] = None
    reason: str


class PlanConflict(BaseModel):
    row: int
    kind: str
    detail: str


class UploadPlan(BaseModel):
    """Structured create/rename/overwrite/skip/conflict summary (issue #100 item 2).
    Only populated for upload types that build one — currently new-experiments."""
    creates: list[PlanCreate] = []
    renames: list[PlanRename] = []
    overwrites: list[PlanOverwrite] = []
    skips: list[PlanSkip] = []
    conflicts: list[PlanConflict] = []
    counts: dict[str, int] = {}


class UploadResponse(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]
    message: str
    warnings: list[str] = []
    feedbacks: list[dict] = []
    dry_run: bool = False
    plan: Optional[UploadPlan] = None


class SampleConflictMatch(BaseModel):
    sample_id: str
    similarity: float


class SampleConflict(BaseModel):
    incoming_id: str
    normalized: str
    candidate_matches: list[SampleConflictMatch]


class ConflictCheckResponse(BaseModel):
    status: Literal["warnings"]
    conflicts: list[SampleConflict]
    message: str
