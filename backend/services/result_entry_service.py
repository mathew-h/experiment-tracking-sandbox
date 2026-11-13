"""Hand entry of one sample (result + scalar rows) for any experiment type (issue #146).

Extracted from core_flood_service. Create and edit are atomic and audited: every
rejection happens before the first write, the service only flushes, and the
router commits once. Which columns a type may write is a FieldProfile; which
experiments a caller may touch is an `allow` guard on the conditions row.
Errors are ResultEntryError subclasses; routers translate them to HTTP statuses.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal

import structlog
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

import backend.services.calculations  # noqa: F401 — registers @register decorators
from backend.services import notes as notes_service
from backend.services.calculations.registry import recalculate
from backend.services.experiment_lookup import find_experiment
from backend.services.result_merge_utils import (
    resolve_primary_timepoint, update_cumulative_times_for_chain,
)
from backend.services.workdays import LAB_TZ
from database.models import ModificationsLog
from database.models.conditions import ExperimentalConditions
from database.models.enums import NoteType
from database.models.experiments import Experiment, ExperimentNotes
from database.models.results import ExperimentalResults, ScalarResults

log = structlog.get_logger(__name__)


class ResultEntryError(Exception):
    """Base for service errors the router maps to HTTP statuses."""


class ResultEntryNotFound(ResultEntryError):
    """Maps to 404."""


class ResultEntryInvalid(ResultEntryError):
    """Maps to 422."""


@dataclass(frozen=True)
class FieldProfile:
    """The result and scalar columns one experiment type may write by hand."""
    name: str
    result_fields: tuple[str, ...]
    scalar_fields: tuple[str, ...]


COMMON_RESULT_FIELDS = ("sample_tube_number",)
COMMON_SCALAR_FIELDS = (
    "measurement_date", "gc_run_date", "sampling_volume_mL", "h2_concentration",
    "gas_sampling_volume_ml", "gas_sampling_pressure_MPa", "final_ph",
    "final_conductivity_mS_cm",
)

CF_PROFILE = FieldProfile(
    name="core_flood",
    result_fields=COMMON_RESULT_FIELDS + (
        "flow_rate_mL_min", "nitrogen_flow_rate_mL_min", "inlet_pressure_psi",
        "outlet_pressure_psi", "permeability_flow_rate_mL_min",
    ),
    scalar_fields=COMMON_SCALAR_FIELDS,
)
# HPHT, Serum, Autoclave, Other. background_ammonium_concentration_mM is not
# writable here: it keeps its model default and its dedicated endpoint.
STANDARD_PROFILE = FieldProfile(
    name="standard",
    result_fields=COMMON_RESULT_FIELDS,
    scalar_fields=COMMON_SCALAR_FIELDS + ("gross_ammonium_concentration_mM",),
)

Guard = Callable[[ExperimentalConditions | None], bool]

_DATE_FIELDS = ("measurement_date", "gc_run_date")


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _lab_local(dt: datetime | None) -> datetime | None:
    """Naive input (including a date-only string) is lab-local; aware is kept."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=LAB_TZ)
    return dt


def _wall(dt: datetime) -> datetime:
    """Naive lab-local wall clock of an aware datetime.

    A start date loaded from Postgres carries a fixed offset (-04:00 / -05:00)
    while _lab_local attaches ZoneInfo(LAB_TZ); Python subtracts aware datetimes
    with different tzinfo as instants, which adds the DST hour across a change.
    Subtracting wall clocks does not.
    """
    return dt.astimezone(LAB_TZ).replace(tzinfo=None)


def _is_date_only(dt: datetime) -> bool:
    """A naive value at exactly midnight: what a date-only string parses to."""
    return dt.tzinfo is None and dt.time() == datetime.min.time()


def _default_day(raw_measurement: datetime, start: datetime) -> float:
    """Day of a sample from the experiment start, in lab-local time.

    A date-only sample date counts lab-local calendar days from the start date
    (31 of 85 production Core Flood starts carry a time of day, so a same-day
    sample would otherwise be negative). A full timestamp keeps the fractional
    wall-clock difference.
    """
    start_wall = _wall(_aware(start))
    sample_wall = _wall(_lab_local(raw_measurement))
    if _is_date_only(raw_measurement):
        return float((sample_wall.date() - start_wall.date()).days)
    return round((sample_wall - start_wall).total_seconds() / 86400, 4)


def conditions_for(db: Session, exp: Experiment) -> ExperimentalConditions | None:
    """The experiment's conditions row (lowest id, should a duplicate survive)."""
    return db.execute(
        select(ExperimentalConditions)
        .where(ExperimentalConditions.experiment_fk == exp.id)
        .order_by(ExperimentalConditions.id).limit(1)
    ).scalar_one_or_none()


def _jsonable(values: dict) -> dict:
    """Audit-log payload: datetimes become ISO strings."""
    return {k: v.isoformat() if isinstance(v, datetime) else v for k, v in values.items()}


def _audit(
    db: Session, exp: Experiment, table: str,
    mod_type: Literal["create", "update", "delete"],
    old: dict | None, new: dict | None, user_email: str,
) -> None:
    db.add(ModificationsLog(
        experiment_fk=exp.id,
        experiment_id=exp.experiment_id,
        modified_by=user_email,
        modification_type=mod_type,
        modified_table=table,
        old_values=_jsonable(old) if old is not None else None,
        new_values=_jsonable(new) if new is not None else None,
    ))


def _apply_result_note(
    db: Session, exp: Experiment, result: ExperimentalResults,
    text: str | None, user_email: str,
) -> None:
    """Set the sample's first result_note (lowest id, any author). Blank deletes it.

    Observation and modification notes are never touched. Audits only a change.
    """
    cleaned = text.strip() if text is not None else ""
    first = db.execute(
        select(ExperimentNotes)
        .where(ExperimentNotes.result_id == result.id,
               ExperimentNotes.note_type == NoteType.result_note)
        .order_by(ExperimentNotes.id).limit(1)
    ).scalar_one_or_none()
    if not cleaned:
        if first is None:
            return
        old = first.note_text
        db.delete(first)
        db.flush()
        _audit(db, exp, "experiment_notes", "delete", {"note_text": old}, None, user_email)
    elif first is None:
        notes_service.add_note(db, exp, cleaned, note_type=NoteType.result_note,
                               result_id=result.id, created_by=user_email)
        _audit(db, exp, "experiment_notes", "create", None, {"note_text": cleaned},
               user_email)
    else:
        if first.note_text == cleaned:
            return
        old = first.note_text
        first.note_text = cleaned
        previous = notes_service.release_upload_slot(first, user_email)
        old_vals: dict = {"note_text": old}
        new_vals: dict = {"note_text": cleaned}
        if previous is not None and previous != user_email:
            old_vals["created_by"] = previous
            new_vals["created_by"] = user_email
        _audit(db, exp, "experiment_notes", "update", old_vals, new_vals, user_email)
    db.flush()


def _add_modification_note(
    db: Session, exp: Experiment, result: ExperimentalResults,
    text: str | None, user_email: str,
) -> None:
    """Append a new 'modification' note when text is non-blank; never edits old ones."""
    cleaned = text.strip() if text is not None else ""
    if not cleaned:
        return
    notes_service.add_note(db, exp, cleaned, note_type=NoteType.modification,
                           result_id=result.id, created_by=user_email)
    _audit(db, exp, "experiment_notes", "create", None,
           {"note_type": NoteType.modification.value, "note_text": cleaned}, user_email)
    db.flush()


def _differs(current, new) -> bool:
    if isinstance(new, datetime) and isinstance(current, datetime):
        return _aware(current) != _aware(new)
    return current != new


def _check_allowed(
    cond: ExperimentalConditions | None, exp: Experiment, allow: Guard, rejection: str,
) -> None:
    if not allow(cond):
        raise ResultEntryInvalid(rejection.format(experiment_id=exp.experiment_id))


def create_result(
    db: Session, experiment_id: str, payload: BaseModel, user_email: str, *,
    profile: FieldProfile, allow: Guard, rejection: str,
) -> int:
    """Create one primary sample (result + scalar rows). Flushes, never commits.

    `payload` carries `measurement_date`, optional `time_post_reaction_days`,
    the profile's fields, optional `result_note` and optional `modification_note`.
    `rejection` is the 422 message when `allow` refuses the experiment; it may
    use `{experiment_id}`. All validation runs before resolve_primary_timepoint,
    which demotes the existing primary row eagerly.
    """
    exp = find_experiment(db, experiment_id)
    if exp is None:
        raise ResultEntryNotFound(f"Experiment {experiment_id} not found")
    _check_allowed(conditions_for(db, exp), exp, allow, rejection)

    measurement_date = _lab_local(payload.measurement_date)
    day = payload.time_post_reaction_days
    if day is None:
        if exp.date is None:
            raise ResultEntryInvalid(
                "time_post_reaction_days is required when the experiment has no start date")
        day = _default_day(payload.measurement_date, exp.date)
        if day < 0:
            raise ResultEntryInvalid("measurement_date is before the experiment start date")

    try:
        resolved_time, bucket = resolve_primary_timepoint(db, exp, day, True)
    except ValueError as exc:
        raise ResultEntryInvalid(str(exc)) from exc

    result_values = {f: getattr(payload, f) for f in profile.result_fields}
    result = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=resolved_time,
        time_post_reaction_bucket_days=bucket,
        is_primary_timepoint_result=True,
        **result_values,
    )
    db.add(result)
    db.flush()

    scalar_values: dict[str, Any] = {f: getattr(payload, f) for f in profile.scalar_fields}
    scalar_values["measurement_date"] = measurement_date
    scalar_values["gc_run_date"] = _lab_local(payload.gc_run_date) or measurement_date
    if scalar_values["h2_concentration"] is not None:
        scalar_values["h2_concentration_unit"] = "ppm"
    scalar = ScalarResults(result_id=result.id, **scalar_values)
    db.add(scalar)
    db.flush()
    recalculate(scalar, db)

    update_cumulative_times_for_chain(db, exp.id)

    _audit(db, exp, "experimental_results", "create", None,
           {"time_post_reaction_days": resolved_time,
            **{k: v for k, v in result_values.items() if v is not None}}, user_email)
    _audit(db, exp, "scalar_results", "create", None,
           {k: v for k, v in scalar_values.items() if v is not None}, user_email)
    result_note = getattr(payload, "result_note", None)
    if result_note is not None and result_note.strip():
        _apply_result_note(db, exp, result, result_note, user_email)
    _add_modification_note(db, exp, result, getattr(payload, "modification_note", None),
                           user_email)
    db.flush()
    log.info("result_entry_created", profile=profile.name,
             experiment_id=experiment_id, result_id=result.id)
    return result.id


def update_result(
    db: Session, result_id: int, payload: BaseModel, user_email: str, *,
    profile: FieldProfile, allow: Guard, rejection: str,
    experiment_id: str | None = None,
) -> None:
    """Edit one primary sample's fields. Flushes, never commits; a no-op writes nothing.

    Only the fields set on `payload` are considered. When `experiment_id` is
    given, a result belonging to another experiment is not found. Every
    rejection happens before the first write.
    """
    result = db.get(ExperimentalResults, result_id)
    if result is None:
        raise ResultEntryNotFound(f"Result {result_id} not found")
    exp = db.get(Experiment, result.experiment_fk)
    if experiment_id is not None and exp.experiment_id != experiment_id:
        raise ResultEntryNotFound(f"Result {result_id} not found on {experiment_id}")
    _check_allowed(conditions_for(db, exp), exp, allow, rejection)
    if not result.is_primary_timepoint_result:
        raise ResultEntryNotFound("Sample is not a primary timepoint")

    data = payload.model_dump(exclude_unset=True)
    for f in _DATE_FIELDS:
        if f in data:
            data[f] = _lab_local(data[f])
    new_result = {k: v for k, v in data.items() if k in profile.result_fields}
    new_scalar = {k: v for k, v in data.items() if k in profile.scalar_fields}
    if new_scalar.get("h2_concentration") is not None:
        new_scalar["h2_concentration_unit"] = "ppm"

    changed_result = {k: v for k, v in new_result.items()
                      if _differs(getattr(result, k), v)}
    old_result = {k: getattr(result, k) for k in changed_result}
    for k, v in changed_result.items():
        setattr(result, k, v)

    scalar = db.execute(
        select(ScalarResults).where(ScalarResults.result_id == result.id)
    ).scalar_one_or_none()
    created = False
    # A payload of nulls on a sample with no scalar row is a no-op, not a create.
    if scalar is None and any(v is not None for v in new_scalar.values()):
        scalar = ScalarResults(result_id=result.id)
        db.add(scalar)
        created = True
    changed_scalar: dict = {}
    old_scalar: dict = {}
    if scalar is not None:
        changed_scalar = {k: v for k, v in new_scalar.items()
                          if _differs(getattr(scalar, k), v)}
        old_scalar = {k: getattr(scalar, k) for k in changed_scalar}
        for k, v in changed_scalar.items():
            setattr(scalar, k, v)

    db.flush()
    if scalar is not None and (changed_scalar or created):
        recalculate(scalar, db)

    if "result_note" in data:
        _apply_result_note(db, exp, result, data["result_note"], user_email)
    if "modification_note" in data:
        _add_modification_note(db, exp, result, data["modification_note"], user_email)
    if changed_result:
        _audit(db, exp, "experimental_results", "update", old_result, changed_result,
               user_email)
    if created:
        _audit(db, exp, "scalar_results", "create", None, changed_scalar, user_email)
    elif changed_scalar:
        _audit(db, exp, "scalar_results", "update", old_scalar, changed_scalar, user_email)
    db.flush()
    log.info("result_entry_updated", profile=profile.name, result_id=result_id,
             fields=sorted({*changed_result, *changed_scalar}))
