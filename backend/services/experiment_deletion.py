"""Experiment deletion: impact scan and the orphan-safe delete path (issue #99).

Deletion is a HARD delete, available to any approved researcher. The controls
are the ModificationsLog snapshot written by delete_experiment_cascade() and
the typed-ID confirmation in the UI -- there is no role gate (locked decision,
2026-07-29).

Why this module exists rather than a bare db.delete(exp): three references to
an experiment are NOT covered by the cascade="all, delete-orphan" relationships
on Experiment (database/models/experiments.py:30-35), and one of them has no
DB-level protection at all:

  1. xrd_phases -- experiment_fk is ondelete="SET NULL" and the relationship
     (experiments.py:44) declares no cascade, so rows survive with a stale
     experiment_id string. The uq_xrd_phase_experiment_time_mineral constraint
     on (experiment_id, time_post_reaction_days, mineral_name) then blocks
     re-creating that experiment's XRD data. These rows are DELETED.
  2. scalar_results.background_experiment_id -- a plain String with NO foreign
     key. The parallel background_experiment_fk column is unpopulated in
     practice (0 of 1056 rows as of 2026-07-29; only the string is ever written,
     see backend/services/scalar_results_service.py:155), so the DB-level
     SET NULL on the FK protects nothing that matters. Both are NULLed out.
     This is provenance only -- the background NUMBER lives in
     background_ammonium_concentration_mM, so nulling it changes no derived
     value and needs no recalculate() call.
  3. reactor_change_requests.experiment_id -- ondelete="SET NULL"; nulled
     explicitly so behavior does not depend on deployed constraint parity.

Deployed constraints are not guaranteed to match the model declarations: the
dev and test DBs are built with Base.metadata.create_all (which honors the
ondelete clauses), while the lab PC came up through the Alembic chain, whose
initial migration declared none. Everything here is therefore explicit in
application code, so behavior is identical either way.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import delete as sql_delete, func, or_, select, update
from sqlalchemy.orm import Session

from database.models.analysis import ExternalAnalysis
from database.models.chemicals import ChemicalAdditive, Compound
from database.models.conditions import ExperimentalConditions
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.notion_sync import ReactorChangeRequest
from database.models.results import (
    ExperimentalResults, ICPResults, ResultFiles, ScalarResults,
)
from database.models.xrd import XRDPhase

log = structlog.get_logger(__name__)


@dataclass
class DeleteImpact:
    """What deleting one experiment destroys (counts) and decouples (lists)."""

    experiment_id: str
    results: int = 0
    scalar_results: int = 0
    icp_results: int = 0
    result_files: int = 0
    notes: int = 0
    additives: int = 0
    external_analyses: int = 0
    xrd_phases: int = 0
    change_requests: int = 0
    # Other experiments that name this one as their ammonium background.
    background_for: list[str] = field(default_factory=list)
    # Experiments whose parent_experiment_fk points at this one. Their
    # base_experiment_id STRING is untouched, so replicate groups -- addressed
    # by that string, not by a row lookup (MODELS.md, issue #87) -- keep
    # working. Reported so the researcher is told, not because data is lost.
    replicate_children: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Rows destroyed. Excludes background_for/replicate_children, which
        are decoupled and survive. The UI gates typed-ID confirmation on this.
        """
        return (
            self.results + self.scalar_results + self.icp_results
            + self.result_files + self.notes + self.additives
            + self.external_analyses + self.xrd_phases + self.change_requests
        )


def _count(db: Session, stmt) -> int:
    return db.execute(stmt).scalar_one() or 0


def collect_delete_impact(db: Session, exp: Experiment) -> DeleteImpact:
    """Count every dependent record and resolve both decoupling lists.

    Read-only -- safe to call from a GET. Shared by the delete-impact endpoint
    and by delete_experiment_cascade so the dialog and the audit log agree.
    """
    result_ids = db.execute(
        select(ExperimentalResults.id).where(ExperimentalResults.experiment_fk == exp.id)
    ).scalars().all()

    # ChemicalAdditive.experiment_id is an INTEGER FK to
    # experimental_conditions.id -- not the experiment string, not experiments.id.
    condition_ids = db.execute(
        select(ExperimentalConditions.id).where(ExperimentalConditions.experiment_fk == exp.id)
    ).scalars().all()

    impact = DeleteImpact(
        experiment_id=exp.experiment_id,
        results=len(result_ids),
        notes=_count(db, select(func.count()).select_from(ExperimentNotes)
                     .where(ExperimentNotes.experiment_fk == exp.id)),
        external_analyses=_count(db, select(func.count()).select_from(ExternalAnalysis)
                                 .where(ExternalAnalysis.experiment_fk == exp.id)),
        # Matched on fk OR string: a row whose fk was nulled by an earlier
        # delete still names this experiment and still holds the unique slot.
        xrd_phases=_count(db, select(func.count()).select_from(XRDPhase).where(
            or_(XRDPhase.experiment_fk == exp.id,
                XRDPhase.experiment_id == exp.experiment_id))),
        change_requests=_count(db, select(func.count()).select_from(ReactorChangeRequest)
                               .where(ReactorChangeRequest.experiment_id == exp.experiment_id)),
    )

    if result_ids:
        impact.scalar_results = _count(db, select(func.count()).select_from(ScalarResults)
                                       .where(ScalarResults.result_id.in_(result_ids)))
        impact.icp_results = _count(db, select(func.count()).select_from(ICPResults)
                                    .where(ICPResults.result_id.in_(result_ids)))
        impact.result_files = _count(db, select(func.count()).select_from(ResultFiles)
                                     .where(ResultFiles.result_id.in_(result_ids)))

    if condition_ids:
        impact.additives = _count(db, select(func.count()).select_from(ChemicalAdditive)
                                  .where(ChemicalAdditive.experiment_id.in_(condition_ids)))

    # Other experiments using this one as their ammonium background. Keyed on
    # the string (the FK is unpopulated in practice); self-references excluded.
    impact.background_for = sorted(set(db.execute(
        select(Experiment.experiment_id)
        .join(ExperimentalResults, ExperimentalResults.experiment_fk == Experiment.id)
        .join(ScalarResults, ScalarResults.result_id == ExperimentalResults.id)
        .where(
            or_(ScalarResults.background_experiment_id == exp.experiment_id,
                ScalarResults.background_experiment_fk == exp.id),
            Experiment.id != exp.id,
        )
    ).scalars().all()))

    impact.replicate_children = sorted(db.execute(
        select(Experiment.experiment_id).where(
            Experiment.parent_experiment_fk == exp.id,
            Experiment.id != exp.id,
        )
    ).scalars().all())

    return impact


def _primitive(value: Any) -> Any:
    """Coerce a column value to something json/JSONB can hold."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "value"):  # enum member (e.g. ExperimentStatus)
        return value.value
    if hasattr(value, "isoformat"):  # date / datetime
        return value.isoformat()
    return str(value)


def _row_to_dict(instance: Any) -> dict[str, Any]:
    return {
        col.name: _primitive(getattr(instance, col.name))
        for col in instance.__table__.columns
    }


def serialize_experiment_snapshot(db: Session, exp: Experiment) -> dict[str, Any]:
    """A restorable snapshot of the experiment, its conditions, additives and notes.

    Every value is JSON-primitive because this lands in ModificationsLog.old_values
    (a JSONB column) -- enums and datetimes would otherwise fail the flush.
    Results/ICP are deliberately excluded: they are bulk-uploadable and would
    make the audit row unbounded. Their counts are recorded in new_values.
    """
    conditions = db.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
    ).scalar_one_or_none()

    additives: list[dict[str, Any]] = []
    if conditions is not None:
        rows = db.execute(
            select(ChemicalAdditive, Compound.name)
            .join(Compound, Compound.id == ChemicalAdditive.compound_id)
            .where(ChemicalAdditive.experiment_id == conditions.id)
        ).all()
        for additive, compound_name in rows:
            entry = _row_to_dict(additive)
            entry["compound_name"] = compound_name
            additives.append(entry)

    notes = db.execute(
        select(ExperimentNotes.note_text)
        .where(ExperimentNotes.experiment_fk == exp.id)
        .order_by(ExperimentNotes.created_at)
    ).scalars().all()

    return {
        "experiment": _row_to_dict(exp),
        "conditions": _row_to_dict(conditions) if conditions is not None else None,
        "additives": additives,
        "notes": [n for n in notes if n is not None],
    }


def delete_experiment_cascade(
    db: Session, exp: Experiment, modified_by: str | None
) -> DeleteImpact:
    """Decouple, audit, then hard-delete an experiment. Commits.

    Order matters: the impact scan and the snapshot both read rows that the
    delete destroys, so they run first. The ModificationsLog row is added with
    experiment_fk=None -- that FK is ondelete="CASCADE", so a populated value
    would take the audit row down with the experiment.
    """
    experiment_id = exp.experiment_id
    exp_pk = exp.id

    impact = collect_delete_impact(db, exp)
    snapshot = serialize_experiment_snapshot(db, exp)

    # 1. XRD phases: DELETE, not decouple. Matched on fk OR string so a row
    #    orphaned by an earlier delete cannot keep holding the unique slot on
    #    (experiment_id, time_post_reaction_days, mineral_name).
    db.execute(
        sql_delete(XRDPhase).where(
            or_(XRDPhase.experiment_fk == exp_pk,
                XRDPhase.experiment_id == experiment_id)
        )
    )

    # 2. Ammonium background provenance on OTHER experiments' scalar results.
    #    The string has no FK and is the column actually in use; the fk is
    #    nulled too so nothing depends on deployed constraint parity.
    db.execute(
        update(ScalarResults)
        .where(or_(ScalarResults.background_experiment_id == experiment_id,
                   ScalarResults.background_experiment_fk == exp_pk))
        .values(background_experiment_id=None, background_experiment_fk=None)
    )

    # 3. Reactor change requests keep their row, lose the reference. Safe
    #    against uq_change_request_reactor_experiment_date: PostgreSQL treats
    #    NULL as distinct in unique constraints.
    db.execute(
        update(ReactorChangeRequest)
        .where(ReactorChangeRequest.experiment_id == experiment_id)
        .values(experiment_id=None)
    )

    # 4. Replicate children: drop the parent pointer explicitly rather than
    #    relying on the DB SET NULL. base_experiment_id is untouched, so the
    #    group stays addressable by string (MODELS.md, issue #87).
    if impact.replicate_children:
        db.execute(
            update(Experiment)
            .where(Experiment.parent_experiment_fk == exp_pk, Experiment.id != exp_pk)
            .values(parent_experiment_fk=None)
        )

    # 5. The audit trail -- experiment_fk=None so it outlives the experiment.
    db.add(ModificationsLog(
        experiment_id=experiment_id,
        experiment_fk=None,
        sample_id=exp.sample_id,
        modified_by=modified_by,
        modification_type="delete",
        modified_table="experiments",
        old_values=snapshot,
        new_values={
            "impact": {
                "results": impact.results,
                "scalar_results": impact.scalar_results,
                "icp_results": impact.icp_results,
                "result_files": impact.result_files,
                "notes": impact.notes,
                "additives": impact.additives,
                "external_analyses": impact.external_analyses,
                "xrd_phases": impact.xrd_phases,
                "change_requests": impact.change_requests,
                "total": impact.total,
            },
            "decoupled_background_for": impact.background_for,
            "decoupled_replicate_children": impact.replicate_children,
        },
    ))
    db.flush()

    db.delete(exp)
    db.commit()

    log.info(
        "experiment_deleted",
        experiment_id=experiment_id,
        user=modified_by,
        rows_destroyed=impact.total,
        decoupled_background_for=impact.background_for,
        decoupled_replicate_children=impact.replicate_children,
    )
    return impact
