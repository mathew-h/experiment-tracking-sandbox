from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql import func
from ..database import Base

class ExperimentalConditions(Base):
    __tablename__ = "experimental_conditions"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(String, nullable=False, index=True) # Human-readable ID
    experiment_fk = Column(Integer, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False) # FK to Experiment PK
    particle_size = Column(String, nullable=True)  # Accept strings like '<75', '>100', '75-100', or numeric values
    initial_ph = Column(Float)
    rock_mass_g = Column(Float)
    water_volume_mL = Column(Float)
    temperature_c = Column(Float)
    experiment_type = Column(String)
    reactor_number = Column(Integer, nullable=True)
    feedstock = Column(String, nullable=True)
    room_temp_pressure_psi = Column(Float, nullable=True)  # in psi instead of bar
    rxn_temp_pressure_psi = Column(Float, nullable=True)
    stir_speed_rpm = Column(Float, nullable=True)
    initial_conductivity_mS_cm = Column(Float, nullable=True)
    core_height_cm = Column(Float, nullable=True)
    core_width_cm = Column(Float, nullable=True)
    core_volume_cm3 = Column(Float, nullable=True)

    # DEPRECATED: Migrated to ChemicalAdditive - use chemical_additives relationship
    catalyst = Column(String)
    catalyst_mass = Column(Float)
    buffer_system = Column(String, nullable=True)
    
    water_to_rock_ratio = Column(Float, nullable=True)
    
    # DEPRECATED: Now calculated in ChemicalAdditive model
    catalyst_percentage = Column(Float, nullable=True)
    catalyst_ppm = Column(Float, nullable=True)
    
    # DEPRECATED: Migrated to ChemicalAdditive - use chemical_additives relationship
    buffer_concentration = Column(Float, nullable=True)  # in mM
    flow_rate = Column(Float, nullable=True)
    initial_nitrate_concentration = Column(Float, nullable=True)  # in mM, optional
    initial_dissolved_oxygen = Column(Float, nullable=True)  # in ppm, optional
    
    # DEPRECATED: Migrated to ChemicalAdditive - use chemical_additives relationship
    surfactant_type = Column(String, nullable=True)  # optional
    surfactant_concentration = Column(Float, nullable=True)  # optional
    
    co2_partial_pressure_MPa = Column(Float, nullable=True)  # in MPa, optional
    confining_pressure = Column(Float, nullable=True)  # optional
    pore_pressure = Column(Float, nullable=True)  # optional
    
    # DEPRECATED: Migrated to ChemicalAdditive - use chemical_additives relationship
    ammonium_chloride_concentration = Column(Float, nullable=True)  # optional
    
   
    initial_alkalinity = Column(Float, nullable=True) 
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    experiment = relationship("Experiment", back_populates="conditions", foreign_keys=[experiment_fk])
    chemical_additives = relationship("ChemicalAdditive", back_populates="experiment", cascade="all, delete-orphan")

    @hybrid_property
    def formatted_additives(self):
        """Formatted string of all chemical additives for PowerBI reporting.
        
        Returns a newline-separated list of chemical additives in the format:
        "5 g Magnesium Hydroxide
        1 g Magnetite"
        
        This property is accessible in PowerBI as a regular text column.
        """
        if not self.chemical_additives:
            return ""
        
        formatted_items = [additive.format_additive() for additive in self.chemical_additives]
        return "\n".join(formatted_items)

    def calculate_derived_conditions(self):
        """
        Calculate derived experimental conditions. This method calculates:
        - water_to_rock_ratio
        
        DEPRECATED: Catalyst calculations (catalyst_percentage, catalyst_ppm) have been moved to
        ChemicalAdditive.calculate_derived_values(). This method is retained for backwards compatibility
        and to calculate water_to_rock_ratio which is still relevant to ExperimentalConditions.
        """
        # Calculate water_to_rock_ratio
        if self.water_volume_mL is not None and self.rock_mass_g is not None and self.rock_mass_g > 0:
            self.water_to_rock_ratio = self.water_volume_mL / self.rock_mass_g
        else:
            self.water_to_rock_ratio = None  # Ensure it is null if inputs are missing

        # DEPRECATED: Catalyst calculation logic has been moved to ChemicalAdditive.calculate_derived_values()
        # The following code is commented out but retained for reference:
        #
        # # Reset catalyst-related fields to ensure they are always recalculated
        # self.catalyst_percentage = 0.0
        # self.catalyst_ppm = 0.0
        # elemental_metal_mass = None
        #
        # # Step 1: Calculate elemental metal mass if a catalyst is specified
        # if self.catalyst and self.catalyst.strip() and self.catalyst_mass is not None and self.catalyst_mass > 0:
        #     catalyst_name = self.catalyst.lower()
        #
        #     # Nickel calculation (assuming NiCl2·6H2O)
        #     if 'nickel' in catalyst_name or 'ni' in catalyst_name:
        #         # Molar masses: Ni = 58.69, NiCl2·6H2O = 237.69
        #         elemental_metal_mass = self.catalyst_mass * (58.69 / 237.69)
        #     
        #     # Copper calculation (assuming CuCl2·2H2O)
        #     elif 'copper' in catalyst_name or 'cu' in catalyst_name:
        #         # Molar masses: Cu = 63.55, CuCl2·2H2O = 170.48
        #         elemental_metal_mass = self.catalyst_mass * (63.55 / 170.48)
        #
        # # Step 2: If elemental mass was determined, calculate percentage and PPM based on their respective dependencies
        # if elemental_metal_mass is not None:
        #     # Calculate catalyst_percentage if rock_mass is valid
        #     if self.rock_mass_g is not None and self.rock_mass_g > 0:
        #         self.catalyst_percentage = (elemental_metal_mass / self.rock_mass_g) * 100
        #
        #     # Calculate catalyst_ppm if water_volume is valid (independent of rock_mass)
        #     if self.water_volume_mL is not None and self.water_volume_mL > 0:
        #         # ppm = (mass_of_solute [g] / mass_of_solvent [g]) * 1,000,000
        #         # Assuming water density is 1 g/mL, water_volume in mL is equivalent to water_mass in g.
        #         unrounded_ppm = (elemental_metal_mass / self.water_volume_mL) * 1_000_000
        #         self.catalyst_ppm = round(unrounded_ppm / 10) * 10
