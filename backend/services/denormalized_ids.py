"""Single definition of the denormalized-`experiment_id` fan-out on a rename.

Five tables carry a copy of `experiments.experiment_id` next to the
authoritative `experiment_fk`. Renaming an experiment without updating all five
leaves debris: 187 of 1013 `experimental_conditions` rows were stale as of
2026-08-05, almost all of it rename debris from the replicate/-t<days> ID
migration. The bulk-upload rename path synced two of the five;
`PATCH /api/experiments/{id}` synced four. This module is the one place that
knows the whole list, so a sixth table is a one-file change.

`experiment_fk` remains the only authoritative link on every one of these
tables — nothing here makes the string resolvable-by. It is kept correct so
reporting columns, the Power BI views and the XRD uniqueness slot read the
current name.

**Scope: copies of *this* experiment's own id, and nothing else.**
Cross-experiment references are deliberately out of scope and still name the
old id after a rename — `scalar_results.background_experiment_id` (provenance
pointing at a *different* experiment) and the `experiments.base_experiment_id`
carried by this experiment's replicate children (a parsed group key addressed
as a string, issue #87). Neither is a copy of the renamed row's own id, so
neither belongs to this fan-out.

reactor_slot needs no recompute. `experimental_conditions` is the only table
here that carries it, and this helper updates that table through the **ORM**,
so the `set_reactor_slot` before_update listener does fire — and recomputes
idempotently from `(reactor_number, experiment_type)`, neither of which this
helper touches.

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

    `xrd_phases` rows that would collide on
    `uq_xrd_phase_experiment_time_mineral` (`experiment_id`,
    `time_post_reaction_days`, `mineral_name`) are left stale and returned in
    `xrd_phases_skipped`; renaming into an occupied slot would raise
    `IntegrityError` at flush and take the whole rename down with it. Both
    kinds of collision are caught: a slot already held in the database, and a
    slot claimed by an earlier row of this same call (which is pending, not
    yet visible to a query, under `autoflush=False`).
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
    # expires matching in-session objects. The load-bearing caller is
    # `PATCH /api/experiments/{id}`: it keeps working in the same session after
    # this call (audit row, recalculate, response build) and never expires it,
    # so a Core UPDATE that left the identity map alone would go on serving the
    # old string from already-loaded objects. The bulk parser is not the reason
    # — it runs `db.flush()` then `db.expire_all()` before its conditions
    # sheet, so its identity map is reset either way.
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

    # XRD phases: row-by-row, because of the string-keyed unique slot. Two
    # different things can already hold the target slot, and each needs its own
    # detection:
    #   1. a row committed in the DB           -> the `blocker` SELECT below
    #   2. a row THIS call just pointed at new_id -> `claimed`
    # (2) cannot be a query: production and test sessions both run
    # autoflush=False, so an assignment made on an earlier iteration is still
    # pending and invisible to the SELECT. Without `claimed`, two rows sharing
    # (time, mineral) but differing in their stale strings would both be
    # assigned new_id and raise IntegrityError on
    # `uq_xrd_phase_experiment_time_mineral` at the next flush — precisely the
    # failure this skip logic exists to prevent.
    claimed: set[tuple[float | None, str | None]] = set()
    phases = db.execute(
        select(XRDPhase)
        .where(XRDPhase.experiment_fk == experiment_fk)
        .order_by(XRDPhase.id)
    ).scalars().all()
    for phase in phases:
        slot = (phase.time_post_reaction_days, phase.mineral_name)
        if phase.experiment_id == new_id:
            # Already at the target. It still occupies the slot, so record it
            # to block a later row that shares (time, mineral).
            claimed.add(slot)
            result.xrd_phases += 1
            continue
        if slot in claimed:
            result.xrd_phases_skipped.append(phase.id)
            continue
        # No `XRDPhase.id != phase.id` term: the branch above has already
        # returned for every row sitting at new_id, so this row can never come
        # back as its own blocker.
        blocker = db.execute(
            select(XRDPhase.id)
            .where(
                XRDPhase.experiment_id == new_id,
                XRDPhase.time_post_reaction_days == phase.time_post_reaction_days,
                XRDPhase.mineral_name == phase.mineral_name,
            )
        ).scalars().first()
        if blocker is not None:
            result.xrd_phases_skipped.append(phase.id)
            continue
        claimed.add(slot)
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
