from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from database.models.enums import AmountUnit


class CompoundCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    formula: Optional[str] = None
    cas_number: Optional[str] = Field(
        None,
        min_length=5,
        max_length=20,
        pattern=r'^[\d\-\.]+$',
    )
    molecular_weight_g_mol: Optional[float] = Field(None, gt=0, le=10000)
    density_g_cm3: Optional[float] = Field(None, gt=0, le=50)
    melting_point_c: Optional[float] = None
    boiling_point_c: Optional[float] = None
    solubility: Optional[str] = None
    hazard_class: Optional[str] = None
    supplier: Optional[str] = None
    catalog_number: Optional[str] = None
    notes: Optional[str] = None
    preferred_unit: Optional[AmountUnit] = None
    elemental_fraction: Optional[float] = None
    catalyst_formula: Optional[str] = None


class CompoundUpdate(BaseModel):
    """Partial update — all fields optional, same validation rules as CompoundCreate."""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    formula: Optional[str] = None
    cas_number: Optional[str] = Field(
        None,
        min_length=5,
        max_length=20,
        pattern=r'^[\d\-\.]+$',
    )
    molecular_weight_g_mol: Optional[float] = Field(None, gt=0, le=10000)
    density_g_cm3: Optional[float] = Field(None, gt=0, le=50)
    melting_point_c: Optional[float] = None
    boiling_point_c: Optional[float] = None
    solubility: Optional[str] = None
    hazard_class: Optional[str] = None
    supplier: Optional[str] = None
    catalog_number: Optional[str] = None
    notes: Optional[str] = None
    preferred_unit: Optional[AmountUnit] = None
    elemental_fraction: Optional[float] = None
    catalyst_formula: Optional[str] = None


class CompoundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    formula: Optional[str] = None
    cas_number: Optional[str] = None
    molecular_weight_g_mol: Optional[float] = None
    density_g_cm3: Optional[float] = None
    melting_point_c: Optional[float] = None
    boiling_point_c: Optional[float] = None
    solubility: Optional[str] = None
    hazard_class: Optional[str] = None
    preferred_unit: Optional[AmountUnit] = None
    supplier: Optional[str] = None
    catalog_number: Optional[str] = None
    notes: Optional[str] = None
    elemental_fraction: Optional[float] = None
    catalyst_formula: Optional[str] = None


class ChemicalAdditiveUpsert(BaseModel):
    """Payload for PUT /api/experiments/{id}/additives/{compound_id}.

    compound_id and experiment_id are provided via path parameters, not in the body.
    """
    amount: float = Field(gt=0)
    unit: AmountUnit
    addition_order: Optional[int] = None
    addition_method: Optional[str] = None
    purity: Optional[float] = None
    lot_number: Optional[str] = None


class AdditiveCreate(BaseModel):
    compound_id: int
    amount: float = Field(gt=0)
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
