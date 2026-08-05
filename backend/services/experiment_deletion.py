"""Experiment deletion: impact scan and the orphan-safe delete path (issue #99).

Deletion is a HARD delete, available to any approved researcher. The controls
are the ModificationsLog snapshot written by delete_experiment_cascade() and
the typed-ID confirmation in the UI -- there is no role gate (locked decision,
2026-07-29).

Governing principle (product owner, 2026-07-29): deleting an experiment PURGES
everything it owns. The one hard boundary is that "owns" stops at rows belonging
to THIS experiment -- another experiment's data is never destroyed, only
decoupled (see items 2 and 4 below).

Why this module exists rather than a bare db.delete(exp): four references to an
experiment are NOT handled correctly by the cascade="all, delete-orphan"
relationships on Experiment (database/models/experiments.py:30-35), and two of
them have no usable DB-level protection:

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
     This is a DECOUPLING of another experiment's row: provenance only -- the
     background NUMBER lives in background_ammonium_concentration_mM, which is
     left intact, so no derived value changes and no recalculate() is needed.
  3. reactor_change_requests.experiment_id -- ondelete="SET NULL", but these
     rows are PURGED (product decision, 2026-07-29): they belong to this
     experiment, and change_requests is summed into DeleteImpact.total, which is
     documented as rows destroyed. Purging makes that count truthful.
  4. Replicate children -- parent_experiment_fk is dropped, nothing else. Their
     base_experiment_id and replicate_label stay, because replicate groups are
     addressed by the base-ID string (issue #87). A DECOUPLING, not a purge.
  5. elemental_analysis -- external_analysis_id is nullable=False, yet the
     relationship (characterization.py:43) is a bare backref with no cascade and
     no passive_deletes. When the ORM cascade-deletes this experiment's
     external_analyses it therefore tries to NULL that child FK BEFORE the
     DB-level ON DELETE CASCADE can act, raising NotNullViolation and failing
     the whole delete with a 500. These rows are DELETED up front, in the
     service: database/models/ is locked and models are storage-only here, so
     the fix cannot be a passive_deletes=True on the relationship.

Deployed constraints are not guaranteed to match the model declarations: the
dev and test DBs are built with Base.metadata.create_all (which honors the
ondelete clauses), while the lab PC came up through the Alembic chain, whose
initial migration declared none. A normal single-row delete is therefore
explicit in application code either way, so behavior is identical regardless
of how the DB was provisioned.

Exception: a pre-constraint anomaly left one production experiment with TWO
experimental_conditions rows for the same experiment_fk (issue #109).
serialize_experiment_snapshot() and _build_list_item() (backend/api/routers/
experiments.py) now tolerate this by reading only the lowest-id row, but the
delete itself still goes through Experiment.conditions, which is
uselist=False -- so db.delete(exp) cascades only the ONE row the ORM believes
exists. The second row is removed by Postgres' ON DELETE CASCADE on
experimental_conditions.experiment_fk, not by anything in this module. This
is the one place deletion genuinely depends on a DB-level constraint being
present; it is confirmed present in both the 2026-08-05 production dump and
the dev DB.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import delete as sql_delete, func, or_, select, update
from sqlalchemy.orm import Session

from database.models.analysis import ExternalAnalysis
from database.models.characterization import ElementalAnalysis
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
    # The setup row (temperature, initial pH, rock mass, water volume, reactor
    # number, pressures, total_ferrous_iron_g). Hard-deleted by the ORM cascade,
    # so it must be counted: 44 dev-DB experiments have conditions and nothing
    # else, and an uncounted destruction leaves total == 0, which makes the
    # dialog claim "nothing else is affected" and drops the typed-ID gate.
    conditions: int = 0
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
            self.conditions + self.results + self.scalar_results
            + self.icp_results + self.result_files + self.notes + self.additives
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
        conditions=len(condition_ids),
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
    """A record of WHAT WAS DELETED -- not a restore point.

    Captures the experiment header row, its conditions row, its additives (with
    the compound name) and its note TEXT. Deletion is an explicit purge, and the
    following are NOT reconstructable from this snapshot:

      - every ExperimentalResults / ScalarResults / ICPResults / ResultFiles
        value (deliberately excluded: bulk-uploadable and unbounded -- only the
        counts are kept, in new_values);
      - purged xrd_phases rows (mineral_name, amount, time_post_reaction_days,
        rwp) and ExternalAnalysis rows with their metadata and files;
      - note timestamps, and the experiment's prior ModificationsLog history,
        which is purged with it;
      - lineage: parent_experiment_fk is stored as a stale integer PK that can no
        longer be resolved to an experiment.

    Every value is JSON-primitive because this lands in ModificationsLog.old_values
    (a JSONB column) -- enums and datetimes would otherwise fail the flush.
    """
    # .first(), not scalar_one_or_none(): a duplicate conditions row used to
    # raise MultipleResultsFound here, inside delete_experiment_cascade, which
    # made the experiment undeletable through both the single-delete endpoint
    # and the bulk uploader (issue #109). impact.conditions still counts every
    # row; only the snapshot narrows to one.
    conditions = db.execute(
        select(ExperimentalConditions)
        .where(ExperimentalConditions.experiment_fk == exp.id)
        .order_by(ExperimentalConditions.id)
    ).scalars().first()

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
    """Purge an experiment and everything it owns; decouple, audit, then delete.

    Order matters: the impact scan and the snapshot both read rows that the
    delete destroys, so they run first. The ModificationsLog row is added with
    experiment_fk=None -- that FK is ondelete="CASCADE", so a populated value
    would take the audit row down with the experiment.

    The experiment's PRIOR ModificationsLog history is purged with it, via
    Experiment.modifications (cascade="all, delete-orphan") -- accepted product
    decision (2026-07-29), consistent with purging everything it owns. The single
    delete-snapshot row written here is the surviving trace, and it is what
    justifies opening this endpoint to any approved researcher with no role gate.
    Commits.
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

    # 3. Reactor change requests are PURGED, not unlinked (product decision,
    #    2026-07-29): they belong to this experiment, and change_requests is
    #    already summed into impact.total, which is documented as rows destroyed.
    db.execute(
        sql_delete(ReactorChangeRequest)
        .where(ReactorChangeRequest.experiment_id == experiment_id)
    )

    # 3b. elemental_analysis children of THIS experiment's external analyses.
    #     external_analysis_id is nullable=False but its relationship is a bare
    #     backref, so the ORM would try to NULL it when the parent
    #     ExternalAnalysis is cascade-deleted -> NotNullViolation, 500, no
    #     delete. Purged here because database/models/ is locked (no
    #     passive_deletes=True available) and these rows are owned by the
    #     experiment anyway.
    ext_ids = db.execute(
        select(ExternalAnalysis.id).where(ExternalAnalysis.experiment_fk == exp_pk)
    ).scalars().all()
    if ext_ids:
        db.execute(
            sql_delete(ElementalAnalysis)
            .where(ElementalAnalysis.external_analysis_id.in_(ext_ids))
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
                "conditions": impact.conditions,
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
