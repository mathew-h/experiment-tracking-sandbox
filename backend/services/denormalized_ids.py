"""Single definition of the denormalized-`experiment_id` fan-out on a rename.

Five tables carry a copy of `experiments.experiment_id` next to the
authoritative `experiment_fk`. Renaming an experiment without updating all five
leaves debris: 187 of 1013 `experimental_conditions` rows were stale as of
2026-08-05, all of it produced by the bulk-upload rename path, which synced two
of the five. `PATCH /api/experiments/{id}` synced four. This module is the one
place that knows the whole list, so a sixth table is a one-file change.

`experiment_fk` remains the only authoritative link on every one of these
tables — nothing here makes the string resolvable-by. It is kept correct so
reporting columns, the Power BI views and the XRD uniqueness slot read the
current name.

reactor_slot is NOT affected. Per `.claude/rules/MODELS.md`, a Core `UPDATE`
does not fire the `set_reactor_slot` mapper listener — but `reactor_slot`
derives from `(reactor_number, experiment_type)`, and nothing here touches
either, so no recompute is needed. Same argument as
`database/data_migrations/dedupe_conditions_and_backfill_ids_018.py`.

See docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md
"""
from __future__ import annotations

from dataclasses import dataclass, field

import structlog
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from database import (
    ExperimentNotes,
    ExperimentalConditions,
    ExternalAnalysis,
    ModificationsLog,
    XRDPhase,
)

log = structlog.get_logger(__name__)


@dataclass
class DenormalizedIdSync:
    """Rows updated per table, plus XRD rows deliberately left stale."""

    conditions: int = 0
    notes: int = 0
    modifications: int = 0
    external_analyses: int = 0
    xrd_phases: int = 0
    xrd_phases_skipped: list[int] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            self.conditions + self.notes + self.modifications
            + self.external_analyses + self.xrd_phases
        )


def sync_denormalized_experiment_id(
    db: Session, experiment_fk: int, new_id: str
) -> DenormalizedIdSync:
    """Point every denormalized `experiment_id` copy for one experiment at `new_id`.

    Call this AFTER the rename itself has been flushed. Flushes nothing and
    commits nothing — the caller owns the transaction boundary.

    `xrd_phases` rows that would collide with an existing holder of
    `uq_xrd_phase_experiment_time_mineral` (`experiment_id`,
    `time_post_reaction_days`, `mineral_name`) are left stale and returned in
    `xrd_phases_skipped`; renaming into an occupied slot would raise
    `IntegrityError` at flush and take the whole rename down with it.
    """
    result = DenormalizedIdSync()

    # Conditions: ORM assignment, not a Core UPDATE. UNIQUE (experiment_fk)
    # makes this at most one row going forward, but a database that predates
    # `uq_conditions_experiment_fk` can still hold several — update all of them
    # rather than picking one.
    conditions = db.execute(
        select(ExperimentalConditions)
        .where(ExperimentalConditions.experiment_fk == experiment_fk)
        .order_by(ExperimentalConditions.id)
    ).scalars().all()
    for cond in conditions:
        cond.experiment_id = new_id
    result.conditions = len(conditions)

    # Notes / audit log / external analyses: unbounded row counts, so Core
    # UPDATE. `synchronize_session` is left at its default ("auto"), which
    # expires matching in-session objects — the bulk parser processes its
    # conditions sheet after this call using the same session.
    for model, attr in (
        (ExperimentNotes, "notes"),
        (ModificationsLog, "modifications"),
        (ExternalAnalysis, "external_analyses"),
    ):
        res = db.execute(
            update(model)
            .where(model.experiment_fk == experiment_fk)
            .values(experiment_id=new_id)
        )
        setattr(result, attr, res.rowcount or 0)

    # XRD phases: row-by-row, because of the string-keyed unique slot.
    phases = db.execute(
        select(XRDPhase)
        .where(XRDPhase.experiment_fk == experiment_fk)
        .order_by(XRDPhase.id)
    ).scalars().all()
    for phase in phases:
        if phase.experiment_id == new_id:
            result.xrd_phases += 1
            continue
        blocker = db.execute(
            select(XRDPhase.id)
            .where(
                XRDPhase.experiment_id == new_id,
                XRDPhase.time_post_reaction_days == phase.time_post_reaction_days,
                XRDPhase.mineral_name == phase.mineral_name,
                XRDPhase.id != phase.id,
            )
        ).scalars().first()
        if blocker is not None:
            result.xrd_phases_skipped.append(phase.id)
            continue
        phase.experiment_id = new_id
        result.xrd_phases += 1

    if result.xrd_phases_skipped:
        log.warning(
            "denormalized_id_sync_xrd_slot_conflict",
            experiment_fk=experiment_fk,
            new_id=new_id,
            skipped_phase_ids=result.xrd_phases_skipped,
        )
    log.info(
        "denormalized_id_synced",
        experiment_fk=experiment_fk,
        new_id=new_id,
        conditions=result.conditions,
        notes=result.notes,
        modifications=result.modifications,
        external_analyses=result.external_analyses,
        xrd_phases=result.xrd_phases,
    )
    return result
