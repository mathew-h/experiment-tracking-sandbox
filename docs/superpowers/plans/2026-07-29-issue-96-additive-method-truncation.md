# Issue #96: Additive `method` Truncation & Bulk-Upload Data Loss — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two compounding defects in the New Experiments bulk upload additives phase: (1) `ChemicalAdditive.addition_method` is `String(50)` but is documented/used as free text, causing `StringDataRightTruncation`; (2) the additives loop has no savepoint isolation, so one bad row poisons the whole transaction and discards all 50 experiments in the batch.

**Architecture:** Widen `addition_method` to `Text` (locked-model change, single field, purely additive migration). Add a shared `ADDITION_METHOD_MAX_LENGTH` app-layer constant enforced by Pydantic (`max_length`, rejects) and by both bulk-upload parsers (truncate-with-warning, so the row's quantitative data still lands). Mirror the existing `db.begin_nested()` savepoint pattern from the issue #86 experiments-sheet loop into the additives phases of `new_experiments.py` and `experiment_additives.py`.

**Tech Stack:** SQLAlchemy 2.x models, Alembic migrations, FastAPI + Pydantic v2 schemas, pandas-based Excel parsers, pytest against a real PostgreSQL test DB (`experiments_test`).

## Global Constraints

- `database/models/chemicals.py` and `backend/services/bulk_uploads/{new_experiments,experiment_additives}.py` are locked components (CLAUDE.md §5) — this plan is the explicit sign-off; do not extend changes beyond what each task specifies.
- Alembic migrations must be purely additive with both `upgrade`/`downgrade` implemented (CLAUDE.md §7, `docs/LOCKED_COMPONENTS.md`).
- Never delete, rewrite, or squash existing migration files.
- `ADDITION_METHOD_MAX_LENGTH = 500` is the single app-layer bound (defined once in `database/models/chemicals.py`, imported everywhere else) — do not hardcode `500` a second time anywhere.
- Bulk-upload parsers: prefer truncate-with-warning over reject (per issue #96's own recommendation) — a row's quantitative data (amount/unit/compound) must still persist even if its `method` text is over-length.
- API PATCH/PUT/POST schemas: reject over-length `addition_method` with a normal Pydantic validation error (422) — no truncate-and-succeed behavior needed at the single-object API layer, unlike the bulk parsers.
- Test DB is `postgresql://experiments_user:password@localhost:5432/experiments_test`; its schema is bootstrapped via `Base.metadata.create_all(bind=_test_engine)` in test conftest files, **not** via Alembic — `create_all` only creates missing tables, so an existing `chemical_additives` table's column type will **not** change just from editing the model. Task 1 includes a one-time step to bring `experiments_test`'s Alembic state in line so the real migration can apply to it too (see Task 1 Step 3 rationale).
- Commit format per `.claude/CLAUDE.md` §8, issue-task style: `[#96] <imperative description>`.

---

## File Structure

- `database/models/chemicals.py` — model change: `addition_method` → `Text`; add `ADDITION_METHOD_MAX_LENGTH` constant.
- `alembic/versions/293d0ea59422_widen_addition_method_to_text.py` — new migration (already has its revision ID reserved: revises `a1f2c3d4e5b6`, the current head).
- `backend/api/schemas/chemicals.py` — add `max_length=ADDITION_METHOD_MAX_LENGTH` to `addition_method` on `ChemicalAdditiveUpsert`, `AdditiveUpdate`, `AdditiveCreate`.
- `backend/services/bulk_uploads/new_experiments.py` — additives loop (lines ~792–877): add per-row `db.begin_nested()` savepoint isolation + truncate-with-warning for `method_text`.
- `backend/services/bulk_uploads/experiment_additives.py` — per-row loop (lines ~41–142): same two fixes.
- `.claude/rules/MODELS.md` — document the new `Text` type and the 500-char app-layer bound on `ChemicalAdditive.addition_method`.
- `backend/api/routers/bulk_uploads.py` — update the New Experiments template INSTRUCTIONS sheet row for `method` (line ~812).
- New tests: `tests/models/test_addition_method_column.py`, `tests/services/bulk_uploads/test_new_experiments_additives.py`, `tests/services/bulk_uploads/test_experiment_additives.py`; additions to `tests/api/test_schemas.py` and `tests/api/test_additives.py`.

---

### Task 1: Widen `addition_method` to `Text` (model + migration)

**Files:**
- Modify: `database/models/chemicals.py:1-6` (imports), `database/models/chemicals.py:59` (column definition)
- Create: `alembic/versions/293d0ea59422_widen_addition_method_to_text.py`
- Test: `tests/models/test_addition_method_column.py`

**Interfaces:**
- Produces: `database.models.chemicals.ADDITION_METHOD_MAX_LENGTH` (int, `500`) — imported by Task 2 (`backend/api/schemas/chemicals.py`) and Tasks 3/4 (both bulk-upload parsers).
- Produces: `ChemicalAdditive.addition_method` is now `Column(Text, nullable=True)` — no DB-level length ceiling; the 500-char bound is enforced only at the app layer (Tasks 2–4).

- [ ] **Step 1: Write the failing test**

Create `tests/models/test_addition_method_column.py`:

```python
"""Tests for ChemicalAdditive.addition_method being widened to Text (issue #96)."""
import pytest
from sqlalchemy import create_engine, inspect, types
from sqlalchemy.orm import sessionmaker

from database import Base
from database.models.chemicals import Compound, ChemicalAdditive, ADDITION_METHOD_MAX_LENGTH
from database.models.enums import AmountUnit

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(TEST_DB_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=eng)
    yield eng


@pytest.fixture
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def test_addition_method_column_is_text(engine):
    """The chemical_additives.addition_method column must be TEXT (unbounded), not varchar(50)."""
    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("chemical_additives")}
    col_type = columns["addition_method"]["type"]
    assert isinstance(col_type, types.Text) and not isinstance(col_type, types.String), (
        f"expected Text, got {col_type!r} ({type(col_type)})"
    )


def _seed_conditions(db, experiment_id: str, experiment_number: int):
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(experiment_id=experiment_id, experiment_number=experiment_number, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    conditions = ExperimentalConditions(experiment_id=exp.experiment_id, experiment_fk=exp.id)
    db.add(conditions)
    db.flush()
    return conditions


def test_addition_method_85_char_value_round_trips_intact(db):
    """Reproduces the exact issue #96 example: an 85-char prep note must survive a real flush to
    PostgreSQL unmodified. Pre-fix, this raises StringDataRightTruncation (85 > varchar(50))."""
    long_method = "11.8 mL master stock diluted to 20 mL total with DI water; no rock (background blank)"
    assert len(long_method) == 85

    conditions = _seed_conditions(db, "MODEL_I96_001", 980001)
    compound = Compound(name="Iron Oxide Test I96")
    db.add(compound)
    db.flush()

    additive = ChemicalAdditive(
        experiment_id=conditions.id,
        compound_id=compound.id,
        amount=5.0,
        unit=AmountUnit.GRAM,
        addition_method=long_method,
    )
    db.add(additive)
    db.flush()  # pre-fix: raises StringDataRightTruncation here

    db.expire(additive)
    assert additive.addition_method == long_method
    assert len(additive.addition_method) == 85


def test_addition_method_has_no_database_level_length_ceiling(db):
    """The DB column itself must be unbounded — only the app layer (Tasks 2-4) caps at
    ADDITION_METHOD_MAX_LENGTH. A value far beyond that app-layer bound must still flush cleanly
    at the ORM/DB level; it is the parsers'/schemas' job to stop such values before they get here."""
    conditions = _seed_conditions(db, "MODEL_I96_002", 980002)
    compound = Compound(name="Iron Oxide Test I96 B")
    db.add(compound)
    db.flush()

    text_5000 = "x" * 5000
    additive = ChemicalAdditive(
        experiment_id=conditions.id,
        compound_id=compound.id,
        amount=1.0,
        unit=AmountUnit.GRAM,
        addition_method=text_5000,
    )
    db.add(additive)
    db.flush()  # pre-fix: raises StringDataRightTruncation here too

    db.expire(additive)
    assert len(additive.addition_method) == 5000


def test_addition_method_max_length_constant_is_500():
    """Pin the shared app-layer bound so Tasks 2-4 all import the same value."""
    assert ADDITION_METHOD_MAX_LENGTH == 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/models/test_addition_method_column.py -v`

Expected: the whole file errors at collection with `ImportError: cannot import name 'ADDITION_METHOD_MAX_LENGTH'` (it doesn't exist yet). If you temporarily comment out that import to check the rest: `test_addition_method_column_is_text` FAILS (`col_type` is `VARCHAR(50)`, not `Text`), and both round-trip tests FAIL with `sqlalchemy.exc.DataError: ... StringDataRightTruncation ... value too long for type character varying(50)` — this is the literal bug from issue #96, now reproduced as a failing test.

- [ ] **Step 3: One-time fix for the `experiments_test` DB's stale Alembic state**

`experiments_test`'s tables are created via `Base.metadata.create_all`, not via Alembic, and its `alembic_version` table is stamped at a stale revision (`927e08db6505`) that predates many already-applied-via-`create_all` columns. Running `alembic upgrade head` against it directly would try to replay every migration since that stale point and fail on "column already exists" errors. Instead, stamp it to the current dev head first (structurally already true, since `create_all` always reflects the latest models), then apply just the new migration:

Run (from project root):
```bash
DATABASE_URL=postgresql://experiments_user:password@localhost:5432/experiments_test .venv/Scripts/alembic stamp a1f2c3d4e5b6
```
Expected: command succeeds, no migrations run (stamp only rewrites the version table).

- [ ] **Step 4: Write the model change**

In `database/models/chemicals.py`, update the import line (currently line 1):

```python
from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, UniqueConstraint, Enum, Text
```

Add the shared constant immediately after the imports (before `class Compound`):

```python
# Practical free-text bound for ChemicalAdditive.addition_method (issue #96). The DB column
# itself is unbounded Text; this is the single source of truth for the app-layer cap enforced
# by backend/api/schemas/chemicals.py (reject) and both bulk-upload parsers (truncate + warn).
ADDITION_METHOD_MAX_LENGTH = 500
```

Change line 59 (currently `addition_method = Column(String(50), nullable=True)    # "solid", "solution", "dropwise", etc.`) to:

```python
    addition_method = Column(Text, nullable=True)  # Free-text addition/prep description; see ADDITION_METHOD_MAX_LENGTH
```

- [ ] **Step 5: Create the migration**

Create `alembic/versions/293d0ea59422_widen_addition_method_to_text.py` with this exact content:

```python
"""widen addition method to text

Revision ID: 293d0ea59422
Revises: a1f2c3d4e5b6
Create Date: 2026-07-29 08:23:02.919540

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '293d0ea59422'
down_revision: Union[str, None] = 'a1f2c3d4e5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'chemical_additives',
        'addition_method',
        existing_type=sa.String(length=50),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'chemical_additives',
        'addition_method',
        existing_type=sa.Text(),
        type_=sa.String(length=50),
        existing_nullable=True,
    )
```

- [ ] **Step 6: Apply the migration to both databases and validate up/down**

Run (dev DB, uses `.env`'s `DATABASE_URL`):
```bash
.venv/Scripts/alembic upgrade head
.venv/Scripts/alembic downgrade -1
.venv/Scripts/alembic upgrade head
```
Expected: all three succeed with no errors; final state is at `293d0ea59422`.

Run (test DB, explicit override):
```bash
DATABASE_URL=postgresql://experiments_user:password@localhost:5432/experiments_test .venv/Scripts/alembic upgrade head
DATABASE_URL=postgresql://experiments_user:password@localhost:5432/experiments_test .venv/Scripts/alembic downgrade -1
DATABASE_URL=postgresql://experiments_user:password@localhost:5432/experiments_test .venv/Scripts/alembic upgrade head
```
Expected: all three succeed; final state is at `293d0ea59422`.

Then recreate reporting views (they select `addition_method` directly — confirm the drop/recreate still succeeds; the view SQL text itself does not change):
```bash
.venv/Scripts/python -c "import database.event_listeners"
```
Expected: no exceptions; check for `Failed to create view` in output (there should be none).

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/models/test_addition_method_column.py -v`

Expected: all 4 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add database/models/chemicals.py alembic/versions/293d0ea59422_widen_addition_method_to_text.py tests/models/test_addition_method_column.py
git commit -m "$(cat <<'EOF'
[#96] Widen addition_method to Text

- Free-text prep notes no longer overflow varchar(50)
- ADDITION_METHOD_MAX_LENGTH=500 app-layer bound added for Tasks 2-4
- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 2: Reject over-length `addition_method` in the API schemas

**Files:**
- Modify: `backend/api/schemas/chemicals.py:1-5` (import), lines `84`, `95`, `105` (`addition_method` fields)
- Test: `tests/api/test_schemas.py`, `tests/api/test_additives.py`

**Interfaces:**
- Consumes: `database.models.chemicals.ADDITION_METHOD_MAX_LENGTH` (from Task 1).
- Produces: no new names — `ChemicalAdditiveUpsert`, `AdditiveUpdate`, `AdditiveCreate` keep the same field names/types, just gain a `max_length` constraint.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_schemas.py`:

```python
# --- Issue #96 addition_method length guard ---

def test_additive_update_method_over_max_length_rejected():
    from backend.api.schemas.chemicals import AdditiveUpdate
    from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH
    with pytest.raises(ValidationError):
        AdditiveUpdate(addition_method="x" * (ADDITION_METHOD_MAX_LENGTH + 1))


def test_additive_update_method_at_max_length_accepted():
    from backend.api.schemas.chemicals import AdditiveUpdate
    from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH
    u = AdditiveUpdate(addition_method="x" * ADDITION_METHOD_MAX_LENGTH)
    assert len(u.addition_method) == ADDITION_METHOD_MAX_LENGTH


def test_additive_create_method_over_max_length_rejected():
    from backend.api.schemas.chemicals import AdditiveCreate
    from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH
    with pytest.raises(ValidationError):
        AdditiveCreate(
            compound_id=1, amount=1.0, unit=AmountUnit.GRAM,
            addition_method="x" * (ADDITION_METHOD_MAX_LENGTH + 1),
        )


def test_chemical_additive_upsert_method_over_max_length_rejected():
    from backend.api.schemas.chemicals import ChemicalAdditiveUpsert
    from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH
    with pytest.raises(ValidationError):
        ChemicalAdditiveUpsert(
            amount=1.0, unit=AmountUnit.GRAM,
            addition_method="x" * (ADDITION_METHOD_MAX_LENGTH + 1),
        )
```

Append to `tests/api/test_additives.py`:

```python
# --- Issue #96 addition_method length guard ---

def test_patch_additive_method_over_max_length_returns_422(client, db_session):
    from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH
    _, _, _, additive = _setup_experiment_with_additive(db_session, "ADDTEST_I96_001", 96001)
    resp = client.patch(
        f"/api/additives/{additive.id}",
        json={"addition_method": "x" * (ADDITION_METHOD_MAX_LENGTH + 1)},
    )
    assert resp.status_code == 422


def test_patch_additive_method_at_max_length_succeeds(client, db_session):
    from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH
    _, _, _, additive = _setup_experiment_with_additive(db_session, "ADDTEST_I96_002", 96002)
    method_text = "x" * ADDITION_METHOD_MAX_LENGTH
    resp = client.patch(
        f"/api/additives/{additive.id}",
        json={"addition_method": method_text},
    )
    assert resp.status_code == 200
    assert resp.json()["addition_method"] == method_text
```

Note: this last assertion requires `AdditiveResponse` (in the same schemas file, around line 110-124) to expose `addition_method`. It currently does **not** — it only has `id, compound_id, amount, unit, mass_in_grams, moles_added, final_concentration, concentration_units, catalyst_ppm, catalyst_percentage, elemental_metal_mass, compound`. Step 3 below adds `addition_order`/`addition_method` to it (the PATCH endpoint at `backend/api/routers/additives.py:21-42` already returns `AdditiveResponse.model_validate(additive)`, so once the fields exist on the schema they flow through automatically — no router change needed).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_schemas.py -v -k additive_update_method or additive_create_method or chemical_additive_upsert_method`
Run: `pytest tests/api/test_additives.py -v -k method_over_max_length or method_at_max_length`

Expected: the `_rejected` tests FAIL (no `ValidationError` raised — current schemas have no `max_length`), and/or the `_succeeds`/`_at_max_length` test fails on the response body assertion if `AdditiveResponse` doesn't yet include `addition_method`.

- [ ] **Step 3: Implement**

In `backend/api/schemas/chemicals.py`, add the import:

```python
from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH
```

Change each of the three `addition_method: Optional[str] = None` occurrences (lines 84, 95, 105) to:

```python
    addition_method: Optional[str] = Field(None, max_length=ADDITION_METHOD_MAX_LENGTH)
```

In `AdditiveResponse` (around line 110-124), add two fields immediately after `unit: AmountUnit`:

```python
    addition_order: Optional[int] = None
    addition_method: Optional[str] = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/test_schemas.py tests/api/test_additives.py -v`

Expected: all PASS, including pre-existing tests in both files (no regressions).

- [ ] **Step 5: Commit**

```bash
git add backend/api/schemas/chemicals.py tests/api/test_schemas.py tests/api/test_additives.py
git commit -m "$(cat <<'EOF'
[#96] Reject over-length addition_method in API schemas

- max_length=500 on ChemicalAdditiveUpsert/AdditiveUpdate/AdditiveCreate
- AdditiveResponse now exposes addition_method/addition_order
- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 3: Savepoint isolation + truncate-with-warning in `new_experiments.py`

**Files:**
- Modify: `backend/services/bulk_uploads/new_experiments.py` (imports near line 10-24; additives loop lines ~792–877)
- Test: `tests/services/bulk_uploads/test_new_experiments_additives.py` (new file)

**Interfaces:**
- Consumes: `database.models.chemicals.ADDITION_METHOD_MAX_LENGTH` (from Task 1).
- Produces: no new public names. `NewExperimentsUploadService.bulk_upsert_from_excel` keeps its existing signature/return shape `(created_exp, updated_exp, skipped, errors, warnings, info_messages)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/services/bulk_uploads/test_new_experiments_additives.py`:

```python
"""Tests for the additives-phase fixes in issue #96: method truncation + savepoint isolation."""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import Experiment, ChemicalAdditive, Compound, ExperimentalConditions
from database.models.enums import ExperimentStatus
from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH
from backend.services.bulk_uploads.new_experiments import NewExperimentsUploadService

from .excel_helpers import make_excel_multisheet

_EXP_HEADERS = [
    "experiment_id", "old_experiment_id", "sample_id", "researcher",
    "date", "status", "initial_note", "overwrite",
]
_ADD_HEADERS = ["experiment_id", "compound", "amount", "unit", "order", "method"]


def _seed_experiment(db: Session, experiment_id: str, exp_num: int) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=exp_num,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.flush()
    return exp


def test_85_char_method_round_trips_intact(db_session: Session):
    """Reproduces the exact issue #96 example: an 85-char value must survive unmodified."""
    _seed_experiment(db_session, "ADD_I96_A001", 960001)
    long_method = "11.8 mL master stock diluted to 20 mL total with DI water; no rock (background blank)"
    assert len(long_method) == 85

    xlsx = make_excel_multisheet({
        "experiments": (_EXP_HEADERS, []),
        "additives": (_ADD_HEADERS, [
            ["ADD_I96_A001", "Iron Oxide I96", 5.0, "g", 1, long_method],
        ]),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )
    assert errors == [], f"Unexpected errors: {errors}"
    assert not any("truncated" in w for w in warnings), f"Should not truncate an 85-char value: {warnings}"

    additive = (
        db_session.query(ChemicalAdditive)
        .join(Compound)
        .filter(Compound.name == "Iron Oxide I96")
        .one()
    )
    assert additive.addition_method == long_method


def test_method_over_max_length_is_truncated_with_warning(db_session: Session):
    _seed_experiment(db_session, "ADD_I96_A002", 960002)
    over_length = "y" * (ADDITION_METHOD_MAX_LENGTH + 100)

    xlsx = make_excel_multisheet({
        "experiments": (_EXP_HEADERS, []),
        "additives": (_ADD_HEADERS, [
            ["ADD_I96_A002", "Iron Oxide I96 B", 5.0, "g", 1, over_length],
        ]),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )
    assert errors == [], f"Unexpected errors: {errors}"
    assert any("truncated" in w and "Row 2" in w for w in warnings), (
        f"Expected a truncation warning for row 2, got: {warnings}"
    )

    additive = (
        db_session.query(ChemicalAdditive)
        .join(Compound)
        .filter(Compound.name == "Iron Oxide I96 B")
        .one()
    )
    assert len(additive.addition_method) == ADDITION_METHOD_MAX_LENGTH
    assert additive.addition_method == over_length[:ADDITION_METHOD_MAX_LENGTH]


def test_duplicate_compound_row_failure_does_not_poison_other_rows(db_session: Session):
    """A row that fails mid-write (unique constraint violation) must roll back only itself —
    other rows in the same batch, and the session itself, must remain usable (issue #96 Defect B)."""
    _seed_experiment(db_session, "ADD_I96_A003", 960003)

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["ADD_I96_A003", None, None, None, None, "ONGOING", None, True]],
        ),
        "additives": (_ADD_HEADERS, [
            ["ADD_I96_A003", "Dup Compound I96", 5.0, "g", 1, "first insert"],
            ["ADD_I96_A003", "Dup Compound I96", 3.0, "g", 2, "duplicate - should fail"],
            ["ADD_I96_A003", "Other Compound I96", 2.0, "g", 3, "third row - must still land"],
        ]),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )
    assert errors == [], f"Unexpected top-level errors: {errors}"

    row_warnings = [w for w in warnings if w.startswith("[additives] Row 3:")]
    assert len(row_warnings) == 1, f"Expected exactly one warning for row 3, got: {warnings}"

    # Regression guard: the session must not be left in a rollback-pending state.
    count = db_session.query(Experiment).count()
    assert count >= 1

    additives = (
        db_session.query(ChemicalAdditive)
        .join(Compound)
        .filter(Compound.name.in_(["Dup Compound I96", "Other Compound I96"]))
        .all()
    )
    names = sorted(a.compound.name for a in additives)
    assert names == ["Dup Compound I96", "Other Compound I96"], (
        f"Expected exactly one surviving 'Dup Compound I96' additive plus 'Other Compound I96', got: {names}"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/bulk_uploads/test_new_experiments_additives.py -v`

Expected:
- `test_85_char_method_round_trips_intact` currently ERRORS (`StringDataRightTruncation` — the exact bug from issue #96 — surfaces as an unhandled `sqlalchemy.exc.DataError` since there's no savepoint to convert it into a caught warning yet, or the raw error propagates because `db.flush()` inside the loop's own `try/except Exception` catches it but then the session is poisoned for the assertion query below, raising `PendingRollbackError` when the test tries to query afterward).
- `test_method_over_max_length_is_truncated_with_warning` FAILS (no truncation logic exists yet; either raises `StringDataRightTruncation` too, since 600 > 50, or silently attempts an over-length insert).
- `test_duplicate_compound_row_failure_does_not_poison_other_rows` FAILS: the third row's additive is missing, and/or the query at the end raises `PendingRollbackError` (this is the exact defect from issue #96 — no savepoint isolation).

- [ ] **Step 3: Implement**

In `backend/services/bulk_uploads/new_experiments.py`, add to the existing `from database import (...)` block (or as a separate import line right after it):

```python
from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH
```

Replace the additives loop body (currently lines ~792–877, from `for ridx, row in group.iterrows():` through the final `except Exception as e: warnings.append(...)`) with:

```python
                    for ridx, row in group.iterrows():
                        # Per-row savepoint isolation (issue #96 Defect B, mirrors issue #86's
                        # experiments-sheet loop): a failed flush anywhere in this row's processing
                        # is confined to its own SAVEPOINT and rolled back, leaving the session
                        # usable for the remaining additive rows.
                        savepoint = db.begin_nested()
                        row_ok = False
                        try:
                            comp_name = str(row.get('compound') or '').strip()
                            if not comp_name:
                                skipped += 1
                                continue

                            # amount
                            try:
                                amount_val = float(row.get('amount'))
                            except Exception:
                                warnings.append(f"[additives] Row {int(ridx)+2}: invalid amount '{row.get('amount')}'")
                                continue
                            if amount_val <= 0:
                                warnings.append(f"[additives] Row {int(ridx)+2}: amount must be > 0")
                                continue

                            # unit
                            unit_text = str(row.get('unit') or '').strip()
                            unit_enum: Optional[AmountUnit] = None
                            for u in AmountUnit:
                                if unit_text == u.value:
                                    unit_enum = u
                                    break
                            if unit_enum is None:
                                warnings.append(f"[additives] Row {int(ridx)+2}: invalid unit '{unit_text}'")
                                continue

                            # Resolve or auto-create compound by name
                            comp = name_to_compound.get(comp_name.lower())
                            if not comp:
                                comp = Compound(name=comp_name)
                                db.add(comp)
                                db.flush()
                                name_to_compound[comp_name.lower()] = comp

                            # order and method
                            order_val = row.get('order') if 'order' in df_add.columns else None
                            try:
                                order_int = int(order_val) if order_val is not None and str(order_val).strip() != '' else None
                            except Exception:
                                order_int = None
                            method_text = str(row.get('method')).strip() if 'method' in df_add.columns and row.get('method') is not None and str(row.get('method')).strip() != '' else None
                            if method_text and len(method_text) > ADDITION_METHOD_MAX_LENGTH:
                                warnings.append(
                                    f"[additives] Row {int(ridx)+2}: method truncated to {ADDITION_METHOD_MAX_LENGTH} "
                                    f"characters (was {len(method_text)})"
                                )
                                method_text = method_text[:ADDITION_METHOD_MAX_LENGTH]

                            if replace_all:
                                # Always insert fresh records
                                new_add = ChemicalAdditive(
                                    experiment_id=conditions.id,
                                    compound_id=comp.id,
                                    amount=amount_val,
                                    unit=unit_enum,
                                    addition_order=order_int,
                                    addition_method=method_text,
                                )
                                db.add(new_add)
                                db.flush()
                                recalculate(new_add, db)
                            else:
                                # Upsert per-compound
                                existing_add = db.query(ChemicalAdditive).filter(
                                    ChemicalAdditive.experiment_id == conditions.id,
                                    ChemicalAdditive.compound_id == comp.id,
                                ).first()
                                if existing_add:
                                    # Update existing (could be from parent copy or previous upload)
                                    existing_add.amount = amount_val
                                    existing_add.unit = unit_enum
                                    existing_add.addition_order = order_int
                                    existing_add.addition_method = method_text
                                    db.flush()
                                    recalculate(existing_add, db)
                                else:
                                    # New additive from user sheet
                                    new_add = ChemicalAdditive(
                                        experiment_id=conditions.id,
                                        compound_id=comp.id,
                                        amount=amount_val,
                                        unit=unit_enum,
                                        addition_order=order_int,
                                        addition_method=method_text,
                                    )
                                    db.add(new_add)
                                    db.flush()
                                    recalculate(new_add, db)

                            # Row body completed without exception or early `continue`.
                            row_ok = True
                        except Exception as e:
                            warnings.append(f"[additives] Row {int(ridx)+2}: {e}")
                        finally:
                            if row_ok:
                                savepoint.commit()
                            else:
                                savepoint.rollback()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/bulk_uploads/test_new_experiments_additives.py -v`

Expected: all 3 tests PASS.

Also run the full existing suite for this file to confirm no regression:

Run: `pytest tests/services/bulk_uploads/test_new_experiments.py tests/services/bulk_uploads/test_new_experiments_rename_lineage.py -v`

Expected: all PASS (unchanged behavior for the experiments/conditions sheets).

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/new_experiments.py tests/services/bulk_uploads/test_new_experiments_additives.py
git commit -m "$(cat <<'EOF'
[#96] Isolate additive-row failures with savepoints

- Per-row db.begin_nested() in the additives phase (mirrors issue #86)
- Over-length method truncated with a warning instead of raising
- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 4: Savepoint isolation + truncate-with-warning in `experiment_additives.py`

**Files:**
- Modify: `backend/services/bulk_uploads/experiment_additives.py` (imports; loop body lines ~41–142)
- Test: `tests/services/bulk_uploads/test_experiment_additives.py` (new file)

**Interfaces:**
- Consumes: `database.models.chemicals.ADDITION_METHOD_MAX_LENGTH` (from Task 1).
- Produces: no new public names. `ExperimentAdditivesService.bulk_upsert_from_excel` keeps its existing signature/return shape `(created, updated, skipped, errors)` (this file has no separate `warnings` list — truncation notices go into `errors`, matching how this file already reports other non-fatal per-row issues like "invalid amount").

- [ ] **Step 1: Write the failing tests**

Create `tests/services/bulk_uploads/test_experiment_additives.py`:

```python
"""Tests for the savepoint isolation + method-length fixes in issue #96."""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import Experiment, ExperimentalConditions, Compound, ChemicalAdditive
from database.models.enums import ExperimentStatus
from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH
import backend.services.bulk_uploads.experiment_additives as ea_mod
from backend.services.bulk_uploads.experiment_additives import ExperimentAdditivesService

from .excel_helpers import make_excel

_HEADERS = ["experiment_id", "compound", "amount", "unit", "order", "method"]


def _seed_experiment_with_compounds(db: Session, exp_id: str, exp_num: int, compound_names: list[str]):
    exp = Experiment(experiment_id=exp_id, experiment_number=exp_num, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    compounds = {}
    for name in compound_names:
        c = Compound(name=name)
        db.add(c)
        db.flush()
        compounds[name] = c
    return exp, compounds


def test_85_char_method_round_trips_intact(db_session: Session):
    long_method = "11.8 mL master stock diluted to 20 mL total with DI water; no rock (background blank)"
    assert len(long_method) == 85
    exp, compounds = _seed_experiment_with_compounds(db_session, "EA_I96_001", 970001, ["Iron Oxide EA I96"])

    xlsx = make_excel(_HEADERS, [
        ["EA_I96_001", "Iron Oxide EA I96", 5.0, "g", 1, long_method],
    ])
    created, updated, skipped, errors = ExperimentAdditivesService.bulk_upsert_from_excel(db_session, xlsx)
    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    additive = db_session.query(ChemicalAdditive).filter_by(compound_id=compounds["Iron Oxide EA I96"].id).one()
    assert additive.addition_method == long_method


def test_method_over_max_length_is_truncated_with_warning(db_session: Session):
    exp, compounds = _seed_experiment_with_compounds(db_session, "EA_I96_002", 970002, ["Iron Oxide EA I96 B"])
    over_length = "z" * (ADDITION_METHOD_MAX_LENGTH + 50)

    xlsx = make_excel(_HEADERS, [
        ["EA_I96_002", "Iron Oxide EA I96 B", 5.0, "g", 1, over_length],
    ])
    created, updated, skipped, errors = ExperimentAdditivesService.bulk_upsert_from_excel(db_session, xlsx)
    assert any("truncated" in e and "Row 2" in e for e in errors), f"Expected a truncation notice, got: {errors}"
    assert created == 1

    additive = db_session.query(ChemicalAdditive).filter_by(compound_id=compounds["Iron Oxide EA I96 B"].id).one()
    assert len(additive.addition_method) == ADDITION_METHOD_MAX_LENGTH


def test_mid_row_failure_isolated_by_savepoint(db_session: Session, monkeypatch):
    """Simulate a post-write exception (e.g. a recalculation bug) on row 2 and verify it does not
    poison the session for row 3, and row 1 remains committed (issue #96 Defect B)."""
    exp, compounds = _seed_experiment_with_compounds(
        db_session, "EA_I96_003", 970003, ["Good Compound A", "Poison Compound", "Good Compound B"]
    )
    poison_id = compounds["Poison Compound"].id
    real_recalculate = ea_mod.recalculate

    def fake_recalculate(instance, session):
        if instance.compound_id == poison_id:
            raise ValueError("simulated recalculation failure")
        return real_recalculate(instance, session)

    monkeypatch.setattr(ea_mod, "recalculate", fake_recalculate)

    xlsx = make_excel(_HEADERS, [
        ["EA_I96_003", "Good Compound A", 5.0, "g", 1, "ok"],
        ["EA_I96_003", "Poison Compound", 3.0, "g", 2, "will fail"],
        ["EA_I96_003", "Good Compound B", 2.0, "g", 3, "must still land"],
    ])
    created, updated, skipped, errors = ExperimentAdditivesService.bulk_upsert_from_excel(db_session, xlsx)

    row_errors = [e for e in errors if e.startswith("Row 3:")]
    assert len(row_errors) == 1, f"Expected exactly one error for row 3 (the poisoned row), got: {errors}"
    assert created == 2, f"Expected rows 1 and 3 to still create additives, got created={created}"

    # Regression guard: the session must not be left in a rollback-pending state.
    surviving = (
        db_session.query(ChemicalAdditive)
        .filter(ChemicalAdditive.compound_id.in_([compounds["Good Compound A"].id, compounds["Good Compound B"].id]))
        .all()
    )
    assert len(surviving) == 2
    poisoned = db_session.query(ChemicalAdditive).filter_by(compound_id=poison_id).first()
    assert poisoned is None, "The poisoned row's insert must have been rolled back by its savepoint"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/bulk_uploads/test_experiment_additives.py -v`

Expected:
- `test_85_char_method_round_trips_intact` PASSES already if Task 1's migration has landed on the test DB (Text column has no length limit) — that's fine, it exists as a regression guard for this file specifically.
- `test_method_over_max_length_is_truncated_with_warning` FAILS: no truncation logic exists yet, so no `"truncated"` message appears in `errors`, and the stored value is the full 550-char string, not 500.
- `test_mid_row_failure_isolated_by_savepoint` FAILS: without a savepoint, `db.flush()` for row 2 raises inside the bare `try/except`, but the session's transaction is left poisoned; the subsequent query for row 3's success (or the loop continuing to process row 3 at all) raises `sqlalchemy.exc.PendingRollbackError`, and `created` will be less than 2.

- [ ] **Step 3: Implement**

In `backend/services/bulk_uploads/experiment_additives.py`, add the import (after the existing `from backend.services.calculations.registry import recalculate` line):

```python
from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH
```

Replace the `for idx, row in df.iterrows():` loop body (currently lines ~41–142) with:

```python
        for idx, row in df.iterrows():
            # Per-row savepoint isolation (issue #96 Defect B): a failed flush or recalculation
            # anywhere in this row's processing is confined to its own SAVEPOINT and rolled back,
            # leaving the session usable for the remaining rows.
            savepoint = db.begin_nested()
            row_ok = False
            try:
                exp_id = str(row.get('experiment_id') or '').strip()
                comp_name = str(row.get('compound') or '').strip()
                unit_val = str(row.get('unit') or '').strip()
                amount_val = row.get('amount')
                order_val = row.get('order') if 'order' in df.columns else None
                method_val = row.get('method') if 'method' in df.columns else None

                if not exp_id or not comp_name or not unit_val:
                    skipped += 1
                    continue

                try:
                    amount_float = float(amount_val)
                except Exception:
                    errors.append(f"Row {idx+2}: invalid amount '{amount_val}'")
                    continue
                if amount_float <= 0:
                    errors.append(f"Row {idx+2}: amount must be > 0")
                    continue

                # Validate unit
                unit_enum = None
                for u in AmountUnit:
                    if u.value == unit_val:
                        unit_enum = u
                        break
                if unit_enum is None:
                    errors.append(f"Row {idx+2}: invalid unit '{unit_val}'")
                    continue

                # Resolve experiment
                exp_id_norm = ''.join(ch for ch in exp_id.lower() if ch not in ['-', '_', ' '])
                experiment = db.query(Experiment).filter(
                    func.lower(
                        func.replace(
                            func.replace(
                                func.replace(Experiment.experiment_id, '-', ''),
                                '_', ''
                            ),
                            ' ', ''
                        )
                    ) == exp_id_norm
                ).first()
                if not experiment:
                    errors.append(f"Row {idx+2}: experiment_id '{exp_id}' not found")
                    continue

                # Resolve or create ExperimentalConditions for this experiment
                conditions = db.query(ExperimentalConditions).filter(ExperimentalConditions.experiment_fk == experiment.id).first()
                if not conditions:
                    conditions = ExperimentalConditions(
                        experiment_id=experiment.experiment_id,
                        experiment_fk=experiment.id,
                    )
                    db.add(conditions)
                    db.flush()

                # Resolve compound
                comp = name_to_compound.get(comp_name.lower())
                if not comp:
                    errors.append(f"Row {idx+2}: compound '{comp_name}' not found; upload inventory first")
                    continue

                # Upsert additive
                existing_add = db.query(ChemicalAdditive).filter(
                    ChemicalAdditive.experiment_id == conditions.id,
                    ChemicalAdditive.compound_id == comp.id,
                ).first()

                # Parse order int
                try:
                    order_int = int(order_val) if order_val is not None and str(order_val).strip() != '' else None
                except Exception:
                    order_int = None

                method_text = str(method_val).strip() if method_val is not None and str(method_val).strip() != '' else None
                if method_text and len(method_text) > ADDITION_METHOD_MAX_LENGTH:
                    errors.append(
                        f"Row {idx+2}: method truncated to {ADDITION_METHOD_MAX_LENGTH} characters (was {len(method_text)})"
                    )
                    method_text = method_text[:ADDITION_METHOD_MAX_LENGTH]

                if existing_add:
                    existing_add.amount = amount_float
                    existing_add.unit = unit_enum
                    existing_add.addition_order = order_int
                    existing_add.addition_method = method_text
                    db.flush()
                    recalculate(existing_add, db)
                    updated += 1
                else:
                    new_add = ChemicalAdditive(
                        experiment_id=conditions.id,
                        compound_id=comp.id,
                        amount=amount_float,
                        unit=unit_enum,
                        addition_order=order_int,
                        addition_method=method_text,
                    )
                    db.add(new_add)
                    db.flush()
                    recalculate(new_add, db)
                    created += 1

                # Row body completed without exception or early `continue`.
                row_ok = True
            except Exception as e:
                errors.append(f"Row {idx+2}: {e}")
            finally:
                if row_ok:
                    savepoint.commit()
                else:
                    savepoint.rollback()
```

Note: `recalculate` in this module's namespace must remain called as `recalculate(...)` (a bare module-level name, not `ea_mod.recalculate(...)`) so that `tests/services/bulk_uploads/test_experiment_additives.py`'s `monkeypatch.setattr(ea_mod, "recalculate", fake_recalculate)` can intercept it — this already matches the existing `from backend.services.calculations.registry import recalculate` import style in this file, so no change needed there.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/bulk_uploads/test_experiment_additives.py -v`

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/experiment_additives.py tests/services/bulk_uploads/test_experiment_additives.py
git commit -m "$(cat <<'EOF'
[#96] Isolate additive-row failures with savepoints

- Per-row db.begin_nested() in ExperimentAdditivesService (mirrors new_experiments.py)
- Over-length method truncated with a notice instead of raising
- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 5: Documentation sync

**Files:**
- Modify: `.claude/rules/MODELS.md` (`ChemicalAdditive` section)
- Modify: `backend/api/routers/bulk_uploads.py:812` (template INSTRUCTIONS sheet)

**Interfaces:**
- Consumes: nothing new — this task only updates prose/comments to reflect Tasks 1–4.
- Produces: nothing consumed by other tasks.

- [ ] **Step 1: Update `.claude/rules/MODELS.md`**

Find the `### \`ChemicalAdditive\`` section:

```markdown
### `ChemicalAdditive`
Join table linking `ExperimentalConditions` to `Compound` with specific quantities.
- **Keys**: `experiment_id` (FK to `experimental_conditions.id`), `compound_id` (FK to `compounds.id`); unique per (experiment, compound).
- **Fields**: `amount`, `unit` (AmountUnit enum: g, mg, mM, ppm, % of Rock, etc.), `addition_order`, `addition_method`, `purity`, `lot_number`, `supplier_lot`.
```

Replace the **Fields** bullet with:

```markdown
- **Fields**: `amount`, `unit` (AmountUnit enum: g, mg, mM, ppm, % of Rock, etc.), `addition_order`, `addition_method` (Text, free-text prep/addition description; app-layer bound of 500 chars enforced by `ADDITION_METHOD_MAX_LENGTH` in `database/models/chemicals.py` — the DB column itself is unbounded, per issue #96), `purity`, `lot_number`, `supplier_lot`.
```

- [ ] **Step 2: Update the template INSTRUCTIONS sheet text**

In `backend/api/routers/bulk_uploads.py`, find line ~812:

```python
            ("method", "Free-text addition method description (optional)."),
```

Replace with:

```python
            ("method", f"Free-text addition method description (optional, max {ADDITION_METHOD_MAX_LENGTH} characters — longer values are truncated with a warning)."),
```

This requires `ADDITION_METHOD_MAX_LENGTH` to be imported in `backend/api/routers/bulk_uploads.py` — check the existing import block near the top of the file and add:

```python
from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH
```

- [ ] **Step 3: Verify the docs sync hook fired**

`.claude/rules/MODELS.md` is not under `docs/`, so the `sync_docs_to_project_context.py` hook does not apply to it — no action needed there. Confirm `backend/api/routers/bulk_uploads.py` is also outside `docs/`, so no `docs/project_context/` copy is expected for this task either.

- [ ] **Step 4: Manually verify the template renders correctly**

Run (from project root, with the FastAPI server already running per `backend/CLAUDE.md` — do not start/stop it):
```bash
curl -s http://localhost:8000/api/bulk-uploads/new-experiments/template -o /tmp/template.xlsx 2>&1 | head -5
```
If the server isn't reachable, skip this step and note it in the final report — do not attempt to start the server yourself (per `backend/CLAUDE.md` "Server Management").

- [ ] **Step 5: Commit**

```bash
git add ".claude/rules/MODELS.md" backend/api/routers/bulk_uploads.py
git commit -m "$(cat <<'EOF'
[#96] Document addition_method Text widening

- MODELS.md and template INSTRUCTIONS reflect the new 500-char app-layer bound
- Tests added: no
- Docs updated: yes
EOF
)"
```

---

## Final Validation (after all tasks)

- [ ] Run the full relevant test suite: `pytest tests/models/test_addition_method_column.py tests/api/test_schemas.py tests/api/test_additives.py tests/services/bulk_uploads/ -v`
- [ ] Confirm `alembic current` reports `293d0ea59422 (head)` against both the dev DB and (via `DATABASE_URL=...experiments_test`) the test DB.
- [ ] Re-read the issue #96 Acceptance Criteria list and confirm each is satisfied by the tasks above before running `/complete-task`.
