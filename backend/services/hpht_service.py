"""HPHT runs (issue #149), read-only.

A run is every HPHT experiment sharing a base_experiment_id (HPHT_068,
HPHT_068-2, HPHT_068_Acidified). Run values (cumulative H2, H2 rate, is_variant)
are read from v_hpht_samples, never recomputed here; run loading is shared with
Core Flood through run_service. Samples are written through the generic results
endpoints (#146), so there is no write path here.
"""
from __future__ import annotations

import re
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.schemas.hpht import (
    HphtConditionsSummary, HphtRun, HphtRunListItem, HphtSample, HphtWarning,
)
from backend.api.schemas.results import IcpRow
from backend.api.schemas.runs import RunSegment
from backend.services import run_service as runs
from database.models.conditions import ExperimentalConditions
from database.models.experiments import Experiment
from database.reactor_slot import series_prefix

_VIEW = "v_hpht_samples"

# Yushen/Tan R slots, then Parr P slots, then anything else (no reactor last).
_SLOT_RE = re.compile(r"^(R|P)(\d+)$")
_SERIES_ORDER = {"R": 0, "P": 1}


def _slot_key(slot: str | None) -> tuple[int, int]:
    """Sort key for a reactor slot label: R01..R16, P01..P06, then the rest.

    Numeric, so R10 sorts after R09 rather than after R01."""
    match = _SLOT_RE.match(slot or "")
    if not match:
        return (len(_SERIES_ORDER), 0)
    return (_SERIES_ORDER[match.group(1)], int(match.group(2)))


def _sort_by_reactor(items: list[HphtRunListItem]) -> list[HphtRunListItem]:
    """Active first, then reactor slot. In place.

    Applied on top of run_service.sort_runs: the sort is stable, so runs on the
    same reactor keep its newest-sample-first, then base_id order."""
    runs.sort_runs(items)
    items.sort(key=lambda i: (not i.ongoing_experiment_ids,
                              _slot_key(i.reactor_slot)))
    return items


class HphtRunNotFound(LookupError):
    """No HPHT experiment has this base ID. Maps to 404."""


def is_hpht(conditions: ExperimentalConditions | None) -> bool:
    """HPHT the way v_hpht_samples reads it (reactor_slot._SERIES_BY_TYPE)."""
    return conditions is not None and series_prefix(conditions.experiment_type) == "R"


# Every spelling is_hpht accepts contains this once lower-cased. A SQL
# pre-filter only; is_hpht stays the rule (run_service.load_segments).
HPHT_TYPE_CONTAINS = ("hpht",)


def _base_mismatch(base_id: str, experiment_id: str) -> bool:
    """True unless the ID is the base itself or `<base>-...` / `<base>_...`.

    A bare prefix test would let HPHT_1960 pass under base HPHT_196."""
    return not (experiment_id == base_id
                or experiment_id.startswith(base_id + "-")
                or experiment_id.startswith(base_id + "_"))


def compute_warnings(base_id: str, segments: list[RunSegment]) -> list[HphtWarning]:
    """One warning per code, only when non-empty, IDs sorted."""
    found = {
        **runs.multi_root_and_ongoing(segments),
        "missing_description": sorted({s.experiment_id for s in segments if not s.description}),
        "base_mismatch": sorted({s.experiment_id for s in segments
                                 if _base_mismatch(base_id, s.experiment_id)}),
    }
    return [HphtWarning(code=code, experiment_ids=v) for code, v in found.items() if v]


def _conditions_summary(db: Session, segments: list[RunSegment]) -> HphtConditionsSummary | None:
    """Setup of the latest non-variant segment; None if the run is all variants."""
    real = [s for s in segments if not s.is_variant]
    if not real:
        return None
    seg = runs.latest_segment(real)
    exp, cond = db.execute(
        select(Experiment, ExperimentalConditions)
        .join(ExperimentalConditions, ExperimentalConditions.experiment_fk == Experiment.id)
        .where(ExperimentalConditions.id == seg.conditions_id)
    ).one()
    return HphtConditionsSummary(
        experiment_id=exp.experiment_id,
        conditions_id=cond.id,
        date=exp.date,
        sample_id=exp.sample_id,
        temperature_c=cond.temperature_c,
        rxn_temp_pressure_psi=cond.rxn_temp_pressure_psi,
        rock_mass_g=cond.rock_mass_g,
        water_volume_mL=cond.water_volume_mL,
        water_to_rock_ratio=cond.water_to_rock_ratio,
        catalyst=cond.catalyst,
        catalyst_ppm=cond.catalyst_ppm,
        feedstock=cond.feedstock,
    )


def _resolve(db: Session, requested_id: str) -> tuple[str, list[RunSegment]]:
    """Base ID and segments (by date) of the HPHT run `requested_id` names: a
    base, segment or variant ID (issue #158). Not-found reports the ID
    the caller sent."""
    base_id, segments = runs.resolve_run(
        db, requested_id, include=is_hpht, not_found=HphtRunNotFound,
        type_contains=HPHT_TYPE_CONTAINS)
    return base_id, runs.by_date(segments)


def get_run(db: Session, base_id: str) -> HphtRun:
    base_id, segments = _resolve(db, base_id)
    samples = runs.fetch_samples(db, _VIEW, base_ids=[base_id])
    return HphtRun(
        base_id=base_id,
        segments=segments,
        conditions=_conditions_summary(db, segments),
        samples=[HphtSample.model_validate(r) for r in runs.attach_notes(db, samples)],
        warnings=compute_warnings(base_id, segments),
    )


def get_run_icp(db: Session, base_id: str) -> list[IcpRow]:
    """ICP-OES readings for a run's samples, in view order; samples without ICP are omitted."""
    base_id, _ = _resolve(db, base_id)
    return runs.run_icp(db, _VIEW, base_id)


def list_runs(
    db: Session, scope: Literal["active", "all"] = "active", q: str | None = None,
) -> list[HphtRunListItem]:
    items = [
        HphtRunListItem(
            base_id=run.base_id,
            description=run.description,
            segment_count=len(run.segments),
            ongoing_experiment_ids=run.ongoing_experiment_ids,
            reactor_slot=runs.latest_segment(run.segments).reactor_slot,
            sample_count=len(run.real_samples),
            last_sample_date=run.last_sample_date,
            latest_cumulative_h2_grams_per_ton=run.latest_cumulative_h2_grams_per_ton,
            warning_count=len(compute_warnings(run.base_id, run.segments)),
        )
        for run in runs.summarize_runs(db, include=is_hpht, view=_VIEW, scope=scope, q=q,
                                       type_contains=HPHT_TYPE_CONTAINS)
    ]
    return _sort_by_reactor(items)
