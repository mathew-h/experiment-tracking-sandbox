from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ConditionsCreate(BaseModel):
    experiment_fk: int
    experiment_id: str
    temperature_c: Optional[float] = None
    initial_ph: Optional[float] = None
    rock_mass_g: Optional[float] = None
    water_volume_mL: Optional[float] = None
    experiment_type: Optional[str] = None
    reactor_number: Optional[int] = None
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
    experiment_type: Optional[str] = None
    reactor_number: Optional[int] = None
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
    water_to_rock_ratio: Optional[float] = None
    experiment_type: Optional[str] = None
    reactor_number: Optional[int] = None
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
