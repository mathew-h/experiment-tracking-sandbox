from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from database.models.enums import AmmoniumQuantMethod
from backend.api.schemas.experiments import NoteResponse


class ResultCreate(BaseModel):
    model_config = ConfigDict(strict=True)

    # experiment_fk must be experiments.id (the integer primary key), NOT the
    # human-readable experiment_id string (e.g. "HPHT_001").  Resolve the full
    # Experiment object from the API first, then pass experiment.id here.
    experiment_fk: int = Field(
        description="FK to experiments.id (integer PK). Never pass the string experiment_id."
    )
    time_post_reaction_days: Optional[float] = None
    time_post_reaction_bucket_days: Optional[float] = None
    cumulative_time_post_reaction_days: Optional[float] = None
    is_primary_timepoint_result: bool = True


class ResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_fk: int
    time_post_reaction_days: Optional[float] = None
    time_post_reaction_bucket_days: Optional[float] = None
    cumulative_time_post_reaction_days: Optional[float] = None
    is_primary_timepoint_result: bool
    created_at: datetime


class ScalarCreate(BaseModel):
    result_id: int
    final_ph: Optional[float] = None
    final_conductivity_mS_cm: Optional[float] = None
    final_dissolved_oxygen_mg_L: Optional[float] = None
    final_nitrate_concentration_mM: Optional[float] = None
    final_alkalinity_mg_L: Optional[float] = None
    gross_ammonium_concentration_mM: Optional[float] = None
    background_ammonium_concentration_mM: Optional[float] = 0.2
    ammonium_quant_method: Optional[AmmoniumQuantMethod] = None
    ferrous_iron_yield: Optional[float] = None
    sampling_volume_mL: Optional[float] = None
    measurement_date: Optional[datetime] = None
    nmr_run_date: Optional[datetime] = None
    icp_run_date: Optional[datetime] = None
    gc_run_date: Optional[datetime] = None
    xrd_run_date: Optional[datetime] = None
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
    nmr_run_date: Optional[datetime] = None
    icp_run_date: Optional[datetime] = None
    gc_run_date: Optional[datetime] = None
    xrd_run_date: Optional[datetime] = None


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
    nmr_run_date: Optional[datetime] = None
    icp_run_date: Optional[datetime] = None
    gc_run_date: Optional[datetime] = None
    xrd_run_date: Optional[datetime] = None
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
                "sr","y","nb","sb","cs","ba","nd","gd","pt","rh","ir","pd","ru","os","tl",
                "ag","ce","k","la","na","pb","sc","th","v","s","ti"]


class ResultWithFlagsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_fk: int
    time_post_reaction_days: Optional[float] = None
    time_post_reaction_bucket_days: Optional[float] = None
    cumulative_time_post_reaction_days: Optional[float] = None
    is_primary_timepoint_result: bool
    created_at: datetime
    # Read-only here (issue #146); written by the result-entry endpoints.
    sample_tube_number: Optional[int] = None
    has_scalar: bool = False
    has_icp: bool = False
    # Issue #118 PR3: the MOD badge is now "this timepoint has a 'modification'
    # note" (EXISTS over experiment_notes); the legacy per-result flag column was
    # dropped by issue #122 PR-D. Not a calculation-engine field -- nothing in
    # backend/services/calculations/ references notes and it must stay that way.
    has_modification_note: bool = False
    # Every typed note scoped to this result, in id order.
    notes: list[NoteResponse] = []
    # Key scalar values for the list (None if no scalar)
    grams_per_ton_yield: Optional[float] = None
    h2_concentration: Optional[float] = None
    h2_grams_per_ton_yield: Optional[float] = None
    h2_micromoles: Optional[float] = None
    gross_ammonium_concentration_mM: Optional[float] = None
    background_ammonium_concentration_mM: Optional[float] = None
    final_conductivity_mS_cm: Optional[float] = None
    final_ph: Optional[float] = None
    scalar_measurement_date: Optional[datetime] = None
    ferrous_iron_yield_h2_pct: Optional[float] = None
    ferrous_iron_yield_nh3_pct: Optional[float] = None
    nmr_run_date: Optional[datetime] = None
    icp_run_date: Optional[datetime] = None
    gc_run_date: Optional[datetime] = None
    xrd_run_date: Optional[datetime] = None


class _ResultEntryFields(BaseModel):
    """Optional fields shared by hand-entry create and edit (STANDARD_PROFILE in
    backend/services/result_entry_service.py; one definition of each constraint)."""
    model_config = ConfigDict(extra="forbid")

    gc_run_date: Optional[datetime] = None
    sample_tube_number: Optional[int] = Field(None, gt=0)
    sampling_volume_mL: Optional[float] = Field(None, ge=0)
    h2_concentration: Optional[float] = Field(None, ge=0)
    gas_sampling_volume_ml: Optional[float] = Field(None, ge=0)
    gas_sampling_pressure_MPa: Optional[float] = Field(None, ge=0)
    final_ph: Optional[float] = None
    final_conductivity_mS_cm: Optional[float] = None
    gross_ammonium_concentration_mM: Optional[float] = Field(None, ge=0)
    # The sample's first result_note; blank on edit deletes it.
    result_note: Optional[str] = Field(None, max_length=2000)
    # Non-blank appends a new 'modification' note; existing ones are never edited.
    modification_note: Optional[str] = Field(None, max_length=2000)


class ResultEntryCreate(_ResultEntryFields):
    """Body of POST /api/experiments/{experiment_id}/results (not Core Flood)."""
    measurement_date: datetime
    # Omitted: derived from measurement_date - experiment start (lab-local).
    time_post_reaction_days: Optional[float] = Field(None, ge=0)


class ResultEntryUpdate(_ResultEntryFields):
    """Body of PATCH /api/experiments/{experiment_id}/results/{result_id}; the day
    is not editable."""
    measurement_date: Optional[datetime] = None

    @field_validator("measurement_date")
    @classmethod
    def _omittable_not_nullable(cls, v):
        # Omitting it leaves the date alone (validators skip unset defaults);
        # an explicit null is rejected.
        if v is None:
            raise ValueError("may be omitted but not null")
        return v


class BackgroundAmmoniumUpdate(BaseModel):
    value: float = Field(ge=0.0, description="Background ammonium concentration to apply to all timepoints (mM)")


class BackgroundAmmoniumUpdated(BaseModel):
    updated: int


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
    ag: Optional[float] = None
    ce: Optional[float] = None
    k:  Optional[float] = None
    la: Optional[float] = None
    na: Optional[float] = None
    pb: Optional[float] = None
    sc: Optional[float] = None
    th: Optional[float] = None
    v:  Optional[float] = None
    s:  Optional[float] = None
    ti: Optional[float] = None


class ICPResponse(ICPCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class RollupTimepointResponse(BaseModel):
    """One row of v_results_scalar_rollup: cross-replicate stats per timepoint bucket.

    Field names match the view's (quoted, mixed-case) column aliases exactly.
    """
    base_experiment_id: str
    time_post_reaction_bucket_days: Optional[float] = None
    # Replaced the former single `n_replicates` (2026-08-01). It counted
    # scalar ROWS, so it read 0 for ICP-only timepoints and over-counted a
    # vial holding several primary rows. See
    # docs/issues/issue-rollup-replicate-count-and-null-timepoint-buckets.md
    n_vials: int
    n_replicate_letters: int
    n_values: int
    mean_gross_ammonium_mM: Optional[float] = None
    median_gross_ammonium_mM: Optional[float] = None
    sd_gross_ammonium_mM: Optional[float] = None
    mean_net_ammonium_mM: Optional[float] = None
    sd_net_ammonium_mM: Optional[float] = None
    mean_h2_ppm: Optional[float] = None
    sd_h2_ppm: Optional[float] = None
    mean_h2_micromoles: Optional[float] = None
    sd_h2_micromoles: Optional[float] = None
    mean_h2_grams_per_ton: Optional[float] = None
    sd_h2_grams_per_ton: Optional[float] = None
    mean_fe_yield_h2_pct: Optional[float] = None
    sd_fe_yield_h2_pct: Optional[float] = None
    mean_fe_yield_nh3_pct: Optional[float] = None
    sd_fe_yield_nh3_pct: Optional[float] = None
    mean_grams_per_ton_yield: Optional[float] = None
    sd_grams_per_ton_yield: Optional[float] = None
    mean_final_ph: Optional[float] = None
    # Issue #152: true when every non-outlier member of the group is a
    # background, so these statistics are the background's own.
    is_background_group: bool = False


class IcpRow(BaseModel):
    """One sample's ICP-OES reading (non-null fixed elements only, ppm).

    Shared by GET /api/core-floods/{base_id}/icp and
    GET /api/experiments/{experiment_id}/icp (issue #143)."""
    result_id: int
    experiment_id: str
    is_variant: bool
    cumulative_time_post_reaction_days: Optional[float] = None
    sample_date: Optional[datetime] = None
    elements: dict[str, float]


class IcpSegmentStart(BaseModel):
    """First cumulative day of a chained segment (an experiment with a parent
    that is not a `_Text` variant); drawn as a marker on the ICP chart."""
    experiment_id: str
    day: float


class ExperimentIcpResponse(BaseModel):
    rows: list[IcpRow]
    segment_starts: list[IcpSegmentStart]
