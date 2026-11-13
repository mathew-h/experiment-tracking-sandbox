from __future__ import annotations

from typing import List, Optional

from sqlalchemy import and_, or_, func as sa_func, update
from sqlalchemy.orm import Session, joinedload

from database import ExperimentalResults, Experiment
from backend.services.experiment_lookup import series_key

TIMEPOINT_TOLERANCE_DAYS = 0.0001
TIMEPOINT_BUCKET_DECIMALS = 4


def normalize_timepoint(time_post_reaction: Optional[float]) -> Optional[float]:
    """Normalize timepoint values to a stable bucketable float."""
    if time_post_reaction is None:
        return None
    return round(float(time_post_reaction), TIMEPOINT_BUCKET_DECIMALS)


def apply_id_timepoint(id_timepoint_days, time_post_reaction):
    """
    Resolve a result's time against an ID-encoded timepoint (issue #81).

    The '-t<days>' token in an experiment ID is canonical for that vial's
    timepoint: a missing time is filled from it; a conflicting time (beyond
    the bucket tolerance) is rejected so one vial never holds result rows at
    a different day.

    Returns the effective time_post_reaction value.
    Raises ValueError when the supplied time conflicts with the ID.
    """
    if id_timepoint_days is None:
        return time_post_reaction
    if time_post_reaction is None:
        return id_timepoint_days
    delta = abs(float(time_post_reaction) - float(id_timepoint_days))
    if delta > TIMEPOINT_TOLERANCE_DAYS:
        raise ValueError(
            f"Time (days) {time_post_reaction} conflicts with the timepoint "
            f"encoded in the experiment ID (-t{id_timepoint_days:g} = "
            f"day {id_timepoint_days:g}). "
            "The ID is canonical: leave Time blank to use the ID's day, or fix the ID."
        )
    return time_post_reaction


def resolve_primary_timepoint(
    db: Session,
    exp: Experiment,
    time_post_reaction_days: Optional[float],
    is_primary: bool = True,
) -> tuple[Optional[float], Optional[float]]:
    """
    Resolve a new result row's time and bucket, demoting a clashing primary row.

    Returns ``(resolved_time, bucket)``. Raises ValueError (from
    ``apply_id_timepoint``) when the time conflicts with the ``-t`` token in the
    experiment ID. Does not insert, flush or commit.
    """
    # Issue #81: '-t<days>' in the experiment ID is canonical for the timepoint.
    time = apply_id_timepoint(exp.id_timepoint_days, time_post_reaction_days)
    # Issue #83: the server owns the bucket — mirror the resolved time and
    # ignore any client-supplied value, so hand-entered rows land in
    # v_results_scalar_rollup's per-day buckets like bulk-uploaded ones.
    bucket = normalize_timepoint(time)
    if bucket is not None and is_primary:
        # Newest wins: demote any existing primary row in this bucket so
        # uq_primary_result_per_experiment_bucket cannot reject the insert.
        db.execute(
            update(ExperimentalResults)
            .where(
                ExperimentalResults.experiment_fk == exp.id,
                ExperimentalResults.time_post_reaction_bucket_days == bucket,
                ExperimentalResults.is_primary_timepoint_result.is_(True),
            )
            .values(is_primary_timepoint_result=False)
        )
    return time, bucket


def find_timepoint_candidates(
    db: Session,
    experiment_fk: int,
    time_post_reaction: Optional[float],
) -> List[ExperimentalResults]:
    """Find result rows for an experiment that match the timepoint bucket/tolerance."""
    query = (
        db.query(ExperimentalResults)
        .options(
            joinedload(ExperimentalResults.scalar_data),
            joinedload(ExperimentalResults.icp_data),
        )
        .filter(ExperimentalResults.experiment_fk == experiment_fk)
    )

    normalized = normalize_timepoint(time_post_reaction)
    if normalized is None:
        return (
            query.filter(
                and_(
                    ExperimentalResults.time_post_reaction_days.is_(None),
                    ExperimentalResults.time_post_reaction_bucket_days.is_(None),
                )
            )
            .order_by(ExperimentalResults.id.asc())
            .all()
        )

    lower_bound = normalized - TIMEPOINT_TOLERANCE_DAYS
    upper_bound = normalized + TIMEPOINT_TOLERANCE_DAYS
    return (
        query.filter(
            or_(
                ExperimentalResults.time_post_reaction_bucket_days.between(lower_bound, upper_bound),
                ExperimentalResults.time_post_reaction_days.between(lower_bound, upper_bound),
            )
        )
        .order_by(ExperimentalResults.id.asc())
        .all()
    )


def _rank_primary_candidate(row: ExperimentalResults) -> tuple:
    has_scalar = row.scalar_data is not None
    has_icp = row.icp_data is not None
    has_both = has_scalar and has_icp
    has_any = has_scalar or has_icp
    if has_both:
        return (0, -row.id)
    if has_any:
        return (1, -row.id)
    return (2, -row.id)


def choose_parent_candidate(
    candidates: List[ExperimentalResults],
    incoming_data_type: str,
) -> Optional[ExperimentalResults]:
    """
    Deterministically choose a parent row before child upsert.

    Preference:
    1) existing row with both scalar+icp
    2) row that has opposite data type (merge to complete row)
    3) most recent row with any data
    4) most recent row
    """
    if not candidates:
        return None

    both_rows = [row for row in candidates if row.scalar_data is not None and row.icp_data is not None]
    if both_rows:
        return max(both_rows, key=lambda row: row.id)

    if incoming_data_type == "scalar":
        opposite_rows = [row for row in candidates if row.icp_data is not None and row.scalar_data is None]
    else:
        opposite_rows = [row for row in candidates if row.scalar_data is not None and row.icp_data is None]
    if opposite_rows:
        return max(opposite_rows, key=lambda row: row.id)

    any_data_rows = [row for row in candidates if row.scalar_data is not None or row.icp_data is not None]
    if any_data_rows:
        return max(any_data_rows, key=lambda row: row.id)

    return max(candidates, key=lambda row: row.id)


def ensure_primary_result_for_timepoint(
    db: Session,
    experiment_fk: int,
    time_post_reaction: Optional[float],
) -> Optional[ExperimentalResults]:
    """
    Enforce a single primary row for an experiment/timepoint bucket.

    Returns the selected primary row, or None if no candidates exist.
    """
    candidates = find_timepoint_candidates(db, experiment_fk, time_post_reaction)
    if not candidates:
        return None

    primary_row = min(candidates, key=_rank_primary_candidate)
    normalized = normalize_timepoint(time_post_reaction)

    # Demote first to avoid unique partial-index conflicts when promoting.
    for row in candidates:
        row.is_primary_timepoint_result = False
        if normalized is not None:
            row.time_post_reaction_bucket_days = normalized

    primary_row.is_primary_timepoint_result = True
    if normalized is not None:
        primary_row.time_post_reaction_bucket_days = normalized

    db.flush()
    return primary_row


def create_experimental_result_row(
    db: Session,
    experiment: Experiment,
    time_post_reaction: Optional[float],
) -> ExperimentalResults:
    """Create an ExperimentalResults row with normalized bucket metadata."""
    if time_post_reaction is None:
        raise ValueError("time_post_reaction is required to create an experimental result row.")
    normalized = normalize_timepoint(time_post_reaction)
    new_result = ExperimentalResults(
        experiment_fk=experiment.id,
        time_post_reaction_days=time_post_reaction,
        time_post_reaction_bucket_days=normalized,
        is_primary_timepoint_result=True,
    )
    db.add(new_result)
    db.flush()
    return new_result


# ---------------------------------------------------------------------------
# Cumulative time across experiment lineage chains
# ---------------------------------------------------------------------------

def _ancestor_time_offset(
    experiment: Experiment,
    experiments_by_id: dict[int, Experiment],
    max_time_by_id: dict[int, float],
) -> float:
    """Sum of the max ``time_post_reaction_days`` of each ancestor, nearest first.

    For a base experiment (no parent) the offset is 0.
    For a derivation like ``HPHT_051-3`` whose chain is
    ``HPHT_051 → HPHT_051-2 → HPHT_051-3``, the offset equals
    ``max_time(HPHT_051-2) + max_time(HPHT_051)``, added in that order.

    Reads only the two mappings, so it issues no query. An ancestor missing
    from ``experiments_by_id`` ends the walk, as a missing row always did.
    """
    offset = 0.0
    current = experiment
    visited: set[int] = set()  # guard against cycles

    while current.parent_experiment_fk is not None:
        if current.id in visited:
            break  # safety: stop on cycles
        visited.add(current.id)

        parent = experiments_by_id.get(current.parent_experiment_fk)
        if parent is None:
            break

        max_time = max_time_by_id.get(parent.id)
        if max_time is not None:
            offset += max_time

        current = parent

    return offset


def _load_ancestors(db: Session, experiments_by_id: dict[int, Experiment]) -> None:
    """Add to ``experiments_by_id`` every ancestor that is not already in it.

    Ancestors normally share the chain's base ID and are already loaded, so
    this usually runs no query. It loops only for a parent outside the chain.
    """
    while True:
        missing = {
            exp.parent_experiment_fk for exp in experiments_by_id.values()
            if exp.parent_experiment_fk is not None and exp.parent_experiment_fk not in experiments_by_id
        }
        if not missing:
            return
        found = db.query(Experiment).filter(Experiment.id.in_(missing)).all()
        if not found:
            return  # dangling parent ids; the walk stops there
        for exp in found:
            experiments_by_id[exp.id] = exp


def update_cumulative_times_for_chain(db: Session, experiment_fk: int) -> None:
    """Recalculate ``cumulative_time_post_reaction`` for every result row in
    the same lineage chain as the given experiment.

    This is safe to call after any result insert / update — it will update
    the calling experiment **and** all sibling / downstream experiments that
    share the same ``base_experiment_id``.

    The chain is loaded once (issue #191, E-09): its experiments, each
    experiment's max time in one grouped query, and all its results in one
    query. It used to re-query every ancestor and its max time for every
    experiment of the chain, on every uploaded row.
    """
    experiment = db.query(Experiment).filter(Experiment.id == experiment_fk).first()
    if experiment is None:
        return

    base_id = series_key(experiment)

    # Gather every experiment in the chain
    chain_experiments = (
        db.query(Experiment)
        .filter(Experiment.base_experiment_id == base_id)
        .all()
    )
    if not chain_experiments:
        db.flush()
        return

    experiments_by_id = {exp.id: exp for exp in chain_experiments}
    _load_ancestors(db, experiments_by_id)

    max_time_by_id: dict[int, float] = {
        fk: max_time for fk, max_time in (
            db.query(
                ExperimentalResults.experiment_fk,
                sa_func.max(ExperimentalResults.time_post_reaction_days),
            )
            .filter(ExperimentalResults.experiment_fk.in_(list(experiments_by_id)))
            .group_by(ExperimentalResults.experiment_fk)
            .all()
        )
    }

    results_by_experiment: dict[int, list[ExperimentalResults]] = {}
    for result in (
        db.query(ExperimentalResults)
        .filter(ExperimentalResults.experiment_fk.in_([exp.id for exp in chain_experiments]))
        .all()
    ):
        results_by_experiment.setdefault(result.experiment_fk, []).append(result)

    for exp in chain_experiments:
        offset = _ancestor_time_offset(exp, experiments_by_id, max_time_by_id)
        for result in results_by_experiment.get(exp.id, []):
            if result.time_post_reaction_days is not None:
                result.cumulative_time_post_reaction_days = offset + result.time_post_reaction_days
            else:
                result.cumulative_time_post_reaction_days = None

    db.flush()
