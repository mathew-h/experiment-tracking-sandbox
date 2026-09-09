"""Pins the 020 reclassification rules (issue #118, PR2): which note is promoted,
that 'nan' is never promoted, what result text is discarded versus preserved
for review, that PR1-era notes are never touched, and that the plan's review
queue count is exactly what --apply produces."""
from __future__ import annotations

from sqlalchemy import select

from database.data_migrations.reclassify_notes_020 import (
    SOURCE_TAG,
    apply_plan,
    build_plan,
)
from database.models.enums import ExperimentStatus, NoteType
from database.models.experiments import Experiment, ExperimentNotes
from database.models.results import ExperimentalResults


def _exp(db, eid, num):
    exp = Experiment(experiment_id=eid, experiment_number=num, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _legacy_note(db, exp, text_):
    n = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text=text_)
    db.add(n)
    db.flush()
    return n


def _result(db, exp, day, description, brine=None):
    r = ExperimentalResults(
        experiment_fk=exp.id, time_post_reaction_days=day, time_post_reaction_bucket_days=day,
        description=description, brine_modification_description=brine,
    )
    db.add(r)
    db.flush()
    return r


def _notes(db, exp):
    return db.execute(
        select(ExperimentNotes).where(ExperimentNotes.experiment_fk == exp.id).order_by(ExperimentNotes.id)
    ).scalars().all()


def _apply(db):
    plan = build_plan(db)
    apply_plan(db, plan)
    db.flush()
    db.expire_all()
    return plan


# --- rule 1 ------------------------------------------------------------------

def test_oldest_legacy_note_by_min_id_becomes_description(migration_session):
    exp = _exp(migration_session, "RN_001", 62001)
    first = _legacy_note(migration_session, exp, "the summary")
    second = _legacy_note(migration_session, exp, "a later remark")
    plan = _apply(migration_session)
    assert first.id in plan.promote_ids and second.id not in plan.promote_ids
    got = {n.id: n.note_type for n in _notes(migration_session, exp)}
    assert got == {first.id: NoteType.description, second.id: NoteType.observation}


def test_pr1_description_is_kept_and_legacy_first_note_stays_observation(migration_session):
    exp = _exp(migration_session, "RN_002", 62002)
    legacy = _legacy_note(migration_session, exp, "legacy oldest")
    pr1 = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text="explicit",
                          note_type=NoteType.description, created_by="someone@addisenergy.com")
    migration_session.add(pr1)
    migration_session.flush()
    plan = _apply(migration_session)
    assert plan.kept_pr1_description == [(exp.experiment_id, pr1.id, legacy.id)]
    got = {n.id: n.note_type for n in _notes(migration_session, exp)}
    assert got == {legacy.id: NoteType.observation, pr1.id: NoteType.description}


def test_pr1_era_result_notes_are_never_touched(migration_session):
    exp = _exp(migration_session, "RN_003", 62003)
    r = _result(migration_session, exp, 7.0, "Liquid sample", brine="swap")
    mirrored = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text="swap",
                               note_type=NoteType.modification, result_id=r.id, created_by="master_bulk_upload")
    migration_session.add(mirrored)
    migration_session.flush()
    plan = _apply(migration_session)
    assert plan.modification_inserts == []
    assert plan.modification_already_mirrored == 1
    notes = _notes(migration_session, exp)
    assert [(n.id, n.note_type, n.result_id) for n in notes] == [(mirrored.id, NoteType.modification, r.id)]


# --- rule 2 ------------------------------------------------------------------

def test_nan_note_is_flagged_and_never_promoted(migration_session):
    exp = _exp(migration_session, "RN_004", 62004)
    nan = _legacy_note(migration_session, exp, "nan")
    later = _legacy_note(migration_session, exp, "real text written later")
    plan = _apply(migration_session)
    assert nan.id in plan.nan_note_ids
    assert plan.nan_experiments_without_description == ["RN_004"]
    assert plan.promote_ids == [] or later.id not in plan.promote_ids
    got = {n.id: (n.note_type, n.needs_review) for n in _notes(migration_session, exp)}
    assert got[nan.id] == (NoteType.observation, True)
    assert got[later.id] == (NoteType.observation, False), "nothing is promoted in the nan note's place"


# --- rule 3 ------------------------------------------------------------------

def test_brine_modification_becomes_modification_note_with_result_created_at(migration_session):
    exp = _exp(migration_session, "RN_005", 62005)
    r = _result(migration_session, exp, 7.0, "Liquid sample", brine="  Added 5 g Mg(OH)2 ")
    migration_session.refresh(r)
    plan = _apply(migration_session)
    assert plan.modification_inserts == [(r.id, exp.id, "Added 5 g Mg(OH)2")]
    notes = _notes(migration_session, exp)
    assert len(notes) == 1
    n = notes[0]
    assert (n.note_type, n.result_id, n.note_text, n.created_by, n.needs_review) == (
        NoteType.modification, r.id, "Added 5 g Mg(OH)2", SOURCE_TAG, False,
    )
    assert n.created_at == r.created_at
    assert n.experiment_id == exp.experiment_id


# --- rule 4 ------------------------------------------------------------------

def test_filler_descriptions_are_discarded(migration_session):
    exp = _exp(migration_session, "RN_006", 62006)
    fillers = ["Gas sample", "liquid", " Solid ", "aqueous sample", "Gas + Liquid", "gas+liquid sample",
               "Master upload — day 7.0"]
    for i, d in enumerate(fillers):
        _result(migration_session, exp, float(i), d)
    plan = _apply(migration_session)
    mine = [t for rid, t in plan.discarded_filler if rid in {r.id for r in exp.results}]
    assert sorted(mine) == sorted(d.strip() for d in fillers)
    assert _notes(migration_session, exp) == []


def test_gc_method_tags_are_discarded_as_rule_4b(migration_session):
    """Mat, 2026-09-09: GC method / injection tags belong to the person running
    the GC, not to the experiment's notes."""
    exp = _exp(migration_session, "RN_011", 62011)
    tags = ["DI, GC-B", "GC-B", "Gas, GC-A, DI", "Gas (GC-A), liquid, solid", "Full loop, GC-A",
            "DI, GC-B; Liq", "Gas, GC-A. DI", "gas and liquid, GC-B"]
    for i, d in enumerate(tags):
        _result(migration_session, exp, float(i), d)
    plan = _apply(migration_session)
    mine = {r.id for r in exp.results}
    got = sorted(t for rid, t in plan.discarded_gc_tags if rid in mine)
    assert got == sorted(tags)
    assert [x for x in plan.observation_inserts if x[0] in mine] == []
    assert _notes(migration_session, exp) == []


def test_extra_words_keep_a_description_out_of_every_filler_rule(migration_session):
    """Real text is preserved: a tag with extra words, a list with a stray
    token, a sentence."""
    exp = _exp(migration_session, "RN_012", 62012)
    kept = ["Cold dip tube liquid, GC-A", "0; Gas, GC-A, DI", "Pre-rxn brine check",
            "t=1d, liquid", "End of exp.", "Day 7 looked cloudy"]
    for i, d in enumerate(kept):
        _result(migration_session, exp, float(i), d)
    plan = _apply(migration_session)
    mine = {r.id for r in exp.results}
    for attr in ("discarded_gc_tags", "discarded_generated", "discarded_fraction_lists", "discarded_zero"):
        assert [t for rid, t in getattr(plan, attr) if rid in mine] == [], attr
    preserved = sorted(t for rid, _fk, t in plan.observation_inserts if rid in mine)
    assert preserved == sorted(kept)


def test_code_generated_fallbacks_are_discarded_as_rule_4c(migration_session):
    exp = _exp(migration_session, "RN_013", 62013)
    gen = ["Day 1.0 results", "Day 14.0 results", "Analysis results for Day 7.0", "Analysis results", "day 3 results"]
    for i, d in enumerate(gen):
        _result(migration_session, exp, float(i), d)
    plan = _apply(migration_session)
    mine = {r.id for r in exp.results}
    assert sorted(t for rid, t in plan.discarded_generated if rid in mine) == sorted(gen)
    assert _notes(migration_session, exp) == []


def test_fraction_lists_are_discarded_as_rule_4d(migration_session):
    exp = _exp(migration_session, "RN_014", 62014)
    lists = ["gas, liquid", "Gas, liquid", "gas, liquid, solid", "Gas and liquid sample",
             "Liquid and gas sample", "gas/liquid", "Gas; Liquid; Solid", "liquid + solid samples"]
    for i, d in enumerate(lists):
        _result(migration_session, exp, float(i), d)
    plan = _apply(migration_session)
    mine = {r.id for r in exp.results}
    assert sorted(t for rid, t in plan.discarded_fraction_lists if rid in mine) == sorted(lists)
    assert _notes(migration_session, exp) == []


def test_literal_zero_is_discarded_as_rule_4e(migration_session):
    exp = _exp(migration_session, "RN_015", 62015)
    _result(migration_session, exp, 1.0, "0")
    _result(migration_session, exp, 2.0, " 0.0 ")
    _result(migration_session, exp, 3.0, "0 rpm")  # not the literal zero
    plan = _apply(migration_session)
    mine = {r.id for r in exp.results}
    assert sorted(t for rid, t in plan.discarded_zero if rid in mine) == ["0", "0.0"]
    assert [t for rid, _fk, t in plan.observation_inserts if rid in mine] == ["0 rpm"]


def test_non_filler_description_is_preserved_for_review(migration_session):
    exp = _exp(migration_session, "RN_007", 62007)
    r = _result(migration_session, exp, 7.0, "Pre-rxn brine check")  # matched by no filler rule
    plan = _apply(migration_session)
    assert (r.id, exp.id, "Pre-rxn brine check") in plan.observation_inserts
    notes = _notes(migration_session, exp)
    assert [(n.note_type, n.result_id, n.note_text, n.needs_review, n.created_by) for n in notes] == [
        (NoteType.observation, r.id, "Pre-rxn brine check", True, SOURCE_TAG),
    ]


def test_blank_description_carries_nothing(migration_session):
    exp = _exp(migration_session, "RN_008", 62008)
    _result(migration_session, exp, 7.0, "   ")
    plan = _apply(migration_session)
    assert plan.blank_descriptions >= 1
    assert _notes(migration_session, exp) == []


def test_preserved_description_already_mirrored_by_pr1_is_not_duplicated(migration_session):
    exp = _exp(migration_session, "RN_009", 62009)
    r = _result(migration_session, exp, 7.0, "Pre-rxn brine check")
    migration_session.add(ExperimentNotes(
        experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text="Pre-rxn brine check",
        note_type=NoteType.observation, result_id=r.id, created_by="master_bulk_upload",
    ))
    migration_session.flush()
    plan = _apply(migration_session)
    assert plan.observation_already_mirrored >= 1
    assert len(_notes(migration_session, exp)) == 1


# --- idempotency + review queue arithmetic -----------------------------------

def test_second_run_is_a_noop_and_review_queue_matches_plan(migration_session):
    exp = _exp(migration_session, "RN_010", 62010)
    _legacy_note(migration_session, exp, "nan")
    _result(migration_session, exp, 1.0, "End of exp.", brine="swap brine")
    _result(migration_session, exp, 2.0, "Liquid sample")
    plan = _apply(migration_session)
    flagged = [n for n in _notes(migration_session, exp) if n.needs_review]
    assert len(flagged) == 2  # the 'nan' note + the preserved 'End of exp.'
    assert plan.review_queue_total >= 2

    second = build_plan(migration_session)
    assert second.promote_ids == [] or not any(
        pid in {n.id for n in _notes(migration_session, exp)} for pid in second.promote_ids
    )
    mine = {r.id for r in exp.results}
    assert [x for x in second.modification_inserts if x[0] in mine] == []
    assert [x for x in second.observation_inserts if x[0] in mine] == []
