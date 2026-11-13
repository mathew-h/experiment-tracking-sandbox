"""Core flood runs (issue #133).

A run is every Core Flood experiment sharing a base_experiment_id. Run values
(cumulative volume, H2 rate, is_variant, ...) are read from v_core_flood_samples,
never recomputed here; run loading is shared with HPHT through
run_service (#149). Sample create/edit delegate to result_entry_service with
CF_PROFILE (issue #146). The service raises CoreFloodError subclasses; the
router translates them to HTTP statuses.
"""
from __future__ import annotations

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
from backend.services.result_entry_service import CF_PROFILE
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


# Every spelling is_core_flood accepts ("Core Flood", "CoreFlood", "CF", in any
# case or spacing) contains one of these once lower-cased. A SQL pre-filter
# only; is_core_flood stays the rule (run_service.load_segments).
CORE_FLOOD_TYPE_CONTAINS = ("core", "cf")


_VIEW = "v_core_flood_samples"


def fetch_samples(
    db: Session, *, base_ids: list[str] | None = None, result_id: int | None = None,
) -> list[dict]:
    """Rows of v_core_flood_samples in view order, optionally filtered."""
    return runs.fetch_samples(db, _VIEW, base_ids=base_ids, result_id=result_id)


# Shared with the HPHT run page; the router calls it as svc.attach_notes.
attach_notes = runs.attach_notes


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


def _resolve(
    db: Session, requested_id: str,
) -> tuple[str, list[CoreFloodSegment]]:
    """Base ID and segments of the core flood run `requested_id` names:
    a base, segment or variant ID (issue #158). Not-found reports the
    ID the caller sent."""
    return runs.resolve_run(db, requested_id, include=is_core_flood, not_found=CoreFloodNotFound,
                            type_contains=CORE_FLOOD_TYPE_CONTAINS)


def get_run(db: Session, base_id: str) -> CoreFloodRun:
    base_id, segments = _resolve(db, base_id)
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
    base_id, _ = _resolve(db, base_id)
    return runs.run_icp(db, _VIEW, base_id)


def list_runs(
    db: Session, scope: Literal["active", "all"] = "active", q: str | None = None,
) -> list[CoreFloodRunListItem]:
    items = [
        CoreFloodRunListItem(
            base_id=run.base_id,
            description=run.description,
            segment_count=len(run.segments),
            ongoing_experiment_ids=run.ongoing_experiment_ids,
            rig=runs.latest_segment(run.segments).reactor_slot,
            sample_count=len(run.real_samples),
            first_sample_date=run.first_sample_date,
            last_sample_date=run.last_sample_date,
            latest_cumulative_h2_grams_per_ton=run.latest_cumulative_h2_grams_per_ton,
            warning_count=len(compute_warnings(run.segments, run.samples)),
        )
        for run in runs.summarize_runs(db, include=is_core_flood, view=_VIEW, scope=scope, q=q,
                                       type_contains=CORE_FLOOD_TYPE_CONTAINS)
    ]
    return runs.sort_runs(items)


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
