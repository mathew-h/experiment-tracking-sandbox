"""HPHT run page schemas (issue #149). Read-only: samples are written through
POST/PATCH /api/experiments/{experiment_id}/results (#146)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from backend.api.schemas.runs import RunSampleNote, RunSegment

HphtWarningCode = Literal[
    "multiple_roots", "multiple_ongoing", "missing_description", "base_mismatch",
]


class HphtWarning(BaseModel):
    code: HphtWarningCode
    experiment_ids: list[str]


class HphtConditionsSummary(BaseModel):
    """Setup of the run's latest non-variant segment.

    `catalyst` / `catalyst_ppm` are the legacy conditions columns, empty on
    current runs; catalysts live in GET /api/experiments/{experiment_id}/additives.
    """
    experiment_id: str
    conditions_id: int
    date: Optional[datetime] = None
    sample_id: Optional[str] = None
    temperature_c: Optional[float] = None
    rxn_temp_pressure_psi: Optional[float] = None
    rock_mass_g: Optional[float] = None
    water_volume_mL: Optional[float] = None
    water_to_rock_ratio: Optional[float] = None
    catalyst: Optional[str] = None
    catalyst_ppm: Optional[float] = None
    feedstock: Optional[str] = None


class HphtSample(BaseModel):
    """One v_hpht_samples row; field names are the view's column names."""
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
    sampling_volume_mL: Optional[float] = None
    h2_concentration: Optional[float] = None
    gas_sampling_volume_ml: Optional[float] = None
    gas_sampling_pressure_MPa: Optional[float] = None
    h2_micromoles: Optional[float] = None
    h2_mass_ug: Optional[float] = None
    h2_grams_per_ton_yield: Optional[float] = None
    ferrous_iron_yield_h2_pct: Optional[float] = None
    final_ph: Optional[float] = None
    final_conductivity_mS_cm: Optional[float] = None
    reactor_slot: Optional[str] = None
    interval_days: Optional[float] = None
    cumulative_h2_grams_per_ton: Optional[float] = None
    h2_grams_per_ton_per_day: Optional[float] = None
    cumulative_h2_micromoles: Optional[float] = None
    cumulative_ferrous_iron_yield_h2_pct: Optional[float] = None
    notes: list[RunSampleNote] = []


class HphtRun(BaseModel):
    base_id: str
    segments: list[RunSegment]
    conditions: Optional[HphtConditionsSummary] = None
    samples: list[HphtSample]
    warnings: list[HphtWarning]


class HphtRunListItem(BaseModel):
    base_id: str
    description: Optional[str] = None
    segment_count: int
    ongoing_experiment_ids: list[str]
    reactor_slot: Optional[str] = None
    sample_count: int
    last_sample_date: Optional[datetime] = None
    latest_cumulative_h2_grams_per_ton: Optional[float] = None
    warning_count: int
