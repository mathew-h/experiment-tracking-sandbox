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

    def calculate_derived_values(self):
        """Calculate derived values (mass, moles, and concentration) based on unit and context.

        This leverages the associated `ExperimentalConditions` (via `experiment`) for
        solution volume to compute concentrations where possible, assuming water density ~1 g/mL
        for conversions between mass and volume if needed.
        
        For catalysts, also calculates elemental metal mass, catalyst percentage, and catalyst ppm.
        """
        volume_liters = None
        water_volume_ml = None
        rock_mass = None
        
        if getattr(self, 'experiment', None) is not None:
            try:
                water_volume_ml = getattr(self.experiment, 'water_volume_mL', None)
                if isinstance(water_volume_ml, (int, float)) and water_volume_ml and water_volume_ml > 0:
                    volume_liters = float(water_volume_ml) / 1000.0
                rock_mass = getattr(self.experiment, 'rock_mass_g', None)
            except Exception:
                volume_liters = None
                rock_mass = None

        molecular_weight = getattr(self.compound, 'molecular_weight_g_mol', None) if self.compound else None

        # Reset outputs
        self.mass_in_grams = None
        self.moles_added = None
        self.final_concentration = None
        self.concentration_units = None
        self.elemental_metal_mass = None
        self.catalyst_percentage = None
        self.catalyst_ppm = None

        # Handle concentration-style inputs first
        if self.unit == AmountUnit.PERCENT_OF_ROCK:
            # Interpret amount as mass percentage relative to rock mass
            # mass_in_grams = (percent / 100) * rock_mass
            try:
                if rock_mass is not None and isinstance(rock_mass, (int, float)) and rock_mass > 0:
                    self.mass_in_grams = (float(self.amount) / 100.0) * float(rock_mass)
            except Exception:
                self.mass_in_grams = None
            # If molecular weight is known and mass computed, set moles
            if self.mass_in_grams and molecular_weight:
                try:
                    self.moles_added = self.mass_in_grams / molecular_weight
                except Exception:
                    self.moles_added = None

        elif self.unit in (AmountUnit.PERCENT, AmountUnit.WEIGHT_PERCENT):
            # Interpret amount as % (w/w) in solution; assume density ~1 g/mL
            try:
                if water_volume_ml is not None and isinstance(water_volume_ml, (int, float)) and water_volume_ml > 0:
                    solution_mass_g = float(water_volume_ml)
                    self.mass_in_grams = (float(self.amount) / 100.0) * solution_mass_g
            except Exception:
                self.mass_in_grams = None

            if self.mass_in_grams and molecular_weight:
                try:
                    self.moles_added = self.mass_in_grams / molecular_weight
                except Exception:
                    self.moles_added = None

            # final concentration mirrors input
            self.final_concentration = float(self.amount)
            self.concentration_units = self.unit.value

        elif self.unit == AmountUnit.PPM:
            # ppm input is mg/L; compute grams if volume known
            if volume_liters is not None:
                try:
                    self.mass_in_grams = (float(self.amount) * volume_liters) / 1_000.0 / 1_000.0  # mg/L * L => mg; /1000 => g
                except Exception:
                    self.mass_in_grams = None
            # moles if we have mass and MW
            if self.mass_in_grams and molecular_weight:
                self.moles_added = self.mass_in_grams / molecular_weight
            # final concentration is what was entered
            self.final_concentration = float(self.amount)
            self.concentration_units = 'ppm'

        elif self.unit == AmountUnit.MILLIMOLAR:
            # amount in mM; compute moles if volume known
            if volume_liters is not None:
                try:
                    moles = (float(self.amount) / 1000.0) * volume_liters  # mM -> M, then * L => moles
                    self.moles_added = moles
                    if molecular_weight:
                        self.mass_in_grams = moles * molecular_weight
                except Exception:
                    pass
            # final concentration mirrors input
            self.final_concentration = float(self.amount)
            self.concentration_units = 'mM'

        elif self.unit == AmountUnit.MOLAR:
            # amount in M; compute moles if volume known
            if volume_liters is not None:
                try:
                    moles = float(self.amount) * volume_liters
                    self.moles_added = moles
                    if molecular_weight:
                        self.mass_in_grams = moles * molecular_weight
                except Exception:
                    pass
            # final concentration mirrors input
            self.final_concentration = float(self.amount)
            self.concentration_units = 'M'

        elif self.unit in (AmountUnit.MICROMOLE, AmountUnit.MILLIMOLE, AmountUnit.MOLE):
            # Amount is already in moles-scale units
            try:
                scale = {
                    AmountUnit.MICROMOLE: 1e-6,
                    AmountUnit.MILLIMOLE: 1e-3,
                    AmountUnit.MOLE: 1.0,
                }[self.unit]
                moles = float(self.amount) * scale
                self.moles_added = moles
                if molecular_weight:
                    self.mass_in_grams = moles * molecular_weight
                if volume_liters is not None:
                    # Prefer mM for readability
                    self.final_concentration = (moles / volume_liters) * 1000.0
                    self.concentration_units = 'mM'
            except Exception:
                pass

        else:
            # Mass/volume style inputs; convert to grams where possible
            self.mass_in_grams = self._convert_to_grams()
            if self.mass_in_grams and molecular_weight:
                try:
                    self.moles_added = self.mass_in_grams / molecular_weight
                except Exception:
                    self.moles_added = None
            if self.mass_in_grams and volume_liters is not None:
                try:
                    # Default to ppm for solution concentrations
                    ppm = (self.mass_in_grams / volume_liters) * 1_000_000.0
                    self.final_concentration = ppm
                    self.concentration_units = 'ppm'
                except Exception:
                    pass
        
        # === Catalyst-specific calculations (migrated from ExperimentalConditions) ===
        # Calculate elemental metal mass for catalysts if mass_in_grams is available
        if self.mass_in_grams and self.mass_in_grams > 0 and self.compound:
            elemental_fraction = None
            
            # First, check if compound has pre-calculated elemental_fraction
            if hasattr(self.compound, 'elemental_fraction') and self.compound.elemental_fraction:
                elemental_fraction = self.compound.elemental_fraction
            else:
                # Fall back to name-based detection for backwards compatibility
                compound_name = self.compound.name.lower() if self.compound.name else ""
                
                # Nickel calculation (assuming NiCl2·6H2O)
                if 'nickel' in compound_name or 'ni' in compound_name:
                    # Molar masses: Ni = 58.69, NiCl2·6H2O = 237.69
                    elemental_fraction = 58.69 / 237.69
                
                # Copper calculation (assuming CuCl2·2H2O)
                elif 'copper' in compound_name or 'cu' in compound_name:
                    # Molar masses: Cu = 63.55, CuCl2·2H2O = 170.48
                    elemental_fraction = 63.55 / 170.48
            
            # Calculate elemental metal mass if fraction was determined
            if elemental_fraction:
                self.elemental_metal_mass = self.mass_in_grams * elemental_fraction
                
                # Calculate catalyst_percentage if rock_mass is available
                if rock_mass is not None and rock_mass > 0:
                    self.catalyst_percentage = (self.elemental_metal_mass / rock_mass) * 100
                
                # Calculate catalyst_ppm if water_volume is available (independent of rock_mass)
                if water_volume_ml is not None and water_volume_ml > 0:
                    # ppm = (mass_of_solute [g] / mass_of_solvent [g]) * 1,000,000
                    # Assuming water density is 1 g/mL, water_volume in mL is equivalent to water_mass in g
                    unrounded_ppm = (self.elemental_metal_mass / water_volume_ml) * 1_000_000
                    self.catalyst_ppm = round(unrounded_ppm / 10) * 10

    def _convert_to_grams(self):
        """Convert amount to grams based on unit"""
        if not self.amount:
            return None

        unit_conversions = {
            AmountUnit.GRAM: 1.0,
            AmountUnit.MILLIGRAM: 0.001,
            AmountUnit.MICROGRAM: 0.000001,
            AmountUnit.KILOGRAM: 1000.0,
            AmountUnit.MICROLITER: 0.001,  # Assuming density of 1 g/mL
            AmountUnit.MILLILITER: 1.0,    # Assuming density of 1 g/mL
            AmountUnit.LITER: 1000.0,      # Assuming density of 1 g/mL
            AmountUnit.MICROMOLE: None,    # Need molecular weight
            AmountUnit.MILLIMOLE: None,    # Need molecular weight
            AmountUnit.MOLE: None,         # Need molecular weight
            AmountUnit.PPM: None,          # Concentration unit
            AmountUnit.MILLIMOLAR: None,   # Concentration unit
            AmountUnit.MOLAR: None,        # Concentration unit
        }

        if self.unit in unit_conversions:
            conversion = unit_conversions[self.unit]
            if conversion is not None:
                return self.amount * conversion

        return None
