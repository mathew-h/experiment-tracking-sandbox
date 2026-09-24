"""Issue #118 PR3: the review queue and resolving notes.

GET /api/experiments/notes/review lists needs_review notes across experiments;
PATCH /experiments/{id}/notes/{note_id} clears the flag, retypes, or edits.
"""
from __future__ import annotations

from sqlalchemy import select

from database.models.enums import ExperimentStatus, NoteType
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.results import ExperimentalResults


def _exp(db, eid, num, researcher=None):
    exp = Experiment(experiment_id=eid, experiment_number=num, status=ExperimentStatus.ONGOING, researcher=researcher)
    db.add(exp)
    db.flush()
    return exp


def _result(db, exp, day=7.0):
    r = ExperimentalResults(experiment_fk=exp.id, time_post_reaction_days=day,
                            time_post_reaction_bucket_days=day, description="legacy")
    db.add(r)
    db.flush()
    return r


def _note(db, exp, text_, **kw):
    n = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text=text_, **kw)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def test_review_queue_lists_flagged_notes_with_context(client, db_session):
    a = _exp(db_session, "RQ_001", 7201, researcher="MH")
    b = _exp(db_session, "RQ_002", 7202, researcher="JW")
    ra = _result(db_session, a, 3.0)
    flagged_a = _note(db_session, a, "t=3d liquid", needs_review=True, result_id=ra.id,
                      created_by="reclassify_notes_020")
    _note(db_session, a, "fine", needs_review=False)
    flagged_b = _note(db_session, b, "End of exp.", needs_review=True)

    resp = client.get("/api/experiments/notes/review")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = {i["id"] for i in body["items"]}
    assert {flagged_a.id, flagged_b.id} <= ids
    assert body["total"] >= 2
    item = next(i for i in body["items"] if i["id"] == flagged_a.id)
    assert item["experiment_id"] == "RQ_001"
    assert item["researcher"] == "MH"
    assert item["time_post_reaction_days"] == 3.0
    assert item["note_type"] == "observation"
    assert item["needs_review"] is True


def test_review_queue_filters_by_researcher(client, db_session):
    a = _exp(db_session, "RQ_003", 7203, researcher="MH")
    b = _exp(db_session, "RQ_004", 7204, researcher="JW")
    _note(db_session, a, "mine", needs_review=True)
    other = _note(db_session, b, "theirs", needs_review=True)
    resp = client.get("/api/experiments/notes/review?researcher=MH")
    assert resp.status_code == 200
    ids = {i["id"] for i in resp.json()["items"]}
    assert other.id not in ids
    assert all(i["researcher"] == "MH" for i in resp.json()["items"])


def test_review_queue_path_is_not_captured_as_an_experiment_id(client, db_session):
    """/notes/review must not fall into /{experiment_id}/... and 404."""
    resp = client.get("/api/experiments/notes/review?limit=1")
    assert resp.status_code == 200
    assert set(resp.json()) == {"items", "total", "skip", "limit", "distinct_texts"}


def test_patch_clears_needs_review_and_logs_it(client, db_session):
    exp = _exp(db_session, "RQ_005", 7205)
    n = _note(db_session, exp, "check me", needs_review=True)
    resp = client.patch(f"/api/experiments/{exp.experiment_id}/notes/{n.id}", json={"needs_review": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["needs_review"] is False
    assert resp.json()["note_text"] == "check me"
    log = db_session.execute(
        select(ModificationsLog).where(ModificationsLog.experiment_fk == exp.id,
                                       ModificationsLog.modified_table == "experiment_notes")
    ).scalars().all()
    assert len(log) == 1
    assert log[0].old_values == {"needs_review": True}
    assert log[0].new_values == {"needs_review": False}
    assert client.get("/api/experiments/notes/review").json()["items"] == [] or n.id not in {
        i["id"] for i in client.get("/api/experiments/notes/review").json()["items"]
    }


def test_patch_retypes_a_result_scoped_note(client, db_session):
    exp = _exp(db_session, "RQ_006", 7206)
    r = _result(db_session, exp)
    n = _note(db_session, exp, "swapped brine", result_id=r.id, needs_review=True)
    resp = client.patch(f"/api/experiments/{exp.experiment_id}/notes/{n.id}",
                        json={"note_type": "modification", "needs_review": False})
    assert resp.status_code == 200, resp.text
    assert (resp.json()["note_type"], resp.json()["needs_review"]) == ("modification", False)


def test_patch_rejects_description_on_a_result_scoped_note(client, db_session):
    exp = _exp(db_session, "RQ_007", 7207)
    r = _result(db_session, exp)
    n = _note(db_session, exp, "x", result_id=r.id)
    resp = client.patch(f"/api/experiments/{exp.experiment_id}/notes/{n.id}", json={"note_type": "description"})
    assert resp.status_code == 422


def test_patch_rejects_modification_without_result(client, db_session):
    exp = _exp(db_session, "RQ_008", 7208)
    n = _note(db_session, exp, "x")
    resp = client.patch(f"/api/experiments/{exp.experiment_id}/notes/{n.id}", json={"note_type": "modification"})
    assert resp.status_code == 422


def test_patch_second_description_is_409(client, db_session):
    exp = _exp(db_session, "RQ_009", 7209)
    _note(db_session, exp, "the description", note_type=NoteType.description)
    other = _note(db_session, exp, "an observation")
    resp = client.patch(f"/api/experiments/{exp.experiment_id}/notes/{other.id}", json={"note_type": "description"})
    assert resp.status_code == 409


def test_patch_empty_body_is_422(client, db_session):
    exp = _exp(db_session, "RQ_010", 7210)
    n = _note(db_session, exp, "x")
    resp = client.patch(f"/api/experiments/{exp.experiment_id}/notes/{n.id}", json={})
    assert resp.status_code == 422


def test_patch_text_only_still_works_as_before(client, db_session):
    exp = _exp(db_session, "RQ_011", 7211)
    n = _note(db_session, exp, "old")
    resp = client.patch(f"/api/experiments/{exp.experiment_id}/notes/{n.id}", json={"note_text": "new"})
    assert resp.status_code == 200
    assert resp.json()["note_text"] == "new"


# ------------------------------------------- issue #122 PR-A: filters ----

def test_review_queue_filters_by_note_type(client, db_session):
    exp = _exp(db_session, "RQ_101", 7401)
    r = _result(db_session, exp)
    obs = _note(db_session, exp, "obs", needs_review=True)
    mod = _note(db_session, exp, "mod", needs_review=True, result_id=r.id, note_type=NoteType.modification)
    ids = {i["id"] for i in client.get("/api/experiments/notes/review?note_type=modification").json()["items"]}
    assert mod.id in ids and obs.id not in ids


def test_review_queue_q_is_case_insensitive_contains(client, db_session):
    exp = _exp(db_session, "RQ_102", 7402)
    hit = _note(db_session, exp, "Swapped Brine at t=3", needs_review=True)
    miss = _note(db_session, exp, "nothing", needs_review=True)
    ids = {i["id"] for i in client.get("/api/experiments/notes/review?q=brine").json()["items"]}
    assert hit.id in ids and miss.id not in ids


def test_review_queue_q_treats_percent_and_underscore_literally(client, db_session):
    exp = _exp(db_session, "RQ_103", 7403)
    lit = _note(db_session, exp, "yield 5% at t_0", needs_review=True)
    other = _note(db_session, exp, "yield 5 at t0", needs_review=True)
    # Only an unescaped LIKE would match this: "%" absorbs "X", "_" matches "Q".
    wildcard_bait = _note(db_session, exp, "yield 5X at tQ0", needs_review=True)
    ids = {i["id"] for i in client.get("/api/experiments/notes/review", params={"q": "5% at t_0"}).json()["items"]}
    assert lit.id in ids and other.id not in ids and wildcard_bait.id not in ids


def test_review_queue_filters_by_experiment_id_contains(client, db_session):
    a = _exp(db_session, "RQ_104_SERUM", 7404)
    b = _exp(db_session, "RQ_105_HPHT", 7405)
    # Only an unescaped LIKE would match "104_serum" against this: "_" matches "X".
    c = _exp(db_session, "RQ_104XSERUM", 7408)
    na = _note(db_session, a, "x", needs_review=True)
    nb = _note(db_session, b, "x", needs_review=True)
    nc = _note(db_session, c, "x", needs_review=True)
    ids = {i["id"] for i in client.get("/api/experiments/notes/review?experiment_id=104_serum").json()["items"]}
    assert na.id in ids and nb.id not in ids and nc.id not in ids


def test_review_queue_orders_by_created_at_desc(client, db_session):
    exp = _exp(db_session, "RQ_106", 7406)
    first = _note(db_session, exp, "first", needs_review=True)
    second = _note(db_session, exp, "second", needs_review=True)
    items = client.get("/api/experiments/notes/review?experiment_id=RQ_106&order=created_at&desc=true").json()["items"]
    assert [i["id"] for i in items][:2] == [second.id, first.id]
    items = client.get("/api/experiments/notes/review?experiment_id=RQ_106&order=text").json()["items"]
    assert [i["note_text"] for i in items] == ["first", "second"]


def test_review_queue_rejects_unknown_order(client, db_session):
    assert client.get("/api/experiments/notes/review?order=bogus").status_code == 422


def test_review_queue_distinct_texts_count_within_filter_only(client, db_session):
    exp = _exp(db_session, "RQ_107", 7407, researcher="ZZ")
    for _ in range(3):
        _note(db_session, exp, "t=0", needs_review=True)
    _note(db_session, exp, "Day 7", needs_review=True)
    _note(db_session, exp, "t=0", needs_review=False)  # resolved: not counted
    body = client.get("/api/experiments/notes/review?researcher=ZZ").json()
    assert body["distinct_texts"][0] == {"text": "t=0", "count": 3}
    assert {"text": "Day 7", "count": 1} in body["distinct_texts"]
    # Filter narrows the histogram too.
    body = client.get("/api/experiments/notes/review?researcher=ZZ&q=day").json()
    assert body["distinct_texts"] == [{"text": "Day 7", "count": 1}]
