from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from database.models.enums import AmmoniumQuantMethod


class ResultCreate(BaseModel):
    experiment_fk: int
    time_post_reaction_days: Optional[float] = None
    time_post_reaction_bucket_days: Optional[float] = None
    cumulative_time_post_reaction_days: Optional[float] = None
    is_primary_timepoint_result: bool = True
    description: str


class ResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_fk: int
    time_post_reaction_days: Optional[float] = None
    time_post_reaction_bucket_days: Optional[float] = None
    cumulative_time_post_reaction_days: Optional[float] = None
    is_primary_timepoint_result: bool
    description: str
    created_at: datetime


class ScalarCreate(BaseModel):
    result_id: int
    final_ph: Optional[float] = None
    final_conductivity_mS_cm: Optional[float] = None
    final_dissolved_oxygen_mg_L: Optional[float] = None
    final_nitrate_concentration_mM: Optional[float] = None
    final_alkalinity_mg_L: Optional[float] = None
    gross_ammonium_concentration_mM: Optional[float] = None
    background_ammonium_concentration_mM: Optional[float] = None
    ammonium_quant_method: Optional[AmmoniumQuantMethod] = None
    ferrous_iron_yield: Optional[float] = None
    sampling_volume_mL: Optional[float] = None
    measurement_date: Optional[datetime] = None
    h2_concentration: Optional[float] = None
    h2_concentration_unit: Optional[str] = "ppm"
    gas_sampling_volume_ml: Optional[float] = None
    gas_sampling_pressure_MPa: Optional[float] = None
    background_experiment_fk: Optional[int] = None
    co2_partial_pressure_MPa: Optional[float] = None


class ScalarUpdate(BaseModel):
    final_ph: Optional[float] = None
    gross_ammonium_concentration_mM: Optional[float] = None
    background_ammonium_concentration_mM: Optional[float] = None
    h2_concentration: Optional[float] = None
    gas_sampling_volume_ml: Optional[float] = None
    gas_sampling_pressure_MPa: Optional[float] = None
    sampling_volume_mL: Optional[float] = None
    ferrous_iron_yield: Optional[float] = None
    measurement_date: Optional[datetime] = None


class ScalarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    result_id: int
    final_ph: Optional[float] = None
    final_conductivity_mS_cm: Optional[float] = None
    final_dissolved_oxygen_mg_L: Optional[float] = None
    final_nitrate_concentration_mM: Optional[float] = None
    final_alkalinity_mg_L: Optional[float] = None
    gross_ammonium_concentration_mM: Optional[float] = None
    background_ammonium_concentration_mM: Optional[float] = None
    grams_per_ton_yield: Optional[float] = None
    ammonium_quant_method: Optional[AmmoniumQuantMethod] = None
    ferrous_iron_yield: Optional[float] = None
    sampling_volume_mL: Optional[float] = None
    measurement_date: Optional[datetime] = None
    h2_concentration: Optional[float] = None
    h2_concentration_unit: Optional[str] = None
    gas_sampling_volume_ml: Optional[float] = None
    gas_sampling_pressure_MPa: Optional[float] = None
    h2_micromoles: Optional[float] = None
    h2_mass_ug: Optional[float] = None
    h2_grams_per_ton_yield: Optional[float] = None
    ferrous_iron_yield_h2_pct: Optional[float] = None
    ferrous_iron_yield_nh3_pct: Optional[float] = None
    co2_partial_pressure_MPa: Optional[float] = None
    background_experiment_fk: Optional[int] = None


ICP_ELEMENTS = ["fe","si","mg","ca","ni","cu","mo","zn","mn","cr","co","al",
                "sr","y","nb","sb","cs","ba","nd","gd","pt","rh","ir","pd","ru","os","tl"]


class ResultWithFlagsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_fk: int
    time_post_reaction_days: Optional[float] = None
    time_post_reaction_bucket_days: Optional[float] = None
    cumulative_time_post_reaction_days: Optional[float] = None
    is_primary_timepoint_result: bool
    description: str
    created_at: datetime
    has_scalar: bool = False
    has_icp: bool = False
    has_brine_modification: bool = False
    brine_modification_description: Optional[str] = None
    # Key scalar values for the list (None if no scalar)
    grams_per_ton_yield: Optional[float] = None
    h2_grams_per_ton_yield: Optional[float] = None
    h2_micromoles: Optional[float] = None
    gross_ammonium_concentration_mM: Optional[float] = None
    final_conductivity_mS_cm: Optional[float] = None
    final_ph: Optional[float] = None


class ICPCreate(BaseModel):
    result_id: int
    dilution_factor: Optional[float] = None
    instrument_used: Optional[str] = None
    raw_label: Optional[str] = None
    measurement_date: Optional[datetime] = None
    sample_date: Optional[datetime] = None
    all_elements: Optional[dict] = None
    # fixed element columns — all optional
    fe: Optional[float] = None
    si: Optional[float] = None
    mg: Optional[float] = None
    ca: Optional[float] = None
    ni: Optional[float] = None
    cu: Optional[float] = None
    mo: Optional[float] = None
    zn: Optional[float] = None
    mn: Optional[float] = None
    cr: Optional[float] = None
    co: Optional[float] = None
    al: Optional[float] = None
    sr: Optional[float] = None
    y:  Optional[float] = None
    nb: Optional[float] = None
    sb: Optional[float] = None
    cs: Optional[float] = None
    ba: Optional[float] = None
    nd: Optional[float] = None
    gd: Optional[float] = None
    pt: Optional[float] = None
    rh: Optional[float] = None
    ir: Optional[float] = None
    pd: Optional[float] = None
    ru: Optional[float] = None
    os: Optional[float] = None
    tl: Optional[float] = None


class ICPResponse(ICPCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
