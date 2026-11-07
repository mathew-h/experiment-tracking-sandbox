from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Upper bound for serum_vial_size_mL. The column is int4; an unbounded value would
# pass validation and 500 at flush. App-layer cap only (no DB CHECK).
SERUM_VIAL_SIZE_MAX_ML = 10_000


def _normalize_series(v: object) -> object:
    """Blank -> None and upper-case, so 'p' and ' P ' reach the CHECK as 'P'.

    Whether the value is allowed for the experiment type is checked in the
    router (it needs the stored type on PATCH).
    """
    if isinstance(v, str):
        v = v.strip().upper()
        return v or None
    return v


class ConditionsCreate(BaseModel):
    experiment_fk: int
    experiment_id: str
    temperature_c: Optional[float] = None
    initial_ph: Optional[float] = None
    rock_mass_g: Optional[float] = None
    water_volume_mL: Optional[float] = None
    # Nominal serum vial size, whole mL. Positive integer, capped at
    # SERUM_VIAL_SIZE_MAX_ML (10,000); 120.0 coerces to 120, 120.5 is rejected. Accepted on any experiment type -- "Serum only" is
    # a UI rule, not an API rule.
    serum_vial_size_mL: Optional[int] = Field(default=None, gt=0, le=SERUM_VIAL_SIZE_MAX_ML)
    # Core pore volume in mL (Core Flood). Float column, so no upper bound.
    pore_volume_mL: Optional[float] = Field(default=None, gt=0)
    experiment_type: Optional[str] = None
    reactor_number: Optional[int] = None
    # Slot series for reactor_number (issue #147): None = the type's default
    # (R for HPHT, CF for Core Flood); 'P' = Parr vessels P01-P06, HPHT only.
    reactor_series: Optional[str] = Field(default=None, max_length=4)

    _norm_series = field_validator("reactor_series", mode="before")(_normalize_series)
    feedstock: Optional[str] = None
    particle_size: Optional[str] = None
    stir_speed_rpm: Optional[float] = None
    room_temp_pressure_psi: Optional[float] = None
    rxn_temp_pressure_psi: Optional[float] = None
    initial_conductivity_mS_cm: Optional[float] = None
    co2_partial_pressure_MPa: Optional[float] = None
    confining_pressure: Optional[float] = None
    pore_pressure: Optional[float] = None
    flow_rate: Optional[float] = None
    initial_nitrate_concentration: Optional[float] = None
    initial_dissolved_oxygen: Optional[float] = None
    initial_alkalinity: Optional[float] = None
    total_ferrous_iron: Optional[float] = None
    core_height_cm: Optional[float] = None
    core_width_cm: Optional[float] = None
    core_volume_cm3: Optional[float] = None


class ConditionsUpdate(BaseModel):
    temperature_c: Optional[float] = None
    initial_ph: Optional[float] = None
    rock_mass_g: Optional[float] = None
    water_volume_mL: Optional[float] = None
    serum_vial_size_mL: Optional[int] = Field(default=None, gt=0, le=SERUM_VIAL_SIZE_MAX_ML)
    pore_volume_mL: Optional[float] = Field(default=None, gt=0)
    experiment_type: Optional[str] = None
    reactor_number: Optional[int] = None
    # Slot series for reactor_number (issue #147): None = the type's default
    # (R for HPHT, CF for Core Flood); 'P' = Parr vessels P01-P06, HPHT only.
    reactor_series: Optional[str] = Field(default=None, max_length=4)

    _norm_series = field_validator("reactor_series", mode="before")(_normalize_series)
    feedstock: Optional[str] = None
    particle_size: Optional[str] = None
    stir_speed_rpm: Optional[float] = None
    room_temp_pressure_psi: Optional[float] = None
    rxn_temp_pressure_psi: Optional[float] = None
    initial_conductivity_mS_cm: Optional[float] = None
    co2_partial_pressure_MPa: Optional[float] = None
    initial_nitrate_concentration: Optional[float] = None
    initial_dissolved_oxygen: Optional[float] = None
    initial_alkalinity: Optional[float] = None
    total_ferrous_iron: Optional[float] = None
    confining_pressure: Optional[float] = None
    pore_pressure: Optional[float] = None
    core_height_cm: Optional[float] = None
    core_width_cm: Optional[float] = None
    core_volume_cm3: Optional[float] = None


class ConditionsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_fk: int
    experiment_id: str
    temperature_c: Optional[float] = None
    initial_ph: Optional[float] = None
    rock_mass_g: Optional[float] = None
    water_volume_mL: Optional[float] = None
    serum_vial_size_mL: Optional[int] = None
    pore_volume_mL: Optional[float] = None
    water_to_rock_ratio: Optional[float] = None
    total_ferrous_iron_g: Optional[float] = None
    experiment_type: Optional[str] = None
    reactor_number: Optional[int] = None
    reactor_series: Optional[str] = None
    reactor_slot: Optional[str] = None
    feedstock: Optional[str] = None
    particle_size: Optional[str] = None
    stir_speed_rpm: Optional[float] = None
    room_temp_pressure_psi: Optional[float] = None
    rxn_temp_pressure_psi: Optional[float] = None
    initial_conductivity_mS_cm: Optional[float] = None
    co2_partial_pressure_MPa: Optional[float] = None
    initial_nitrate_concentration: Optional[float] = None
    initial_dissolved_oxygen: Optional[float] = None
    initial_alkalinity: Optional[float] = None
    total_ferrous_iron: Optional[float] = None
    confining_pressure: Optional[float] = None
    pore_pressure: Optional[float] = None
    core_height_cm: Optional[float] = None
    core_width_cm: Optional[float] = None
    core_volume_cm3: Optional[float] = None
    created_at: datetime
