"""backend/services/notes.py -- the legacy -> typed note mapping (issue #118, PR1)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.services.notes import UPLOAD_SLOT_SIGNERS, add_note, release_upload_slot, sync_result_note
from database import Experiment, ExperimentNotes, ExperimentalResults
from database.models.enums import ExperimentStatus, NoteType


def _exp(db, exp_id, number):
    exp = Experiment(experiment_id=exp_id, experiment_number=number, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _result(db, exp, day=1.0):
    r = ExperimentalResults(
        experiment_fk=exp.id, time_post_reaction_days=day,
        time_post_reaction_bucket_days=day,
    )
    db.add(r)
    db.flush()
    return r


def _notes(db, exp):
    return db.execute(
        select(ExperimentNotes).where(ExperimentNotes.experiment_fk == exp.id).order_by(ExperimentNotes.id)
    ).scalars().all()


# --- add_note ----------------------------------------------------------------

def test_add_note_sets_scope_and_provenance(db_session):
    exp = _exp(db_session, "NH_ADD_001", 9118103)
    r = _result(db_session, exp)
    n = add_note(db_session, exp, "swapped brine", note_type=NoteType.modification,
                 result_id=r.id, created_by="test@addisenergy.com")
    db_session.refresh(n)
    assert (n.note_type, n.result_id, n.created_by, n.needs_review) == (
        NoteType.modification, r.id, "test@addisenergy.com", False,
    )
    assert n.experiment_id == exp.experiment_id


# --- sync_result_note --------------------------------------------------------

def test_sync_creates_then_updates_in_place(db_session):
    exp = _exp(db_session, "NH_SYNC_001", 9118104)
    r = _result(db_session, exp)
    first = sync_result_note(db_session, r, NoteType.modification, "added 5 g Mg(OH)2", created_by="master_bulk_upload")
    second = sync_result_note(db_session, r, NoteType.modification, "added 10 g Mg(OH)2",
                              created_by="master_bulk_upload")
    assert first is not None and second is not None
    assert first.id == second.id, "a re-upload must update the slot, not append"
    notes = _notes(db_session, exp)
    assert [(n.note_type, n.note_text) for n in notes] == [(NoteType.modification, "added 10 g Mg(OH)2")]


def test_sync_same_text_is_a_noop(db_session):
    exp = _exp(db_session, "NH_SYNC_002", 9118105)
    r = _result(db_session, exp)
    a = sync_result_note(db_session, r, NoteType.observation, "Liquid sample", created_by="master_bulk_upload")
    b = sync_result_note(db_session, r, NoteType.observation, "Liquid sample", created_by="master_bulk_upload")
    assert a.id == b.id
    assert len(_notes(db_session, exp)) == 1


def test_sync_blank_deletes_the_slot(db_session):
    exp = _exp(db_session, "NH_SYNC_003", 9118106)
    r = _result(db_session, exp)
    sync_result_note(db_session, r, NoteType.modification, "x", created_by="timepoint_modifications")
    assert sync_result_note(db_session, r, NoteType.modification, None, created_by="timepoint_modifications") is None
    assert _notes(db_session, exp) == []


def test_sync_blank_with_no_slot_is_a_noop(db_session):
    exp = _exp(db_session, "NH_SYNC_004", 9118107)
    r = _result(db_session, exp)
    assert sync_result_note(db_session, r, NoteType.modification, "   ", created_by="x") is None
    assert sync_result_note(db_session, r, NoteType.observation, "nan", created_by="x") is None
    assert _notes(db_session, exp) == []


def test_sync_never_touches_another_authors_note_of_the_same_type(db_session):
    """A researcher's hand-written modification note must survive a bulk
    upload mirroring the same column: created_by is part of the slot key."""
    exp = _exp(db_session, "NH_SYNC_005", 9118108)
    r = _result(db_session, exp)
    hand = add_note(db_session, exp, "hand-written", note_type=NoteType.modification,
                    result_id=r.id, created_by="researcher@addisenergy.com")
    mirrored = sync_result_note(db_session, r, NoteType.modification, "from sheet", created_by="master_bulk_upload")
    assert mirrored.id != hand.id
    sync_result_note(db_session, r, NoteType.modification, None, created_by="master_bulk_upload")
    remaining = _notes(db_session, exp)
    assert [n.id for n in remaining] == [hand.id]
    assert remaining[0].note_text == "hand-written"


def test_sync_slots_are_independent_per_type(db_session):
    exp = _exp(db_session, "NH_SYNC_006", 9118109)
    r = _result(db_session, exp)
    sync_result_note(db_session, r, NoteType.observation, "obs", created_by="master_bulk_upload")
    sync_result_note(db_session, r, NoteType.modification, "mod", created_by="master_bulk_upload")
    got = sorted((n.note_type.value, n.note_text, n.result_id) for n in _notes(db_session, exp))
    assert got == [("modification", "mod", r.id), ("observation", "obs", r.id)]


# --- release_upload_slot -----------------------------------------------------

@pytest.mark.parametrize("signer", sorted(UPLOAD_SLOT_SIGNERS))
def test_release_upload_slot_resigns_each_parser_tag(db_session, signer):
    exp = _exp(db_session, f"NH_REL_{signer}", 9118120 + sorted(UPLOAD_SLOT_SIGNERS).index(signer))
    r = _result(db_session, exp)
    n = add_note(db_session, exp, "parser text", result_id=r.id, created_by=signer)
    assert release_upload_slot(n, "editor@addisenergy.com") == signer
    assert n.created_by == "editor@addisenergy.com"


@pytest.mark.parametrize("signer", ["someone@addisenergy.com", "reclassify_notes_020", None])
def test_release_upload_slot_ignores_non_parser_signers(db_session, signer):
    exp = _exp(db_session, f"NH_KEEP_{signer}", 9118130 + ["someone@addisenergy.com", "reclassify_notes_020", None].index(signer))
    r = _result(db_session, exp)
    n = add_note(db_session, exp, "text", result_id=r.id, created_by=signer)
    assert release_upload_slot(n, "editor@addisenergy.com") is None
    assert n.created_by == signer


def test_release_upload_slot_ignores_experiment_level_parser_note(db_session):
    exp = _exp(db_session, "NH_KEEP_EXPLVL", 9118135)
    n = add_note(db_session, exp, "text", created_by="master_bulk_upload")
    assert release_upload_slot(n, "editor@addisenergy.com") is None
    assert n.created_by == "master_bulk_upload"


def test_upload_slot_signers_match_the_parsers_tags():
    """Drift guard: a parser that starts signing notes with a new tag must be
    added to UPLOAD_SLOT_SIGNERS, or a UI edit to its notes stays in its slot."""
    from backend.services.bulk_uploads import master_bulk_upload

    root = Path(master_bulk_upload.__file__).parent
    literal = re.compile(r"""\[\s*['"]_note_source['"]\s*\]\s*=\s*['"]([^'"]+)['"]""")
    scanned = {m for path in root.glob("*.py") for m in literal.findall(path.read_text(encoding="utf-8"))}
    assert scanned, "the regex found no _note_source assignments; update it"
    assert UPLOAD_SLOT_SIGNERS == {master_bulk_upload._NOTE_SOURCE} | scanned
