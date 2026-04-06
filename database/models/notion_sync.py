"""ReactorChangeRequest — daily Notion reactor change request import."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func

from ..database import Base


class ReactorChangeRequest(Base):
    """One row per reactor per sync date; upserted on re-run."""

    __tablename__ = "reactor_change_requests"

    id: int = Column(Integer, primary_key=True)
    reactor_label: str = Column(String(10), nullable=False)
    # Nullable FK — not resolved during import; populated by future logic if needed.
    experiment_id: str | None = Column(
        String,
        ForeignKey("experiments.experiment_id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_change: str = Column(String, nullable=False)
    notion_status: str = Column(String(50), nullable=False)
    carried_forward: bool = Column(Boolean, nullable=False, default=False)
    date: date = Column(Date, nullable=False)
    # 32-char UUID (hyphens stripped) for Notion page traceability.
    notion_page_id: str = Column(String(32), nullable=False)
    created_at: datetime = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("reactor_label", "date", name="uq_change_request_reactor_date"),
    )
