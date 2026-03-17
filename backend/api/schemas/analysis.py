from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class XRDPhaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mineral_name: str
    amount: Optional[float] = None
    time_post_reaction_days: Optional[float] = None
    measurement_date: Optional[datetime] = None
    rwp: Optional[float] = None


class PXRFResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reading_no: str
    fe: Optional[float] = None
    mg: Optional[float] = None
    ni: Optional[float] = None
    cu: Optional[float] = None
    si: Optional[float] = None
    co: Optional[float] = None
    mo: Optional[float] = None
    al: Optional[float] = None
    ca: Optional[float] = None
    zn: Optional[float] = None
    ingested_at: datetime


class ExternalAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sample_id: Optional[str] = None
    experiment_id: Optional[str] = None
    analysis_type: Optional[str] = None
    analysis_date: Optional[datetime] = None
    laboratory: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime
