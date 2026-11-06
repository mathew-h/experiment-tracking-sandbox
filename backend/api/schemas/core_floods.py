from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

WarningCode = Literal[
    "multiple_roots", "multiple_ongoing", "missing_pore_volume",
    "missing_description", "sample_missing_flow_rate",
]


class CoreFloodWarning(BaseModel):
    code: WarningCode
    experiment_ids: list[str]


class CoreFloodSegment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: str
    status: Optional[str] = None
    date: Optional[datetime] = None
    parent_experiment_id: Optional[str] = None
    is_variant: bool
    description: Optional[str] = None
    # Not in the spec: the run page edits pore volume via PATCH /api/conditions/{id}.
    conditions_id: Optional[int] = None
    pore_volume_mL: Optional[float] = None
    rock_mass_g: Optional[float] = None
    reactor_slot: Optional[str] = None


class CoreFloodSampleNote(BaseModel):
    """A result-scoped note shown on a sample (never the experiment description)."""
    id: int
    note_type: Literal["observation", "result_note", "modification"]
    note_text: str
    created_by: Optional[str] = None


class CoreFloodSample(BaseModel):
    """One v_core_flood_samples row; field names are the view's column names."""
    model_config = ConfigDict(from_attributes=True)

    result_id: int
    experiment_id: str
    experiment_fk: int
    run_base_id: Optional[str] = None
    is_variant: bool
    time_post_reaction_days: Optional[float] = None
    cumulative_time_post_reaction_days: Optional[float] = None
    sample_date: Optional[datetime] = None
    gc_run_date: Optional[datetime] = None
    sample_tube_number: Optional[int] = None
    flow_rate_mL_min: Optional[float] = None
    nitrogen_flow_rate_mL_min: Optional[float] = None
    inlet_pressure_psi: Optional[float] = None
    outlet_pressure_psi: Optional[float] = None
    permeability_flow_rate_mL_min: Optional[float] = None
    sampling_volume_mL: Optional[float] = None
    h2_concentration: Optional[float] = None
    gas_sampling_volume_ml: Optional[float] = None
    gas_sampling_pressure_MPa: Optional[float] = None
    h2_micromoles: Optional[float] = None
    h2_mass_ug: Optional[float] = None
    h2_grams_per_ton_yield: Optional[float] = None
    final_ph: Optional[float] = None
    final_conductivity_mS_cm: Optional[float] = None
    pore_volume_mL: Optional[float] = None
    interval_days: Optional[float] = None
    cumulative_liquid_volume_mL: Optional[float] = None
    cumulative_pore_volumes: Optional[float] = None
    cumulative_h2_grams_per_ton: Optional[float] = None
    h2_grams_per_ton_per_day: Optional[float] = None
    is_hold_interval: Optional[bool] = None
    notes: list[CoreFloodSampleNote] = []


class CoreFloodRun(BaseModel):
    base_id: str
    segments: list[CoreFloodSegment]
    samples: list[CoreFloodSample]
    warnings: list[CoreFloodWarning]


class CoreFloodRunListItem(BaseModel):
    base_id: str
    description: Optional[str] = None
    segment_count: int
    ongoing_experiment_ids: list[str]
    rig: Optional[str] = None
    sample_count: int
    first_sample_date: Optional[datetime] = None
    last_sample_date: Optional[datetime] = None
    latest_cumulative_h2_grams_per_ton: Optional[float] = None
    warning_count: int


class _CoreFloodSampleFields(BaseModel):
    """Optional sample fields shared by create and edit (one definition of each constraint)."""
    model_config = ConfigDict(extra="forbid")

    gc_run_date: Optional[datetime] = None
    sample_tube_number: Optional[int] = Field(None, gt=0)
    sampling_volume_mL: Optional[float] = Field(None, ge=0)
    h2_concentration: Optional[float] = Field(None, ge=0)
    gas_sampling_volume_ml: Optional[float] = Field(None, ge=0)
    gas_sampling_pressure_MPa: Optional[float] = Field(None, ge=0)
    final_ph: Optional[float] = None
    final_conductivity_mS_cm: Optional[float] = None
    nitrogen_flow_rate_mL_min: Optional[float] = None
    inlet_pressure_psi: Optional[float] = None
    outlet_pressure_psi: Optional[float] = None
    permeability_flow_rate_mL_min: Optional[float] = Field(None, gt=0)
    # Edits the sample's first result_note; blank deletes it (see core_flood_service).
    result_note: Optional[str] = Field(None, max_length=2000)


class CoreFloodSampleCreate(_CoreFloodSampleFields):
    """Body of POST /api/core-floods/{experiment_id}/samples."""
    measurement_date: datetime
    time_post_reaction_days: Optional[float] = Field(None, ge=0)
    flow_rate_mL_min: float = Field(..., ge=0)


class CoreFloodSampleUpdate(_CoreFloodSampleFields):
    """Body of PATCH /api/core-floods/samples/{result_id}; the day is not editable."""
    measurement_date: Optional[datetime] = None
    flow_rate_mL_min: Optional[float] = Field(None, ge=0)

    @field_validator("measurement_date", "flow_rate_mL_min")
    @classmethod
    def _omittable_not_nullable(cls, v):
        # Omitting either field leaves it alone (validators skip unset defaults);
        # an explicit null is rejected. A hold is flow 0, not null.
        if v is None:
            raise ValueError("may be omitted but not null")
        return v
