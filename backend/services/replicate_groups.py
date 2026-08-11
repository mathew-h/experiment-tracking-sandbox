"""Replicate-group resolution by base-ID string (issue #87, Phase 1).

A replicate group is addressed by the base-ID string (`base_experiment_id`),
which is NOT guaranteed to name an experiment row: lettered members
(`a`/`b`/`c`) are the common case and the group parent frequently never
exists. `resolve_group` is the single code path both the new `/groups/{base_id}`
routes and the existing `/{experiment_id}/replicate-group` +
`/{experiment_id}/rollup` wrapper endpoints delegate to.

Label non-uniqueness: `replicate_label` is NOT unique within a group — a
`-t<days>` timepoint vial carries the same letter as its parent vial
(`SERUM_001a` and `SERUM_001a-t7` are both label `a`). Members are always
identified by `id`, never by `replicate_label`. A member may also have NO
label: a letterless `-t<days>` vial of the stem is a member (issue #101), so
`replicates` (the per-letter grouping) can be empty while `members` is not.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy import ColumnElement, and_, bindparam, func, or_, select, text
from sqlalchemy.orm import Session

from backend.services.replicate_collapse import timepoint_stem_expr
from database.lineage_utils import find_replicate_group_parent
from database.models.conditions import ExperimentalConditions
from database.models.experiments import Experiment
from database.models.results import ExperimentalResults

# Reserved columns never compared across members: identity/FK/timestamps.
_CONDITION_RESERVED_FIELDS = {"id", "experiment_id", "experiment_fk", "created_at", "updated_at"}

# DEPRECATED/legacy ExperimentalConditions columns (database/models/conditions.py),
# superseded by ChemicalAdditive — excluded from the divergence scan so a group
# never surfaces noise on fields nobody writes anymore.
_CONDITION_DEPRECATED_FIELDS = {
    "catalyst", "catalyst_mass", "buffer_system",
    "catalyst_percentage", "catalyst_ppm",
    "buffer_concentration",
    "surfactant_type", "surfactant_concentration",
    "ammonium_chloride_concentration",
}


def _condition_field_names() -> list[str]:
    """All comparable ExperimentalConditions scalar columns, sorted for
    deterministic shared/divergent ordering."""
    return sorted(
        col.name for col in ExperimentalConditions.__table__.columns
        if col.name not in _CONDITION_RESERVED_FIELDS
        and col.name not in _CONDITION_DEPRECATED_FIELDS
    )


@dataclass
class GroupMemberData:
    """One replicate-group member: the raw Experiment row plus its
    divergent-only condition values and result count."""
    experiment: Experiment
    divergent_conditions: dict[str, Any] = field(default_factory=dict)
    result_count: int = 0


@dataclass
class LetterGroupData:
    """One replicate letter and the vials carrying it, in display order.

    A letter maps to several vials when the set is sacrificed per timepoint
    (issue #98): letter "a" of SERUM_001 is SERUM_001a-t1 plus SERUM_001a-t3.
    """
    replicate_label: str
    vials: list[GroupMemberData] = field(default_factory=list)


@dataclass
class GroupData:
    """Resolved replicate group for a base-ID string."""
    base_experiment_id: str
    parent: Optional[Experiment]
    members: list[GroupMemberData]
    replicates: list[LetterGroupData]
    shared_conditions: dict[str, Any]
    divergent_fields: list[str]
    additives_summary: Optional[str]
    additive_names: Optional[str]
    additives_diverge: bool
    # The parent's own result count (issue #98 follow-up). The parent is never
    # a member (member_count stays len(members)), but it has its own results
    # like any experiment, and the group page renders this value directly --
    # defaulting it to 0 would show a confident wrong count instead of the "--"
    # shown before the parent field was widened to ReplicateGroupMemberDetail.
    parent_result_count: int = 0


def _member_clause(base_id: str) -> ColumnElement[bool]:
    """Group membership for `base_id`: a lettered replicate, OR a letterless
    '-t<days>' timepoint vial of this stem (issue #101).

    A letterless `-t` vial is one destructively-sampled instance of the stem
    itself, not a replicate of a sibling — `SERUM_001-t1/-t3/-t7` is one
    experiment sampled three times. It carries `replicate_label = NULL` and
    `base_experiment_id = stem`, and `v_results_scalar_rollup` already groups
    it on that stem, so excluding it here made the members table and the
    rollup disagree about who belonged to the group.

    The second clause is keyed on the timepoint-stripped `experiment_id`, NOT
    on `id_timepoint_days IS NOT NULL` alone, because `base_experiment_id` is
    the stem for derivations too: `SERUM_001-2-t0` (a vial of the *re-run*)
    and `SERUM_001_Desorption-t5` both carry base `SERUM_001` and would
    otherwise be adopted. Reducing the ID instead admits only vials whose ID
    IS the stem plus a token. Equality on that expression — rather than a
    `LIKE base_id || '-t%'` — also avoids treating the `_` in a stem such as
    `SERUM_pH_002` as a single-character wildcard.
    """
    return or_(
        Experiment.replicate_label.isnot(None),
        and_(
            Experiment.replicate_label.is_(None),
            Experiment.id_timepoint_days.isnot(None),
            timepoint_stem_expr(Experiment) == base_id,
        ),
    )


def _fetch_members(db: Session, base_id: str) -> list[Experiment]:
    """All replicate-group members for a base ID (see `_member_clause`), in
    display order: replicate_label ASC (NULLS FIRST, so the stem's own
    letterless timepoint vials lead), then id_timepoint_days ASC (NULLS
    FIRST), then experiment_number ASC. A '-t<days>' vial shares its letter
    with its parent vial, so ordering never assumes one row per letter."""
    return db.execute(
        select(Experiment)
        .where(
            Experiment.base_experiment_id == base_id,
            _member_clause(base_id),
        )
        .order_by(
            Experiment.replicate_label.asc().nulls_first(),
            Experiment.id_timepoint_days.asc().nulls_first(),
            Experiment.experiment_number.asc(),
        )
    ).scalars().all()


def group_vials_by_letter(members: Sequence[GroupMemberData]) -> list[LetterGroupData]:
    """Group members by replicate_label, preserving input order (issue #98).

    `members` arrives already ordered by _fetch_members (replicate_label,
    id_timepoint_days NULLS FIRST, experiment_number), so letters come out
    alphabetically and each letter's vials come out in timepoint order.
    Members with a NULL label are skipped -- the group parent is carried
    separately on GroupData.parent.
    """
    groups: dict[str, LetterGroupData] = {}
    order: list[str] = []
    for member in members:
        label = member.experiment.replicate_label
        if label is None:
            continue
        if label not in groups:
            groups[label] = LetterGroupData(replicate_label=label)
            order.append(label)
        groups[label].vials.append(member)
    return [groups[label] for label in order]


def _compare_conditions(
    members: list[Experiment],
) -> tuple[dict[str, Any], list[str], dict[int, dict[str, Any]]]:
    """Compare each condition field across members. Identical value across
    every compared member -> shared. Any field that differs -> divergent_fields,
    with each member's own value carried in the returned per-member map.

    Issue #98 (D5): a member with NO `conditions` row is EXCLUDED from the
    scan rather than contributing None for every field. Sacrificial-timepoint
    vials frequently have no conditions row of their own, and treating them as
    all-None pushed nearly every field out of shared_conditions and into
    "varies -- see members table". A NULL field WITHIN an existing conditions
    row still counts as a real value that can differ (D5); the grain stays
    per-vial rather than per-letter (D6).

    Excluded members still receive an entry in the per-member map (all
    divergent fields -> None) so their table cells render as em dashes.
    """
    if not members:
        return {}, [], {}

    fields = _condition_field_names()
    compared = [m for m in members if m.conditions is not None]

    values_by_member_id: dict[int, dict[str, Any]] = {}
    for member in members:
        cond = member.conditions
        values_by_member_id[member.id] = {
            f: getattr(cond, f, None) if cond is not None else None for f in fields
        }

    shared_conditions: dict[str, Any] = {}
    divergent_fields: list[str] = []
    if compared:
        for f in fields:
            values = [values_by_member_id[m.id][f] for m in compared]
            if all(v == values[0] for v in values):
                shared_conditions[f] = values[0]
            else:
                divergent_fields.append(f)

    per_member_divergent = {
        m.id: {f: values_by_member_id[m.id][f] for f in divergent_fields}
        for m in members
    }
    return shared_conditions, divergent_fields, per_member_divergent


def _resolve_additives(
    db: Session, members: list[Experiment]
) -> tuple[Optional[str], Optional[str], bool]:
    """Read v_experiment_additives_summary / v_experiment_additive_names_summary
    for each member. All members agreeing on both -> expose the shared values.
    Any disagreement -> additives_diverge=True, summaries None."""
    if not members:
        return None, None, False

    experiment_ids = [m.experiment_id for m in members]

    summary_rows = db.execute(
        text(
            "SELECT experiment_id, additives_summary FROM v_experiment_additives_summary "
            "WHERE experiment_id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": experiment_ids},
    ).mappings().all()
    summary_by_id = {r["experiment_id"]: r["additives_summary"] for r in summary_rows}

    names_rows = db.execute(
        text(
            "SELECT experiment_id, additive_names FROM v_experiment_additive_names_summary "
            "WHERE experiment_id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": experiment_ids},
    ).mappings().all()
    names_by_id = {r["experiment_id"]: r["additive_names"] for r in names_rows}

    summaries = [summary_by_id.get(eid) for eid in experiment_ids]
    names = [names_by_id.get(eid) for eid in experiment_ids]

    if all(s == summaries[0] for s in summaries) and all(n == names[0] for n in names):
        return summaries[0], names[0], False
    return None, None, True


def _result_counts(db: Session, member_ids: list[int]) -> dict[int, int]:
    if not member_ids:
        return {}
    rows = db.execute(
        select(ExperimentalResults.experiment_fk, func.count(ExperimentalResults.id))
        .where(ExperimentalResults.experiment_fk.in_(member_ids))
        .group_by(ExperimentalResults.experiment_fk)
    ).all()
    return {fk: count for fk, count in rows}


def resolve_group(db: Session, base_id: str) -> GroupData:
    """Resolve the replicate group for a base-ID string.

    Parent resolution keeps `-0`/`-1` spellings working (see
    `find_replicate_group_parent`) and may return None (the common case:
    lettered members exist but no parent row does). Members are all
    experiments with `base_experiment_id == base_id` that satisfy
    `_member_clause` — the stem's lettered replicates plus its own letterless
    `-t<days>` timepoint vials — regardless of whether a parent row exists.
    A bare-stem parent row carries no timepoint token, so it is the `parent`
    and never also a member.

    Does not raise on an unknown base_id — returns a GroupData with
    `parent=None` and `members=[]`. Callers (the `/groups/{base_id}` routes)
    are responsible for the 404 in that case.
    """
    parent = find_replicate_group_parent(db, base_id)
    members = _fetch_members(db, base_id)

    shared_conditions, divergent_fields, per_member_divergent = _compare_conditions(members)
    additives_summary, additive_names, additives_diverge = _resolve_additives(db, members)
    result_counts = _result_counts(
        db,
        [m.id for m in members] + ([parent.id] if parent is not None else []),
    )

    member_data = [
        GroupMemberData(
            experiment=m,
            divergent_conditions=per_member_divergent.get(m.id, {}),
            result_count=result_counts.get(m.id, 0),
        )
        for m in members
    ]

    return GroupData(
        base_experiment_id=base_id,
        parent=parent,
        members=member_data,
        replicates=group_vials_by_letter(member_data),
        shared_conditions=shared_conditions,
        divergent_fields=divergent_fields,
        additives_summary=additives_summary,
        additive_names=additive_names,
        additives_diverge=additives_diverge,
        parent_result_count=result_counts.get(parent.id, 0) if parent is not None else 0,
    )


def group_exists(db: Session, base_id: str) -> bool:
    """True if `base_id` names an experiment row (any parent spelling) or is
    the base_experiment_id of at least one member (`_member_clause`)."""
    if find_replicate_group_parent(db, base_id) is not None:
        return True
    return db.execute(
        select(Experiment.id)
        .where(
            Experiment.base_experiment_id == base_id,
            _member_clause(base_id),
        )
        .limit(1)
    ).first() is not None


def resolve_rollup_rows(db: Session, base_id: str) -> list[Mapping[str, Any]]:
    """Cross-replicate mean/median/std per timepoint from v_results_scalar_rollup.
    Identical SQL to the pre-refactor /{experiment_id}/rollup endpoint."""
    return db.execute(
        text("""
            SELECT * FROM v_results_scalar_rollup
            WHERE base_experiment_id = :base
            ORDER BY time_post_reaction_bucket_days
        """),
        {"base": base_id},
    ).mappings().all()
