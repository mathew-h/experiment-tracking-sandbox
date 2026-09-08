# Typed Experiment Notes — PR1 (schema + dual-write) and PR2 (backfill) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `experiment_notes` a declared type and an optional result scope, mirror every legacy free-text write into it, and produce an audited, deterministic backfill plan — without changing anything a user or Power BI reads yet.

**Architecture:** PR1 is purely additive: four new columns on `experiment_notes`, a `note_type` Postgres enum, a partial unique index (one `description` per experiment), a composite FK that ties a note's `result_id` to a result of the *same* experiment, and a scope CHECK — all enforced by the database. A small shared helper (`backend/services/notes.py`) is the single place that decides how a legacy value maps onto a typed note; each of the five write paths calls it *after* writing the legacy column, so both sides always agree. PR2 is a dry-run-first data migration script following `fix_nan_text_fields_019.py`; it prints the report Mat audits and does nothing without `--apply`.

**Tech Stack:** SQLAlchemy 2.0.39 declarative models, Alembic 1.15, PostgreSQL 15+, FastAPI + Pydantic v2, pandas for the parsers, pytest against `experiments_test`.

**Spec:** GitHub issue #118 (`gh issue view 118`) — the task text from Mat Hearl, 2026-09-08.

## Global Constraints

- Issue mode. Commit subjects: `[#118] <imperative, <50 chars>` with the body bullets from `.claude/CLAUDE.md` §8.
- Branches: PR1 `feat/typed-notes-schema`, PR2 `chore/reclassify-notes-backfill`, both from `develop`; PRs `--base develop`.
- PR1 migration must be **additive only**. No column drops until PR4.
- **Do not change readers in PR1.** `Experiment.description`, the `min(id)` subqueries, the views: untouched.
- Nothing becomes required at entry; no validator replaces a removed one.
- `observation` is scope-free: valid with or without `result_id`. Do not narrow it.
- `master_bulk_upload.py` footnote ² properties must all still hold; `tests/services/bulk_uploads/test_master_bulk_upload.py` must pass **unchanged**.
- `backend/services/notion_sync/` is not a consumer; do not touch it.
- PR2: **dry run only**. Never run `--apply`. Post the report and stop.
- Test runner: `.venv/Scripts/pytest`. Never run two pytest processes at once (shared `experiments_test`).

---

## File Structure

| File | Responsibility |
|---|---|
| `database/models/enums.py` | `NoteType` enum (additive). |
| `database/models/experiments.py` | New `ExperimentNotes` columns, constraints, indexes, viewonly `result` relationship. |
| `database/models/results.py` | `UNIQUE (experiment_fk, id)` so the composite FK has a target; viewonly `notes` relationship. |
| `alembic/versions/b7e2c9a41d05_typed_experiment_notes.py` | The additive migration, upgrade + downgrade. |
| `backend/services/notes.py` | **Single definition** of legacy → typed mapping: `add_note`, `add_first_or_observation_note`, `sync_result_note`. |
| `backend/api/schemas/experiments.py` | `NoteCreate` gains `note_type`, `result_id`; `NoteResponse` gains the four new fields. |
| `backend/api/routers/experiments.py` | `POST /{id}/notes` validates scope + result ownership, sets `created_by`. |
| `backend/api/routers/results.py` | `POST /api/results` dual-writes `description` → observation note, `brine_modification_description` → modification note. |
| `backend/services/bulk_uploads/master_bulk_upload.py` | v4 headers via aliases, drop the `Master upload — day` fallback, dual-write both text columns. |
| `backend/services/bulk_uploads/timepoint_modifications.py` | Dual-write the modification note; accept `modification note` header. |
| `backend/services/bulk_uploads/new_experiments.py` | `initial_note` NaN fix; gate note clearing on real text; write the typed note. |
| `database/lineage_utils.py` | `auto_create_treatment_experiment` initial note goes through the helper. |
| `database/data_migrations/reclassify_notes_020.py` | PR2 backfill, dry run by default. |
| Tests | `tests/models/test_typed_notes_columns.py`, `tests/api/test_notes.py`, `tests/api/test_results.py`, `tests/services/bulk_uploads/test_typed_notes_dual_write.py`, `tests/services/bulk_uploads/test_new_experiments_rename_denormalized_ids.py`. |
| Docs | `.claude/rules/MODELS.md`, `docs/LOCKED_COMPONENTS.md`, `docs/upload_templates/{master_bulk_upload,new_experiments,timepoint_modifications}.md`, `docs/user_guide/BULK_UPLOADS.md`, `docs/api/API_REFERENCE.md`, `docs/issues/issue-blank-initial-note-parses-to-nan.md`, `docs/working/issue-log.md`. |

## Decisions recorded here (not in the spec)

1. **`initial_note` on an experiment that already has notes becomes `observation`, not `description`.** The legacy rule ("oldest note is the description") means a later note was never the description; making it one would also trip the partial unique index once PR2 promotes the oldest note. The helper `add_first_or_observation_note` encodes this: `description` iff the experiment has zero notes at write time.
2. **Blank `initial_note` on an `overwrite=TRUE` row leaves notes untouched.** This resolves the product question in `issue-blank-initial-note-parses-to-nan.md`: a blank cell means "don't touch the notes". When text IS supplied with overwrite, the clear still happens, but one `ModificationsLog` row now snapshots the deleted texts so the destruction is auditable.
3. **Bulk-path mirroring is a slot, not an append.** `sync_result_note` keeps exactly one note per `(result_id, note_type, created_by)`, updating its text on re-upload and deleting it when the legacy column is cleared. This is what makes "matching values on both sides" true after a second upload of the same workbook.
4. **Filler descriptions generated by code are not mirrored.** `scalar_results_service` / `icp_service` fallbacks ("Analysis results for Day 7") satisfy the NOT NULL column and carry no information, so no note row is written for them. Only researcher-supplied text is mirrored.
5. **`created_by`** is the Firebase email on API paths and a source tag on bulk paths (`master_bulk_upload`, `timepoint_modifications`/the caller's `modified_by`, `new_experiments`).

---

### Task 1: `NoteType` enum + model columns/constraints (DB-enforced), with model tests

**Files:**
- Modify: `database/models/enums.py` (append)
- Modify: `database/models/experiments.py` (`ExperimentNotes`)
- Modify: `database/models/results.py` (`ExperimentalResults.__table_args__`, relationship)
- Test: `tests/models/test_typed_notes_columns.py`

**Interfaces:**
- Produces: `NoteType` with members `description`, `modification`, `observation`, `result_note` (name == value). `ExperimentNotes.note_type`, `.result_id`, `.created_by`, `.needs_review`, `.result` (viewonly). `ExperimentalResults.notes` (viewonly).

- [ ] **Step 1: Write the failing tests**

```python
# tests/models/test_typed_notes_columns.py
"""DB-level guarantees on experiment_notes (issue #118, PR1).

Every assertion here is about what PostgreSQL rejects, not what app code
checks — the spec requires the partial unique index, composite FK and scope
CHECK to be enforced by the database. The test DB is built with
Base.metadata.create_all, so the model's __table_args__ must carry them.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database import Experiment, ExperimentNotes, ExperimentalResults
from database.models.enums import ExperimentStatus, NoteType


def _exp(db, exp_id, number):
    exp = Experiment(experiment_id=exp_id, experiment_number=number, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _result(db, exp, day):
    r = ExperimentalResults(experiment_fk=exp.id, time_post_reaction_days=day,
                            time_post_reaction_bucket_days=day, description="seed")
    db.add(r)
    db.flush()
    return r


def _note(db, exp, **kw):
    n = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, **kw)
    db.add(n)
    db.flush()
    return n


def test_defaults_are_observation_not_reviewed(db_session):
    exp = _exp(db_session, "TN_DEF_001", 9118001)
    n = _note(db_session, exp, note_text="plain")
    db_session.refresh(n)
    assert n.note_type is NoteType.observation
    assert n.result_id is None
    assert n.created_by is None
    assert n.needs_review is False


@pytest.mark.parametrize("note_type", [NoteType.modification, NoteType.result_note])
def test_scope_check_rejects_result_scoped_type_without_result(db_session, note_type):
    exp = _exp(db_session, "TN_CK_001", 9118002)
    with pytest.raises(IntegrityError, match="ck_note_scope"):
        _note(db_session, exp, note_text="x", note_type=note_type)


def test_scope_check_rejects_description_with_result(db_session):
    exp = _exp(db_session, "TN_CK_002", 9118003)
    r = _result(db_session, exp, 1.0)
    with pytest.raises(IntegrityError, match="ck_note_scope"):
        _note(db_session, exp, note_text="x", note_type=NoteType.description, result_id=r.id)


def test_observation_is_valid_with_and_without_result(db_session):
    exp = _exp(db_session, "TN_OBS_001", 9118004)
    r = _result(db_session, exp, 1.0)
    _note(db_session, exp, note_text="free", note_type=NoteType.observation)
    _note(db_session, exp, note_text="scoped", note_type=NoteType.observation, result_id=r.id)
    rows = db_session.execute(select(ExperimentNotes).where(ExperimentNotes.experiment_fk == exp.id)).scalars().all()
    assert sorted(n.result_id for n in rows if n.result_id) == [r.id]
    assert len(rows) == 2


def test_partial_unique_index_rejects_second_description(db_session):
    exp = _exp(db_session, "TN_UQ_001", 9118005)
    _note(db_session, exp, note_text="first", note_type=NoteType.description)
    with pytest.raises(IntegrityError, match="uq_one_description_per_experiment"):
        _note(db_session, exp, note_text="second", note_type=NoteType.description)


def test_two_experiments_may_each_have_a_description(db_session):
    a = _exp(db_session, "TN_UQ_002", 9118006)
    b = _exp(db_session, "TN_UQ_003", 9118007)
    _note(db_session, a, note_text="a", note_type=NoteType.description)
    _note(db_session, b, note_text="b", note_type=NoteType.description)


def test_composite_fk_rejects_result_from_another_experiment(db_session):
    a = _exp(db_session, "TN_FK_001", 9118008)
    b = _exp(db_session, "TN_FK_002", 9118009)
    rb = _result(db_session, b, 1.0)
    with pytest.raises(IntegrityError, match="fk_note_result_same_experiment"):
        _note(db_session, a, note_text="x", note_type=NoteType.modification, result_id=rb.id)


def test_composite_fk_accepts_result_from_same_experiment(db_session):
    a = _exp(db_session, "TN_FK_003", 9118010)
    ra = _result(db_session, a, 1.0)
    n = _note(db_session, a, note_text="x", note_type=NoteType.modification, result_id=ra.id)
    db_session.refresh(n)
    assert n.result.id == ra.id
    db_session.refresh(ra)
    assert [x.id for x in ra.notes] == [n.id]


def test_deleting_result_cascades_to_its_notes_but_not_experiment_notes(db_session):
    a = _exp(db_session, "TN_CAS_001", 9118011)
    ra = _result(db_session, a, 1.0)
    scoped = _note(db_session, a, note_text="scoped", note_type=NoteType.result_note, result_id=ra.id)
    free = _note(db_session, a, note_text="free")
    db_session.execute(ExperimentalResults.__table__.delete().where(ExperimentalResults.id == ra.id))
    db_session.expire_all()
    ids = set(db_session.execute(select(ExperimentNotes.id).where(ExperimentNotes.experiment_fk == a.id)).scalars())
    assert ids == {free.id}
    assert scoped.id not in ids
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/pytest tests/models/test_typed_notes_columns.py -q`
Expected: ImportError on `NoteType` / TypeError on unknown kwargs.

- [ ] **Step 3: Implement**

`database/models/enums.py` — append:

```python
# === Notes (issue #118) ===
class NoteType(enum.Enum):
    """Declared purpose of an experiment_notes row.

    Member NAME equals the stored VALUE (lowercase) so SQLAlchemy's default
    persist-by-name produces exactly the Postgres enum labels the migration
    declares ('description', 'modification', 'observation', 'result_note').
    """
    description = "description"    # the experiment's one-line summary; at most one per experiment, never result-scoped
    modification = "modification"  # what was done to the vial at a timepoint (the MOD badge); result-scoped
    observation = "observation"    # free text; valid with or without a result — deliberately scope-free
    result_note = "result_note"    # a remark about a specific measurement; result-scoped
```

`database/models/experiments.py` — imports add `CheckConstraint, ForeignKeyConstraint, Index`; `from .enums import ExperimentStatus, NoteType`. Replace `ExperimentNotes`:

```python
class ExperimentNotes(Base):
    """Typed free text about an experiment, optionally scoped to one result row.

    Issue #118. The database, not app code, enforces the three rules:
      * uq_one_description_per_experiment — at most one 'description' note.
      * fk_note_result_same_experiment   — a result-scoped note points at a
        result of THIS experiment (composite FK; MATCH SIMPLE leaves rows
        with result_id NULL unconstrained, which is intended).
      * ck_note_scope — 'description' is never result-scoped, 'modification'
        and 'result_note' always are, 'observation' may be either.
    """
    __tablename__ = "experiment_notes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["experiment_fk", "result_id"],
            ["experimental_results.experiment_fk", "experimental_results.id"],
            name="fk_note_result_same_experiment",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(note_type = 'description' AND result_id IS NULL) OR "
            "(note_type IN ('modification', 'result_note') AND result_id IS NOT NULL) OR "
            "(note_type = 'observation')",
            name="ck_note_scope",
        ),
        Index("uq_one_description_per_experiment", "experiment_fk", unique=True,
              postgresql_where=text("note_type = 'description'")),
        Index("ix_experiment_notes_result_id", "result_id"),
        Index("ix_experiment_notes_scope", "experiment_fk", "note_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(String, nullable=False, index=True)  # Human-readable ID (denormalized; synced by denormalized_ids.py)
    experiment_fk = Column(Integer, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False)
    note_text = Column(Text)
    note_type = Column(SQLEnum(NoteType, name="note_type"), nullable=False,
                       default=NoteType.observation, server_default=text("'observation'"))
    result_id = Column(Integer, nullable=True)  # scoped to one experimental_results row; see composite FK above
    created_by = Column(String, nullable=True)  # Firebase email on API paths, a source tag on bulk paths
    needs_review = Column(Boolean, nullable=False, default=False, server_default=text("false"))  # backfill could not place this row with certainty
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    experiment = relationship("Experiment", back_populates="notes", foreign_keys=[experiment_fk])
    # viewonly: the DB cascade owns deletion; the ORM must not try to NULL result_id.
    result = relationship(
        "ExperimentalResults",
        primaryjoin="ExperimentNotes.result_id == ExperimentalResults.id",
        foreign_keys=[result_id],
        viewonly=True,
    )
```

`database/models/results.py` — add `UniqueConstraint` import; in `__table_args__` add `UniqueConstraint("experiment_fk", "id", name="uq_results_experiment_fk_id")`; add relationship:

```python
    # Typed notes scoped to this timepoint (issue #118). viewonly: deletion is
    # the DB's ON DELETE CASCADE, and experiment_fk is shared with the
    # composite FK so the ORM must not try to manage it from this side.
    notes = relationship(
        "ExperimentNotes",
        primaryjoin="ExperimentalResults.id == foreign(ExperimentNotes.result_id)",
        viewonly=True,
        order_by="ExperimentNotes.id",
    )
```

- [ ] **Step 4: Run tests** — `.venv/Scripts/pytest tests/models/test_typed_notes_columns.py -q` → all pass. Then `.venv/Scripts/pytest tests/models tests/api/test_notes.py tests/api/test_results.py -q` → no regressions.

- [ ] **Step 5: Commit** — `[#118] Add typed note columns and constraints`

---

### Task 2: Alembic migration (additive), verified up/down against the dev DB

**Files:**
- Create: `alembic/versions/b7e2c9a41d05_typed_experiment_notes.py` (down_revision `00063a5dd6a8`)

- [ ] **Step 1: Write the migration**

```python
"""Typed experiment notes: note_type, result_id, created_by, needs_review (issue #118, PR1).

Additive only. Existing rows get note_type='observation'; PR2's
reclassify_notes_020.py promotes the right one per experiment to 'description'.

Revision ID: b7e2c9a41d05
Revises: 00063a5dd6a8
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b7e2c9a41d05"
down_revision = "00063a5dd6a8"
branch_labels = None
depends_on = None

NOTE_TYPES = ("description", "modification", "observation", "result_note")


def upgrade() -> None:
    note_type = postgresql.ENUM(*NOTE_TYPES, name="note_type", create_type=False)
    note_type.create(op.get_bind(), checkfirst=True)

    op.add_column("experiment_notes", sa.Column("note_type", note_type, nullable=False, server_default="observation"))
    op.add_column("experiment_notes", sa.Column("result_id", sa.Integer(), nullable=True))
    op.add_column("experiment_notes", sa.Column("created_by", sa.String(), nullable=True))
    op.add_column("experiment_notes", sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    op.create_index("uq_one_description_per_experiment", "experiment_notes", ["experiment_fk"], unique=True,
                    postgresql_where=sa.text("note_type = 'description'"))
    op.create_unique_constraint("uq_results_experiment_fk_id", "experimental_results", ["experiment_fk", "id"])
    op.create_foreign_key("fk_note_result_same_experiment", "experiment_notes", "experimental_results",
                          ["experiment_fk", "result_id"], ["experiment_fk", "id"], ondelete="CASCADE")
    op.create_check_constraint("ck_note_scope", "experiment_notes",
        "(note_type = 'description' AND result_id IS NULL) OR "
        "(note_type IN ('modification', 'result_note') AND result_id IS NOT NULL) OR "
        "(note_type = 'observation')")
    op.create_index("ix_experiment_notes_result_id", "experiment_notes", ["result_id"])
    op.create_index("ix_experiment_notes_scope", "experiment_notes", ["experiment_fk", "note_type"])


def downgrade() -> None:
    op.drop_index("ix_experiment_notes_scope", table_name="experiment_notes")
    op.drop_index("ix_experiment_notes_result_id", table_name="experiment_notes")
    op.drop_constraint("ck_note_scope", "experiment_notes", type_="check")
    op.drop_constraint("fk_note_result_same_experiment", "experiment_notes", type_="foreignkey")
    op.drop_constraint("uq_results_experiment_fk_id", "experimental_results", type_="unique")
    op.drop_index("uq_one_description_per_experiment", table_name="experiment_notes")
    op.drop_column("experiment_notes", "needs_review")
    op.drop_column("experiment_notes", "created_by")
    op.drop_column("experiment_notes", "result_id")
    op.drop_column("experiment_notes", "note_type")
    postgresql.ENUM(name="note_type").drop(op.get_bind(), checkfirst=True)
```

- [ ] **Step 2: Verify** — `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` against the dev DB (DATABASE_URL from `.env`), then `psql \d experiment_notes` shows the four columns, the index, the FK and the check.

- [ ] **Step 3: Commit** — `[#118] Migrate experiment_notes to typed schema`

---

### Task 3: Shared dual-write helper `backend/services/notes.py`

**Interfaces (Produces):**

```python
def add_note(db, experiment, note_text, *, note_type=NoteType.observation, result_id=None, created_by=None, needs_review=False, created_at=None) -> ExperimentNotes
def add_first_or_observation_note(db, experiment, note_text, *, created_by=None) -> ExperimentNotes
    # 'description' iff the experiment has zero notes; else 'observation'
def sync_result_note(db, result, note_type, note_text, *, created_by) -> Optional[ExperimentNotes]
    # one slot per (result_id, note_type, created_by): create / update text / delete when note_text is blank
```

- [ ] Write tests in `tests/services/bulk_uploads/test_typed_notes_dual_write.py` (section "helper"): first note becomes description, second observation; sync creates, updates in place (same id), deletes on blank, ignores another created_by's note of the same type.
- [ ] Implement; run; commit `[#118] Add typed-note dual-write helper`.

---

### Task 4: `POST /experiments/{id}/notes` gains `note_type`/`result_id`; `POST /api/results` dual-writes

**Files:** `backend/api/schemas/experiments.py`, `backend/api/routers/experiments.py:1425-1446`, `backend/api/routers/results.py:78-124`, tests `tests/api/test_notes.py`, `tests/api/test_results.py`.

- [ ] Tests: default note is `observation`; `note_type="modification"` with a valid `result_id` → 201 with fields echoed; `result_id` from another experiment → 422; `description` with `result_id` → 422; second `description` → 409; `POST /api/results` with description + brine text → two notes on the result with matching text, `created_by == test@addisenergy.com`; blank description → no observation note (the column still stores it — reader unchanged).
- [ ] Implement: `NoteCreate(note_text: str, note_type: NoteType = observation, result_id: int | None = None)`; `NoteResponse` + `note_type`, `result_id`, `created_by`, `needs_review`. Router pre-checks scope (422) and ownership (422), catches `IntegrityError` on the unique index → 409. `create_result` calls `add_note` twice when text is non-blank.
- [ ] Commit `[#118] Dual-write typed notes on API write paths`.

---

### Task 5: `master_bulk_upload.py` — v4 headers, no fallback, dual-write

**Files:** `backend/services/bulk_uploads/master_bulk_upload.py:83-110,183,938-1000`; docstring header; tests in `test_typed_notes_dual_write.py`.

- [ ] Tests: v3 headers (`Description`, `Modification`) and v4 headers (`Observation Note`, `Modification Note`) upload the same rows → identical `(note_type, result_id, note_text)` sets; blank Description → no observation note and the stored `description` is the service fallback, never `Master upload — day`; re-upload with edited text updates in place (one note per slot).
- [ ] Implement: aliases `description`/`observation note` → `Observation Note`, `modification`/`modification note` → `Modification Note`; `_JOINED_TEXT_COLUMNS = ("Observation Note", "Modification Note")`; row reads use the new names; `"description": description` (no fallback); after `savepoint`-guarded upsert: `if description: sync_result_note(... observation ...)`, `if modification: sync_result_note(... modification ...)`, both **inside** the savepoint so a note failure rolls back only that row.
- [ ] Run `tests/services/bulk_uploads/test_master_bulk_upload.py` **unchanged** → pass. Commit `[#118] Accept v4 Dashboard headers; mirror notes`.

---

### Task 6: `timepoint_modifications.py` dual-write

- [ ] Test: upload sets `brine_modification_description` AND a `modification` note with equal text; overwrite with blank clears both.
- [ ] Implement: add `"modification note"` alias; after the legacy assignment call `sync_result_note(db, target, NoteType.modification, modification or None, created_by=modified_by)`.
- [ ] Commit `[#118] Mirror timepoint modifications into notes`.

---

### Task 7: `new_experiments.py` — NaN fix + typed initial note

**Files:** `backend/services/bulk_uploads/new_experiments.py:539-540,724-728,742-751`; `tests/services/bulk_uploads/test_new_experiments_rename_denormalized_ids.py::test_bulk_rename_syncs_all_five_tables` (update the pinned `"nan"` assertion); new tests.

- [ ] Tests: blank `initial_note` + overwrite → seeded note survives, no `"nan"` row; new experiment with `initial_note` → one `description` note; existing experiment (no overwrite) with `initial_note` → new note is `observation`, the old one untouched; overwrite with text → old notes gone, one `ModificationsLog` row with the deleted texts, new `description` note.
- [ ] Implement: `initial_note = None if pd.isna(raw) else str(raw).strip() or None`; move the clearing block under `if initial_note:` and snapshot texts to `ModificationsLog(modification_type="delete", modified_table="experiment_notes", old_values={"note_texts": [...]})`; replace the `ExperimentNotes(...)` construction with `add_first_or_observation_note(db, experiment, initial_note, created_by="new_experiments")`.
- [ ] Update `database/lineage_utils.py:517-524` to the same helper.
- [ ] Commit `[#118] Fix blank initial_note NaN; type initial notes`.

---

### Task 8: Docs for PR1 + PR

- [ ] `.claude/rules/MODELS.md` `ExperimentNotes` section: new fields, constraints, helper, dual-write, PR sequence.
- [ ] `docs/LOCKED_COMPONENTS.md`: footnote on the typed-notes mirror for the three parsers.
- [ ] `docs/upload_templates/master_bulk_upload.md`, `new_experiments.md`, `timepoint_modifications.md`; `docs/user_guide/BULK_UPLOADS.md` §6; `docs/api/API_REFERENCE.md` notes endpoint.
- [ ] `docs/issues/issue-blank-initial-note-parses-to-nan.md` status → fixed in #118 PR1.
- [ ] `docs/working/issue-log.md` entry.
- [ ] Full run: `.venv/Scripts/pytest tests/services/ tests/regression/ tests/api/ tests/models/ -q`.
- [ ] Commit `[#118] Document typed notes schema and dual-write`; push; `gh pr create --base develop` with the footnote ² six-property statement.

---

### Task 9 (PR2): `database/data_migrations/reclassify_notes_020.py` + dry-run report, then STOP

**Branch:** `chore/reclassify-notes-backfill` from `develop` after PR1 merges (or stacked on PR1 if it has not merged — say which in the handoff).

- [ ] Write the script per the house pattern: docstring with reasoning, `--apply`, `DATABASE_URL` override, before/after counts. Rules in the spec's order; every SQL statement idempotent (skip a result-derived note if an identical `(result_id, note_type, note_text)` already exists).
- [ ] Report sections: experiments with zero notes; experiments whose min(id) note is `'nan'` (left `observation`, `needs_review`); PR1-era explicit `description` notes that are not min(id) (kept, counted); `brine_modification_description` → modification notes to insert; `results.description` discarded vs preserved with 20 samples each **and** the top 15 distinct preserved texts by frequency; total review-queue rows.
- [ ] Run dry run against the dev DB, save output to `docs/issues/reclassify-notes-020-dryrun-2026-09-08.md`, commit, open PR2, **stop**.

## Self-review

- Spec coverage: PR1 migration DDL ✔ (Task 2), five write paths ✔ (Tasks 4–7), nan bug ✔ (Task 7), v3/v4 aliases + joined columns + fallback deletion ✔ (Task 5), tests for CHECK / unique / FK / dual-write ✔ (Tasks 1, 3–7), docs ✔ (Task 8), PR2 rules and report ✔ (Task 9), stop gate ✔.
- Not in PR1 by design: readers, views, frontend, `has_modification_note`, review endpoint (PR3).
