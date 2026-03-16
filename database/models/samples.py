from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base

class SamplePhotos(Base):
    __tablename__ = "sample_photos"

    id = Column(Integer, primary_key=True, index=True)
    sample_id = Column(String, ForeignKey("sample_info.sample_id"), nullable=False) # Added FK to SampleInfo.sample_id
    file_path = Column(String, nullable=False)
    file_name = Column(String)
    file_type = Column(String)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    sample_info = relationship("SampleInfo", back_populates="photos", foreign_keys=[sample_id])

class SampleInfo(Base):
    __tablename__ = "sample_info"

    # Use sample_id as the primary key
    sample_id = Column(String, primary_key=True, index=True)
    rock_classification = Column(String)
    state = Column(String)
    country = Column(String)
    locality = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    description = Column(Text)
    characterized = Column(Boolean, default=False, server_default='false', nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    experiments = relationship("Experiment", back_populates="sample_info", foreign_keys="[Experiment.sample_id]")
    external_analyses = relationship(
        "ExternalAnalysis",
        back_populates="sample_info",
        cascade="all, delete-orphan",
        foreign_keys="[ExternalAnalysis.sample_id]" # Join on sample_id
    )
    photos = relationship("SamplePhotos", back_populates="sample_info", cascade="all, delete-orphan", foreign_keys="[SamplePhotos.sample_id]")
    # Elemental analysis results (normalized) relationship
    elemental_results = relationship("ElementalAnalysis", backref="sample_info", cascade="all, delete-orphan", foreign_keys="[ElementalAnalysis.sample_id]")
