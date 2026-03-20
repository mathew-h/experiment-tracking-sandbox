from __future__ import annotations
from pydantic import BaseModel


class UploadResponse(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]
    message: str
    warnings: list[str] = []
    feedbacks: list[dict] = []
