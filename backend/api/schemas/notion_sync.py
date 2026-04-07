from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ChangeRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reactor_label: str
    requested_change: str
    notion_status: str
    carried_forward: bool
    sync_date: date
    created_at: datetime
