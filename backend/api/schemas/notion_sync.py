from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ChangeRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reactor_label: str
    requested_change: str
    notion_status: Optional[str] = None
    carried_forward: bool
    sync_date: date
    created_at: datetime


class ChangeRequestUpsertRequest(BaseModel):
    reactor_label: str
    requested_change: str
    sync_date: Optional[date] = None


class RecentChangeRequestsResponse(BaseModel):
    selected: Optional[ChangeRequestResponse] = None
    previous: Optional[ChangeRequestResponse] = None
