"""Typed experiment notes: the single definition of how text becomes a note row.

Issue #118, PR1. Free text about an experiment used to live in four places
(the positional "first note", experimental_results.description,
brine_modification_description, and ordinary notes) with nothing declaring what
each was for. experiment_notes now carries a note_type and an optional
result_id, and during the transition every legacy write path writes BOTH its
old column and a typed note row through the helpers here, so Power BI (still
reading the old columns) and the new model always agree.

Three helpers, three situations:

* add_note -- append one typed note. Used when the caller knows the type and
  scope (POST /experiments/{id}/notes, POST /api/results).
* add_first_or_observation_note -- the legacy "first note is the description"
  rule, made explicit: a note written to an experiment that has NO notes yet is
  its 'description'; any later note is an 'observation'. Making a later note the
  description would (a) contradict what the legacy min(id) readers show until
  PR3 and (b) collide with the partial unique index once PR2 promotes the
  oldest note. Used by the New Experiments upload and treatment auto-creation.
* sync_result_note -- mirror a legacy result COLUMN into a note SLOT. A column
  holds one value, so the mirror is one note per (result, type, created_by):
  re-uploading a workbook updates the note's text in place rather than
  appending a duplicate, and clearing the column deletes the note. This is what
  makes "both sides match" true after the second upload, not just the first.

Nothing here validates content. Nothing is required; a blank value simply
writes no note (spec: behaviour change comes from visibility, not validators).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.enums import NoteType
from database.models.experiments import Experiment, ExperimentNotes
from database.models.results import ExperimentalResults


def _clean(text: Optional[str]) -> Optional[str]:
    """Trim; return None for None, blank, or pandas' stringified NaN."""
    if text is None:
        return None
    cleaned = str(text).strip()
    if not cleaned or cleaned.lower() == "nan":
        return None
    return cleaned


def add_note(
    db: Session,
    experiment: Experiment,
    note_text: str,
    *,
    note_type: NoteType = NoteType.observation,
    result_id: Optional[int] = None,
    created_by: Optional[str] = None,
    needs_review: bool = False,
    created_at: Optional[datetime] = None,
) -> ExperimentNotes:
    """Append one typed note to ``experiment`` and flush it.

    The database enforces scope (ck_note_scope), the one-description rule
    (uq_one_description_per_experiment) and same-experiment result ownership
    (fk_note_result_same_experiment); an invalid combination raises
    IntegrityError at flush. Callers that want a friendlier error pre-check
    (see the notes router) -- this helper does not, so the DB stays the
    authority.
    """
    note = ExperimentNotes(
        experiment_id=experiment.experiment_id,
        experiment_fk=experiment.id,
        note_text=note_text,
        note_type=note_type,
        result_id=result_id,
        created_by=created_by,
        needs_review=needs_review,
    )
    if created_at is not None:
        note.created_at = created_at
    db.add(note)
    db.flush()
    return note


def add_first_or_observation_note(
    db: Session,
    experiment: Experiment,
    note_text: str,
    *,
    created_by: Optional[str] = None,
) -> ExperimentNotes:
    """Write ``note_text`` as the experiment's 'description' iff it has no notes
    yet; otherwise as an 'observation'. See the module docstring for why."""
    has_any = db.execute(
        select(ExperimentNotes.id)
        .where(ExperimentNotes.experiment_fk == experiment.id)
        .limit(1)
    ).first() is not None
    note_type = NoteType.observation if has_any else NoteType.description
    return add_note(db, experiment, note_text, note_type=note_type, created_by=created_by)


def sync_result_note(
    db: Session,
    result: ExperimentalResults,
    note_type: NoteType,
    note_text: Optional[str],
    *,
    created_by: str,
) -> Optional[ExperimentNotes]:
    """Mirror a legacy result column into its typed-note slot.

    Exactly one note exists per (result.id, note_type, created_by):
      * text present, no slot   -> create the note
      * text present, slot held -> update note_text in place (same row id)
      * text blank/None, slot   -> delete the note (the column was cleared)
      * text blank/None, none   -> no-op

    ``created_by`` is part of the slot key on purpose: a researcher's
    hand-written modification note (created_by = their email) is never
    overwritten by a bulk upload's mirror (created_by = 'master_bulk_upload').

    Returns the note now standing in the slot, or None if the slot is empty.
    """
    cleaned = _clean(note_text)
    existing = db.execute(
        select(ExperimentNotes)
        .where(
            ExperimentNotes.result_id == result.id,
            ExperimentNotes.note_type == note_type,
            ExperimentNotes.created_by == created_by,
        )
        .order_by(ExperimentNotes.id)
    ).scalars().first()

    if cleaned is None:
        if existing is not None:
            db.delete(existing)
            db.flush()
        return None

    if existing is not None:
        if existing.note_text != cleaned:
            existing.note_text = cleaned
            db.flush()
        return existing

    experiment = result.experiment or db.get(Experiment, result.experiment_fk)
    return add_note(
        db,
        experiment,
        cleaned,
        note_type=note_type,
        result_id=result.id,
        created_by=created_by,
    )
