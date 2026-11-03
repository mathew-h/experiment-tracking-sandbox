"""Core flood runs (issue #133): read side.

A run is every Core Flood experiment sharing a base_experiment_id. Run values
(cumulative volume, H2 rate, is_variant, ...) are read from v_core_flood_samples,
never recomputed here. The service raises CoreFloodError subclasses; the router
translates them to HTTP statuses.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable, Literal

import structlog
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from backend.api.schemas.core_floods import (
    CoreFloodRun, CoreFloodRunListItem, CoreFloodSample, CoreFloodSegment,
    CoreFloodWarning,
)
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus
from database.models.experiments import Experiment
from database.reactor_slot import series_prefix

log = structlog.get_logger(__name__)

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


class CoreFloodError(Exception):
    """Base for service errors the router maps to HTTP statuses."""


class CoreFloodNotFound(CoreFloodError):
    """Maps to 404."""


class CoreFloodInvalid(CoreFloodError):
    """Maps to 422."""


def is_core_flood(conditions: ExperimentalConditions | None) -> bool:
    return conditions is not None and series_prefix(conditions.experiment_type) == "CF"


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def fetch_samples(
    db: Session, *, base_ids: list[str] | None = None, result_id: int | None = None,
) -> list[dict]:
    """Rows of v_core_flood_samples in view order, optionally filtered."""
    sql = "SELECT * FROM v_core_flood_samples"
    clauses: list[str] = []
    params: dict = {}
    if base_ids is not None:
        if not base_ids:
            return []
        clauses.append("run_base_id = ANY(:base_ids)")
        params["base_ids"] = list(base_ids)
    if result_id is not None:
        clauses.append("result_id = :result_id")
        params["result_id"] = result_id
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += (" ORDER BY run_base_id, cumulative_time_post_reaction_days NULLS LAST,"
            " result_id")
    return [dict(r) for r in db.execute(text(sql), params).mappings()]


def _load_segments(db: Session, base_id: str | None = None) -> dict[str, list[CoreFloodSegment]]:
    """Core Flood segments grouped by base_experiment_id (one query)."""
    stmt = (
        select(Experiment, ExperimentalConditions)
        .join(ExperimentalConditions, ExperimentalConditions.experiment_fk == Experiment.id)
        .where(Experiment.base_experiment_id.is_not(None))
        .options(selectinload(Experiment.parent), selectinload(Experiment.description_note))
    )
    if base_id is not None:
        stmt = stmt.where(Experiment.base_experiment_id == base_id)
    grouped: dict[str, list[CoreFloodSegment]] = defaultdict(list)
    seen: set[int] = set()
    for exp, cond in db.execute(stmt).all():
        # uq_conditions_experiment_fk makes this 1:1, but guard older databases.
        if exp.id in seen or not is_core_flood(cond):
            continue
        seen.add(exp.id)
        parent = exp.parent
        grouped[exp.base_experiment_id].append(CoreFloodSegment(
            id=exp.id,
            experiment_id=exp.experiment_id,
            status=exp.status.value if exp.status is not None else None,
            date=exp.date,
            parent_experiment_id=parent.experiment_id if parent is not None else None,
            is_variant=parent is not None
            and exp.experiment_id.startswith(parent.experiment_id + "_"),
            description=exp.description,
            conditions_id=cond.id,
            pore_volume_mL=cond.pore_volume_mL,
            rock_mass_g=cond.rock_mass_g,
            reactor_slot=cond.reactor_slot,
        ))
    return dict(grouped)


def compute_warnings(
    segments: list[CoreFloodSegment], samples: list[dict],
) -> list[CoreFloodWarning]:
    """One warning per code, only when non-empty, IDs sorted."""
    def ids(items: Iterable[CoreFloodSegment]) -> list[str]:
        return sorted({s.experiment_id for s in items})

    non_variant = [s for s in segments if not s.is_variant]
    roots = ids(s for s in non_variant if s.parent_experiment_id is None)
    ongoing = ids(s for s in segments if s.status == ExperimentStatus.ONGOING.value)
    found = {
        "multiple_roots": roots if len(roots) > 1 else [],
        "multiple_ongoing": ongoing if len(ongoing) > 1 else [],
        "missing_pore_volume": ids(s for s in non_variant if s.pore_volume_mL is None),
        "missing_description": ids(s for s in segments if not s.description),
        "sample_missing_flow_rate": sorted({
            r["experiment_id"] for r in samples
            if not r["is_variant"] and r["flow_rate_mL_min"] is None
        }),
    }
    return [CoreFloodWarning(code=code, experiment_ids=v) for code, v in found.items() if v]


def get_run(db: Session, base_id: str) -> CoreFloodRun:
    segments = _load_segments(db, base_id).get(base_id)
    if not segments:
        raise CoreFloodNotFound(base_id)
    segments = sorted(segments, key=lambda s: (
        s.date is None, _aware(s.date) or _EPOCH, s.experiment_id))
    samples = fetch_samples(db, base_ids=[base_id])
    return CoreFloodRun(
        base_id=base_id,
        segments=segments,
        samples=[CoreFloodSample.model_validate(r) for r in samples],
        warnings=compute_warnings(segments, samples),
    )


def list_runs(
    db: Session, scope: Literal["active", "all"] = "active", q: str | None = None,
) -> list[CoreFloodRunListItem]:
    by_base = _load_segments(db)
    samples_by_base: dict[str, list[dict]] = defaultdict(list)
    for row in fetch_samples(db, base_ids=list(by_base)):
        samples_by_base[row["run_base_id"]].append(row)

    needle = q.strip().lower() if q and q.strip() else None
    items: list[CoreFloodRunListItem] = []
    for base_id, segments in by_base.items():
        if needle and needle not in base_id.lower() and not any(
            needle in s.experiment_id.lower() for s in segments
        ):
            continue
        samples = samples_by_base.get(base_id, [])
        ongoing = sorted(s.experiment_id for s in segments
                         if s.status == ExperimentStatus.ONGOING.value)
        if scope == "active" and not ongoing:
            continue
        real = [r for r in samples if not r["is_variant"]]
        dates = [_aware(r["sample_date"]) for r in real if r["sample_date"] is not None]
        latest_seg = max(segments, key=lambda s: (
            s.date is not None, _aware(s.date) or _EPOCH, s.id))
        items.append(CoreFloodRunListItem(
            base_id=base_id,
            segment_count=len(segments),
            ongoing_experiment_ids=ongoing,
            rig=latest_seg.reactor_slot,
            sample_count=len(real),
            first_sample_date=min(dates) if dates else None,
            last_sample_date=max(dates) if dates else None,
            latest_cumulative_h2_grams_per_ton=(
                real[-1]["cumulative_h2_grams_per_ton"] if real else None),
            warning_count=len(compute_warnings(segments, samples)),
        ))
    # Active first, then most recent sample first (NULLs last), then base_id.
    items.sort(key=lambda i: (
        not i.ongoing_experiment_ids,
        i.last_sample_date is None,
        -i.last_sample_date.timestamp() if i.last_sample_date else 0,
        i.base_id,
    ))
    return items
