# Notes Review Queue Tooling (issue #122, PR-A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a researcher empty the 1,288-row `needs_review` queue from a single `/notes/review` page with audited bulk actions, so PR-D (dropping the legacy result columns) can ever be unblocked.

**Architecture:** Two new bulk endpoints (`PATCH` / `DELETE /api/experiments/notes/bulk`) sit beside the existing `GET /api/experiments/notes/review` in `backend/api/routers/experiments.py`, registered before the `/{experiment_id}` routes so the literal path wins. Both are atomic: every id is validated before anything is written, and one `ModificationsLog` row is written per note. The review GET gains four filters, an order, and a `distinct_texts` histogram. A new React page consumes them with React Query; the nav gets an open-count badge from the same GET.

**Tech Stack:** FastAPI + Pydantic v2 + SQLAlchemy 2 (backend); React 18 + TypeScript + TanStack Query v5 + React Router v6 + Tailwind (frontend); pytest against `experiments_test` Postgres; vitest + Testing Library.

**Spec:** The phase-2 prompt, saved in Task 1 as `docs/working/issues/07-notes-overhaul-phase-2.md` (section "PR-A"), plus the four in-chat design calls recorded in the issue-log entry for this PR: atomic bulk calls; `order` + `desc`; select-all means the loaded set (page `limit=500` = bulk cap); nav badge reuses `GET /notes/review?limit=1`.

## Global Constraints

- Branch `feat/notes-review-queue` off `develop`; PR base `develop` (`gh pr create --base develop`).
- Commit format `[#122] <imperative, <50 chars>` with `- Tests added:` / `- Docs updated:` lines and `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- No schema change. No file under `backend/services/bulk_uploads/` or `database/models/` is touched.
- Nothing becomes required (design decision 4): no validator is added to any existing write path.
- `structlog` only; no `print`. Frontend: functional components, props interfaces, React Query for all server state, Tailwind classes only, no hex literals, no `console.log`.
- Tests: reset `experiments_test` (`DROP SCHEMA public CASCADE; CREATE SCHEMA public;`) once before the first run if the schema is stale; **one pytest process at a time**; never include root-level `tests/test_*.py` in the same invocation as `tests/api`.
- Python: `.venv/Scripts/python.exe`, `.venv/Scripts/pytest.exe`. Frontend: run `npx vitest run <path>` and `npx eslint src/...` from `frontend/`.
- Every backend test module in `tests/api/` uses the existing `client` and `db_session` fixtures from `tests/api/conftest.py` (auth is overridden to `test@addisenergy.com`).

## Review Focus

Inputs the spec implies but names no test for; each is pinned in the owning task.

1. **Duplicate ids in one bulk body** (`[5, 5, 7]`) — must count 5 once, log once, not 500. Pinned in Task 2.
2. **Retype to `description` where two selected notes belong to the same experiment** — must 409 naming the experiment, not raise `IntegrityError` mid-loop. Pinned in Task 2.
3. **`q` containing `%` or `_`** — must be treated as literal characters, not ILIKE wildcards. Pinned in Task 4.
4. **A bulk body whose ids are all already in the requested state** (`needs_review: false` on already-reviewed rows) — must return `updated: 0` with no log rows, not error. Pinned in Task 2.
5. **Chip click when some matching rows are already selected** — must not toggle them off; selection is a union. Pinned in Task 7.

---

### Task 1: Save the phase-2 prompt as the working issue doc

**Files:**
- Create: `docs/working/issues/07-notes-overhaul-phase-2.md`

`docs/working/` is excluded from the `project_context` sync hook, so this is internal-only. The content is the phase-2 prompt Mat supplied on 2026-09-23 (the full text is in the session transcript; the Conductor holds it — paste it verbatim, restoring the lines the paste truncated from the surrounding context, and add the header below).

- [ ] **Step 1: Write the file**

Header, then the prompt body verbatim:

```markdown
# 07 — Notes overhaul, phase 2 (issue #122)

Saved 2026-09-23 from Mat Hearl's session prompt. This is the working spec for
PR-A (`feat/notes-review-queue`), PR-B (`feat/reactor-mods-as-notes`),
PR-C (`feat/notes-timeline`) and PR-D (`chore/drop-legacy-note-columns`).

Pre-authorizations given 2026-09-23 (Mat, in-session): (1) `event_date` column
+ relaxed `ck_note_scope` on `experiment_notes`; (2) edits to the locked parsers
`scalar_results.py`, `quick_upload.py`, `long_format.py`, `master_bulk_upload.py`
(fallback removal), `icp_service.py`; (3) the three non-additive column drops on
`experimental_results` in PR-D. Still gated regardless: the 021 `--apply` waits
for Mat's audit of the dry-run report, and PR-D does not open until the
production review queue reads 0.

PR-A design calls made in-session (approved 2026-09-23): bulk calls are atomic;
`order` has a `desc` flag; select-all-in-filter means the loaded set (page limit
500 = bulk cap); the nav badge reuses `GET /notes/review?limit=1`.

---

<prompt body verbatim>
```

- [ ] **Step 2: Commit**

```bash
git add docs/working/issues/07-notes-overhaul-phase-2.md
git commit -F <scratchpad>/msg.txt
```
where `msg.txt` is:
```
[#122] Save phase-2 notes overhaul prompt as working doc

- docs/working/issues/07-notes-overhaul-phase-2.md
- Tests added: no
- Docs updated: yes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 2: Bulk PATCH endpoint — schemas, router, tests

**Files:**
- Modify: `backend/api/schemas/experiments.py` (after `ReviewQueueResponse`, ~line 180)
- Modify: `backend/api/routers/experiments.py` (import block lines 17-22; new route immediately after `list_review_queue`, i.e. before line 529 `@router.get("/{experiment_id}/results"`)
- Create: `tests/api/test_notes_bulk.py`

**Interfaces:**
- Produces: `NotesBulkPatch(ids: list[int], needs_review: bool | None, note_type: NoteType | None)`, `NotesBulkResponse(count: int, ids: list[int])`, route `PATCH /api/experiments/notes/bulk`. Task 3 adds `NotesBulkDelete` beside these and reuses `NotesBulkResponse`. Task 6 mirrors the two request types in TypeScript.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_notes_bulk.py`:

```python
"""Issue #122 PR-A: bulk review-queue actions.

PATCH /api/experiments/notes/bulk and DELETE /api/experiments/notes/bulk act on
a list of note ids atomically: every id is validated first, then all rows change
in one transaction, with one ModificationsLog row per note.
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


def _logs(db, exp):
    return db.execute(
        select(ModificationsLog).where(ModificationsLog.experiment_fk == exp.id,
                                       ModificationsLog.modified_table == "experiment_notes")
    ).scalars().all()


# ---------------------------------------------------------------- PATCH ----

def test_bulk_patch_marks_reviewed_and_logs_one_row_per_note(client, db_session):
    exp = _exp(db_session, "BULK_001", 7301)
    a = _note(db_session, exp, "t=0", needs_review=True)
    b = _note(db_session, exp, "Day 7", needs_review=True)
    resp = client.patch("/api/experiments/notes/bulk", json={"ids": [a.id, b.id], "needs_review": False})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"count": 2, "ids": sorted([a.id, b.id])}
    db_session.expire_all()
    assert db_session.get(ExperimentNotes, a.id).needs_review is False
    assert db_session.get(ExperimentNotes, b.id).needs_review is False
    logs = _logs(db_session, exp)
    assert len(logs) == 2
    assert all(l.modification_type == "update" for l in logs)
    assert all(l.old_values == {"needs_review": True} and l.new_values == {"needs_review": False} for l in logs)
    assert all(l.modified_by == "test@addisenergy.com" for l in logs)


def test_bulk_patch_duplicate_ids_are_counted_once(client, db_session):
    exp = _exp(db_session, "BULK_002", 7302)
    a = _note(db_session, exp, "x", needs_review=True)
    resp = client.patch("/api/experiments/notes/bulk", json={"ids": [a.id, a.id, a.id], "needs_review": False})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"count": 1, "ids": [a.id]}
    assert len(_logs(db_session, exp)) == 1


def test_bulk_patch_already_in_state_is_a_no_op(client, db_session):
    exp = _exp(db_session, "BULK_003", 7303)
    a = _note(db_session, exp, "x", needs_review=False)
    resp = client.patch("/api/experiments/notes/bulk", json={"ids": [a.id], "needs_review": False})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"count": 0, "ids": []}
    assert _logs(db_session, exp) == []


def test_bulk_patch_retypes_result_scoped_notes_and_clears_review(client, db_session):
    exp = _exp(db_session, "BULK_004", 7304)
    r = _result(db_session, exp)
    a = _note(db_session, exp, "swapped brine", result_id=r.id, needs_review=True)
    b = _note(db_session, exp, "added Cu", result_id=r.id, needs_review=True)
    resp = client.patch("/api/experiments/notes/bulk",
                        json={"ids": [a.id, b.id], "note_type": "modification", "needs_review": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] == 2
    db_session.expire_all()
    assert db_session.get(ExperimentNotes, a.id).note_type is NoteType.modification
    logs = _logs(db_session, exp)
    assert len(logs) == 2
    assert logs[0].new_values == {"note_type": "modification", "needs_review": False}


def test_bulk_patch_scope_violation_is_422_naming_ids_and_changes_nothing(client, db_session):
    exp = _exp(db_session, "BULK_005", 7305)
    r = _result(db_session, exp)
    ok = _note(db_session, exp, "on result", result_id=r.id, needs_review=True)
    bad = _note(db_session, exp, "experiment-level", needs_review=True)
    resp = client.patch("/api/experiments/notes/bulk",
                        json={"ids": [ok.id, bad.id], "note_type": "modification", "needs_review": False})
    assert resp.status_code == 422, resp.text
    assert str(bad.id) in resp.json()["detail"]
    assert str(ok.id) not in resp.json()["detail"]
    db_session.expire_all()
    # Atomic: the valid one did not change either.
    assert db_session.get(ExperimentNotes, ok.id).note_type is NoteType.observation
    assert db_session.get(ExperimentNotes, ok.id).needs_review is True
    assert _logs(db_session, exp) == []


def test_bulk_patch_description_on_result_scoped_note_is_422(client, db_session):
    exp = _exp(db_session, "BULK_006", 7306)
    r = _result(db_session, exp)
    n = _note(db_session, exp, "x", result_id=r.id)
    resp = client.patch("/api/experiments/notes/bulk", json={"ids": [n.id], "note_type": "description"})
    assert resp.status_code == 422
    assert str(n.id) in resp.json()["detail"]


def test_bulk_patch_second_description_is_409_when_experiment_has_one(client, db_session):
    exp = _exp(db_session, "BULK_007", 7307)
    _note(db_session, exp, "the description", note_type=NoteType.description)
    other = _note(db_session, exp, "an observation", needs_review=True)
    resp = client.patch("/api/experiments/notes/bulk", json={"ids": [other.id], "note_type": "description"})
    assert resp.status_code == 409, resp.text
    assert "BULK_007" in resp.json()["detail"]
    db_session.expire_all()
    assert db_session.get(ExperimentNotes, other.id).note_type is NoteType.observation


def test_bulk_patch_two_selected_on_same_experiment_to_description_is_409(client, db_session):
    exp = _exp(db_session, "BULK_008", 7308)
    a = _note(db_session, exp, "one", needs_review=True)
    b = _note(db_session, exp, "two", needs_review=True)
    resp = client.patch("/api/experiments/notes/bulk", json={"ids": [a.id, b.id], "note_type": "description"})
    assert resp.status_code == 409, resp.text
    assert "BULK_008" in resp.json()["detail"]
    assert _logs(db_session, exp) == []


def test_bulk_patch_unknown_id_is_404_naming_it(client, db_session):
    exp = _exp(db_session, "BULK_009", 7309)
    a = _note(db_session, exp, "x", needs_review=True)
    resp = client.patch("/api/experiments/notes/bulk", json={"ids": [a.id, 999999], "needs_review": False})
    assert resp.status_code == 404, resp.text
    assert "999999" in resp.json()["detail"]
    db_session.expire_all()
    assert db_session.get(ExperimentNotes, a.id).needs_review is True


def test_bulk_patch_body_validation(client, db_session):
    # No action field.
    assert client.patch("/api/experiments/notes/bulk", json={"ids": [1]}).status_code == 422
    # Empty ids.
    assert client.patch("/api/experiments/notes/bulk", json={"ids": [], "needs_review": False}).status_code == 422
    # Over the cap.
    too_many = list(range(1, 502))
    assert client.patch("/api/experiments/notes/bulk", json={"ids": too_many, "needs_review": False}).status_code == 422


def test_bulk_path_is_not_captured_as_an_experiment_id(client, db_session):
    """/notes/bulk must hit the bulk route (422 on a bad body), not /{experiment_id}/... (404)."""
    resp = client.patch("/api/experiments/notes/bulk", json={})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest.exe tests/api/test_notes_bulk.py -v -k "patch or bulk_path"`
Expected: every test FAILS with `405 Method Not Allowed` or `404` (the literal path currently falls into `PATCH /{experiment_id}/notes/{note_id}` mismatch).

- [ ] **Step 3: Add the schemas**

In `backend/api/schemas/experiments.py`, directly after `class ReviewQueueResponse`:

```python
class NotesBulkPatch(BaseModel):
    """Body of PATCH /experiments/notes/bulk (issue #122 PR-A).

    Acts on up to 500 notes at once. At least one of `needs_review` /
    `note_type` must be present. The call is atomic: any id that is unknown
    (404) or whose scope forbids the requested type (422) rejects the whole
    request before a row is written. Duplicate ids are collapsed.
    """
    ids: list[int] = Field(min_length=1, max_length=500)
    needs_review: Optional[bool] = None
    note_type: Optional[NoteType] = None

    @model_validator(mode="after")
    def _at_least_one_action(self):
        if self.needs_review is None and self.note_type is None:
            raise ValueError("provide at least one of needs_review, note_type")
        return self


class NotesBulkDelete(BaseModel):
    """Body of DELETE /experiments/notes/bulk (issue #122 PR-A). Same cap and
    atomicity as NotesBulkPatch."""
    ids: list[int] = Field(min_length=1, max_length=500)


class NotesBulkResponse(BaseModel):
    """`count` notes changed (or deleted); `ids` names them, sorted. A note
    already in the requested state is not counted and gets no audit row."""
    count: int
    ids: list[int]
```

`Field` and `model_validator` are already imported in this module (used by `NoteUpdate`).

- [ ] **Step 4: Add the router**

In `backend/api/routers/experiments.py`, extend the schema import (line 19) so it reads:

```python
    NoteCreate, NoteResponse, NoteUpdate, ReviewNoteItem, ReviewQueueResponse,
    NotesBulkPatch, NotesBulkDelete, NotesBulkResponse,
```

Then insert, immediately after `list_review_queue` returns and before `@router.get("/{experiment_id}/results", ...)`:

```python
def _load_notes_for_bulk(db: Session, ids: list[int]) -> list[ExperimentNotes]:
    """Resolve a bulk body's ids to rows, 404 naming every id that does not exist."""
    unique = sorted(set(ids))
    notes = db.execute(
        select(ExperimentNotes).where(ExperimentNotes.id.in_(unique)).order_by(ExperimentNotes.id)
    ).scalars().all()
    missing = sorted(set(unique) - {n.id for n in notes})
    if missing:
        raise HTTPException(status_code=404, detail=f"Notes not found: {missing}")
    return notes


def _check_bulk_retype(db: Session, notes: list[ExperimentNotes], target: NoteType) -> None:
    """Mirror ck_note_scope and uq_one_description_per_experiment for a whole
    batch so the caller gets one 422/409 naming the offenders and nothing is
    half-applied. Same rules as patch_note, applied to N rows."""
    if target is NoteType.description:
        offending = [n.id for n in notes if n.result_id is not None]
        if offending:
            raise HTTPException(
                status_code=422,
                detail=f"Result-scoped notes cannot become 'description': {offending}",
            )
        # Two selected notes on one experiment, or an existing description there.
        wanting = [n for n in notes if n.note_type is not NoteType.description]
        per_exp: dict[int, list[int]] = {}
        for n in wanting:
            per_exp.setdefault(n.experiment_fk, []).append(n.id)
        clashing_fks = {fk for fk, ids in per_exp.items() if len(ids) > 1}
        if per_exp:
            existing = db.execute(
                select(ExperimentNotes.experiment_fk)
                .where(ExperimentNotes.experiment_fk.in_(list(per_exp)))
                .where(ExperimentNotes.note_type == NoteType.description)
                .where(ExperimentNotes.id.notin_([n.id for n in notes]))
            ).scalars().all()
            clashing_fks |= set(existing)
        if clashing_fks:
            eids = sorted({n.experiment_id for n in wanting if n.experiment_fk in clashing_fks})
            raise HTTPException(
                status_code=409,
                detail=f"These experiments would end up with more than one description: {eids}",
            )
    elif target in (NoteType.modification, NoteType.result_note):
        offending = [n.id for n in notes if n.result_id is None]
        if offending:
            raise HTTPException(
                status_code=422,
                detail=f"A '{target.value}' note must be scoped to a result; these are not: {offending}",
            )


@router.patch("/notes/bulk", response_model=NotesBulkResponse)
def bulk_patch_notes(
    payload: NotesBulkPatch,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> NotesBulkResponse:
    """Resolve or retype many review-queue notes at once (issue #122 PR-A).

    Atomic: ids are validated (404), scope is checked for the whole batch
    (422/409), then every row changes in one transaction with one
    ModificationsLog row per changed note. Registered before the
    /{experiment_id} routes so the literal path is not captured.
    """
    notes = _load_notes_for_bulk(db, payload.ids)
    if payload.note_type is not None:
        _check_bulk_retype(db, notes, payload.note_type)

    changed: list[int] = []
    for n in notes:
        old: dict = {}
        new: dict = {}
        if payload.note_type is not None and payload.note_type is not n.note_type:
            old["note_type"], new["note_type"] = n.note_type.value, payload.note_type.value
            n.note_type = payload.note_type
        if payload.needs_review is not None and payload.needs_review != n.needs_review:
            old["needs_review"], new["needs_review"] = n.needs_review, payload.needs_review
            n.needs_review = payload.needs_review
        if not new:
            continue
        db.add(ModificationsLog(
            experiment_id=n.experiment_id,
            experiment_fk=n.experiment_fk,
            modified_by=current_user.email,
            modification_type="update",
            modified_table="experiment_notes",
            old_values=old,
            new_values=new,
        ))
        changed.append(n.id)

    if not changed:
        return NotesBulkResponse(count=0, ids=[])
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "uq_one_description_per_experiment" in str(exc.orig):
            raise HTTPException(status_code=409, detail="An experiment already has a description note.")
        raise
    log.info("notes_bulk_patched", count=len(changed),
             note_type=payload.note_type.value if payload.note_type else None,
             needs_review=payload.needs_review)
    return NotesBulkResponse(count=len(changed), ids=sorted(changed))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest.exe tests/api/test_notes_bulk.py -v -k "patch or bulk_path"`
Expected: 11 PASS.

Run the neighbours too: `.venv/Scripts/pytest.exe tests/api/test_notes.py tests/api/test_notes_review.py tests/api/test_notes_delete.py -q`
Expected: all PASS (route order unchanged for them).

- [ ] **Step 6: Commit**

```
[#122] Add atomic bulk PATCH for review-queue notes

- PATCH /api/experiments/notes/bulk: needs_review / note_type on up to 500 ids
- 404 / 422 / 409 name the offending ids or experiments; nothing half-applied
- One ModificationsLog row per changed note
- Tests added: yes (tests/api/test_notes_bulk.py, 11)
- Docs updated: no (Task 8)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 3: Bulk DELETE endpoint

**Files:**
- Modify: `backend/api/routers/experiments.py` (directly after `bulk_patch_notes`)
- Modify: `tests/api/test_notes_bulk.py` (append)

**Interfaces:**
- Consumes: `NotesBulkDelete`, `NotesBulkResponse`, `_load_notes_for_bulk` from Task 2.
- Produces: route `DELETE /api/experiments/notes/bulk` with a JSON body `{ids}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_notes_bulk.py`:

```python
# --------------------------------------------------------------- DELETE ----

def test_bulk_delete_removes_notes_and_logs_one_row_per_note(client, db_session):
    exp = _exp(db_session, "BULK_010", 7310)
    r = _result(db_session, exp)
    a = _note(db_session, exp, "t=0", needs_review=True, result_id=r.id)
    b = _note(db_session, exp, "Day 7", needs_review=True)
    keep = _note(db_session, exp, "keep me")
    resp = client.request("DELETE", "/api/experiments/notes/bulk", json={"ids": [b.id, a.id]})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"count": 2, "ids": sorted([a.id, b.id])}
    db_session.expire_all()
    assert db_session.get(ExperimentNotes, a.id) is None
    assert db_session.get(ExperimentNotes, b.id) is None
    assert db_session.get(ExperimentNotes, keep.id) is not None
    logs = _logs(db_session, exp)
    assert len(logs) == 2
    assert all(l.modification_type == "delete" for l in logs)
    snap = next(l for l in logs if l.old_values["note_text"] == "t=0").old_values
    assert snap == {"id": a.id, "note_text": "t=0", "note_type": "observation",
                    "result_id": r.id, "created_by": None, "needs_review": True}


def test_bulk_delete_unknown_id_is_404_and_deletes_nothing(client, db_session):
    exp = _exp(db_session, "BULK_011", 7311)
    a = _note(db_session, exp, "x", needs_review=True)
    resp = client.request("DELETE", "/api/experiments/notes/bulk", json={"ids": [a.id, 999999]})
    assert resp.status_code == 404
    assert "999999" in resp.json()["detail"]
    db_session.expire_all()
    assert db_session.get(ExperimentNotes, a.id) is not None
    assert _logs(db_session, exp) == []


def test_bulk_delete_body_validation(client, db_session):
    assert client.request("DELETE", "/api/experiments/notes/bulk", json={"ids": []}).status_code == 422
    assert client.request("DELETE", "/api/experiments/notes/bulk",
                          json={"ids": list(range(1, 502))}).status_code == 422
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/pytest.exe tests/api/test_notes_bulk.py -v -k delete`
Expected: 3 FAIL (405 or 404).

- [ ] **Step 3: Implement**

After `bulk_patch_notes` in the router:

```python
@router.delete("/notes/bulk", response_model=NotesBulkResponse)
def bulk_delete_notes(
    payload: NotesBulkDelete,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> NotesBulkResponse:
    """Delete many notes at once (issue #122 PR-A). Atomic; one
    ModificationsLog 'delete' row per note holding the full note snapshot
    (text, type, result_id, created_by, needs_review) -- the only trace left."""
    notes = _load_notes_for_bulk(db, payload.ids)
    ids: list[int] = []
    for n in notes:
        db.add(ModificationsLog(
            experiment_id=n.experiment_id,
            experiment_fk=n.experiment_fk,
            modified_by=current_user.email,
            modification_type="delete",
            modified_table="experiment_notes",
            old_values={
                "id": n.id,
                "note_text": n.note_text,
                "note_type": n.note_type.value,
                "result_id": n.result_id,
                "created_by": n.created_by,
                "needs_review": n.needs_review,
            },
            new_values=None,
        ))
        db.delete(n)
        ids.append(n.id)
    db.commit()
    log.info("notes_bulk_deleted", count=len(ids))
    return NotesBulkResponse(count=len(ids), ids=sorted(ids))
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/pytest.exe tests/api/test_notes_bulk.py -v`
Expected: 14 PASS.

- [ ] **Step 5: Commit**

```
[#122] Add atomic bulk DELETE for review-queue notes

- DELETE /api/experiments/notes/bulk with {ids}; full snapshot per note in ModificationsLog
- Tests added: yes (3)
- Docs updated: no (Task 8)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 4: Extend `GET /notes/review` — filters, order, `distinct_texts`

**Files:**
- Modify: `backend/api/schemas/experiments.py` (`ReviewQueueResponse`)
- Modify: `backend/api/routers/experiments.py:488-527` (`list_review_queue`)
- Modify: `tests/api/test_notes_review.py` (one existing assertion + new tests)

**Interfaces:**
- Produces: query params `note_type`, `q`, `experiment_id`, `order` (`experiment|created_at|text`), `desc`; response field `distinct_texts: list[DistinctText]` with `DistinctText(text: str, count: int)`. Task 6 mirrors these in TS.

- [ ] **Step 1: Update the one existing assertion and write the failing tests**

In `tests/api/test_notes_review.py`, change `test_review_queue_path_is_not_captured_as_an_experiment_id`'s last line to:

```python
    assert set(resp.json()) == {"items", "total", "skip", "limit", "distinct_texts"}
```

Append:

```python
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
    ids = {i["id"] for i in client.get("/api/experiments/notes/review", params={"q": "5% at t_0"}).json()["items"]}
    assert lit.id in ids and other.id not in ids


def test_review_queue_filters_by_experiment_id_contains(client, db_session):
    a = _exp(db_session, "RQ_104_SERUM", 7404)
    b = _exp(db_session, "RQ_105_HPHT", 7405)
    na = _note(db_session, a, "x", needs_review=True)
    nb = _note(db_session, b, "x", needs_review=True)
    ids = {i["id"] for i in client.get("/api/experiments/notes/review?experiment_id=104_serum").json()["items"]}
    assert na.id in ids and nb.id not in ids


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
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/pytest.exe tests/api/test_notes_review.py -v`
Expected: the 7 new tests FAIL (unknown params ignored → wrong sets; `distinct_texts` KeyError); the modified path test FAILS on the key set.

- [ ] **Step 3: Implement**

Schema — in `backend/api/schemas/experiments.py`, replace `ReviewQueueResponse` with:

```python
class DistinctText(BaseModel):
    """One bar of the review-queue text histogram (issue #122 PR-A): how many
    rows in the current filter carry exactly this note_text."""
    text: str
    count: int


class ReviewQueueResponse(BaseModel):
    items: list[ReviewNoteItem]
    total: int
    skip: int
    limit: int
    #: Top 50 distinct note_text values in the current filter, most frequent
    #: first, so the page can offer "select all 30 rows reading `t=0`".
    distinct_texts: list[DistinctText] = []
```

Router — replace `list_review_queue` (lines 488-527) with:

```python
_REVIEW_ORDERS = ("experiment", "created_at", "text")


def _escape_like(s: str) -> str:
    """Make a user string safe as a LIKE *literal*: `%`/`_` lose their wildcard meaning."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/notes/review", response_model=ReviewQueueResponse)
def list_review_queue(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    researcher: str | None = None,
    note_type: NoteType | None = None,
    q: str | None = Query(None, description="case-insensitive substring of note_text"),
    experiment_id: str | None = Query(None, description="case-insensitive substring of experiment_id"),
    order: str = Query("experiment", pattern="^(experiment|created_at|text)$"),
    desc: bool = False,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ReviewQueueResponse:
    """Notes with needs_review = true across all experiments (issue #118 PR3;
    filters, order and distinct_texts added by #122 PR-A).

    These are the rows the 020 backfill could not place with certainty.
    Resolve rows with PATCH /notes/bulk (many) or PATCH
    /experiments/{id}/notes/{note_id} (one). `distinct_texts` is the top-50
    histogram of note_text over the *current filter* (not the page), so the
    page can select every row reading e.g. `t=0`. Registered before the
    /{experiment_id} routes so the literal path is not captured.
    """
    base = (
        select(ExperimentNotes, Experiment.researcher, ExperimentalResults.time_post_reaction_days)
        .join(Experiment, Experiment.id == ExperimentNotes.experiment_fk)
        .outerjoin(ExperimentalResults, ExperimentalResults.id == ExperimentNotes.result_id)
        .where(ExperimentNotes.needs_review.is_(True))
    )
    if researcher:
        base = base.where(Experiment.researcher == researcher)
    if note_type is not None:
        base = base.where(ExperimentNotes.note_type == note_type)
    if q:
        base = base.where(ExperimentNotes.note_text.ilike(f"%{_escape_like(q)}%", escape="\\"))
    if experiment_id:
        base = base.where(Experiment.experiment_id.ilike(f"%{_escape_like(experiment_id)}%", escape="\\"))

    primary = {
        "experiment": Experiment.experiment_id,
        "created_at": ExperimentNotes.created_at,
        "text": ExperimentNotes.note_text,
    }[order]
    ordering = (primary.desc() if desc else primary.asc(), ExperimentNotes.id.desc() if desc else ExperimentNotes.id.asc())

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(base.order_by(*ordering).offset(skip).limit(limit)).all()

    hist_sub = base.subquery()
    hist = db.execute(
        select(hist_sub.c.note_text, func.count().label("n"))
        .group_by(hist_sub.c.note_text)
        .order_by(func.count().desc(), hist_sub.c.note_text.asc())
        .limit(50)
    ).all()

    items = [
        ReviewNoteItem(
            **NoteResponse.model_validate(n).model_dump(),
            experiment_fk=n.experiment_fk,
            researcher=res,
            time_post_reaction_days=day,
        )
        for n, res, day in rows
    ]
    return ReviewQueueResponse(
        items=items, total=total, skip=skip, limit=limit,
        distinct_texts=[DistinctText(text=t if t is not None else "", count=c) for t, c in hist],
    )
```

Add `DistinctText` to the schema import block in the router. If `hist_sub.c.note_text` is ambiguous because the subquery has two `experiment_id`-like columns, SQLAlchemy names them `experiment_id`, `experiment_id_1`; `note_text` is unique so it resolves. Note the `_REVIEW_ORDERS` tuple is documentation only; the `pattern=` on `order` is what enforces it (422 on `bogus`).

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/pytest.exe tests/api/test_notes_review.py tests/api/test_notes_bulk.py -v`
Expected: all PASS (17 + 14).

- [ ] **Step 5: Commit**

```
[#122] Filter, order and histogram the review queue

- GET /notes/review: note_type, q, experiment_id (ILIKE literal), order + desc
- distinct_texts: top-50 note_text histogram over the current filter
- Tests added: yes (7; one key-set assertion extended)
- Docs updated: no (Task 8)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 5: Frontend API client types and functions

**Files:**
- Modify: `frontend/src/api/experiments.ts` (types near line 34-46; functions near line 361-368)

**Interfaces:**
- Produces (used by Tasks 6-7):
  ```ts
  export interface DistinctText { text: string; count: number }
  export interface ReviewQueueResponse { items: ReviewNoteItem[]; total: number; skip: number; limit: number; distinct_texts: DistinctText[] }
  export type ReviewOrder = 'experiment' | 'created_at' | 'text'
  export interface ReviewQueueParams { researcher?: string; note_type?: NoteType; q?: string; experiment_id?: string; order?: ReviewOrder; desc?: boolean; skip?: number; limit?: number }
  export interface NotesBulkPatch { ids: number[]; needs_review?: boolean; note_type?: NoteType }
  export interface NotesBulkResponse { count: number; ids: number[] }
  experimentsApi.getReviewQueue(params?: ReviewQueueParams): Promise<ReviewQueueResponse>
  experimentsApi.bulkPatchNotes(body: NotesBulkPatch): Promise<NotesBulkResponse>
  experimentsApi.bulkDeleteNotes(ids: number[]): Promise<NotesBulkResponse>
  ```

No unit test of its own: the client is exercised through the page test in Task 7 (mocked) and `tsc`.

- [ ] **Step 1: Add the types**

Replace the existing `ReviewQueueResponse` interface with:

```ts
/** Issue #122 PR-A: one bar of the review-queue text histogram. */
export interface DistinctText {
  text: string
  count: number
}

export interface ReviewQueueResponse {
  items: ReviewNoteItem[]
  total: number
  skip: number
  limit: number
  /** Top 50 distinct note_text values in the current filter, most frequent first. */
  distinct_texts: DistinctText[]
}

export type ReviewOrder = 'experiment' | 'created_at' | 'text'

export interface ReviewQueueParams {
  researcher?: string
  note_type?: NoteType
  /** Case-insensitive substring of note_text; `%`/`_` are literal. */
  q?: string
  /** Case-insensitive substring of experiment_id. */
  experiment_id?: string
  order?: ReviewOrder
  desc?: boolean
  skip?: number
  limit?: number
}

/** Issue #122 PR-A: body of PATCH /experiments/notes/bulk. Atomic on the server. */
export interface NotesBulkPatch {
  ids: number[]
  needs_review?: boolean
  note_type?: NoteType
}

export interface NotesBulkResponse {
  count: number
  ids: number[]
}
```

- [ ] **Step 2: Add the functions**

Replace `getReviewQueue` and add two siblings right after it:

```ts
  /** Issue #118/#122: notes flagged needs_review, across all experiments, filtered and ordered. */
  getReviewQueue: (params: ReviewQueueParams = {}) =>
    apiClient
      .get<ReviewQueueResponse>('/experiments/notes/review', { params })
      .then((r) => r.data),

  /** Issue #122 PR-A: resolve / retype many notes in one atomic call (cap 500). */
  bulkPatchNotes: (body: NotesBulkPatch) =>
    apiClient.patch<NotesBulkResponse>('/experiments/notes/bulk', body).then((r) => r.data),

  /** Issue #122 PR-A: delete many notes in one atomic call (cap 500). */
  bulkDeleteNotes: (ids: number[]) =>
    apiClient
      .delete<NotesBulkResponse>('/experiments/notes/bulk', { data: { ids } })
      .then((r) => r.data),
```

- [ ] **Step 3: Type-check**

Run (from `frontend/`): `npx tsc --noEmit -p tsconfig.json 2>&1 | grep -v "ResultsTab.columns.test" | head`
Expected: no new errors (the three `ResultsTab.columns.test.tsx` errors are the pre-existing baseline).

- [ ] **Step 4: Commit**

```
[#122] Add review-queue bulk and filter API client

- ReviewQueueParams, DistinctText, NotesBulkPatch/Response; bulkPatchNotes, bulkDeleteNotes
- Tests added: no (covered by Task 7 page test)
- Docs updated: no

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 6: Route and nav item with open-count badge

**Files:**
- Create: `frontend/src/pages/NotesReview.tsx` (stub export only; Task 7 fills it)
- Modify: `frontend/src/App.tsx` (imports lines 6-15; route list lines 35-44)
- Modify: `frontend/src/layouts/AppLayout.tsx` (`navItems` + render)
- Create: `frontend/src/layouts/__tests__/AppLayout.badge.test.tsx`

**Interfaces:**
- Consumes: `experimentsApi.getReviewQueue({ limit: 1 })` (Task 5).
- Produces: `export function NotesReviewPage()`; React Query key `['notes-review', 'count']`. Task 7 must invalidate the prefix `['notes-review']` after every bulk action so this badge refreshes.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/layouts/__tests__/AppLayout.badge.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { email: 'mh@addisenergy.com', displayName: 'MH' }, signOut: vi.fn() }),
}))
vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    getReviewQueue: vi.fn(() => Promise.resolve({ items: [], total: 1288, skip: 0, limit: 1, distinct_texts: [] })),
  },
}))

import { AppLayout } from '../AppLayout'
import { experimentsApi } from '@/api/experiments'

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <AppLayout />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('AppLayout review-queue badge', () => {
  it('links to /notes/review and shows the open count', async () => {
    wrap()
    const link = screen.getByRole('link', { name: /notes review/i })
    expect(link).toHaveAttribute('href', '/notes/review')
    await waitFor(() => expect(screen.getByText('1288')).toBeInTheDocument())
    expect(experimentsApi.getReviewQueue).toHaveBeenCalledWith({ limit: 1 })
  })

  it('hides the badge when the queue is empty', async () => {
    vi.mocked(experimentsApi.getReviewQueue).mockResolvedValueOnce({ items: [], total: 0, skip: 0, limit: 1, distinct_texts: [] })
    wrap()
    await waitFor(() => expect(experimentsApi.getReviewQueue).toHaveBeenCalled())
    expect(screen.queryByTestId('review-count-badge')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run (from `frontend/`): `npx vitest run src/layouts/__tests__/AppLayout.badge.test.tsx`
Expected: FAIL — no link named "Notes review".

- [ ] **Step 3: Stub the page and add the route**

Create `frontend/src/pages/NotesReview.tsx`:

```tsx
/** Issue #122 PR-A: global review queue for notes the #118 backfill could not
 *  place with certainty. Filled in by the next task. */
export function NotesReviewPage() {
  return <div className="p-6 text-sm text-ink-muted">Notes review</div>
}
```

In `App.tsx`, add `import { NotesReviewPage } from '@/pages/NotesReview'` after the `AnalysisPage` import, and add a route after `/analysis`:

```tsx
          <Route path="/notes/review" element={<NotesReviewPage />} />
```

- [ ] **Step 4: Add the nav item and badge**

In `AppLayout.tsx`:

Add imports at the top:
```tsx
import { useQuery } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
```

Extend `NavItem` with `badge?: number` is not needed — keep `navItems` static and render the badge by path. Append to `navItems` after Chemicals:

```tsx
  {
    path: '/notes/review',
    label: 'Notes review',
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M3 2.5h10v9l-2.5-2H3v-7z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
        <path d="M5.5 5.5h5M5.5 8h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    ),
  },
```

Inside `AppLayout()`, after `const navigate = useNavigate()`:

```tsx
  // Issue #122 PR-A: open review-queue count for the nav badge. Same endpoint
  // the page uses; the page invalidates the ['notes-review'] prefix after every
  // bulk action so this refreshes without a dedicated count route.
  const { data: reviewQueue } = useQuery({
    queryKey: ['notes-review', 'count'],
    queryFn: () => experimentsApi.getReviewQueue({ limit: 1 }),
    staleTime: 60_000,
  })
  const reviewCount = reviewQueue?.total ?? 0
```

In the `NavLink` body, replace `<span className="truncate">{item.label}</span>` with:

```tsx
                  <span className="truncate flex-1">{item.label}</span>
                  {item.path === '/notes/review' && reviewCount > 0 && (
                    <span
                      data-testid="review-count-badge"
                      className="ml-auto shrink-0 rounded-full bg-status-error/20 text-status-error text-2xs font-semibold px-1.5 py-0.5 font-mono-data"
                    >
                      {reviewCount}
                    </span>
                  )}
```

Render the raw number, not `toLocaleString()`, so the test's `getByText('1288')` is exact and jsdom locale cannot insert a separator.

- [ ] **Step 5: Run to verify it passes**

Run: `npx vitest run src/layouts/__tests__/AppLayout.badge.test.tsx`
Expected: 2 PASS.

- [ ] **Step 6: Commit**

```
[#122] Add /notes/review route and nav badge

- Nav item "Notes review" with open count from GET /notes/review?limit=1
- Tests added: yes (AppLayout.badge.test.tsx, 2)
- Docs updated: no

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 7: The `/notes/review` page

**Files:**
- Modify: `frontend/src/pages/NotesReview.tsx` (replace stub)
- Create: `frontend/src/pages/__tests__/NotesReview.test.tsx`

**Interfaces:**
- Consumes: `experimentsApi.getReviewQueue`, `bulkPatchNotes`, `bulkDeleteNotes`, types from Task 5; `Badge`, `Button`, `ConfirmModal`, `Table*`, `Select`, `Input`, `Spinner`, `useToast` from `@/components/ui`; `NOTE_TYPE_LABELS`, `NoteType` from `@/api/noteTypes`.
- Query key: `['notes-review', 'list', params]`; invalidate prefix `['notes-review']` after any mutation.

Behaviour summary (all pinned by the test below):
- Fetches `limit: 500`, `skip: 0` with the current filters. Header: "N open" and, when `total > items.length`, "showing first 500 of N — narrow the filter".
- Filters: researcher (text), experiment (text), type (select: any + 4 types), search (text, 300 ms debounce), order (select) + direction toggle.
- Chips from `distinct_texts`: "`t=0` ×30"; clicking one **adds** every loaded row with that exact text to the selection (union, never toggles off).
- Row: checkbox, experiment link, researcher, `T+7` (or `—`), type badge, text, author, date. Header checkbox selects/clears all loaded rows.
- Sticky action bar when selection > 0: "N selected", Mark reviewed, Retype (type select + button), Delete, Clear. Each action opens `ConfirmModal` whose description states the count. On success: toast, clear selection, invalidate `['notes-review']`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/pages/__tests__/NotesReview.test.tsx
/** Issue #122 PR-A: the global review queue page. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import type { ReviewNoteItem, ReviewQueueResponse } from '@/api/experiments'

vi.mock('@/api/experiments', async () => {
  const actual = await vi.importActual<typeof import('@/api/experiments')>('@/api/experiments')
  return {
    ...actual,
    experimentsApi: {
      getReviewQueue: vi.fn(),
      bulkPatchNotes: vi.fn(() => Promise.resolve({ count: 2, ids: [1, 2] })),
      bulkDeleteNotes: vi.fn(() => Promise.resolve({ count: 1, ids: [3] })),
    },
  }
})

import { NotesReviewPage } from '../NotesReview'
import { experimentsApi } from '@/api/experiments'

function item(p: Partial<ReviewNoteItem> & { id: number; note_text: string; experiment_id: string }): ReviewNoteItem {
  return {
    note_type: 'observation', result_id: null, created_by: 'reclassify_notes_020', needs_review: true,
    created_at: '2026-09-08T12:00:00Z', updated_at: null, experiment_fk: 1, researcher: 'MH',
    time_post_reaction_days: null, ...p,
  }
}

const ITEMS: ReviewNoteItem[] = [
  item({ id: 1, note_text: 't=0', experiment_id: 'SERUM_001a', result_id: 10, time_post_reaction_days: 0 }),
  item({ id: 2, note_text: 't=0', experiment_id: 'SERUM_001b', result_id: 11, time_post_reaction_days: 0 }),
  item({ id: 3, note_text: 'End of exp.', experiment_id: 'HPHT_040', researcher: 'JW' }),
]

const RESPONSE: ReviewQueueResponse = {
  items: ITEMS, total: 3, skip: 0, limit: 500,
  distinct_texts: [{ text: 't=0', count: 2 }, { text: 'End of exp.', count: 1 }],
}

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ToastProvider><NotesReviewPage /></ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.mocked(experimentsApi.getReviewQueue).mockReset()
  vi.mocked(experimentsApi.getReviewQueue).mockResolvedValue(RESPONSE)
  vi.mocked(experimentsApi.bulkPatchNotes).mockClear()
  vi.mocked(experimentsApi.bulkDeleteNotes).mockClear()
})

describe('NotesReviewPage', () => {
  it('renders rows with experiment links, T+day and type badges, fetching 500 at a time', async () => {
    wrap()
    await waitFor(() => expect(screen.getByRole('link', { name: 'SERUM_001a' })).toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'SERUM_001a' })).toHaveAttribute('href', '/experiments/SERUM_001a')
    expect(screen.getAllByText('T+0')).toHaveLength(2)
    expect(screen.getAllByText('Observation').length).toBeGreaterThanOrEqual(3)
    expect(screen.getByText(/3 open/)).toBeInTheDocument()
    expect(experimentsApi.getReviewQueue).toHaveBeenCalledWith(expect.objectContaining({ limit: 500, skip: 0 }))
  })

  it('selecting rows and confirming Mark reviewed calls the bulk API with those ids', async () => {
    const user = userEvent.setup()
    wrap()
    await screen.findByRole('link', { name: 'SERUM_001a' })
    await user.click(screen.getByRole('checkbox', { name: /select note 1/i }))
    await user.click(screen.getByRole('checkbox', { name: /select note 2/i }))
    expect(screen.getByText('2 selected')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /mark reviewed/i }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/2 notes/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: /^mark reviewed$/i }))
    await waitFor(() =>
      expect(experimentsApi.bulkPatchNotes).toHaveBeenCalledWith({ ids: [1, 2], needs_review: false }),
    )
    await waitFor(() => expect(screen.queryByText('2 selected')).not.toBeInTheDocument())
  })

  it('a distinct-text chip adds every row with that text to the selection without toggling', async () => {
    const user = userEvent.setup()
    wrap()
    await screen.findByRole('link', { name: 'SERUM_001a' })
    await user.click(screen.getByRole('checkbox', { name: /select note 1/i }))
    await user.click(screen.getByRole('button', { name: /select all 2 reading/i }))
    expect(screen.getByText('2 selected')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /select note 1/i })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /select note 2/i })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /select note 3/i })).not.toBeChecked()
  })

  it('Retype sends note_type and clears the review flag', async () => {
    const user = userEvent.setup()
    wrap()
    await screen.findByRole('link', { name: 'SERUM_001a' })
    await user.click(screen.getByRole('checkbox', { name: /select all/i }))
    await user.selectOptions(screen.getByLabelText(/retype to/i), 'modification')
    await user.click(screen.getByRole('button', { name: /^retype$/i }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: /^retype$/i }))
    await waitFor(() =>
      expect(experimentsApi.bulkPatchNotes).toHaveBeenCalledWith({ ids: [1, 2, 3], note_type: 'modification', needs_review: false }),
    )
  })

  it('Delete confirms with the count then calls bulkDeleteNotes', async () => {
    const user = userEvent.setup()
    wrap()
    await screen.findByRole('link', { name: 'HPHT_040' })
    await user.click(screen.getByRole('checkbox', { name: /select note 3/i }))
    await user.click(screen.getByRole('button', { name: /^delete$/i }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/1 note/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: /^delete$/i }))
    await waitFor(() => expect(experimentsApi.bulkDeleteNotes).toHaveBeenCalledWith([3]))
  })

  it('filters are passed to the API', async () => {
    const user = userEvent.setup()
    wrap()
    await screen.findByRole('link', { name: 'SERUM_001a' })
    await user.selectOptions(screen.getByLabelText(/^type$/i), 'modification')
    await waitFor(() =>
      expect(experimentsApi.getReviewQueue).toHaveBeenLastCalledWith(expect.objectContaining({ note_type: 'modification' })),
    )
    fireEvent.change(screen.getByLabelText(/search text/i), { target: { value: 'brine' } })
    await waitFor(
      () => expect(experimentsApi.getReviewQueue).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'brine' })),
      { timeout: 2000 },
    )
  })

  it('says when the loaded set is truncated', async () => {
    vi.mocked(experimentsApi.getReviewQueue).mockResolvedValue({ ...RESPONSE, total: 1288 })
    wrap()
    await waitFor(() => expect(screen.getByText(/showing first 3 of 1288/i)).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/pages/__tests__/NotesReview.test.tsx`
Expected: FAIL — the stub renders no links.

- [ ] **Step 3: Implement the page**

Replace `frontend/src/pages/NotesReview.tsx` with:

```tsx
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  experimentsApi,
  type ReviewNoteItem,
  type ReviewOrder,
  type ReviewQueueParams,
} from '@/api/experiments'
import { NOTE_TYPE_LABELS, type NoteType } from '@/api/noteTypes'
import {
  Badge, Button, ConfirmModal, Input, Select, Spinner,
  Table, TableBody, TableHead, TableRow, Td, Th, useToast,
} from '@/components/ui'

/** One page = one bulk call: the server caps bulk bodies at 500 ids, so the
 *  page never loads more than it can act on in one go. */
const PAGE_LIMIT = 500

const NOTE_TYPES: NoteType[] = ['description', 'modification', 'observation', 'result_note']

type PendingAction = { kind: 'review' } | { kind: 'retype'; to: NoteType } | { kind: 'delete' } | null

function typeBadgeVariant(t: NoteType): 'default' | 'warning' | 'info' {
  if (t === 'modification') return 'warning'
  if (t === 'description') return 'info'
  return 'default'
}

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

/** Issue #122 PR-A: the global review queue. Every row is a note the #118
 *  backfill flagged `needs_review`. Researchers filter, select (rows, all
 *  loaded, or "every row reading X"), then Mark reviewed / Retype / Delete in
 *  one atomic, per-note-audited call. */
export function NotesReviewPage() {
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()

  // Filters
  const [researcher, setResearcher] = useState('')
  const [experimentId, setExperimentId] = useState('')
  const [noteType, setNoteType] = useState<NoteType | ''>('')
  const [search, setSearch] = useState('')
  const [order, setOrder] = useState<ReviewOrder>('experiment')
  const [desc, setDesc] = useState(false)
  const q = useDebounced(search.trim(), 300)
  const researcherQ = useDebounced(researcher.trim(), 300)
  const experimentQ = useDebounced(experimentId.trim(), 300)

  const params = useMemo<ReviewQueueParams>(() => ({
    limit: PAGE_LIMIT,
    skip: 0,
    order,
    desc,
    ...(researcherQ ? { researcher: researcherQ } : {}),
    ...(experimentQ ? { experiment_id: experimentQ } : {}),
    ...(noteType ? { note_type: noteType } : {}),
    ...(q ? { q } : {}),
  }), [order, desc, researcherQ, experimentQ, noteType, q])

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['notes-review', 'list', params],
    queryFn: () => experimentsApi.getReviewQueue(params),
  })
  const items: ReviewNoteItem[] = data?.items ?? []
  const total = data?.total ?? 0

  // Selection (ids of loaded rows only)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  useEffect(() => {
    // Drop ids that left the loaded set (filter change or a completed action).
    setSelected((prev) => {
      const live = new Set(items.map((i) => i.id))
      const next = new Set([...prev].filter((id) => live.has(id)))
      return next.size === prev.size ? prev : next
    })
  }, [items])

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  const allSelected = items.length > 0 && items.every((i) => selected.has(i.id))
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(items.map((i) => i.id)))
  const selectText = (text: string) =>
    setSelected((prev) => new Set([...prev, ...items.filter((i) => i.note_text === text).map((i) => i.id)]))
  const selectedIds = () => items.filter((i) => selected.has(i.id)).map((i) => i.id)

  // Actions
  const [retypeTo, setRetypeTo] = useState<NoteType>('observation')
  const [pending, setPending] = useState<PendingAction>(null)
  const afterAction = (msg: string) => {
    success(msg)
    setSelected(new Set())
    setPending(null)
    queryClient.invalidateQueries({ queryKey: ['notes-review'] })
  }
  const patch = useMutation({
    mutationFn: (body: Parameters<typeof experimentsApi.bulkPatchNotes>[0]) => experimentsApi.bulkPatchNotes(body),
    onSuccess: (r) => afterAction(`${plural(r.count, 'note')} updated`),
    onError: (err: Error) => toastError('Bulk update failed', err.message),
  })
  const remove = useMutation({
    mutationFn: (ids: number[]) => experimentsApi.bulkDeleteNotes(ids),
    onSuccess: (r) => afterAction(`${plural(r.count, 'note')} deleted`),
    onError: (err: Error) => toastError('Bulk delete failed', err.message),
  })

  const confirmPending = () => {
    const ids = selectedIds()
    if (!pending || ids.length === 0) return
    if (pending.kind === 'review') patch.mutate({ ids, needs_review: false })
    else if (pending.kind === 'retype') patch.mutate({ ids, note_type: pending.to, needs_review: false })
    else remove.mutate(ids)
  }

  const busy = patch.isPending || remove.isPending
  const count = selected.size
  const pendingCopy = (() => {
    if (!pending) return { title: '', description: '', label: 'Confirm', danger: false }
    if (pending.kind === 'review')
      return { title: 'Mark as reviewed?', description: `${plural(count, 'note')} will leave the review queue. They are not changed otherwise.`, label: 'Mark reviewed', danger: false }
    if (pending.kind === 'retype')
      return { title: `Retype as ${NOTE_TYPE_LABELS[pending.to]}?`, description: `${plural(count, 'note')} will become "${NOTE_TYPE_LABELS[pending.to]}" and leave the review queue. Scope rules apply: the whole batch is rejected if any note cannot take this type.`, label: 'Retype', danger: false }
    return { title: 'Delete notes?', description: `${plural(count, 'note')} will be permanently deleted. Each deletion is recorded in the entry log.`, label: 'Delete', danger: true }
  })()

  return (
    <div className="space-y-4 pb-20">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-lg font-semibold text-ink-primary">Notes review</h1>
          <p className="text-xs text-ink-muted mt-0.5">
            {isLoading ? 'Loading…' : `${total} open`}
            {!isLoading && total > items.length && (
              <> · showing first {items.length} of {total} — narrow the filter to reach the rest</>
            )}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3 items-end">
        <Input label="Researcher" value={researcher} onChange={(e) => setResearcher(e.target.value)} placeholder="MH" />
        <Input label="Experiment" value={experimentId} onChange={(e) => setExperimentId(e.target.value)} placeholder="SERUM_001" />
        <Select
          label="Type"
          value={noteType}
          onChange={(e) => setNoteType(e.target.value as NoteType | '')}
          options={[{ value: '', label: 'Any type' }, ...NOTE_TYPES.map((t) => ({ value: t, label: NOTE_TYPE_LABELS[t] }))]}
        />
        <Input label="Search text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="t=0" />
        <Select
          label="Order"
          value={order}
          onChange={(e) => setOrder(e.target.value as ReviewOrder)}
          options={[
            { value: 'experiment', label: 'Experiment' },
            { value: 'created_at', label: 'Created' },
            { value: 'text', label: 'Text' },
          ]}
        />
        <Button variant="secondary" size="md" onClick={() => setDesc((d) => !d)} aria-label="Toggle sort direction">
          {desc ? 'Descending' : 'Ascending'}
        </Button>
      </div>

      {/* Distinct-text chips */}
      {data && data.distinct_texts.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {data.distinct_texts.map((d) => (
            <button
              key={d.text}
              type="button"
              aria-label={`Select all ${d.count} reading ${d.text}`}
              title={`Select all ${d.count} reading "${d.text}"`}
              onClick={() => selectText(d.text)}
              className="inline-flex items-center gap-1.5 max-w-xs px-2 py-0.5 rounded border border-surface-border bg-surface-raised text-2xs text-ink-secondary hover:text-ink-primary hover:border-ink-muted transition-colors"
            >
              <span className="truncate font-mono-data">{d.text || '(blank)'}</span>
              <span className="text-ink-muted">×{d.count}</span>
            </button>
          ))}
        </div>
      )}

      {/* Table */}
      {isLoading && <div className="py-12 flex justify-center"><Spinner /></div>}
      {isError && <p className="text-sm text-status-error">Failed to load: {(error as Error).message}</p>}
      {data && items.length === 0 && <p className="text-sm text-ink-muted py-8">Nothing left to review in this filter.</p>}
      {items.length > 0 && (
        <Table>
          <TableHead>
            <tr>
              <Th className="w-8">
                <input type="checkbox" aria-label="Select all" checked={allSelected} onChange={toggleAll} />
              </Th>
              <Th>Experiment</Th>
              <Th>Researcher</Th>
              <Th>Timepoint</Th>
              <Th>Type</Th>
              <Th>Text</Th>
              <Th>Author</Th>
              <Th>Date</Th>
            </tr>
          </TableHead>
          <TableBody>
            {items.map((n) => (
              <TableRow key={n.id} className={selected.has(n.id) ? 'bg-red-500/5' : ''}>
                <Td>
                  <input
                    type="checkbox"
                    aria-label={`Select note ${n.id}`}
                    checked={selected.has(n.id)}
                    onChange={() => toggle(n.id)}
                  />
                </Td>
                <Td>
                  <Link to={`/experiments/${encodeURIComponent(n.experiment_id)}`} className="text-ink-primary hover:text-red-400 font-mono-data">
                    {n.experiment_id}
                  </Link>
                </Td>
                <Td className="text-ink-secondary">{n.researcher ?? '—'}</Td>
                <Td className="font-mono-data text-ink-secondary">
                  {n.time_post_reaction_days != null ? `T+${n.time_post_reaction_days}` : '—'}
                </Td>
                <Td><Badge variant={typeBadgeVariant(n.note_type)}>{NOTE_TYPE_LABELS[n.note_type]}</Badge></Td>
                <Td className="max-w-md whitespace-pre-wrap text-ink-primary">{n.note_text}</Td>
                <Td className="text-ink-muted text-xs">{n.created_by ?? '—'}</Td>
                <Td className="text-ink-muted text-xs font-mono-data whitespace-nowrap">
                  {new Date(n.created_at).toLocaleDateString()}
                </Td>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {/* Sticky action bar */}
      {count > 0 && (
        <div className="fixed bottom-0 left-[240px] right-0 border-t border-surface-border bg-surface-raised/95 backdrop-blur-sm px-6 py-3 flex items-center gap-3 flex-wrap z-20">
          <span className="text-sm text-ink-primary font-medium">{count} selected</span>
          <Button variant="primary" size="sm" disabled={busy} onClick={() => setPending({ kind: 'review' })}>
            Mark reviewed
          </Button>
          <div className="flex items-center gap-1.5">
            <label htmlFor="retype-to" className="text-xs text-ink-secondary">Retype to</label>
            <select
              id="retype-to"
              value={retypeTo}
              onChange={(e) => setRetypeTo(e.target.value as NoteType)}
              className="text-xs px-2 py-1 border border-surface-border rounded bg-surface-raised text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50"
            >
              {NOTE_TYPES.map((t) => <option key={t} value={t}>{NOTE_TYPE_LABELS[t]}</option>)}
            </select>
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => setPending({ kind: 'retype', to: retypeTo })}>
              Retype
            </Button>
          </div>
          <Button variant="danger" size="sm" disabled={busy} onClick={() => setPending({ kind: 'delete' })}>
            Delete
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>Clear</Button>
        </div>
      )}

      <ConfirmModal
        open={pending !== null}
        onClose={() => setPending(null)}
        onConfirm={confirmPending}
        loading={busy}
        title={pendingCopy.title}
        description={pendingCopy.description}
        confirmLabel={pendingCopy.label}
        danger={pendingCopy.danger}
      />
    </div>
  )
}
```

Notes for the implementer:
- `Td`, `Th` are exported from `@/components/ui`; `TableHead` wraps a `<thead>` so the header row is a raw `<tr>`.
- `Select`'s `options` prop is required; `Input` is a labelled wrapper around `<input>` — `getByLabelText(/search text/i)` resolves through its `label htmlFor`.
- `ConfirmModal` renders a `role="dialog"` (check `Modal.tsx`; if it does not, add `role="dialog"` and `aria-modal` to the Modal's panel — a one-line, test-visible fix, mention it in the commit body).
- The "Select all" header checkbox and the chips' `aria-label` "Select all N reading X" both match `/select all/i`; the test that clicks `/select all/i` for the header must therefore use `getByRole('checkbox', { name: /select all/i })` (it does) — checkbox vs button roles disambiguate.

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run src/pages/__tests__/NotesReview.test.tsx src/layouts/__tests__/AppLayout.badge.test.tsx`
Expected: 9 PASS. If the Retype test fails to find `/retype to/i`, the `label htmlFor="retype-to"` is what `getByLabelText` needs — confirm it is present.

- [ ] **Step 5: Lint and type-check**

Run: `npx eslint src/pages/NotesReview.tsx src/layouts/AppLayout.tsx src/api/experiments.ts src/App.tsx src/pages/__tests__/NotesReview.test.tsx src/layouts/__tests__/AppLayout.badge.test.tsx`
Expected: no output (zero warnings on the new files).
Run: `npx tsc --noEmit -p tsconfig.json 2>&1 | grep -v "ResultsTab.columns.test"`
Expected: no lines.

- [ ] **Step 6: Commit**

```
[#122] Add /notes/review bulk review-queue page

- Filters, order, distinct-text chips, row/all selection, sticky bar
- Mark reviewed / Retype / Delete with count-stating confirms
- Tests added: yes (NotesReview.test.tsx, 7)
- Docs updated: no (Task 8)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 8: Docs, full verification, issue-log

**Files:**
- Modify: `docs/api/API_REFERENCE.md` (line 15 row; two new rows after line 26)
- Modify: `docs/working/issue-log.md` (append)
- Modify: `docs/user_guide/` — check for an existing notes/review section (`grep -rn "review queue\|needs_review" docs/user_guide/`); if present, add one paragraph pointing at `/notes/review`; if absent, skip and say so.

- [ ] **Step 1: Update API_REFERENCE.md**

Replace the `/api/experiments/notes/review` row with:

```markdown
| GET | `/api/experiments/notes/review` | Review queue: notes with `needs_review = true` across all experiments, with `experiment_id`, `researcher`, `time_post_reaction_days`. Query: `researcher` (exact), `note_type`, `q` and `experiment_id` (case-insensitive substrings; `%`/`_` literal), `order` = `experiment`\|`created_at`\|`text`, `desc`, `skip`, `limit` (≤1000). Response adds `distinct_texts`: top-50 `{text, count}` histogram over the current filter (issue #122 PR-A). |
```

Add after the single-note PATCH row:

```markdown
| PATCH | `/api/experiments/notes/bulk` | Issue #122 PR-A. Body `{"ids": [..≤500], "needs_review"?: bool, "note_type"?: NoteType}` (at least one action). **Atomic**: unknown id → 404 naming ids; scope violation → 422 naming ids; more than one description per experiment → 409 naming experiments; nothing is written on any error. One `ModificationsLog` `update` row per changed note. Response `{count, ids}`; notes already in the requested state are not counted. Registered before `/{experiment_id}`. |
| DELETE | `/api/experiments/notes/bulk` | Issue #122 PR-A. Body `{"ids": [..≤500]}`. Atomic; unknown id → 404. One `ModificationsLog` `delete` row per note with the full snapshot (`id`, `note_text`, `note_type`, `result_id`, `created_by`, `needs_review`) in `old_values`. Response `{count, ids}`. |
```

The `PostToolUse` hook syncs this to `docs/project_context/` when the edit is made with the Edit tool. If the edit is made from a script, run `python -c "from importlib import util; ..."` — simpler: call `.venv/Scripts/python.exe .claude/hooks/sync_docs_to_project_context.py` per memory `docs-sync-hook-bypassed-by-scripts` (check the module exposes `full_sync()` and call it).

- [ ] **Step 2: Full backend verification (one process)**

If the `experiments_test` schema is stale from a previous session, reset first:
```
psql -U experiments_user -d experiments_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
```
Run: `.venv/Scripts/pytest.exe tests/models tests/views tests/api tests/test_icp_handling.py tests/services tests/regression tests/data_migrations -q -p no:cacheprovider`
Expected: 0 failed (baseline on develop was 1,369 passed; expect +21).

- [ ] **Step 3: Full frontend verification**

From `frontend/`: `npx vitest run` → expect 0 failed (baseline 235 passed; expect +9). `npx eslint src --ext .ts,.tsx` → only the #106 baseline (compare counts against `git stash`-free baseline by running the same command on `develop` via `git worktree` or by accepting the count recorded in the 2026-09-23 issue-log entry). `npx tsc --noEmit` → only the 3 pre-existing `ResultsTab.columns.test.tsx` errors.

- [ ] **Step 4: Append the issue-log entry**

```markdown
## 2026-09-23 | issue #122 PR-A — Review-queue bulk tooling (`feat/notes-review-queue`)
- **Files changed:**
  - `backend/api/schemas/experiments.py` — `NotesBulkPatch`, `NotesBulkDelete`, `NotesBulkResponse`, `DistinctText`; `ReviewQueueResponse.distinct_texts`
  - `backend/api/routers/experiments.py` — `PATCH`/`DELETE /notes/bulk` (atomic, one `ModificationsLog` row per note, registered before `/{experiment_id}`); `GET /notes/review` gains `note_type`, `q`, `experiment_id`, `order`, `desc`, `distinct_texts`
  - `frontend/src/api/experiments.ts`, `frontend/src/pages/NotesReview.tsx` (new), `frontend/src/App.tsx` (`/notes/review`), `frontend/src/layouts/AppLayout.tsx` (nav item + open-count badge)
  - Tests: `tests/api/test_notes_bulk.py` (14), `tests/api/test_notes_review.py` (+7), `frontend/src/pages/__tests__/NotesReview.test.tsx` (7), `frontend/src/layouts/__tests__/AppLayout.badge.test.tsx` (2)
  - Docs: `docs/api/API_REFERENCE.md`, `docs/working/issues/07-notes-overhaul-phase-2.md` (the phase-2 prompt), this entry
- **Design calls (approved in-session):** bulk calls are atomic (validate all → write all, one transaction); `order` has a `desc` flag; "select all in filter" means the loaded set — the page fetches `limit=500` to match the bulk cap and says "showing first 500 of N" above that; the nav badge reuses `GET /notes/review?limit=1` (React Query, 60 s stale, invalidated by the `['notes-review']` prefix after every bulk action).
- **Verification:** <paste the pytest / vitest / eslint / tsc counts from Steps 2–3>
- **Tests added:** yes. **Docs updated:** yes. **Decision logged:** no (the phase-2 decisions are in the prompt doc; the "modification anchored to a result or a date" entry belongs to PR-B).
- **Next:** PR-B `feat/reactor-mods-as-notes` — schema (`event_date`, relaxed `ck_note_scope`) pre-authorized 2026-09-23; 021 dry run then STOP for audit.
```

- [ ] **Step 5: Commit**

```
[#122] Document bulk review-queue API; log PR-A

- API_REFERENCE rows for PATCH/DELETE /notes/bulk and the extended GET
- Tests added: no
- Docs updated: yes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

- [ ] **Step 6: Open the PR**

```bash
git push -u origin feat/notes-review-queue
gh pr create --base develop --title "[#122] PR-A: review-queue bulk tooling" --body-file <scratchpad>/pr_body.md
```

PR body must state: closes nothing (issue #122 stays open through PR-D); not stacked — branches directly from `develop`; no schema change; no locked file touched; the verification counts; and that `test_review_queue_path_is_not_captured_as_an_experiment_id` had its key-set assertion extended by `distinct_texts`. End with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

---

## Self-review

**Spec coverage.** PR-A backend: bulk PATCH (Task 2), bulk DELETE (Task 3), 422/409/cap/register-before (Tasks 2-3), extended GET with `note_type`/`q`/`experiment_id`/`order` + `distinct_texts` top-50 (Task 4). Frontend: route + nav badge (Task 6), table columns, filters, chips, row checkboxes, select-all, sticky bar with three confirming actions (Task 7); per-experiment "Review queue only" filter untouched (no task touches `NotesTab.tsx`). Tests named in the spec: bulk endpoints happy/partial-422/409/cap (Task 2-3), review filters (Task 4), `NotesReview.test.tsx` with selection and a bulk action calling the API with selected ids (Task 7). Docs (Task 8). Prompt saved (Task 1).

**Placeholders.** Task 1 says "paste the prompt body verbatim" — the Conductor holds the text; acceptable since the content is not code. Task 8 Step 4 has an explicit `<paste counts>` slot that is filled at execution from real output, not invented.

**Type consistency.** `NotesBulkResponse{count, ids}` is used identically in Tasks 2, 3, 5, 7. `DistinctText{text, count}` in Tasks 4, 5, 6 (mock), 7. `ReviewQueueParams` fields match the router's query names exactly (`note_type`, `q`, `experiment_id`, `order`, `desc`, `skip`, `limit`, `researcher`). Query-key prefix `['notes-review']` in Tasks 6 and 7.

**Review Focus.** (1) duplicate ids → `test_bulk_patch_duplicate_ids_are_counted_once`; (2) two-on-one-experiment → `test_bulk_patch_two_selected_on_same_experiment_to_description_is_409`; (3) `%`/`_` literal → `test_review_queue_q_treats_percent_and_underscore_literally`; (4) already-in-state no-op → `test_bulk_patch_already_in_state_is_a_no_op`; (5) chip is a union → the chip test in Task 7 pre-selects row 1 then asserts rows 1 and 2 checked, 3 not.
