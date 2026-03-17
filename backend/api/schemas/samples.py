from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class SampleCreate(BaseModel):
    sample_id: str
    rock_classification: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None


class SampleUpdate(BaseModel):
    rock_classification: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    characterized: Optional[bool] = None


class SampleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sample_id: str
    rock_classification: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    characterized: bool
    created_at: datetime
