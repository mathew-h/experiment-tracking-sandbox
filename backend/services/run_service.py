"""Run loading shared by the Core Flood (#133) and HPHT (#149) run pages.

A run is every experiment of one series sharing a base_experiment_id, split into
sequential segments (X_001, X_001-2, ...) plus `_Text` variants of a segment
(X_001-2_Bypass, HPHT_061_Desorption). Which experiments belong to the series is
the caller's `include` predicate; nothing here knows about Core Flood or HPHT.
Run values are read from the series' samples view, never recomputed here.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Iterable, Protocol, Sequence, TypeVar

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from backend.api.schemas.runs import RunSegment
from backend.services.icp_series import ICP_SELECT, icp_rows
from backend.api.schemas.results import IcpRow
from backend.services.result_entry_service import _aware
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus, NoteType
from database.models.experiments import Experiment, ExperimentNotes

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)

# Samples views a run can be read from. The name is interpolated into SQL, so it
# must come from this set, never from a request.
SAMPLE_VIEWS = frozenset({"v_core_flood_samples", "v_hpht_samples"})

_SAMPLE_NOTE_TYPES = (NoteType.result_note, NoteType.observation, NoteType.modification)


def _view(name: str) -> str:
    if name not in SAMPLE_VIEWS:
        raise ValueError(f"not a run samples view: {name}")
    return name


def resolve_base_id(db: Session, experiment_or_base_id: str) -> str:
    """base_experiment_id of the experiment with this ID, or the ID
    itself when it is already a base or matches no experiment (so the
    caller's not-found path still runs).

    Lets a run URL take the segment ID a researcher copies from a
    reactor card (HPHT_297-2, CF_020-5_Bypass1) as well as the base
    (issue #158). Type-blind: the caller's `include` predicate still
    decides whether the run is its kind.
    """
    base = db.execute(
        select(Experiment.base_experiment_id)
        .where(Experiment.experiment_id == experiment_or_base_id)
    ).scalar_one_or_none()
    return base or experiment_or_base_id


def load_segments(
    db: Session,
    *,
    include: Callable[[ExperimentalConditions], bool],
    base_id: str | None = None,
) -> dict[str, list[RunSegment]]:
    """Segments whose conditions pass `include`, grouped by base_experiment_id (one query)."""
    stmt = (
        select(Experiment, ExperimentalConditions)
        .join(ExperimentalConditions, ExperimentalConditions.experiment_fk == Experiment.id)
        .where(Experiment.base_experiment_id.is_not(None))
        .options(selectinload(Experiment.parent), selectinload(Experiment.description_note))
        # Lowest conditions id first, so the `seen` guard matches _conditions_for.
        .order_by(Experiment.id, ExperimentalConditions.id)
    )
    if base_id is not None:
        stmt = stmt.where(Experiment.base_experiment_id == base_id)
    grouped: dict[str, list[RunSegment]] = defaultdict(list)
    seen: set[int] = set()
    for exp, cond in db.execute(stmt).all():
        # uq_conditions_experiment_fk makes this 1:1, but guard older databases.
        if exp.id in seen or not include(cond):
            continue
        seen.add(exp.id)
        parent = exp.parent
        grouped[exp.base_experiment_id].append(RunSegment(
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


def by_date(segments: Iterable[RunSegment]) -> list[RunSegment]:
    """Segments oldest first; undated last, then by experiment ID."""
    return sorted(segments, key=lambda s: (
        s.date is None, _aware(s.date) or _EPOCH, s.experiment_id))


def latest_segment(segments: Sequence[RunSegment]) -> RunSegment:
    """The newest dated segment (undated ones lose), ties broken by id."""
    return max(segments, key=lambda s: (s.date is not None, _aware(s.date) or _EPOCH, s.id))


def run_description(segments: list[RunSegment]) -> str | None:
    """Root segment's description (non-variant, no parent, earliest date); else the
    first segment that has one."""
    ordered = by_date(segments)
    roots = [s for s in ordered if not s.is_variant and s.parent_experiment_id is None]
    if roots and roots[0].description:
        return roots[0].description
    return next((s.description for s in ordered if s.description), None)


def ongoing_ids(segments: Iterable[RunSegment]) -> list[str]:
    return sorted(s.experiment_id for s in segments
                  if s.status == ExperimentStatus.ONGOING.value)


def matches(needle: str | None, base_id: str, segments: Sequence[RunSegment],
            description: str | None) -> bool:
    """List filter: `needle` (already lowercased) in the base ID, any segment ID or
    the run description. No needle matches everything."""
    if not needle:
        return True
    return (needle in base_id.lower()
            or any(needle in s.experiment_id.lower() for s in segments)
            or needle in (description or "").lower())


def normalize_query(q: str | None) -> str | None:
    return q.strip().lower() if q and q.strip() else None


def multi_root_and_ongoing(segments: Sequence[RunSegment]) -> dict[str, list[str]]:
    """The `multiple_roots` and `multiple_ongoing` warning IDs (empty when fine)."""
    roots = sorted({s.experiment_id for s in segments
                    if not s.is_variant and s.parent_experiment_id is None})
    ongoing = sorted({s.experiment_id for s in segments
                      if s.status == ExperimentStatus.ONGOING.value})
    return {
        "multiple_roots": roots if len(roots) > 1 else [],
        "multiple_ongoing": ongoing if len(ongoing) > 1 else [],
    }


class _ListItem(Protocol):
    base_id: str
    ongoing_experiment_ids: list[str]
    last_sample_date: datetime | None


T = TypeVar("T", bound=_ListItem)


def sort_runs(items: list[T]) -> list[T]:
    """Active first, then most recent sample first (NULLs last), then base_id. In place."""
    items.sort(key=lambda i: (
        not i.ongoing_experiment_ids,
        i.last_sample_date is None,
        -i.last_sample_date.timestamp() if i.last_sample_date else 0,
        i.base_id,
    ))
    return items


def fetch_samples(
    db: Session, view: str, *, base_ids: list[str] | None = None,
    result_id: int | None = None,
) -> list[dict]:
    """Rows of a run samples view in view order, optionally filtered."""
    sql = f"SELECT * FROM {_view(view)}"
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


def latest_sample_by_base(rows: Iterable[dict]) -> dict[str, dict]:
    """The last non-variant row per run_base_id, given rows in view order.

    Rows come from `fetch_samples`, ordered by run_base_id, then
    cumulative_time_post_reaction_days NULLS LAST, then result_id, so the last
    row seen for a base is the run's latest sample. Rows without a base ID are
    skipped. The dashboard's reactor cards read their run H2 and last sampled
    date from this row (issue #165).
    """
    latest: dict[str, dict] = {}
    for r in rows:
        if r["is_variant"] or r["run_base_id"] is None:
            continue
        latest[r["run_base_id"]] = r
    return latest


def attach_notes(db: Session, rows: list[dict]) -> list[dict]:
    """Add `notes` (result-scoped result_note/observation/modification, by id) to each row."""
    by_result: dict[int, list[dict]] = defaultdict(list)
    ids = [r["result_id"] for r in rows]
    if ids:
        found = db.execute(
            select(ExperimentNotes)
            .where(ExperimentNotes.result_id.in_(ids),
                   ExperimentNotes.note_type.in_(_SAMPLE_NOTE_TYPES))
            .order_by(ExperimentNotes.id)
        ).scalars()
        for n in found:
            by_result[n.result_id].append({
                "id": n.id, "note_type": n.note_type.value,
                "note_text": n.note_text, "created_by": n.created_by})
    return [{**r, "notes": by_result.get(r["result_id"], [])} for r in rows]


def run_icp(db: Session, view: str, base_id: str) -> list[IcpRow]:
    """ICP-OES readings for a run's samples, in view order; samples without ICP are omitted."""
    sql = (
        "SELECT v.result_id, v.experiment_id, v.is_variant, "
        "v.cumulative_time_post_reaction_days, v.sample_date, " + ICP_SELECT +
        f" FROM {_view(view)} v JOIN icp_results i ON i.result_id = v.result_id"
        " WHERE v.run_base_id = :base_id"
        " ORDER BY v.cumulative_time_post_reaction_days NULLS LAST, v.result_id")
    return icp_rows(db.execute(text(sql), {"base_id": base_id}).mappings())
