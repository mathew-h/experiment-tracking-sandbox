from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, UniqueConstraint, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base
from .enums import AmountUnit


class Compound(Base):
    """Model for storing chemical compound information that can be reused across experiments"""
    __tablename__ = 'compounds'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)  # e.g., "Sodium Chloride"
    formula = Column(String(50), nullable=True)             # e.g., "NaCl"
    cas_number = Column(String(20), nullable=True, unique=True)  # Optional but highly recommended for lookup

    # Additional chemical properties
    molecular_weight_g_mol = Column(Float, nullable=True)         # g/mol
    density_g_cm3 = Column(Float, nullable=True)                  # g/cm³ for solids, g/mL for liquids
    melting_point_c = Column(Float, nullable=True)           # °C
    boiling_point_c = Column(Float, nullable=True)           # °C
    solubility = Column(String(100), nullable=True)         # Description of solubility
    hazard_class = Column(String(50), nullable=True)       # Safety information

    # Catalyst-specific properties for service functions
    preferred_unit = Column(Enum(AmountUnit), nullable=True)  # Expected input unit (PPM for catalysts, mM for additives)
    catalyst_formula = Column(String(50), nullable=True)      # Full formula with hydration (e.g., "NiCl2·6H2O")
    elemental_fraction = Column(Float, nullable=True)         # Pre-calculated elemental fraction (e.g., 58.69/237.69 for Ni from NiCl2·6H2O)

    # Metadata
    supplier = Column(String(100), nullable=True)
    catalog_number = Column(String(50), nullable=True)
    notes = Column(String(500), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    chemical_additives = relationship("ChemicalAdditive", back_populates="compound")

    def __repr__(self):
        return f"<Compound(name='{self.name}', formula='{self.formula}')>"


class ChemicalAdditive(Base):
    """Association model linking experimental conditions to specific chemical compounds with quantities"""
    __tablename__ = 'chemical_additives'

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float, nullable=False)
    unit = Column(Enum(AmountUnit), nullable=False)  # Uses the AmountUnit enum

    # Foreign Keys to link everything
    experiment_id = Column(Integer, ForeignKey('experimental_conditions.id', ondelete="CASCADE"), nullable=False)
    compound_id = Column(Integer, ForeignKey('compounds.id', ondelete="CASCADE"), nullable=False)

    # Optional metadata
    addition_order = Column(Integer, nullable=True)         # Order of addition (1st, 2nd, etc.)
    addition_method = Column(String(50), nullable=True)    # "solid", "solution", "dropwise", etc.
    final_concentration = Column(Float, nullable=True)      # Calculated final concentration in mixture
    concentration_units = Column(String(20), nullable=True) # "mM", "M", "ppm", etc.

    # Purity and batch tracking
    purity = Column(Float, nullable=True)                  # Purity percentage (0-100)
    lot_number = Column(String(50), nullable=True)        # Batch/lot tracking
    supplier_lot = Column(String(100), nullable=True)      # Supplier-specific lot info

    # Calculated fields (auto-populated)
    mass_in_grams = Column(Float, nullable=True)           # Normalized mass in grams
    moles_added = Column(Float, nullable=True)             # Calculated moles if molecular weight known
    
    # Catalyst-specific calculated fields
    elemental_metal_mass = Column(Float, nullable=True)    # Elemental metal mass for catalysts (g)
    catalyst_percentage = Column(Float, nullable=True)     # Catalyst % relative to rock mass
    catalyst_ppm = Column(Float, nullable=True)            # Catalyst concentration in solution (ppm)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    experiment = relationship("ExperimentalConditions", back_populates="chemical_additives")
    compound = relationship("Compound", back_populates="chemical_additives")

    # Ensure unique compound per experiment (no duplicates)
    __table_args__ = (
        UniqueConstraint('experiment_id', 'compound_id', name='unique_experiment_compound'),
    )

    def __repr__(self):
        return f"<ChemicalAdditive(compound_id={self.compound_id}, amount={self.amount} {self.unit.value})>"

    def format_additive(self):
        """Format this chemical additive as a human-readable string.
        
        Returns:
            str: Formatted string like "5 g Magnesium Hydroxide"
        """
        if not self.compound:
            return f"{self.amount} {self.unit.value} (Unknown Compound)"
        
        return f"{self.amount} {self.unit.value} {self.compound.name}"

    @classmethod
    def format_additives_list(cls, additives):
        """Format a list of chemical additives as a newline-separated string.
        
        Args:
            additives: List of ChemicalAdditive instances
            
        Returns:
            str: Formatted string with each additive on a new line using <br> tags
                 for HTML rendering (e.g., "5 g Magnesium Hydroxide<br>1 g Magnetite")
        
        Example:
            >>> additives = experiment.chemical_additives
            >>> formula_string = ChemicalAdditive.format_additives_list(additives)
            >>> print(formula_string)
            "5 g Magnesium Hydroxide<br>1 g Magnetite"
        """
        if not additives:
            return ""
        
        formatted_items = [additive.format_additive() for additive in additives]
        return "<br>".join(formatted_items)

