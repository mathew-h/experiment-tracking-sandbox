from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
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
    # Canonical physical slot label — 'R01'..'R16' (HPHT vessels) or 'CF01'..'CF03'
    # (Core Flood rigs). NULL whenever the experiment holds no physical slot:
    # a non-occupancy type (Serum / Autoclave / Other), a missing reactor_number,
    # or reactor_number <= 0.
    #
    # DO NOT SET THIS BY HAND. It is derived from (reactor_number,
    # experiment_type) by database.reactor_slot.derive_reactor_slot and written
    # on every ORM write by the before_insert/before_update listener
    # `set_reactor_slot` in database/event_listeners.py. Assigning it directly
    # will be silently overwritten on the next flush.
    #
    # This is the key for every occupancy comparison (issue #97). Reading
    # reactor_number alone conflates R01 with CF01 — two different vessels that
    # share the number 1 — which is how a Core Flood going ONGOING could
    # auto-complete a running HPHT.
    reactor_slot = Column(String(8), nullable=True, index=True)
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
    total_ferrous_iron_g = Column(Float, nullable=True)  # Derived: (FeO wt% / 100) * FE_IN_FEO_FRACTION * rock_mass_g

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
    total_ferrous_iron = Column(Float, nullable=True)  # grams of initial Fe(II) in the system
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    experiment = relationship("Experiment", back_populates="conditions", foreign_keys=[experiment_fk])
    chemical_additives = relationship("ChemicalAdditive", back_populates="experiment", cascade="all, delete-orphan")

