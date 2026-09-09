from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, Enum as SQLEnum, Float, ForeignKey,
    ForeignKeyConstraint, Index, Integer, String, Text, select, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base
from .enums import ExperimentStatus, NoteType

class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(String, unique=True, nullable=False, index=True)  # User-defined experiment identifier
    experiment_number = Column(Integer, unique=True, nullable=False)  # Auto-incrementing number
    sample_id = Column(String, ForeignKey("sample_info.sample_id", ondelete="SET NULL"), nullable=True) # Foreign key to SampleInfo, SET NULL on delete
    researcher = Column(String)
    date = Column(DateTime(timezone=True))
    status = Column(SQLEnum(ExperimentStatus))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Lineage tracking fields
    base_experiment_id = Column(String, nullable=True, index=True)  # Base experiment ID (e.g., "HPHT_MH_001" for "HPHT_MH_001-2")
    parent_experiment_fk = Column(Integer, ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True)  # FK to parent experiment
    replicate_label = Column(String, nullable=True, index=True)  # "a", "b", "c"; NULL = not a replicate. is_replicate == (replicate_label IS NOT NULL)
    is_outlier = Column(Boolean, nullable=False, default=False, server_default=text("false"))  # True = bad vial (leak, cracked septum): excluded from v_results_scalar_rollup aggregates incl. n_replicates; per-row views and own pages unaffected
    # Day value parsed from a trailing '-t<days>' ID token (issue #81); NULL =
    # not encoded. Canonical for result times; grouping still uses base + bucket.
    id_timepoint_days = Column(Float, nullable=True, index=True)

    conditions = relationship("ExperimentalConditions", back_populates="experiment", uselist=False, cascade="all, delete-orphan")
    notes = relationship("ExperimentNotes", back_populates="experiment", cascade="all, delete-orphan", order_by="ExperimentNotes.created_at")
    modifications = relationship("ModificationsLog", back_populates="experiment", cascade="all, delete-orphan")
    results = relationship("ExperimentalResults", back_populates="experiment", foreign_keys="[ExperimentalResults.experiment_fk]", cascade="all, delete-orphan")
    sample_info = relationship("SampleInfo", back_populates="experiments", foreign_keys=[sample_id])
    external_analyses = relationship("ExternalAnalysis", back_populates="experiment", cascade="all, delete-orphan")
    
    # Lineage relationships
    parent = relationship("Experiment", remote_side=[id], foreign_keys=[parent_experiment_fk], backref="derived_experiments")
    
    # Background experiment relationship (for scalar results that reference this experiment as background)
    scalar_data = relationship("ScalarResults", back_populates="background_experiment", foreign_keys="[ScalarResults.background_experiment_fk]")
    
    # XRD phase data linked to this experiment (Aeris time-series)
    xrd_phases = relationship("XRDPhase", back_populates="experiment", foreign_keys="[XRDPhase.experiment_fk]")
    
    # Issue #118 PR3: the description is the note TYPED 'description', not a row
    # position. At most one exists per experiment (partial unique index
    # uq_one_description_per_experiment), so uselist=False is exact. viewonly:
    # writes go through backend/services/notes.py, never through this attribute.
    description_note = relationship(
        "ExperimentNotes",
        primaryjoin="and_(ExperimentNotes.experiment_fk == Experiment.id, "
                    "ExperimentNotes.note_type == 'description')",
        uselist=False,
        viewonly=True,
    )

    @hybrid_property
    def description(self):
        """The experiment's description: the text of its 'description' note, or None.

        Read-only. Before PR3 of issue #118 this was ``self.notes[0].note_text``
        -- a row position that three readers resolved differently (min(id) in
        the app, created_at in v_experiments). The SQL expression below lets the
        experiments list and dashboard filter and select it in one query.
        """
        note = self.description_note
        return note.note_text if note is not None else None

    @description.inplace.expression
    @classmethod
    def _description_expression(cls):
        return (
            select(ExperimentNotes.note_text)
            .where(
                ExperimentNotes.experiment_fk == cls.id,
                ExperimentNotes.note_type == NoteType.description,
            )
            .correlate(cls)
            .scalar_subquery()
        )

class ExperimentNotes(Base):
    """Typed free text about an experiment, optionally scoped to one result row.

    Issue #118. The database, not app code, enforces the three rules:
      * uq_one_description_per_experiment -- at most one 'description' note
        per experiment (partial unique index).
      * fk_note_result_same_experiment -- a result-scoped note points at a
        result of THIS experiment (composite FK on (experiment_fk, result_id);
        MATCH SIMPLE leaves rows with result_id NULL unconstrained, which is
        intended -- experiment-level notes never touch it).
      * ck_note_scope -- 'description' is never result-scoped, 'modification'
        and 'result_note' always are, 'observation' may be either.

    The legacy -> typed mapping lives in backend/services/notes.py; write paths
    call it rather than constructing rows here directly.
    """
    __tablename__ = "experiment_notes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["experiment_fk", "result_id"],
            ["experimental_results.experiment_fk", "experimental_results.id"],
            name="fk_note_result_same_experiment",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(note_type = 'description' AND result_id IS NULL) OR "
            "(note_type IN ('modification', 'result_note') AND result_id IS NOT NULL) OR "
            "(note_type = 'observation')",
            name="ck_note_scope",
        ),
        Index(
            "uq_one_description_per_experiment", "experiment_fk", unique=True,
            postgresql_where=text("note_type = 'description'"),
        ),
        Index("ix_experiment_notes_result_id", "result_id"),
        Index("ix_experiment_notes_scope", "experiment_fk", "note_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(String, nullable=False, index=True) # Human-readable ID (denormalized; kept in sync by backend/services/denormalized_ids.py)
    experiment_fk = Column(Integer, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False) # FK to Experiment PK
    note_text = Column(Text)
    note_type = Column(
        SQLEnum(NoteType, name="note_type"), nullable=False,
        default=NoteType.observation, server_default=text("'observation'"),
    )
    result_id = Column(Integer, nullable=True)  # scoped to one experimental_results row; see the composite FK above
    created_by = Column(String, nullable=True)  # Firebase email on API paths, a source tag on bulk paths
    needs_review = Column(Boolean, nullable=False, default=False, server_default=text("false"))  # the backfill could not place this row with certainty
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    experiment = relationship("Experiment", back_populates="notes", foreign_keys=[experiment_fk])
    # viewonly: ON DELETE CASCADE owns deletion, and experiment_fk is shared
    # with the composite FK, so the ORM must not try to manage result_id.
    result = relationship(
        "ExperimentalResults",
        primaryjoin="ExperimentNotes.result_id == ExperimentalResults.id",
        foreign_keys=[result_id],
        viewonly=True,
    )

class ModificationsLog(Base):
    __tablename__ = "modifications_log"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(String, nullable=True, index=True) # Human-readable ID, nullable as it might log other things? Or should be non-null? Let's keep nullable for now.
    experiment_fk = Column(Integer, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=True) # FK to Experiment PK, nullable to match experiment_id
    sample_id = Column(String, nullable=True, index=True)  # denormalized sample ID (no FK, matching experiment_id pattern); nullable for experiment-only modifications
    modified_by = Column(String)  # Username or identifier of who made the change
    modification_type = Column(String)  # e.g., 'create', 'update', 'delete'
    modified_table = Column(String)  # Which table was modified
    old_values = Column(JSONB)  # Previous values
    new_values = Column(JSONB)  # New values
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    experiment = relationship("Experiment", back_populates="modifications", foreign_keys=[experiment_fk])
