"""Typed experiment notes: the single definition of how text becomes a note row.

Issue #118, PR1. Free text about an experiment used to live in four places
(the positional "first note", the two free-text result columns dropped by
issue #122 PR-D, and ordinary notes) with nothing declaring what
each was for. experiment_notes now carries a note_type and an optional
result_id, and until issue #122 PR-D (Alembic b8c4e2d7f9a1, 2026-10-14) every legacy
write path wrote both its old column and a typed note through the helpers
here. The columns are gone and the note is the only record; this module stays
the single definition of the mapping.

Two helpers, two situations:

* add_note -- append one typed note. Used when the caller knows the type and
  scope: POST /experiments/{id}/notes, POST /api/results, and the New
  Experiments upload's `initial_note`, which IS the experiment's description
  (note_type='description') -- that column has always been what the app showed
  as the experiment description, and the PR2 backfill promotes the same row
  (the oldest note) for every pre-existing experiment. The partial unique index
  raises if a second description is ever attempted; the New Experiments parser
  only reaches this call for a brand-new experiment or after an overwrite row
  has cleared the old notes, so that cannot happen through the upload.
* sync_result_note -- mirror a caller's text (a parser's free-text column, a
  Timepoint Modifications row) into one note SLOT per (result, type,
  created_by): a re-upload updates the slot in place rather than appending a
  duplicate; blank text deletes the caller's own note. This is what
  makes "both sides match" true after the second upload, not just the first.

A note leaves its parser's slot when a researcher edits its text or retypes it
in the app: release_upload_slot re-signs created_by from the parser tag to the
editor (PATCH /experiments/{id}/notes/{note_id} and PATCH /notes/bulk), so the
next upload neither rewrites nor deletes the edit.

Nothing here validates content. Nothing is required; a blank value simply
writes no note (spec: behaviour change comes from visibility, not validators).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.enums import NoteType
from database.models.experiments import Experiment, ExperimentNotes
from database.models.results import ExperimentalResults


# The created_by tags of the parsers that mirror a sheet column through
# sync_result_note. A result-scoped note signed with one of these sits in that
# parser's slot. Timepoint Modifications signs with the uploader's email and
# new_experiments writes experiment-level descriptions, so neither is here.
UPLOAD_SLOT_SIGNERS: frozenset[str] = frozenset({"master_bulk_upload", "scalar_results", "quick_upload"})


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
    event_date: Optional[date] = None,
) -> ExperimentNotes:
    """Append one typed note to ``experiment`` and flush it.

    The database enforces scope (ck_note_scope), the one-description rule
    (uq_one_description_per_experiment) and same-experiment result ownership
    (fk_note_result_same_experiment); an invalid combination raises
    IntegrityError at flush. Callers that want a friendlier error pre-check
    (see the notes router) -- this helper does not, so the DB stays the
    authority. `event_date` is the calendar anchor a 'modification' may carry
    instead of a result (issue #122 PR-B).
    """
    note = ExperimentNotes(
        experiment_id=experiment.experiment_id,
        experiment_fk=experiment.id,
        note_text=note_text,
        note_type=note_type,
        result_id=result_id,
        created_by=created_by,
        needs_review=needs_review,
        event_date=event_date,
    )
    if created_at is not None:
        note.created_at = created_at
    db.add(note)
    db.flush()
    return note


def sync_result_note(
    db: Session,
    result: ExperimentalResults,
    note_type: NoteType,
    note_text: Optional[str],
    *,
    created_by: str,
) -> Optional[ExperimentNotes]:
    """Mirror a caller's text into its typed-note slot.

    Exactly one note exists per (result.id, note_type, created_by):
      * text present, no slot   -> create the note
      * text present, slot held -> update note_text in place (same row id)
      * text blank/None, slot held -> delete the note (the caller cleared it)
      * text blank/None, none   -> no-op

    ``created_by`` is part of the slot key on purpose: a researcher's
    hand-written modification note (created_by = their email) is never
    overwritten by a bulk upload's mirror (created_by = 'master_bulk_upload').
    The same holds for a parser note a researcher later edited or retyped in
    the app: release_upload_slot re-signed it to the editor, so it is no
    longer in this slot.

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


def release_upload_slot(note: ExperimentNotes, editor: str) -> Optional[str]:
    """Take a parser-written note out of its upload slot by re-signing it.

    Called when a researcher edits the note's text or retypes it in the app.
    If the note is result-scoped and signed by a parser in UPLOAD_SLOT_SIGNERS,
    ``created_by`` becomes ``editor`` and the previous signer is returned, so
    the caller can record the change in its ModificationsLog row. Any other
    note is left unchanged and None is returned. Does not flush.
    """
    if note.result_id is None or note.created_by not in UPLOAD_SLOT_SIGNERS:
        return None
    previous = note.created_by
    note.created_by = editor
    return previous
