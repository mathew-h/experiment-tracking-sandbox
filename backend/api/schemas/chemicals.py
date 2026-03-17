from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from database.models.enums import AmountUnit


class CompoundCreate(BaseModel):
    name: str
    formula: Optional[str] = None
    cas_number: Optional[str] = None
    molecular_weight_g_mol: Optional[float] = None
    density_g_cm3: Optional[float] = None
    supplier: Optional[str] = None
    notes: Optional[str] = None
    elemental_fraction: Optional[float] = None
    catalyst_formula: Optional[str] = None
    preferred_unit: Optional[AmountUnit] = None


class CompoundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    formula: Optional[str] = None
    cas_number: Optional[str] = None
    molecular_weight_g_mol: Optional[float] = None
    density_g_cm3: Optional[float] = None
    elemental_fraction: Optional[float] = None
    catalyst_formula: Optional[str] = None
    preferred_unit: Optional[AmountUnit] = None
    supplier: Optional[str] = None
    notes: Optional[str] = None


class AdditiveCreate(BaseModel):
    compound_id: int
    amount: float
    unit: AmountUnit
    addition_order: Optional[int] = None
    addition_method: Optional[str] = None
    purity: Optional[float] = None
    lot_number: Optional[str] = None


class AdditiveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    compound_id: int
    amount: float
    unit: AmountUnit
    mass_in_grams: Optional[float] = None
    moles_added: Optional[float] = None
    final_concentration: Optional[float] = None
    concentration_units: Optional[str] = None
    catalyst_ppm: Optional[float] = None
    catalyst_percentage: Optional[float] = None
    elemental_metal_mass: Optional[float] = None
    compound: Optional[CompoundResponse] = None
