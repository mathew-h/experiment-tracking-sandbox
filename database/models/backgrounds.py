"""H2BackgroundLink — the background serum vials to subtract from a group's H2.

Issue #144.

One row per sample base experiment. Exactly one of background_base_id (a whole
background replicate set, averaged) or background_stem_id (a single background
vial stem) is set. Bare String IDs, no FKs, matching ModificationsLog.sample_id.
"""
from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String, func

from ..database import Base


class H2BackgroundLink(Base):
    __tablename__ = "h2_background_links"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(background_base_id, background_stem_id) = 1",
            name="ck_h2_background_links_one_ref",
        ),
        CheckConstraint(
            "background_base_id IS DISTINCT FROM base_experiment_id",
            name="ck_h2_background_links_not_self",
        ),
    )

    id = Column(Integer, primary_key=True)
    base_experiment_id = Column(String, nullable=False, unique=True)
    background_base_id = Column(String, nullable=True)
    background_stem_id = Column(String, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
