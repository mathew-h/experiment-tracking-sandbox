# backend/api/schemas/samples.py
from __future__ import annotations
from datetime import date, datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict


# ── Core sample schemas ────────────────────────────────────────────────────

class SampleCreate(BaseModel):
    sample_id: str
    rock_classification: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    well_name: Optional[str] = None
    core_lender: Optional[str] = None
    core_interval_ft: Optional[str] = None
    on_loan_return_date: Optional[date] = None


class SampleUpdate(BaseModel):
    rock_classification: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    characterized: Optional[bool] = None
    well_name: Optional[str] = None
    core_lender: Optional[str] = None
    core_interval_ft: Optional[str] = None
    on_loan_return_date: Optional[date] = None


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
    well_name: Optional[str] = None
    core_lender: Optional[str] = None
    core_interval_ft: Optional[str] = None
    on_loan_return_date: Optional[date] = None
    created_at: datetime


# ── List view (no nested objects) ─────────────────────────────────────────

class SampleListItem(BaseModel):
    """Flat projection for the inventory table — no nested objects."""
    model_config = ConfigDict(from_attributes=True)

    sample_id: str
    rock_classification: Optional[str] = None
    locality: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    description: Optional[str] = None
    characterized: bool
    experiment_count: int = 0
    has_pxrf: bool = False
    has_xrd: bool = False
    has_elemental: bool = False
    created_at: datetime


class SampleListResponse(BaseModel):
    items: list[SampleListItem]
    total: int
    skip: int
    limit: int


# ── Geo view (map markers) ────────────────────────────────────────────────

class SampleGeoItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sample_id: str
    latitude: float
    longitude: float
    rock_classification: Optional[str] = None
    characterized: bool


# ── Photo schemas ─────────────────────────────────────────────────────────

class SamplePhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sample_id: str
    file_name: Optional[str] = None
    file_path: str
    file_type: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime


# ── Analysis schemas ──────────────────────────────────────────────────────

ANALYSIS_TYPE = Literal["pXRF", "XRD", "Elemental", "Titration", "Magnetic Susceptibility", "Other"]

class ExternalAnalysisCreate(BaseModel):
    analysis_type: ANALYSIS_TYPE  # validated against known types
    analysis_date: Optional[datetime] = None
    laboratory: Optional[str] = None
    analyst: Optional[str] = None
    pxrf_reading_no: Optional[str] = None  # comma-separated reading numbers
    description: Optional[str] = None
    magnetic_susceptibility: Optional[str] = None


class AnalysisFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_analysis_id: int
    file_name: Optional[str] = None
    file_path: str
    file_type: Optional[str] = None
    created_at: datetime


class PXRFElementalData(BaseModel):
    """Averaged elemental values from one or more pXRF readings."""
    reading_count: int
    fe: Optional[float] = None
    mg: Optional[float] = None
    ni: Optional[float] = None
    cu: Optional[float] = None
    si: Optional[float] = None
    co: Optional[float] = None
    mo: Optional[float] = None
    al: Optional[float] = None
    ca: Optional[float] = None
    k: Optional[float] = None
    au: Optional[float] = None
    zn: Optional[float] = None


class XRDPhaseData(BaseModel):
    """Mineral phase data from an XRD analysis."""
    mineral_phases: dict[str, float]
    analysis_parameters: Optional[dict] = None


class ExternalAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sample_id: Optional[str] = None
    analysis_type: Optional[str] = None
    analysis_date: Optional[datetime] = None
    laboratory: Optional[str] = None
    analyst: Optional[str] = None
    pxrf_reading_no: Optional[str] = None
    description: Optional[str] = None
    magnetic_susceptibility: Optional[str] = None
    created_at: datetime
    analysis_files: list[AnalysisFileResponse] = []
    pxrf_data: Optional[PXRFElementalData] = None
    xrd_data: Optional[XRDPhaseData] = None


class ExternalAnalysisWithWarnings(BaseModel):
    analysis: ExternalAnalysisResponse
    warnings: list[str] = []


# ── Detail view (full nested) ─────────────────────────────────────────────

class LinkedExperiment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    experiment_id: str
    experiment_type: Optional[str] = None  # from ExperimentalConditions.experiment_type
    status: Optional[str] = None
    date: Optional[datetime] = None


class ElementalAnalysisItem(BaseModel):
    """One analyte row from ElementalAnalysis, for the Analyses tab elemental group."""
    model_config = ConfigDict(from_attributes=True)

    analyte_symbol: str
    unit: str
    analyte_composition: Optional[float] = None


class SampleDetail(BaseModel):
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
    well_name: Optional[str] = None
    core_lender: Optional[str] = None
    core_interval_ft: Optional[str] = None
    on_loan_return_date: Optional[date] = None
    created_at: datetime
    photos: list[SamplePhotoResponse] = []
    analyses: list[ExternalAnalysisResponse] = []
    elemental_results: list[ElementalAnalysisItem] = []
    experiments: list[LinkedExperiment] = []
