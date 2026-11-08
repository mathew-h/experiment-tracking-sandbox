"""Schemas shared by the run pages (Core Flood #133, HPHT #149).

A run is every experiment of one series sharing a base_experiment_id.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class RunSegment(BaseModel):
    """One experiment of a run: a segment (X_001, X_001-2) or a `_Text` variant."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: str
    status: Optional[str] = None
    date: Optional[datetime] = None
    parent_experiment_id: Optional[str] = None
    is_variant: bool
    description: Optional[str] = None
    # The run pages edit conditions via PATCH /api/conditions/{id}.
    conditions_id: Optional[int] = None
    # Core Flood only; always null on HPHT segments.
    pore_volume_mL: Optional[float] = None
    rock_mass_g: Optional[float] = None
    reactor_slot: Optional[str] = None


class RunSampleNote(BaseModel):
    """A result-scoped note shown on a sample (never the experiment description)."""
    id: int
    note_type: Literal["observation", "result_note", "modification"]
    note_text: str
    created_by: Optional[str] = None
