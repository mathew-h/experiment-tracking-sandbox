"""Core flood runs (issue #133).

A run is every Core Flood experiment sharing a base_experiment_id. Run values
(cumulative volume, H2 rate, is_variant, ...) are read from v_core_flood_samples,
never recomputed here; run loading is shared with HPHT through
run_service (#149). Sample create/edit delegate to result_entry_service with
CF_PROFILE (issue #146). The service raises CoreFloodError subclasses; the
router translates them to HTTP statuses.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Literal

import structlog
from sqlalchemy.orm import Session

from backend.api.schemas.core_floods import (
    CoreFloodIcpRow,
    CoreFloodRun, CoreFloodRunListItem, CoreFloodSample, CoreFloodSampleCreate,
    CoreFloodSampleUpdate, CoreFloodSegment, CoreFloodWarning,
)
from backend.services import result_entry_service as entry
from backend.services import run_service as runs
from backend.services.result_entry_service import CF_PROFILE, _aware
from database.models.conditions import ExperimentalConditions
from database.reactor_slot import series_prefix

log = structlog.get_logger(__name__)


class CoreFloodError(entry.ResultEntryError):
    """Base for service errors the router maps to HTTP statuses."""


class CoreFloodNotFound(CoreFloodError, entry.ResultEntryNotFound):
    """Maps to 404."""


class CoreFloodInvalid(CoreFloodError, entry.ResultEntryInvalid):
    """Maps to 422."""


def is_core_flood(conditions: ExperimentalConditions | None) -> bool:
    return conditions is not None and series_prefix(conditions.experiment_type) == "CF"


_VIEW = "v_core_flood_samples"


def fetch_samples(
    db: Session, *, base_ids: list[str] | None = None, result_id: int | None = None,
) -> list[dict]:
    """Rows of v_core_flood_samples in view order, optionally filtered."""
    return runs.fetch_samples(db, _VIEW, base_ids=base_ids, result_id=result_id)


# Shared with the HPHT run page; module names kept for existing importers.
attach_notes = runs.attach_notes
run_description = runs.run_description


def _load_segments(db: Session, base_id: str | None = None) -> dict[str, list[CoreFloodSegment]]:
    """Core Flood segments grouped by base_experiment_id (one query)."""
    return runs.load_segments(db, include=is_core_flood, base_id=base_id)


def compute_warnings(
    segments: list[CoreFloodSegment], samples: list[dict],
) -> list[CoreFloodWarning]:
    """One warning per code, only when non-empty, IDs sorted."""
    def ids(items: Iterable[CoreFloodSegment]) -> list[str]:
        return sorted({s.experiment_id for s in items})

    non_variant = [s for s in segments if not s.is_variant]
    found = {
        **runs.multi_root_and_ongoing(segments),
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
    segments = runs.by_date(segments)
    samples = fetch_samples(db, base_ids=[base_id])
    return CoreFloodRun(
        base_id=base_id,
        segments=segments,
        samples=[CoreFloodSample.model_validate(r) for r in attach_notes(db, samples)],
        warnings=compute_warnings(segments, samples),
    )


def get_run_icp(db: Session, base_id: str) -> list[CoreFloodIcpRow]:
    """ICP-OES readings for a run's samples, in view order; samples without ICP are omitted."""
    if not _load_segments(db, base_id).get(base_id):
        raise CoreFloodNotFound(base_id)
    return runs.run_icp(db, _VIEW, base_id)


def list_runs(
    db: Session, scope: Literal["active", "all"] = "active", q: str | None = None,
) -> list[CoreFloodRunListItem]:
    by_base = _load_segments(db)
    samples_by_base: dict[str, list[dict]] = defaultdict(list)
    for row in fetch_samples(db, base_ids=list(by_base)):
        samples_by_base[row["run_base_id"]].append(row)

    needle = runs.normalize_query(q)
    items: list[CoreFloodRunListItem] = []
    for base_id, segments in by_base.items():
        description = run_description(segments)
        if not runs.matches(needle, base_id, segments, description):
            continue
        samples = samples_by_base.get(base_id, [])
        ongoing = runs.ongoing_ids(segments)
        if scope == "active" and not ongoing:
            continue
        real = [r for r in samples if not r["is_variant"]]
        dates = [_aware(r["sample_date"]) for r in real if r["sample_date"] is not None]
        items.append(CoreFloodRunListItem(
            base_id=base_id,
            description=description,
            segment_count=len(segments),
            ongoing_experiment_ids=ongoing,
            rig=runs.latest_segment(segments).reactor_slot,
            sample_count=len(real),
            first_sample_date=min(dates) if dates else None,
            last_sample_date=max(dates) if dates else None,
            latest_cumulative_h2_grams_per_ton=(
                real[-1]["cumulative_h2_grams_per_ton"] if real else None),
            warning_count=len(compute_warnings(segments, samples)),
        ))
    return runs.sort_runs(items)


# Writable Core Flood columns; kept as module names for existing importers.
RESULT_FIELDS = CF_PROFILE.result_fields
SCALAR_FIELDS = CF_PROFILE.scalar_fields
_NOT_CF = "{experiment_id} is not a Core Flood experiment"


def _as_core_flood_error(exc: entry.ResultEntryError) -> CoreFloodError:
    if isinstance(exc, entry.ResultEntryNotFound):
        return CoreFloodNotFound(str(exc))
    return CoreFloodInvalid(str(exc))


def create_sample(
    db: Session, experiment_id: str, payload: CoreFloodSampleCreate, user_email: str,
) -> int:
    """Create one core flood sample through the shared result-entry service.

    Flushes, never commits; see result_entry_service.create_result.
    """
    try:
        return entry.create_result(db, experiment_id, payload, user_email,
                                   profile=CF_PROFILE, allow=is_core_flood,
                                   rejection=_NOT_CF)
    except entry.ResultEntryError as exc:
        raise _as_core_flood_error(exc) from exc


def update_sample(
    db: Session, result_id: int, payload: CoreFloodSampleUpdate, user_email: str,
) -> None:
    """Edit one core flood sample through the shared result-entry service.

    Flushes, never commits; see result_entry_service.update_result.
    """
    try:
        entry.update_result(db, result_id, payload, user_email,
                            profile=CF_PROFILE, allow=is_core_flood, rejection=_NOT_CF)
    except entry.ResultEntryError as exc:
        raise _as_core_flood_error(exc) from exc
