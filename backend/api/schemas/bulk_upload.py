from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


class UploadResponse(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]
    message: str
    warnings: list[str] = []
    feedbacks: list[dict] = []
    dry_run: bool = False


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
