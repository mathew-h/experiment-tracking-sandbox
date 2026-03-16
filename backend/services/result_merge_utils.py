from __future__ import annotations

from typing import List, Optional

from sqlalchemy import and_, or_, func as sa_func
from sqlalchemy.orm import Session, joinedload

from database import ExperimentalResults, Experiment

TIMEPOINT_TOLERANCE_DAYS = 0.0001
TIMEPOINT_BUCKET_DECIMALS = 4


def normalize_timepoint(time_post_reaction: Optional[float]) -> Optional[float]:
    """Normalize timepoint values to a stable bucketable float."""
    if time_post_reaction is None:
        return None
    return round(float(time_post_reaction), TIMEPOINT_BUCKET_DECIMALS)


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
    description: str,
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
        description=description,
    )
    db.add(new_result)
    db.flush()
    return new_result


# ---------------------------------------------------------------------------
# Cumulative time across experiment lineage chains
# ---------------------------------------------------------------------------

def get_ancestor_time_offset(db: Session, experiment: Experiment) -> float:
    """Walk up the experiment lineage chain and sum the max ``time_post_reaction``
    from each ancestor experiment.

    For a base experiment (no parent) the offset is 0.
    For a derivation like ``HPHT_051-3`` whose chain is
    ``HPHT_051 → HPHT_051-2 → HPHT_051-3``, the offset equals
    ``max_time(HPHT_051) + max_time(HPHT_051-2)``.

    Returns:
        Cumulative offset in days (float).
    """
    offset = 0.0
    current = experiment
    visited: set[int] = set()  # guard against cycles

    while current.parent_experiment_fk is not None:
        if current.id in visited:
            break  # safety: stop on cycles
        visited.add(current.id)

        parent = (
            db.query(Experiment)
            .filter(Experiment.id == current.parent_experiment_fk)
            .first()
        )
        if parent is None:
            break

        max_time = (
            db.query(sa_func.max(ExperimentalResults.time_post_reaction_days))
            .filter(ExperimentalResults.experiment_fk == parent.id)
            .scalar()
        )
        if max_time is not None:
            offset += max_time

        current = parent

    return offset


def update_cumulative_times_for_chain(db: Session, experiment_fk: int) -> None:
    """Recalculate ``cumulative_time_post_reaction`` for every result row in
    the same lineage chain as the given experiment.

    This is safe to call after any result insert / update — it will update
    the calling experiment **and** all sibling / downstream experiments that
    share the same ``base_experiment_id``.
    """
    experiment = db.query(Experiment).filter(Experiment.id == experiment_fk).first()
    if experiment is None:
        return

    base_id = experiment.base_experiment_id or experiment.experiment_id

    # Gather every experiment in the chain
    chain_experiments = (
        db.query(Experiment)
        .filter(Experiment.base_experiment_id == base_id)
        .all()
    )

    for exp in chain_experiments:
        offset = get_ancestor_time_offset(db, exp)

        results = (
            db.query(ExperimentalResults)
            .filter(ExperimentalResults.experiment_fk == exp.id)
            .all()
        )
        for result in results:
            if result.time_post_reaction_days is not None:
                result.cumulative_time_post_reaction_days = offset + result.time_post_reaction_days
            else:
                result.cumulative_time_post_reaction_days = None

    db.flush()
