# Reactor Slot Identity — Issue #97 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store the reactor slot label (`R01` / `CF02`) as a column instead of re-deriving it from `(reactor_number, experiment_type)` at read time, then key every occupancy comparison, label render and write-path gate on that one column — so a Core Flood going ONGOING can no longer silently auto-complete the HPHT that shares its number.

**Architecture:** One new nullable column `experimental_conditions.reactor_slot`, populated by a single SQLAlchemy `before_insert`/`before_update` listener that calls one shared deriver in `database/reactor_slot.py`. The deriver returns `None` for any experiment type that does not bear physical reactor occupancy (Serum, Autoclave, Other) and for `reactor_number <= 0`, which makes the eligibility gate *structural*: an occupancy query filtered on `reactor_slot` cannot see a Serum vial, whether or not the calling code remembered to check. Four query sites, three label-render sites and three write paths then move onto the column.

**Tech Stack:** SQLAlchemy 2.x ORM + Alembic (PostgreSQL), FastAPI + Pydantic v2, pytest, React 18 + TanStack Query + Vitest.

## Global Constraints

- **Branch:** `fix/issue-97-reactor-slot-identity`, already created off `develop`. PRs use `--base develop`.
- **Commit format:** `[#97] <imperative description>` — under 50 chars, no trailing period, then `- Tests added: yes/no` / `- Docs updated: yes/no` lines.
- **Alembic head to branch from:** `293d0ea59422` (`widen addition method to text`). The issue text says `daae92e908f1`; that is two months stale. Verify with `.venv/Scripts/alembic heads` before writing the migration.
- **Locked components — sign-off obtained from Mat 2026-07-29 for exactly these:** `database/models/conditions.py` (add one column + comment), `backend/services/bulk_uploads/experiment_status.py`, `backend/services/bulk_uploads/new_experiments.py`. No field is renamed or removed anywhere. Do not touch any other locked file.
- **Migration must be purely additive** and must implement both `upgrade()` and `downgrade()`. `update.ps1` runs `alembic upgrade head` on the lab PC nightly — a migration that can fail against live data breaks the deploy pipeline. `reactor_slot` + its backfill cannot fail; that is why the uniqueness trigger is out of scope (see below).
- **Occupancy-bearing types are HPHT and Core Flood only** — decided by Mat 2026-07-29. Autoclave is *not* occupancy-bearing, despite `AUTO_JW_022`–`024` carrying historical reactor numbers 1,2,3,5,6,7 (all COMPLETED, all inert once the eligibility gate lands).
- **Python venv prefix:** commands are `.venv/Scripts/pytest`, `.venv/Scripts/alembic`, `.venv/Scripts/python`. Bare `alembic` / `pytest` are not on PATH.
- **Never start, stop or restart uvicorn.** Assume it is running on port 8000.
- **Test-DB hazard (from prior sessions):** `tests/api/conftest.py`'s `db_session` binds to a connection with an outer transaction already open. A router `db.commit()` consumes it, so rows genuinely land in `experiments_test` and leak across files (this is what broke `test_list_experiments_empty` during #100). Any new API test whose endpoint commits must clean up its own rows in a fixture.

### Explicitly NOT in this plan

Recorded here so no implementer adds them opportunistically:

- **The PL/pgSQL uniqueness trigger and `CHECK (reactor_number IS NULL OR reactor_number > 0)`** (issue §4). Blocked: the prerequisite cleanup has not run. `database/data_migrations/018*` does not exist. Task 9 files the follow-up issue (now **GitHub #112**).
  - **Corrected 2026-07-30, measured against the stored `reactor_slot` column:** the dev DB has **4** double-booked slots — `CF01`×6, `CF03`×5, `R01`×6, `R06`×2 — and **13** rows with `reactor_number = 0`. Prod had 2 slots and 11 zeros as of 2026-07-28.
  - **`R00` is NOT a double-booked slot**, though the 2026-07-28 audit listed it as one. Those eight `SERUM_JW_153`–`160` rows carry `reactor_number = 0`, so `derive_reactor_slot` returns `None` and their `reactor_slot` is NULL — they form no slot at all. This branch already made that class inert for occupancy. The audit's figure came from the pre-#97 re-derived `CASE`, which rendered zero as `"R00"`.
  - The two prerequisites are **separate**: the 4 genuine collisions block the trigger; the 13 zero-rows block only the `CHECK`.
- **Passing `newer_than` on the new-experiments upload path** (the second bullet of issue §3). This one follows from the split and is the plan's one deliberate deviation from the issue text — see the rationale in Task 5. Short version: the issue's own justification for passing it is "let the trigger be the backstop", and there is no trigger in this pass, so failing open would *create* silent double-bookings rather than surface them.
- **Deleting the `seen_labels` dedup at `dashboard.py:126-140`.** The issue says do it last, after the constraint is verified. There is no constraint in this pass, so the dedup stays and `_occupancy` keeps under-counting double-booked slots by one. Recorded in the follow-up issue.
- **The frontend "R01 is occupied by HPHT_222 — complete it and start HPHT_230?" confirm dialog.** Deferred by the issue itself. Task 8 only makes the 409 *visible*; today both status mutations swallow errors entirely.
- **Normalizing `experiment_type`** (`SERUM` → `Serum` etc.) and the case-insensitive Serum-KPI fix. Tracked in `docs/issues/issue-experiment-type-enum-binding.md`. This plan tolerates every spelling currently in prod instead.
- **Removing `reactor_number`.** Power BI views, `database/data_migrations/swap_reactor_4_7_015.py`, `database/event_listeners.py` and the `GET /api/experiments?reactor_number=` filter all read it. The reactors-table ticket's job.

---

## File Structure

| File | Responsibility |
|---|---|
| `database/reactor_slot.py` **(new)** | The *only* place slot identity is defined: type→series mapping, `derive_reactor_slot`, `canonical_slot_label`, `is_occupancy_type`. Zero imports from `backend/` or `database.models` so anything can import it. |
| `database/models/conditions.py` | Adds the `reactor_slot` column + a loud comment pointing at the deriver and the listener. Storage only. |
| `alembic/versions/<rev>_add_reactor_slot_to_conditions.py` **(new)** | Adds column + index, backfills in SQL mirroring the Python deriver. |
| `database/event_listeners.py` | One `before_insert`/`before_update` hook keeping `reactor_slot` in sync on every ORM write. |
| `backend/api/schemas/conditions.py` | Exposes `reactor_slot` read-only on `ConditionsResponse` (never accepted on create/update — it is derived). |
| `backend/services/bulk_uploads/experiment_status.py` | Occupant queries and the same-file conflict map move onto `reactor_slot`; messages name the slot. |
| `backend/services/bulk_uploads/new_experiments.py` | Both occupancy call sites gain the eligibility gate, `is not None`, and `newer_than`. |
| `backend/api/routers/experiments.py` | `PATCH /{id}/status` returns 409 instead of silently double-booking. |
| `backend/api/routers/dashboard.py` | Both label-render sites read the column; queries filter on `reactor_slot IS NOT NULL`. |
| `backend/services/notion_sync/import_.py` | `_resolve_experiment_id` matches the column; the NULL-unsafe `!=` branch is deleted. |
| `backend/services/notion_sync/export.py` | `_reactor_label_for` becomes a column read. |
| `frontend/src/pages/ReactorGrid.tsx`, `frontend/src/pages/ExperimentList.tsx` | Surface the 409 in a toast. Both mutations currently have no `onError` at all. |

Tests land beside their subject: `tests/test_reactor_slot.py`, `tests/models/test_reactor_slot_column.py`, `tests/services/bulk_uploads/test_experiment_status.py`, `tests/services/bulk_uploads/test_new_experiments.py`, `tests/api/test_experiments.py`, `tests/api/test_conditions.py`, `tests/api/test_dashboard.py`, `tests/services/test_notion_sync_import.py`, `frontend/src/pages/__tests__/*.test.tsx`.

---

## Task 1: The slot deriver — one source of truth

**Files:**
- Create: `database/reactor_slot.py`
- Test: `tests/test_reactor_slot.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `normalize_experiment_type(experiment_type: object | None) -> str` — lowercased, whitespace-collapsed; tolerates enum instances via `.value`.
  - `series_prefix(experiment_type: object | None) -> str | None` — `"R"`, `"CF"`, or `None`.
  - `is_occupancy_type(experiment_type: object | None) -> bool`
  - `derive_reactor_slot(reactor_number: object | None, experiment_type: object | None) -> str | None` — `object` not `int`, because pandas hands the parsers numpy floats and the conditions sheet can hand over strings
  - `canonical_slot_label(label: str | None) -> str | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_reactor_slot.py`:

```python
"""Unit tests for database/reactor_slot.py — the single definition of slot identity.

Slot identity is a (series, number) pair rendered as one canonical string.
Only HPHT and Core Flood bear physical reactor occupancy (decided 2026-07-29);
every other type derives to None, which is what makes the eligibility gate
structural rather than remembered. See issue #97.
"""
from __future__ import annotations

import pytest

from database.reactor_slot import (
    canonical_slot_label,
    derive_reactor_slot,
    is_occupancy_type,
    normalize_experiment_type,
    series_prefix,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("HPHT", "hpht"),
        ("  HPHT ", "hpht"),
        ("Core  Flood", "core flood"),
        ("SERUM", "serum"),
        (None, ""),
        ("", ""),
    ],
)
def test_normalize_experiment_type(raw, expected):
    assert normalize_experiment_type(raw) == expected


def test_normalize_experiment_type_accepts_enum_instance():
    """experiment_type is a String column, but enum instances reach these helpers
    from the parsers (parse_exp_id_validation returns ExperimentType)."""
    from database.models.enums import ExperimentType

    assert normalize_experiment_type(ExperimentType.HPHT) == "hpht"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("HPHT", "R"),
        ("hpht", "R"),
        ("Core Flood", "CF"),
        ("CORE FLOOD", "CF"),
        ("CoreFlood", "CF"),
        ("CF", "CF"),          # 1 prod row uses this spelling
        ("Serum", None),
        ("SERUM", None),
        ("Autoclave", None),   # decided 2026-07-29: not occupancy-bearing
        ("AUTO", None),
        ("Other", None),
        (None, None),
    ],
)
def test_series_prefix(raw, expected):
    assert series_prefix(raw) == expected


def test_is_occupancy_type_mirrors_series_prefix():
    assert is_occupancy_type("HPHT") is True
    assert is_occupancy_type("Core Flood") is True
    assert is_occupancy_type("Serum") is False
    assert is_occupancy_type(None) is False


@pytest.mark.parametrize(
    "number,etype,expected",
    [
        (1, "HPHT", "R01"),
        (16, "HPHT", "R16"),
        (1, "Core Flood", "CF01"),
        (3, "CF", "CF03"),
        (1, "SERUM", None),        # non-occupancy type gets no slot
        (3, "Autoclave", None),
        (None, "HPHT", None),      # no number, no slot
        (0, "HPHT", None),         # zero is not a slot — this is the R00 defect
        (-2, "HPHT", None),
        (1, None, None),           # unknown type cannot be placed in a series
    ],
)
def test_derive_reactor_slot(number, etype, expected):
    assert derive_reactor_slot(number, etype) == expected


def test_derive_reactor_slot_tolerates_float_and_string_numbers():
    """pandas hands parsers numpy floats; the conditions sheet can hand over strings."""
    assert derive_reactor_slot(5.0, "HPHT") == "R05"
    assert derive_reactor_slot("7", "HPHT") == "R07"
    assert derive_reactor_slot("not a number", "HPHT") is None


@pytest.mark.parametrize(
    "label,expected",
    [
        ("R01", "R01"),
        ("R1", "R01"),        # Notion labels are not guaranteed zero-padded
        ("r5", "R05"),
        ("CF1", "CF01"),
        ("cf03", "CF03"),
        ("R00", None),        # zero is not a slot
        ("X01", None),
        ("R", None),
        ("", None),
        (None, None),
    ],
)
def test_canonical_slot_label(label, expected):
    assert canonical_slot_label(label) == expected
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_reactor_slot.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'database.reactor_slot'`.

- [ ] **Step 3: Write the implementation**

Create `database/reactor_slot.py`:

```python
"""Canonical reactor slot identity.

A physical reactor slot is a *pair*: the series (HPHT vessel vs. Core Flood rig)
and the number within it. `R01` and `CF01` are two different pieces of hardware
that happen to share the number 1. Before issue #97 that label was re-derived
from `(reactor_number, experiment_type == "Core Flood")` in three separate
places, and every occupancy query keyed on the bare integer — so setting a Core
Flood to ONGOING could auto-complete the HPHT sitting in R01.

This module is the ONLY definition of that mapping. It is imported by:
  - database/event_listeners.py  (keeps experimental_conditions.reactor_slot current)
  - backend/services/bulk_uploads/experiment_status.py
  - backend/services/bulk_uploads/new_experiments.py
  - backend/api/routers/experiments.py, dashboard.py
  - backend/services/notion_sync/import_.py

It deliberately imports nothing from `database.models` or `backend` so any layer
can use it. The Alembic backfill in
`alembic/versions/<rev>_add_reactor_slot_to_conditions.py` re-expresses these
rules in SQL; `tests/models/test_reactor_slot_column.py` pins the two together.

`derive_reactor_slot` returns None for anything that does not occupy a physical
slot. That is load-bearing: an occupancy query filtered on `reactor_slot` cannot
see a Serum vial even if the calling code forgot to check the type.
"""
from __future__ import annotations

import re

# Occupancy-bearing types only. Autoclave is deliberately absent — decided
# 2026-07-29 after the audit found AUTO_JW_022-024 carrying historical HPHT
# vessel numbers (all COMPLETED, so inert). If the team later confirms autoclave
# runs occupy the numbered vessels, add "autoclave": "R" here and to the
# dashboard's experiment_type filters; nothing else needs to change.
#
# Keys are the output of normalize_experiment_type, so every casing variant in
# production data (`SERUM`, `CF`, `Core  Flood`) resolves through one lookup.
_SERIES_BY_TYPE: dict[str, str] = {
    "hpht": "R",
    "core flood": "CF",
    "coreflood": "CF",
    "cf": "CF",
}

_SLOT_LABEL_RE = re.compile(r"(CF|R)0*(\d+)", re.IGNORECASE)


def normalize_experiment_type(experiment_type: object | None) -> str:
    """Lowercase + collapse whitespace so 'HPHT ', 'Core  Flood', 'SERUM' compare cleanly.

    Tolerates enum instances as well as strings: `experiment_type` is a String
    column, but the ID parser hands back `ExperimentType` members.
    """
    if experiment_type is None:
        return ""
    raw = experiment_type.value if hasattr(experiment_type, "value") else str(experiment_type)
    return " ".join(raw.strip().lower().split())


def series_prefix(experiment_type: object | None) -> str | None:
    """Return the slot-label prefix ('R' or 'CF') for a type, or None if it holds no slot."""
    return _SERIES_BY_TYPE.get(normalize_experiment_type(experiment_type))


def is_occupancy_type(experiment_type: object | None) -> bool:
    """True for HPHT / Core Flood — the types with physical reactor occupancy."""
    return series_prefix(experiment_type) is not None


def _format_slot(prefix: str, number: int) -> str | None:
    """Render a canonical slot label, or None if the number is not a slot.

    Zero and negatives are rejected here rather than at each call site so the
    guard and the padding width live in one place.
    """
    if number <= 0:
        return None
    return f"{prefix}{number:02d}"


def derive_reactor_slot(
    reactor_number: object | None,
    experiment_type: object | None,
) -> str | None:
    """Build the canonical slot label, or None when there is no slot.

    None is returned when: the type is not occupancy-bearing, the number is
    missing or unparseable, or the number is <= 0. Zero is not a slot — the eight
    `R00` rows in the 2026-07-28 prod audit exist only because `0` is falsy in
    Python and slipped past `if conditions.reactor_number`.
    """
    prefix = series_prefix(experiment_type)
    if prefix is None:
        return None
    if reactor_number is None:
        return None
    try:
        number = int(reactor_number)
    except (TypeError, ValueError):
        return None
    return _format_slot(prefix, number)


def canonical_slot_label(label: str | None) -> str | None:
    """Normalize an externally supplied label ('r5', 'CF1') to canonical form ('R05', 'CF01').

    Used on the Notion sync path, where the reactor label comes from a Notion
    page title and is not guaranteed to be zero-padded or upper-cased.
    """
    if not label:
        return None
    match = _SLOT_LABEL_RE.fullmatch(label.strip())
    if match is None:
        return None
    return _format_slot(match.group(1).upper(), int(match.group(2)))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_reactor_slot.py -q`
Expected: all pass. The parametrized cases expand to 41 test items.

- [ ] **Step 5: Commit**

```bash
git add database/reactor_slot.py tests/test_reactor_slot.py
git commit -m "[#97] Add canonical reactor slot deriver

- One definition of (series, number) slot identity
- Tests added: yes
- Docs updated: no"
```

---

## Task 2: The `reactor_slot` column and its backfill

**Files:**
- Modify: `database/models/conditions.py:18` (insert after `reactor_number`)
- Create: `alembic/versions/<generated_rev>_add_reactor_slot_to_conditions.py`
- Test: `tests/models/test_reactor_slot_column.py`

**Interfaces:**
- Consumes: `database.reactor_slot.derive_reactor_slot` (Task 1), for the SQL-vs-Python parity test only.
- Produces: `ExperimentalConditions.reactor_slot` — `String(8)`, nullable, indexed as `ix_experimental_conditions_reactor_slot`.

- [ ] **Step 1: Add the column to the model**

In `database/models/conditions.py`, replace line 18:

```python
    reactor_number = Column(Integer, nullable=True)
```

with:

```python
    reactor_number = Column(Integer, nullable=True)
    # Canonical physical slot label — 'R01'..'R16' (HPHT vessels) or 'CF01'..'CF03'
    # (Core Flood rigs). NULL whenever the experiment holds no physical slot:
    # a non-occupancy type (Serum / Autoclave / Other), a missing reactor_number,
    # or reactor_number <= 0.
    #
    # DO NOT SET THIS BY HAND. It is derived from (reactor_number,
    # experiment_type) by database.reactor_slot.derive_reactor_slot and written
    # on every ORM write by the before_insert/before_update listener
    # `set_reactor_slot` in database/event_listeners.py. Assigning it directly
    # will be silently overwritten on the next flush.
    #
    # This is the key for every occupancy comparison (issue #97). Reading
    # reactor_number alone conflates R01 with CF01 — two different vessels that
    # share the number 1 — which is how a Core Flood going ONGOING could
    # auto-complete a running HPHT.
    reactor_slot = Column(String(8), nullable=True, index=True)
```

- [ ] **Step 2: Write the failing test**

Create `tests/models/test_reactor_slot_column.py`:

```python
"""Column-level tests for experimental_conditions.reactor_slot (issue #97).

The parity test is the important one: the Alembic backfill re-expresses
derive_reactor_slot's rules in SQL, and nothing but a test stops the two from
drifting.
"""
from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from database.models import ExperimentalConditions
from database.models.enums import ExperimentStatus
from database.models.experiments import Experiment
from database.reactor_slot import derive_reactor_slot


def test_reactor_slot_column_exists_and_is_indexed(db_session: Session):
    insp = inspect(db_session.get_bind())
    cols = {c["name"]: c for c in insp.get_columns("experimental_conditions")}
    assert "reactor_slot" in cols
    assert cols["reactor_slot"]["nullable"] is True
    indexed = {
        col
        for ix in insp.get_indexes("experimental_conditions")
        for col in ix["column_names"]
    }
    assert "reactor_slot" in indexed


# The SQL expression below must stay character-identical to the one in the
# Alembic migration's upgrade(). If you change one, change both and this test
# will tell you if they disagree.
_BACKFILL_SQL = """
SELECT CASE
    WHEN lower(btrim(regexp_replace(coalesce(:etype, ''), '\\s+', ' ', 'g')))
         IN ('core flood', 'coreflood', 'cf')
        THEN 'CF' || lpad((:rnum)::int::text, 2, '0')
    WHEN lower(btrim(regexp_replace(coalesce(:etype, ''), '\\s+', ' ', 'g')))
         = 'hpht'
        THEN 'R' || lpad((:rnum)::int::text, 2, '0')
    ELSE NULL
END AS slot
"""


@pytest.mark.parametrize(
    "rnum,etype",
    [
        (1, "HPHT"),
        (16, "HPHT"),
        (1, "Core Flood"),
        (3, "CF"),
        (2, "CoreFlood"),
        (4, "Core  Flood"),
        (5, "SERUM"),
        (6, "Serum"),
        (7, "Autoclave"),
        (8, "AUTO"),
        (9, "Other"),
        (10, None),
    ],
)
def test_backfill_sql_matches_python_deriver(db_session: Session, rnum, etype):
    """The migration's SQL CASE and derive_reactor_slot must agree on every
    experiment_type spelling present in production data."""
    sql_result = db_session.execute(
        text(_BACKFILL_SQL), {"etype": etype, "rnum": rnum}
    ).scalar_one()
    assert sql_result == derive_reactor_slot(rnum, etype)


def test_zero_and_null_reactor_numbers_are_excluded_by_the_backfill_predicate():
    """The migration's WHERE clause is `reactor_number IS NOT NULL AND reactor_number > 0`,
    so the SQL CASE is never evaluated for those rows. Python must return None for
    them too, which is what makes the two equivalent overall."""
    assert derive_reactor_slot(0, "HPHT") is None
    assert derive_reactor_slot(None, "HPHT") is None


def test_column_accepts_and_returns_a_slot_value(db_session: Session):
    """Storage-level round trip only. Nothing populates reactor_slot yet — the
    listener that derives it lands in Task 3 — so this writes the value directly
    to prove the column persists a string of the expected width.
    """
    exp = Experiment(
        experiment_id="HPHT_SLOT_001",
        experiment_number=97001,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id=exp.experiment_id,
        experiment_type="HPHT",
        reactor_number=4,
    )
    cond.reactor_slot = "R04"
    db_session.add(cond)
    db_session.flush()
    db_session.expire(cond)
    assert cond.reactor_slot == "R04"
```

**This task must end with every test in the file passing.** The derivation tests
belong to Task 3, which adds the listener; do not write them here.

- [ ] **Step 3: Run the test to verify it fails**

Run: `.venv/Scripts/pytest tests/models/test_reactor_slot_column.py -q`
Expected: `test_reactor_slot_column_exists_and_is_indexed` FAILS with `assert 'reactor_slot' in cols` if you have not yet recreated the test schema. The test DB is built by `Base.metadata.create_all`, so the column appears as soon as the model change above is saved and the schema is rebuilt. If the test DB already has a stale `experimental_conditions`, drop and recreate it:

```bash
.venv/Scripts/python -c "from database import Base, engine; Base.metadata.create_all(engine)"
```

(`create_all` does not add columns to existing tables — if `reactor_slot` is missing after this, the `experiments_test` table predates the change and needs the Alembic upgrade below or a manual `ALTER TABLE`.)

- [ ] **Step 4: Generate and write the migration**

```bash
.venv/Scripts/alembic revision -m "add reactor_slot to conditions"
```

Then replace the generated file's body so it reads exactly:

```python
"""add reactor_slot to conditions

Revision ID: <keep generated>
Revises: 293d0ea59422
Create Date: <keep generated>

Issue #97. Stores the canonical physical slot label so occupancy comparisons stop
keying on the bare `reactor_number`, which conflates R01 (HPHT vessel 1) with CF01
(Core Flood rig 1).

Purely additive: one nullable column, one index, one UPDATE. It cannot fail against
production data, which matters because update.ps1 runs `alembic upgrade head` on the
lab PC nightly. The one-ONGOING-per-slot trigger and the
`CHECK (reactor_number > 0)` from the issue's §4 are deliberately NOT here — both
fail against current data until the cleanup in
docs/issues/audit-2026-07-28-results-and-cleanup.md has run.

The CASE below re-expresses database/reactor_slot.py::derive_reactor_slot in SQL.
tests/models/test_reactor_slot_column.py pins the two together over every
experiment_type spelling found in prod (`HPHT`, `Serum`, `SERUM`, `Autoclave`,
`Core Flood`, `Other`, `OTHER`, `AUTO`, `AUTOCLAVE`, `CF`). Rows with a
non-occupancy type, or reactor_number <= 0, are left NULL on purpose: NULL means
"holds no physical slot", which is what makes every downstream occupancy query
type-safe by construction.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '<keep generated>'
down_revision: Union[str, None] = '293d0ea59422'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BACKFILL = """
UPDATE experimental_conditions
SET reactor_slot = CASE
    WHEN lower(btrim(regexp_replace(coalesce(experiment_type, ''), '\\s+', ' ', 'g')))
         IN ('core flood', 'coreflood', 'cf')
        THEN 'CF' || lpad(reactor_number::text, GREATEST(2, length(reactor_number::text)), '0')
    WHEN lower(btrim(regexp_replace(coalesce(experiment_type, ''), '\\s+', ' ', 'g')))
         = 'hpht'
        THEN 'R' || lpad(reactor_number::text, GREATEST(2, length(reactor_number::text)), '0')
    ELSE NULL
END
WHERE reactor_number IS NOT NULL
  AND reactor_number > 0
"""


def upgrade() -> None:
    op.add_column(
        'experimental_conditions',
        sa.Column('reactor_slot', sa.String(length=8), nullable=True),
    )
    op.create_index(
        'ix_experimental_conditions_reactor_slot',
        'experimental_conditions',
        ['reactor_slot'],
    )
    op.execute(BACKFILL)


def downgrade() -> None:
    op.drop_index(
        'ix_experimental_conditions_reactor_slot',
        table_name='experimental_conditions',
    )
    op.drop_column('experimental_conditions', 'reactor_slot')
```

- [ ] **Step 5: Apply the migration and verify both directions**

```bash
.venv/Scripts/alembic upgrade head
.venv/Scripts/alembic downgrade -1
.venv/Scripts/alembic upgrade head
```

Expected: all three succeed with no error. Then confirm the backfill did real work on the dev DB:

```bash
.venv/Scripts/python -c "
from database import engine
from sqlalchemy import text
with engine.connect() as c:
    print('slot counts:', c.execute(text(
        'SELECT reactor_slot, count(*) FROM experimental_conditions '
        'GROUP BY 1 ORDER BY 1 NULLS LAST'
    )).fetchall())
    print('occupancy-type rows still NULL (must be 0):', c.execute(text(
        \"SELECT count(*) FROM experimental_conditions \"
        \"WHERE reactor_number > 0 AND reactor_slot IS NULL \"
        \"AND lower(experiment_type) IN ('hpht','core flood','cf')\"
    )).scalar())
"
```

Expected: a spread of `R01`..`R16` / `CF01`..`CF03` plus a large NULL bucket, and **0** occupancy-type rows left NULL. The 13 `reactor_number = 0` rows and every Serum/Autoclave/Other row are expected to be NULL.

Run the tests: `.venv/Scripts/pytest tests/models/test_reactor_slot_column.py -q`
Expected: **all pass.** Do not leave this task with a failing test.

- [ ] **Step 6: Commit**

```bash
git add database/models/conditions.py alembic/versions/ tests/models/test_reactor_slot_column.py
git commit -m "[#97] Add reactor_slot column and backfill

- Additive migration off 293d0ea59422; no trigger, no CHECK
- Tests added: yes
- Docs updated: no"
```

---

## Task 3: Keep `reactor_slot` current on every ORM write

**Files:**
- Modify: `database/event_listeners.py:4` (import) and append after `calculate_additive_derived_values` (line 682)
- Modify: `backend/api/schemas/conditions.py:60-91` (`ConditionsResponse`)
- Test: `tests/models/test_reactor_slot_column.py` (extend), `tests/api/test_conditions.py` (extend)

**Interfaces:**
- Consumes: `database.reactor_slot.derive_reactor_slot` (Task 1); `ExperimentalConditions.reactor_slot` (Task 2).
- Produces: `database.event_listeners.set_reactor_slot(mapper, connection, target)`. After this task, **every** ORM write to `ExperimentalConditions` — both bulk parsers, the conditions router, the legacy Streamlit app, the `database/data_migrations/` scripts — maintains `reactor_slot` without the calling code knowing it exists.

**Rule every later task must follow:** the listener fires *during* flush. Code that needs "the slot for these values right now", before a flush, must call `derive_reactor_slot(...)` rather than reading `cond.reactor_slot`, which may still hold the pre-change value. Only read `.reactor_slot` off rows loaded from the DB. Production `SessionLocal` has `autoflush=False`, so this is not theoretical.

- [ ] **Step 1: Write the failing tests**

Append to `tests/models/test_reactor_slot_column.py`:

```python
def test_listener_recomputes_slot_when_reactor_number_changes(db_session: Session):
    exp = Experiment(
        experiment_id="HPHT_SLOT_002",
        experiment_number=97002,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id=exp.experiment_id,
        experiment_type="HPHT",
        reactor_number=4,
    )
    db_session.add(cond)
    db_session.flush()
    assert cond.reactor_slot == "R04"

    cond.reactor_number = 9
    db_session.flush()
    db_session.refresh(cond)
    assert cond.reactor_slot == "R09"


def test_listener_recomputes_slot_when_experiment_type_changes(db_session: Session):
    """Changing HPHT -> Core Flood moves the row from R02 to CF02 — a different vessel."""
    exp = Experiment(
        experiment_id="HPHT_SLOT_003",
        experiment_number=97003,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id=exp.experiment_id,
        experiment_type="HPHT",
        reactor_number=2,
    )
    db_session.add(cond)
    db_session.flush()
    assert cond.reactor_slot == "R02"

    cond.experiment_type = "Core Flood"
    db_session.flush()
    db_session.refresh(cond)
    assert cond.reactor_slot == "CF02"


def test_listener_nulls_slot_for_non_occupancy_type(db_session: Session):
    """A Serum vial carrying a stray reactor_number holds no slot. This is the
    structural half of the eligibility gate — the eight R00 SERUM_JW vials in the
    2026-07-28 prod audit become invisible to every occupancy query."""
    exp = Experiment(
        experiment_id="SERUM_SLOT_004",
        experiment_number=97004,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id=exp.experiment_id,
        experiment_type="Serum",
        reactor_number=3,
    )
    db_session.add(cond)
    db_session.flush()
    db_session.refresh(cond)
    assert cond.reactor_slot is None


def test_listener_overwrites_a_hand_assigned_slot(db_session: Session):
    """The column is derived. Assigning it directly must not stick — the model
    comment says so and this is what enforces it."""
    exp = Experiment(
        experiment_id="HPHT_SLOT_005",
        experiment_number=97005,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id=exp.experiment_id,
        experiment_type="HPHT",
        reactor_number=6,
        reactor_slot="CF99",
    )
    db_session.add(cond)
    db_session.flush()
    db_session.refresh(cond)
    assert cond.reactor_slot == "R06"
```

Append to `tests/api/test_conditions.py`:

```python
def test_conditions_response_exposes_reactor_slot(client, db_session):
    """The API surfaces the derived slot so the frontend never re-derives the label."""
    exp = _make_experiment(db_session, "COND_SLOT_001", 97101)
    payload = {
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "experiment_type": "Core Flood",
        "reactor_number": 2,
    }
    resp = client.post("/api/conditions", json=payload)
    assert resp.status_code == 201
    assert resp.json()["reactor_slot"] == "CF02"


def test_conditions_patch_recomputes_reactor_slot(client, db_session):
    exp = _make_experiment(db_session, "COND_SLOT_002", 97102)
    created = client.post(
        "/api/conditions",
        json={
            "experiment_fk": exp.id,
            "experiment_id": exp.experiment_id,
            "experiment_type": "HPHT",
            "reactor_number": 1,
        },
    ).json()
    assert created["reactor_slot"] == "R01"

    resp = client.patch(f"/api/conditions/{created['id']}", json={"reactor_number": 12})
    assert resp.status_code == 200
    assert resp.json()["reactor_slot"] == "R12"


def test_conditions_create_ignores_a_client_supplied_reactor_slot(client, db_session):
    """reactor_slot is not on ConditionsCreate, so an extra key is dropped by
    Pydantic and the derived value wins."""
    exp = _make_experiment(db_session, "COND_SLOT_003", 97103)
    resp = client.post(
        "/api/conditions",
        json={
            "experiment_fk": exp.id,
            "experiment_id": exp.experiment_id,
            "experiment_type": "HPHT",
            "reactor_number": 3,
            "reactor_slot": "CF01",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["reactor_slot"] == "R03"
```

These three API tests let the router commit, so they leak rows per the Global
Constraints hazard. Add this autouse fixture at the top of `tests/api/test_conditions.py`
(after the imports):

```python
@pytest.fixture(autouse=True)
def _cleanup_slot_rows(db_session):
    """The conditions router commits, which consumes the fixture's outer
    transaction and makes rows land for real in experiments_test. Clean up
    anything this file's slot tests create so they cannot leak into other files.
    """
    yield
    from database.models.conditions import ExperimentalConditions as _EC
    from database.models.experiments import Experiment as _E

    db_session.query(_EC).filter(_EC.experiment_id.like("COND_SLOT_%")).delete(
        synchronize_session=False
    )
    db_session.query(_E).filter(_E.experiment_id.like("COND_SLOT_%")).delete(
        synchronize_session=False
    )
    db_session.commit()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest tests/models/test_reactor_slot_column.py tests/api/test_conditions.py -q`
Expected: all four new listener tests fail with `assert None == 'R04'` (and similar); the three new API tests fail with `KeyError: 'reactor_slot'`. Task 2's tests keep passing.

- [ ] **Step 3: Add the listener**

In `database/event_listeners.py`, change line 4 to include the model:

```python
from .models import ExternalAnalysis, SampleInfo, ChemicalAdditive, ElementalAnalysis, Experiment, ExperimentalConditions
```

Then insert this immediately after `calculate_additive_derived_values` (i.e. after line 682, before the `update_experiment_lineage_on_flush` listener):

```python
@event.listens_for(ExperimentalConditions, 'before_insert')
@event.listens_for(ExperimentalConditions, 'before_update')
def set_reactor_slot(mapper, connection, target):
    """Keep experimental_conditions.reactor_slot derived from (reactor_number, experiment_type).

    Issue #97. A mapper-level listener rather than per-write-site assignment,
    because "every path that writes reactor_number must remember to also update
    the slot" is precisely the failure mode the column exists to eliminate.

    This fires for every path that loads an ExperimentalConditions instance and
    mutates its attributes: both bulk-upload parsers, the conditions router,
    experimental_conditions_service.py, and the legacy Streamlit app.

    It does NOT fire for a bulk Query.update() / Core UPDATE, which compiles to
    SQL without per-row mapper events. database/data_migrations/
    swap_reactor_4_7_015.py:96-109 is the existing precedent for that idiom. A
    script changing reactor_number or experiment_type that way must either avoid
    Query.update() for those columns or recompute reactor_slot explicitly in the
    same script, or it will silently leave the slot stale.

    Same pattern as calculate_additive_derived_values above: mutating a column
    attribute in before_insert/before_update is included in the emitted
    INSERT/UPDATE. Note the corollary — the value is only correct *after* a
    flush. Code needing the slot for values it has just assigned, before
    flushing, must call derive_reactor_slot directly.
    """
    from .reactor_slot import derive_reactor_slot
    target.reactor_slot = derive_reactor_slot(target.reactor_number, target.experiment_type)
```

- [ ] **Step 4: Expose the column on the response schema**

In `backend/api/schemas/conditions.py`, add to `ConditionsResponse` immediately after `reactor_number` (line 73):

```python
    reactor_slot: Optional[str] = None
```

Do **not** add it to `ConditionsCreate` or `ConditionsUpdate` — it is derived, and Pydantic's default behaviour of ignoring unknown keys is what makes `test_conditions_create_ignores_a_client_supplied_reactor_slot` pass.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/models/ tests/api/test_conditions.py tests/test_reactor_slot.py -q`
Expected: all pass, including Task 2's `test_column_accepts_and_returns_a_slot_value`.

Then run the whole backend suite to catch any test that asserted an exact `ConditionsResponse` shape:

Run: `.venv/Scripts/pytest tests/api tests/services tests/models tests/views -q`
Expected: no new failures versus `develop`. Three pre-existing failures in `tests/test_pg_backup_restore.py` are known and out of scope — that file is not in the paths above, so you should see zero failures here.

- [ ] **Step 6: Commit**

```bash
git add database/event_listeners.py backend/api/schemas/conditions.py tests/models/test_reactor_slot_column.py tests/api/test_conditions.py
git commit -m "[#97] Derive reactor_slot on every ORM write

- before_insert/before_update listener; exposed on ConditionsResponse
- Tests added: yes
- Docs updated: no"
```

---

## Task 4: Scope the status-upload occupant queries by slot (Defects 1 and 2)

**Files:**
- Modify: `backend/services/bulk_uploads/experiment_status.py` — lines 17, 26-28, 38-50, 66-73, 196-197, 216-231, 244-266, 318-326, 344-416
- Test: `tests/services/bulk_uploads/test_experiment_status.py` (extend)

**Interfaces:**
- Consumes: `database.reactor_slot.{derive_reactor_slot, is_occupancy_type}` (Task 1).
- Produces:
  - `PlannedDemotion` gains `reactor_slot: str` (keeps `reactor_number: int` — `tests/services/bulk_uploads/test_experiment_status.py` and the router's preview response both read it).
  - `ExperimentStatusService.manage_reactor_occupancy(db, new_experiment, reactor_number, commit=True, newer_than=_UNSET, reactor_slot: str | None = None)` — the new trailing keyword. When omitted it derives the slot from `new_experiment.conditions`, which keeps the legacy Streamlit caller at `legacy/streamlit_frontend/new_experiment.py:398` working unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/bulk_uploads/test_experiment_status.py`:

```python
# ---------------------------------------------------------------------------
# Cross-series slot identity (issue #97)
# ---------------------------------------------------------------------------

def test_core_flood_going_ongoing_does_not_demote_hpht_in_same_number(db_session: Session):
    """THE headline regression test. R01 and CF01 are different vessels.

    Before #97 the occupant query keyed on the bare integer, so loading Core
    Flood rig 1 found the HPHT in R01, passed the date guard, and silently set a
    running experiment to COMPLETED.
    """
    from datetime import datetime

    hpht = _seed_experiment(
        db_session, "HPHT_SLOT_209", 97201, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=1, date=datetime(2026, 5, 1),
    )
    cf = _seed_experiment(
        db_session, "CF_SLOT_301", 97202, ExperimentStatus.COMPLETED, "Core Flood",
        reactor_number=1,
    )

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["CF_SLOT_301", "ONGOING", 1, "2026-07-20"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert preview.demotions == []
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.demotions_applied == 0
    db_session.refresh(hpht)
    db_session.refresh(cf)
    assert hpht.status == ExperimentStatus.ONGOING
    assert cf.status == ExperimentStatus.ONGOING


def test_hpht_going_ongoing_does_not_demote_core_flood_in_same_number(db_session: Session):
    """The same collision in the other direction."""
    from datetime import datetime

    cf = _seed_experiment(
        db_session, "CF_SLOT_302", 97203, ExperimentStatus.ONGOING, "Core Flood",
        reactor_number=2, date=datetime(2026, 5, 1),
    )
    hpht = _seed_experiment(
        db_session, "HPHT_SLOT_210", 97204, ExperimentStatus.COMPLETED, "HPHT",
        reactor_number=2,
    )

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_SLOT_210", "ONGOING", 2, "2026-07-20"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.demotions_applied == 0
    db_session.refresh(cf)
    assert cf.status == ExperimentStatus.ONGOING


def test_same_number_different_series_in_one_file_is_not_a_conflict(db_session: Session):
    """An HPHT into R01 and a Core Flood into CF01 in the same workbook is legal.

    Before #97 `reactor_targets` was keyed on the integer, so this produced a
    spurious "Reactor 1 is targeted by multiple rows" error — and conflict_errors
    short-circuits the whole preview, so one false positive blocked the file.
    """
    hpht = _seed_experiment(
        db_session, "HPHT_SLOT_211", 97205, ExperimentStatus.COMPLETED, "HPHT",
        reactor_number=1,
    )
    cf = _seed_experiment(
        db_session, "CF_SLOT_303", 97206, ExperimentStatus.COMPLETED, "Core Flood",
        reactor_number=1,
    )

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [
            ["HPHT_SLOT_211", "ONGOING", 1, "2026-07-20"],
            ["CF_SLOT_303", "ONGOING", 1, "2026-07-20"],
        ],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.errors == []
    assert len(preview.changes) == 2


def test_same_slot_twice_in_one_file_is_still_a_conflict(db_session: Session):
    """The real conflict must survive, and the message must name the slot."""
    _seed_experiment(
        db_session, "HPHT_SLOT_212", 97207, ExperimentStatus.COMPLETED, "HPHT",
        reactor_number=7,
    )
    _seed_experiment(
        db_session, "HPHT_SLOT_213", 97208, ExperimentStatus.COMPLETED, "HPHT",
        reactor_number=7,
    )

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [
            ["HPHT_SLOT_212", "ONGOING", 7, "2026-07-20"],
            ["HPHT_SLOT_213", "ONGOING", 7, "2026-07-20"],
        ],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert len(preview.errors) == 1
    assert "R07" in preview.errors[0]
    assert "HPHT_SLOT_212" in preview.errors[0]
    assert "HPHT_SLOT_213" in preview.errors[0]


def test_demotion_within_the_same_slot_still_works(db_session: Session):
    """Guard against over-correcting: two HPHTs in R11 must still demote."""
    from datetime import datetime

    occupant = _seed_experiment(
        db_session, "HPHT_SLOT_214", 97209, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=11, date=datetime(2026, 1, 1),
    )
    incoming = _seed_experiment(
        db_session, "HPHT_SLOT_215", 97210, ExperimentStatus.COMPLETED, "HPHT",
        reactor_number=11,
    )

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_SLOT_215", "ONGOING", 11, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert [d.reactor_slot for d in preview.demotions] == ["R11"]
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.demotions_applied == 1
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.COMPLETED
    assert any("R11" in w for w in result.warnings)


def test_zero_reactor_number_never_demotes_anyone(db_session: Session):
    """reactor_number = 0 is not a slot. The 8 R00 SERUM_JW vials in the
    2026-07-28 prod audit exist because zero slipped through."""
    from datetime import datetime

    occupant = _seed_experiment(
        db_session, "HPHT_SLOT_216", 97211, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=0, date=datetime(2026, 1, 1),
    )
    incoming = _seed_experiment(
        db_session, "HPHT_SLOT_217", 97212, ExperimentStatus.COMPLETED, "HPHT",
        reactor_number=0,
    )

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_SLOT_217", "ONGOING", 0, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.demotions_applied == 0
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.ONGOING


def test_manage_reactor_occupancy_derives_slot_when_not_passed(db_session: Session):
    """The legacy Streamlit caller (legacy/streamlit_frontend/new_experiment.py:398)
    passes no reactor_slot. It must still be scoped by series."""
    from datetime import datetime

    hpht = _seed_experiment(
        db_session, "HPHT_SLOT_218", 97213, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=5, date=datetime(2026, 1, 1),
    )
    cf = _seed_experiment(
        db_session, "CF_SLOT_304", 97214, ExperimentStatus.ONGOING, "Core Flood",
        reactor_number=5,
    )

    marked, warnings = ExperimentStatusService.manage_reactor_occupancy(
        db_session, cf, 5, commit=False
    )

    assert marked == 0
    db_session.refresh(hpht)
    assert hpht.status == ExperimentStatus.ONGOING
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest tests/services/bulk_uploads/test_experiment_status.py -q -k slot`
Expected: `test_core_flood_going_ongoing_does_not_demote_hpht_in_same_number` fails with `assert 1 == 0` (the demotion happens — this is the live bug reproducing); the same-file test fails with a non-empty `preview.errors`; `test_same_slot_twice_in_one_file_is_still_a_conflict` fails on `"R07" in ...` (the message says `Reactor 7`); `PlannedDemotion` has no `reactor_slot`, so two tests raise `AttributeError`.

- [ ] **Step 3: Rewrite the occupancy logic onto slots**

In `backend/services/bulk_uploads/experiment_status.py`:

**3a.** Replace the type helpers at lines 16-28:

```python
_VALID_STATUSES = {s.value for s in ExperimentStatus}
_OCCUPANCY_TYPES = {"hpht", "core flood"}
_UNSET = object()


def _normalize_type(experiment_type: str | None) -> str:
    """Lowercase + collapse whitespace so 'HPHT ', 'Core  Flood', etc. compare cleanly."""
    return " ".join((experiment_type or "").strip().lower().split())


def _is_eligible_for_occupancy(experiment_type: str | None) -> bool:
    """True for HPHT / Core Flood — the types with physical reactor occupancy."""
    return _normalize_type(experiment_type) in _OCCUPANCY_TYPES
```

with:

```python
_VALID_STATUSES = {s.value for s in ExperimentStatus}
_UNSET = object()
```

**Both local type helpers are deleted, not kept as delegating wrappers.** Every
call site of `_is_eligible_for_occupancy` is replaced below by
`derive_reactor_slot(...) is not None`, which subsumes it — so keeping the
function would leave something that still *reads* like the eligibility gate in a
locked parser while having no effect, and a maintainer would edit it and see
nothing change. `_normalize_type` goes with it for the same reason. (Ruling by the
product owner, 2026-07-29, after the Task 4 review flagged both as dead.)

Note this deletion also **widens** what counts as occupancy-bearing: the deleted
`_OCCUPANCY_TYPES = {"hpht", "core flood"}` did not match the `"cf"` or
`"coreflood"` spellings that `database/reactor_slot.py` accepts, and production
has one row typed literally `CF`. That row becomes occupancy-bearing for the first
time. Intended, and pinned by `test_cf_spelled_type_is_occupancy_bearing` below.

Add to the imports at the top (after line 13) — `derive_reactor_slot` only, since
nothing else from the module is used here:

```python
from database.reactor_slot import derive_reactor_slot
```

**3b.** Replace the two message helpers at lines 38-50 so they name the slot:

```python
def _demoted_message(reactor_slot: str, demoted_id: str, new_id: str) -> str:
    return (
        f"Reactor {reactor_slot}: Marked experiment '{demoted_id}' "
        f"as COMPLETED (replaced by '{new_id}')"
    )


def _not_demoted_message(reactor_slot: str, occupant_id: str, new_id: str) -> str:
    return (
        f"Reactor {reactor_slot}: '{occupant_id}' was NOT completed — its start date "
        f"is not older than '{new_id}''s (or a start date is missing on one of them). "
        f"Manual review needed."
    )
```

**3c.** Add `reactor_slot` to `PlannedDemotion` (lines 66-73):

```python
@dataclass
class PlannedDemotion:
    """One reactor occupant that will be completed when its row's demotion is applied."""
    experiment_id: str
    experiment_pk: int
    reactor_number: int
    reactor_slot: str
    triggering_experiment_id: str
```

**3d.** Key the same-file conflict map on the slot. Replace line 196 (`reactor_targets: Dict[int, str] = {}`) with:

```python
        # Keyed on the canonical slot label, not the bare integer: an HPHT into
        # R01 and a Core Flood into CF01 in one file are two different vessels
        # and must not collide (issue #97, Defect 2).
        reactor_targets: Dict[str, str] = {}
```

and replace the conflict block at lines 216-228 with:

```python
            incoming_slot = derive_reactor_slot(r["reactor_number"], exp_type)
            if (
                r["status"] == ExperimentStatus.ONGOING.value
                and incoming_slot is not None
            ):
                existing = reactor_targets.get(incoming_slot)
                if existing is not None:
                    conflict_errors.append(
                        f"Reactor {incoming_slot} is targeted by multiple rows in "
                        f"this file: '{existing}' and '{exp.experiment_id}'"
                    )
                else:
                    reactor_targets[incoming_slot] = exp.experiment_id
```

`incoming_slot is not None` subsumes the old three-part condition: it is None when `reactor_number` is None, when it is <= 0, and when the type is not occupancy-bearing.

**3e.** Replace the preview demotion scan (lines 236-266) with:

```python
        for r in parsed_rows:
            exp = exp_by_id.get(r["experiment_id"])
            if exp is None or r["status"] != ExperimentStatus.ONGOING.value:
                continue
            exp_type = exp.conditions.experiment_type if exp.conditions else None
            incoming_slot = derive_reactor_slot(r["reactor_number"], exp_type)
            if incoming_slot is None:
                continue

            # Scoped on reactor_slot, so an occupant is only found in the SAME
            # physical vessel. Filtering on reactor_number alone made a Core
            # Flood going ONGOING find the HPHT in R01 (issue #97, Defect 1).
            occupants = db.query(Experiment).join(
                ExperimentalConditions,
                Experiment.id == ExperimentalConditions.experiment_fk,
            ).filter(
                Experiment.id != exp.id,
                Experiment.status == ExperimentStatus.ONGOING,
                ExperimentalConditions.reactor_slot == incoming_slot,
            ).all()

            incoming_date = r["date"].date() if r["date"] is not None else None

            for occ in occupants:
                occ_date = occ.date.date() if occ.date else None
                if _occupant_is_older(occ_date, incoming_date):
                    demotions.append(PlannedDemotion(
                        experiment_id=occ.experiment_id,
                        experiment_pk=occ.id,
                        reactor_number=r["reactor_number"],
                        reactor_slot=incoming_slot,
                        triggering_experiment_id=exp.experiment_id,
                    ))
                    warnings.append(_demoted_message(incoming_slot, occ.experiment_id, exp.experiment_id))
                else:
                    warnings.append(_not_demoted_message(incoming_slot, occ.experiment_id, exp.experiment_id))
```

**3f.** In `apply_status_changes`, replace the occupancy call block at lines 318-326 with:

```python
                incoming_slot = derive_reactor_slot(
                    change.new_reactor_number, change.experiment_type
                )
                if change.new_status == ExperimentStatus.ONGOING.value and incoming_slot is not None:
                    newer_than = change.new_date.to_pydatetime() if change.new_date is not None else None
                    marked, occ_warnings = ExperimentStatusService.manage_reactor_occupancy(
                        db, exp, change.new_reactor_number, commit=False,
                        newer_than=newer_than, reactor_slot=incoming_slot,
                    )
                    demotions_applied += marked
                    warnings.extend(occ_warnings)
```

Note `reactor_slot` is derived here rather than read off `exp.conditions.reactor_slot`: line 315 has just assigned the new `reactor_number` in-session and the listener has not run yet. This is the pre-flush rule from Task 3.

**3g.** Rewrite `manage_reactor_occupancy`'s signature, docstring and query (lines 344-416). Replace the signature and the `Args:` block:

```python
    @staticmethod
    def manage_reactor_occupancy(
        db: Session,
        new_experiment: Experiment,
        reactor_number: int,
        commit: bool = True,
        newer_than: datetime | None = _UNSET,
        reactor_slot: str | None = None,
    ) -> Tuple[int, List[str]]:
        """
        Ensure only one experiment is ONGOING per physical reactor slot at a time.

        Occupancy is keyed on `reactor_slot` (e.g. 'R01', 'CF01'), not on the bare
        `reactor_number` — R01 and CF01 are different vessels that share the number
        1, and keying on the integer let a Core Flood auto-complete a running HPHT
        (issue #97, Defect 1).

        If `newer_than` is explicitly passed (even as None), a start-date guard is
        active: an occupant is only demoted if its `date` is strictly older (by
        calendar date) than `newer_than`; occupants with a missing date, or a date
        that is newer-or-equal, are left ONGOING with a warning instead. Omitting
        `newer_than` entirely preserves the original unconditional behavior relied
        on by `new_experiments.py` (both occupancy call sites) and the legacy
        Streamlit create path. That dependency is live, not historical — do not
        change the `_UNSET` default without updating those callers.

        Args:
            db: Database session
            new_experiment: The experiment being created/updated
            reactor_number: The reactor number being assigned
            commit: Whether to commit changes (default True)
            newer_than: Optional start-date guard (see above)
            reactor_slot: The canonical slot the incoming experiment is claiming.
                Callers that have just assigned a new reactor_number in-session
                must pass this, because the derived column is only written at
                flush time. When omitted it is derived from `new_experiment`'s
                own conditions — which is what keeps the legacy Streamlit caller
                correct without changing it.

        Returns:
            Tuple of (marked_completed_count, warnings). Returns (0, []) when the
            incoming experiment holds no slot at all: a non-occupancy type, a
            missing reactor_number, or reactor_number <= 0.
        """
        warnings: List[str] = []
        marked_completed = 0
        guard_active = newer_than is not _UNSET

        try:
            if new_experiment.status != ExperimentStatus.ONGOING:
                return 0, []

            slot = reactor_slot
            if slot is None:
                conditions = getattr(new_experiment, "conditions", None)
                slot = derive_reactor_slot(
                    reactor_number,
                    conditions.experiment_type if conditions is not None else None,
                )
            if slot is None:
                # No physical slot to contest — nothing to demote, and nothing
                # worth warning about.
                return 0, []

            conflicting_experiments = db.query(Experiment).join(
                ExperimentalConditions,
                Experiment.id == ExperimentalConditions.experiment_fk
            ).filter(
                Experiment.id != new_experiment.id,
                Experiment.status == ExperimentStatus.ONGOING,
                ExperimentalConditions.reactor_slot == slot
            ).all()

            for exp in conflicting_experiments:
                if guard_active:
                    occ_date = exp.date.date() if exp.date else None
                    incoming_date = newer_than.date() if newer_than else None
                    if incoming_date is None or occ_date is None or occ_date >= incoming_date:
                        warnings.append(
                            _not_demoted_message(slot, exp.experiment_id, new_experiment.experiment_id)
                        )
                        continue

                exp.status = ExperimentStatus.COMPLETED
                marked_completed += 1
                warnings.append(
                    _demoted_message(slot, exp.experiment_id, new_experiment.experiment_id)
                )

            if commit:
                db.commit()

        except Exception as e:
            warnings.append(f"Error managing reactor occupancy: {e}")
            if commit:
                db.rollback()

        return marked_completed, warnings
```

**Fixture caveat for the new tests:** `_seed_experiment` flushes the conditions row, so the listener has run and `reactor_slot` is populated before any query. `test_manage_reactor_occupancy_derives_slot_when_not_passed` relies on `cf.conditions` being loadable — it is, because `_seed_experiment` flushed.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/services/bulk_uploads/test_experiment_status.py -q`
Expected: all pass — the ~40 pre-existing tests plus the 7 new ones. Pay particular attention to `test_apply_no_demotion_for_serum_type_even_with_reactor_number` (line 506) and `test_apply_triggers_demotion_for_ongoing_hpht_with_older_occupant` (line 483): both must still pass unchanged.

Then the whole parser suite: `.venv/Scripts/pytest tests/services/bulk_uploads/ -q`
Expected: no new failures (197+ passing before this branch).

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/experiment_status.py tests/services/bulk_uploads/test_experiment_status.py
git commit -m "[#97] Scope status-upload occupancy by reactor slot

- Fixes cross-series demotion and the same-file false conflict
- Tests added: yes
- Docs updated: no"
```

---

## Task 5: Gate the new-experiments upload paths (Defect 3)

**Files:**
- Modify: `backend/services/bulk_uploads/new_experiments.py:830-841` (conditions-sheet path) and `:903-913` (auto-copied-from-parent path)
- Test: `tests/services/bulk_uploads/test_new_experiments.py` (extend)

**Interfaces:**
- Consumes: `database.reactor_slot.derive_reactor_slot` (Task 1); `manage_reactor_occupancy(..., reactor_slot=)` (Task 4).
- Produces: nothing new.

Both call sites currently read `if conditions.reactor_number and experiment.status == ExperimentStatus.ONGOING:` and call `manage_reactor_occupancy` with no eligibility check and no `newer_than`. The issue lists three defects in that one line; **this task fixes two of them and deliberately leaves the third.**

Fixed here: the missing eligibility gate (a Serum row demotes the HPHT occupant), and the falsy-zero bug (`reactor_number == 0` is skipped — the eight `R00` rows in the prod audit exist because of it). Both are handled by one predicate, `derive_reactor_slot(...) is not None`.

**Not fixed here: `newer_than` stays omitted.** This is the plan's one deviation from the issue text, and it falls directly out of Mat's decision to defer §4. The issue's own argument for passing it is:

> Once the trigger exists, failing open produces a **loud row-level error on the upload instead of silent corruption**, which is the behavior we want. So pass `newer_than=experiment.date` and let the trigger be the backstop.

There is no trigger in this pass, so there is no backstop. Passing `newer_than` now would make the guard decline to demote whenever either date is missing — and the new-experiments workbook has no date column in the common case — leaving a real double-booking in the database with nothing but a warning. That is strictly worse than today.

Two concrete consequences worth stating:

1. `tests/services/bulk_uploads/test_new_experiments.py::test_reactivation_via_overwrite_demotes_prior_reactor_occupant` (line 79) seeds an occupant with **no date** and asserts it *is* demoted. Passing `newer_than=experiment.date` (which is `None` there) breaks that test. It encodes issue #68's intended behaviour, so the correct response is not to weaken it.
2. This path therefore remains the least date-guarded of the write paths, exactly as the issue observes. That is now an explicit, recorded gap rather than an oversight — Task 9 carries it into the follow-up issue as work that lands *with* the trigger, in one reviewable change.

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/bulk_uploads/test_new_experiments.py`. These use that file's existing helpers verbatim — `_seed_experiment` (line 23), `_EXP_HEADERS` (line 17), `make_excel_multisheet` (imported line 15) — and the same 6-tuple unpacking and workbook shape as `test_reactivation_via_overwrite_demotes_prior_reactor_occupant` (line 79), which is the closest existing analogue. Read that test before writing these.

**Experiment IDs are deliberately 2-part** (`HPHT_9731`, not `HPHT_NE_301`). A 3-part ID matches the `Type_Initials_Index` grammar and the parser reads the middle token as researcher initials — that cost real debugging time during #100 with `HPHT_PLAN_0NN`.

```python
# ---------------------------------------------------------------------------
# Reactor occupancy gates on the new-experiments path (issue #97, Defect 3)
# ---------------------------------------------------------------------------

def test_serum_row_with_reactor_number_does_not_demote_hpht_occupant(db_session: Session):
    """Mirror of test_apply_no_demotion_for_serum_type_even_with_reactor_number
    (test_experiment_status.py:506) on the other write path, which had no
    equivalent. A Serum vial holds no vessel, so it cannot evict one.
    """
    occupant = _seed_experiment(db_session, "HPHT_9731", 97301, status=ExperimentStatus.ONGOING)
    db_session.add(ExperimentalConditions(
        experiment_id=occupant.experiment_id,
        experiment_fk=occupant.id,
        reactor_number=3,
        experiment_type="HPHT",
    ))
    _seed_experiment(db_session, "SERUM_9741", 97302, status=ExperimentStatus.COMPLETED)
    db_session.flush()
    assert occupant.conditions.reactor_slot == "R03"

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["SERUM_9741", None, None, None, None, "ONGOING", None, True]],
        ),
        "conditions": (
            ["experiment_id", "reactor_number", "experiment_type"],
            [["SERUM_9741", 3, "Serum"]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.ONGOING, (
        "a Serum row with a stray reactor_number completed the HPHT in R03"
    )
    assert not any("Auto-completed" in m for m in info), (
        f"no auto-completion should be reported, got: {info}"
    )


def test_core_flood_row_does_not_demote_hpht_in_same_number(db_session: Session):
    """The cross-series collision on the new-experiments path. R01 and CF01 are
    different vessels."""
    occupant = _seed_experiment(db_session, "HPHT_9732", 97303, status=ExperimentStatus.ONGOING)
    db_session.add(ExperimentalConditions(
        experiment_id=occupant.experiment_id,
        experiment_fk=occupant.id,
        reactor_number=1,
        experiment_type="HPHT",
    ))
    _seed_experiment(db_session, "CF_9742", 97304, status=ExperimentStatus.COMPLETED)
    db_session.flush()

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["CF_9742", None, None, None, None, "ONGOING", None, True]],
        ),
        "conditions": (
            ["experiment_id", "reactor_number", "experiment_type"],
            [["CF_9742", 1, "Core Flood"]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.ONGOING, (
        "loading Core Flood rig 1 completed the HPHT in R01"
    )


def test_hpht_row_still_demotes_the_occupant_of_the_same_slot(db_session: Session):
    """Guard against over-correcting. Two HPHTs in R14 is a real collision and the
    demotion must survive — this is the behaviour test_reactivation_via_overwrite_
    demotes_prior_reactor_occupant (line 79) covers via the same path.
    """
    occupant = _seed_experiment(db_session, "HPHT_9733", 97305, status=ExperimentStatus.ONGOING)
    db_session.add(ExperimentalConditions(
        experiment_id=occupant.experiment_id,
        experiment_fk=occupant.id,
        reactor_number=14,
        experiment_type="HPHT",
    ))
    _seed_experiment(db_session, "HPHT_9743", 97306, status=ExperimentStatus.COMPLETED)
    db_session.flush()

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["HPHT_9743", None, None, None, None, "ONGOING", None, True]],
        ),
        "conditions": (
            ["experiment_id", "reactor_number", "experiment_type"],
            [["HPHT_9743", 14, "HPHT"]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.COMPLETED
    assert any("R14" in m for m in info), (
        f"the auto-completion message should name the slot, got: {info}"
    )


def test_zero_reactor_number_does_not_demote_anyone(db_session: Session):
    """reactor_number = 0 is not a slot, so it evicts nobody.

    NOTE: this passes both before and after the change — before, because `if
    conditions.reactor_number` is falsy for 0; after, because derive_reactor_slot
    returns None for 0. It is here because the fix replaces the falsy check with
    `is not None`, and without this guard that swap would silently start treating
    R00 as a real slot. The eight R00 rows in the 2026-07-28 prod audit are this case.
    """
    occupant = _seed_experiment(db_session, "HPHT_9734", 97307, status=ExperimentStatus.ONGOING)
    db_session.add(ExperimentalConditions(
        experiment_id=occupant.experiment_id,
        experiment_fk=occupant.id,
        reactor_number=0,
        experiment_type="HPHT",
    ))
    _seed_experiment(db_session, "HPHT_9744", 97308, status=ExperimentStatus.COMPLETED)
    db_session.flush()
    assert occupant.conditions.reactor_slot is None

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["HPHT_9744", None, None, None, None, "ONGOING", None, True]],
        ),
        "conditions": (
            ["experiment_id", "reactor_number", "experiment_type"],
            [["HPHT_9744", 0, "HPHT"]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.ONGOING
```

- [ ] **Step 2: Run the tests to verify they fail**

**CORRECTED 2026-07-30 — the original prediction here was wrong, measured against unmodified source.**

Run: `.venv/Scripts/pytest tests/services/bulk_uploads/test_new_experiments.py -q`

Actual pre-change result: **1 failed, 10 passed** (1.56s). The single failure is
`test_hpht_row_still_demotes_the_occupant_of_the_same_slot`, and only on its final
assertion `any("R14" in m for m in info)` — the pre-change message reads
`"Reactor 14: Auto-completed 1 …"`. The demotion itself already fires.

The two tests this plan predicted would fail — the Serum cross-type and Core Flood
cross-series cases — **pass before the change**. Task 4 already fixed them
transitively: the fallback it added inside `manage_reactor_occupancy`
(`experiment_status.py:401-410`) derives the slot from
`new_experiment.conditions.experiment_type` whenever `reactor_slot` is omitted, and
both call sites here omit it. So a Serum row already returned `(0, [])` and a Core
Flood row already scoped to `CF01` rather than `R01`. The falsy-zero half is
equivalent too: `if conditions.reactor_number` skipped `0` before, and
`derive_reactor_slot(0, …) → None` skips it now.

**So this task is not a live-bug fix.** What it genuinely delivers:
1. **Explicitness** — passing `reactor_slot=` removes the dependency on a lazy
   `.conditions` relationship load inside the service, which is fragile for a
   freshly constructed, unflushed conditions row.
2. **`is not None`** removes the falsy-zero footgun (same outcome, no trap for a
   future refactor that treats `0` as truthy).
3. **The info message names the slot**, consistent with Task 4's warnings. This is
   the one user-visible change and the only genuine RED driver.

Two consequences for the implementer, both required:
- The Serum and Core Flood tests' docstrings must **not** claim to reproduce a live
  bug. Write them as regression guards attributing the protection to Task 4's
  fallback.
- Add a test for the **auto-copy call site** (`:905`), which the Task 4 review
  flagged as having no coverage. It reaches that branch only when the experiment has
  a parent AND no conditions-sheet row — a workbook with a conditions sheet silently
  takes the `:833` path instead and proves nothing. Verified outcome: the auto-copy
  path already demoted correctly, so Task 4 introduced no defect there.

- [ ] **Step 3: Gate both call sites**

In `backend/services/bulk_uploads/new_experiments.py`, add to the imports at the top of the file (beside the other `database` imports):

```python
from database.reactor_slot import derive_reactor_slot
```

Replace lines 830-841 (the conditions-sheet path):

```python
                        # Manage reactor occupancy: if experiment is ONGOING and has reactor_number, 
                        # mark other ONGOING experiments in same reactor as COMPLETED
                        if conditions.reactor_number and experiment.status == ExperimentStatus.ONGOING:
                            marked, reactor_warnings = ExperimentStatusService.manage_reactor_occupancy(
                                db, experiment, conditions.reactor_number, commit=False
                            )
                            warnings.extend(reactor_warnings)
                            if marked > 0:
                                info_messages.append(
                                    f"Reactor {conditions.reactor_number}: Auto-completed {marked} "
                                    f"conflicting experiment(s) for '{exp_id}'"
                                )
```

with:

```python
                        # Manage reactor occupancy: only one ONGOING experiment per
                        # physical slot. Keyed on the derived reactor_slot, which is
                        # None for a non-occupancy type (Serum / Autoclave / Other)
                        # and for reactor_number <= 0 — so this path can no longer
                        # complete an HPHT because a Serum row carried a stray
                        # reactor number, and `is not None` no longer skips rows
                        # whose reactor number is 0 (issue #97, Defect 3).
                        #
                        # `newer_than` is still deliberately NOT passed, so the
                        # start-date guard stays inactive and demotion here remains
                        # unconditional. Issue #97 §3 asks for it, but its stated
                        # rationale is "let the trigger be the backstop" — and the
                        # one-ONGOING-per-slot trigger is not in this pass. Failing
                        # open with no backstop would leave real double-bookings in
                        # the DB behind nothing but a warning. Pass newer_than in the
                        # same change that adds the trigger, not before. Tracked in
                        # docs/issues/issue-reactor-occupancy-uniqueness-trigger.md.
                        incoming_slot = derive_reactor_slot(
                            conditions.reactor_number, conditions.experiment_type
                        )
                        if incoming_slot is not None and experiment.status == ExperimentStatus.ONGOING:
                            marked, reactor_warnings = ExperimentStatusService.manage_reactor_occupancy(
                                db, experiment, conditions.reactor_number, commit=False,
                                reactor_slot=incoming_slot,
                            )
                            warnings.extend(reactor_warnings)
                            if marked > 0:
                                info_messages.append(
                                    f"Reactor {incoming_slot}: Auto-completed {marked} "
                                    f"conflicting experiment(s) for '{exp_id}'"
                                )
```

Replace lines 903-913 (the auto-copied-from-parent path) with the same shape:

```python
                # Manage reactor occupancy for auto-copied conditions.
                # Same gates as the conditions-sheet path above (issue #97, Defect 3):
                # slot-scoped, non-occupancy types excluded, zero excluded. `newer_than`
                # is omitted here for the same reason — see the comment on that path.
                incoming_slot = derive_reactor_slot(
                    conditions.reactor_number, conditions.experiment_type
                )
                if incoming_slot is not None and experiment.status == ExperimentStatus.ONGOING:
                    marked, reactor_warnings = ExperimentStatusService.manage_reactor_occupancy(
                        db, experiment, conditions.reactor_number, commit=False,
                        reactor_slot=incoming_slot,
                    )
                    warnings.extend(reactor_warnings)
                    if marked > 0:
                        info_messages.append(
                            f"Reactor {incoming_slot}: Auto-completed {marked} "
                            f"conflicting experiment(s) for '{exp_id}'"
                        )
```

Note both blocks derive the slot from the in-memory `conditions` object rather than reading `conditions.reactor_slot`: at these points the row may be newly constructed and unflushed, so the column is not yet written. This is the pre-flush rule from Task 3.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/services/bulk_uploads/ -q`
Expected: all pass, including the four new tests and every pre-existing new-experiments test — **no pre-existing test should need editing.** In particular `test_reactivation_via_overwrite_demotes_prior_reactor_occupant` (line 79) must still pass untouched: its occupant is an ONGOING HPHT in R07 with no date, its incoming row is also HPHT into 7, so the slot matches, the type is eligible, and the guard is inactive. If you find yourself editing that test, you have accidentally passed `newer_than` — re-read Step 3.

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/new_experiments.py tests/services/bulk_uploads/test_new_experiments.py
git commit -m "[#97] Gate new-experiments reactor occupancy

- Slot-scoped and zero-safe on both call sites; newer_than still omitted
- Tests added: yes
- Docs updated: no"
```

---

## Task 6: `PATCH /{id}/status` rejects a double-booking with 409

**Files:**
- Modify: `backend/api/routers/experiments.py:638-654`
- Test: `tests/api/test_experiments.py` (extend)

**Interfaces:**
- Consumes: `database.reactor_slot.derive_reactor_slot` (Task 1); `ExperimentalConditions.reactor_slot` (Task 2).
- Produces: `PATCH /api/experiments/{experiment_id}/status` may now return **409** with `detail` naming the occupying `experiment_id` and its start date. Task 8's frontend work depends on that `detail` string.

Decided in the issue §3: reject, do not demote. `CF_018`, `-2` and `-3` all went ONGOING through this endpoint with nothing objecting, which is how CF01 ended up triple-booked in production. The endpoint cannot tell "I am advancing a sequential re-run" from "I picked the wrong reactor from a dropdown", and only one of those should close someone else's running experiment.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_experiments.py`:

```python
# ---------------------------------------------------------------------------
# PATCH /status occupancy rejection (issue #97, Defect 4)
# ---------------------------------------------------------------------------

def _seed_slot_experiment(db, eid, num, status, experiment_type, reactor_number, date=None):
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus as _S

    exp = Experiment(
        experiment_id=eid, experiment_number=num, status=status, date=date
    )
    db.add(exp)
    db.flush()
    db.add(ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id=eid,
        experiment_type=experiment_type,
        reactor_number=reactor_number,
    ))
    db.commit()
    db.refresh(exp)
    return exp


@pytest.fixture(autouse=True)
def _cleanup_status_slot_rows(db_session):
    """This endpoint commits, so rows land for real in experiments_test."""
    yield
    from database.models.conditions import ExperimentalConditions as _EC

    db_session.query(_EC).filter(_EC.experiment_id.like("SLOT409_%")).delete(
        synchronize_session=False
    )
    db_session.query(Experiment).filter(
        Experiment.experiment_id.like("SLOT409_%")
    ).delete(synchronize_session=False)
    db_session.commit()


def test_patch_status_to_ongoing_on_occupied_slot_returns_409(client, db_session):
    import datetime as _dt

    occupant = _seed_slot_experiment(
        db_session, "SLOT409_A", 97401, ExperimentStatus.ONGOING, "HPHT", 8,
        date=_dt.datetime(2026, 7, 24),
    )
    challenger = _seed_slot_experiment(
        db_session, "SLOT409_B", 97402, ExperimentStatus.QUEUED, "HPHT", 8,
    )

    resp = client.patch("/api/experiments/SLOT409_B/status", json={"status": "ONGOING"})

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "R08" in detail
    assert "SLOT409_A" in detail
    assert "2026-07-24" in detail

    db_session.refresh(occupant)
    db_session.refresh(challenger)
    assert occupant.status == ExperimentStatus.ONGOING
    assert challenger.status == ExperimentStatus.QUEUED


def test_patch_status_to_ongoing_on_empty_slot_returns_200(client, db_session):
    exp = _seed_slot_experiment(
        db_session, "SLOT409_C", 97403, ExperimentStatus.QUEUED, "HPHT", 10,
    )
    resp = client.patch("/api/experiments/SLOT409_C/status", json={"status": "ONGOING"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ONGOING"


def test_patch_status_ignores_occupancy_across_series(client, db_session):
    """An HPHT in R09 must not block a Core Flood claiming CF09."""
    import datetime as _dt

    _seed_slot_experiment(
        db_session, "SLOT409_D", 97404, ExperimentStatus.ONGOING, "HPHT", 9,
        date=_dt.datetime(2026, 7, 1),
    )
    cf = _seed_slot_experiment(
        db_session, "SLOT409_E", 97405, ExperimentStatus.QUEUED, "Core Flood", 9,
    )
    resp = client.patch("/api/experiments/SLOT409_E/status", json={"status": "ONGOING"})
    assert resp.status_code == 200


def test_patch_status_to_completed_is_never_blocked(client, db_session):
    """Only the transition TO ONGOING is gated. Closing out a run must always work,
    including on a slot that is currently double-booked.

    The second occupant is not decoration: double-booked slots exist in production
    right now (the 2026-07-28 audit found CF01 triple-booked), so "can a researcher
    still close out an experiment sitting in a contended vessel?" is a real
    question. Seeding only one experiment would make this test pass trivially —
    the gate short-circuits on `payload.status == ONGOING` before any slot logic
    runs, so it would pass whether or not non-ONGOING transitions were handled
    correctly.
    """
    import datetime as _dt

    _seed_slot_experiment(
        db_session, "SLOT409_F", 97406, ExperimentStatus.ONGOING, "HPHT", 11,
        date=_dt.datetime(2026, 7, 1),
    )
    other = _seed_slot_experiment(
        db_session, "SLOT409_F2", 97416, ExperimentStatus.ONGOING, "HPHT", 11,
        date=_dt.datetime(2026, 7, 2),
    )
    resp = client.patch("/api/experiments/SLOT409_F/status", json={"status": "COMPLETED"})
    assert resp.status_code == 200
    db_session.refresh(other)
    assert other.status == ExperimentStatus.ONGOING


def test_patch_status_to_ongoing_is_allowed_for_a_serum_vial(client, db_session):
    """A Serum vial holds no slot, so it can never be blocked — even if it
    carries a stray reactor_number matching an ONGOING HPHT."""
    import datetime as _dt

    _seed_slot_experiment(
        db_session, "SLOT409_G", 97407, ExperimentStatus.ONGOING, "HPHT", 12,
        date=_dt.datetime(2026, 7, 1),
    )
    _seed_slot_experiment(
        db_session, "SLOT409_H", 97408, ExperimentStatus.QUEUED, "Serum", 12,
    )
    resp = client.patch("/api/experiments/SLOT409_H/status", json={"status": "ONGOING"})
    assert resp.status_code == 200


def test_patch_status_reongoing_on_own_slot_is_allowed(client, db_session):
    """Re-asserting ONGOING on an experiment that already holds the slot is a
    no-op, not a self-collision."""
    import datetime as _dt

    exp = _seed_slot_experiment(
        db_session, "SLOT409_I", 97409, ExperimentStatus.ONGOING, "HPHT", 15,
        date=_dt.datetime(2026, 7, 1),
    )
    resp = client.patch("/api/experiments/SLOT409_I/status", json={"status": "ONGOING"})
    assert resp.status_code == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest tests/api/test_experiments.py -q -k SLOT409 or slot`
(use `-k "409 or slot"` if the name filter misses)
Expected: `test_patch_status_to_ongoing_on_occupied_slot_returns_409` fails with `assert 200 == 409`. The other six pass already — they are the regression net proving the new check is narrow.

- [ ] **Step 3: Implement the check**

In `backend/api/routers/experiments.py`, replace lines 638-654 with:

```python
@router.patch("/{experiment_id}/status", response_model=ExperimentResponse)
def update_experiment_status(
    experiment_id: str,
    payload: ExperimentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentResponse:
    """Inline status update without full patch.

    A transition to ONGOING is rejected with 409 when another experiment is
    already ONGOING in the same physical reactor slot (issue #97, Defect 4).
    This endpoint deliberately does NOT demote the occupant: it cannot tell
    "I am advancing a sequential re-run" from "I picked the wrong reactor from a
    dropdown", and only one of those should close someone else's running
    experiment. Three CF_018 runs were left simultaneously ONGOING in CF01 in
    production precisely because this handler had no check at all.

    The occupying experiment_id and its start date are in the error detail so
    the caller can complete it and retry. A confirm-and-supersede dialog is a
    deferred follow-up; the backend contract is the same with or without it.
    """
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    if payload.status == ExperimentStatus.ONGOING:
        conditions = exp.conditions
        slot = derive_reactor_slot(
            conditions.reactor_number if conditions else None,
            conditions.experiment_type if conditions else None,
        )
        if slot is not None:
            occupant = db.execute(
                select(Experiment)
                .join(
                    ExperimentalConditions,
                    ExperimentalConditions.experiment_fk == Experiment.id,
                )
                .where(
                    Experiment.id != exp.id,
                    Experiment.status == ExperimentStatus.ONGOING,
                    ExperimentalConditions.reactor_slot == slot,
                )
                .order_by(Experiment.id)
                .limit(1)
            ).scalar_one_or_none()
            if occupant is not None:
                started = (
                    occupant.date.date().isoformat()
                    if occupant.date
                    else "an unrecorded date"
                )
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Reactor {slot} is already occupied by ONGOING experiment "
                        f"'{occupant.experiment_id}' (started {started}). Complete or "
                        f"cancel it before starting '{exp.experiment_id}'."
                    ),
                )

    exp.status = payload.status
    db.commit()
    db.refresh(exp)
    return ExperimentResponse.model_validate(exp)
```

Confirm `ExperimentalConditions`, `ExperimentStatus` and `select` are already imported at the top of this router (they are — `ExperimentalConditions` is used by the additives endpoints and `ExperimentStatus` by the list filter). Add only:

```python
from database.reactor_slot import derive_reactor_slot
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/api/test_experiments.py -q`
Expected: all pass, new and pre-existing.

Then check nothing else drove this endpoint into an occupied slot:
Run: `.venv/Scripts/pytest tests/api -q`
Expected: no new failures. `tests/api/test_queued_status.py` exercises status transitions — read any failure there carefully before changing it; a QUEUED→ONGOING fixture that happens to collide is a legitimate test-data problem, not a reason to loosen the check.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/experiments.py tests/api/test_experiments.py
git commit -m "[#97] Reject ONGOING into an occupied reactor slot

- PATCH /status now 409s instead of silently double-booking
- Tests added: yes
- Docs updated: no"
```

---

## Task 7: Read the column instead of rebuilding the label

**Files:**
- Modify: `backend/api/routers/dashboard.py:94-164` (reactor cards), `:313-360` (`GET /reactor-status`), `:144-147` (stale comment)
- Modify: `backend/services/notion_sync/import_.py:43-68`
- Modify: `backend/services/notion_sync/export.py:30-40`, `:68-82`
- Test: `tests/api/test_dashboard.py` (extend), `tests/services/test_notion_sync_import.py` (extend), `tests/services/test_notion_sync_export.py` (verify unchanged)

**Interfaces:**
- Consumes: `ExperimentalConditions.reactor_slot` (Task 2); `database.reactor_slot.canonical_slot_label` (Task 1).
- Produces: no signature changes. `_reactor_label_for` is deleted from `export.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_dashboard.py`. These follow the inline-seed style of `test_cf_and_hpht_in_same_reactor_number_each_get_own_slot` (line 542) — local model imports, `db_session.add(...)` then `db_session.commit()`, then `client.get("/api/dashboard/")`. That file's tests already commit, so they already leak; keep the `SLOT97_` prefix so a future cleanup fixture can find these.

```python
def test_serum_with_stray_reactor_number_never_reaches_the_grid(client, db_session):
    """A Serum vial has reactor_slot NULL, so the reactor-cards query cannot
    return it. This replaces the experiment_type.in_(...) filter with a
    structural guarantee (issue #97).
    """
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="SLOT97_SERUM_001",
        experiment_number=97501,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(exp)
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="SLOT97_SERUM_001",
        reactor_number=6,
        experiment_type="Serum",
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    ids = {c["experiment_id"] for c in resp.json()["reactors"]}
    assert "SLOT97_SERUM_001" not in ids


def test_reactor_number_zero_never_reaches_the_grid(client, db_session):
    """reactor_number = 0 derives to no slot, so no R00 card can render.

    The old filter pair (reactor_number IS NOT NULL + experiment_type IN (...))
    let an HPHT on 0 through; only #85's label-set filter in _occupancy kept R00
    out of the KPI counts. Now it never reaches the card list at all.
    """
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="SLOT97_ZERO_001",
        experiment_number=97502,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(exp)
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="SLOT97_ZERO_001",
        reactor_number=0,
        experiment_type="HPHT",
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    body = resp.json()
    labels = {c["reactor_label"] for c in body["reactors"]}
    assert "R00" not in labels
    ids = {c["experiment_id"] for c in body["reactors"]}
    assert "SLOT97_ZERO_001" not in ids


def test_reactor_status_endpoint_also_excludes_slotless_rows(client, db_session):
    """The legacy GET /reactor-status moved onto the same predicate."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="SLOT97_SERUM_002",
        experiment_number=97503,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(exp)
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="SLOT97_SERUM_002",
        reactor_number=7,
        experiment_type="Serum",
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/reactor-status")
    assert resp.status_code == 200
    ids = {r["experiment_id"] for r in resp.json()}
    assert "SLOT97_SERUM_002" not in ids
```

Append to `tests/services/test_notion_sync_import.py`. These follow the inline-seed style of `test_import_core_flood_label_resolves_correctly` (line ~237) and call `_resolve_experiment_id` directly rather than going through `run_import`, since the resolution logic is what changed.

```python
def test_resolve_experiment_id_matches_unpadded_notion_label(db_session: Session) -> None:
    """Notion page titles are not guaranteed zero-padded — 'R5' must resolve to R05.

    Regression guard: the old implementation parsed the digits with int() so it
    handled this; canonical_slot_label must preserve that.
    """
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from backend.services.notion_sync.import_ import _resolve_experiment_id

    exp = Experiment(experiment_id="HPHT_TEST_970", experiment_number=97601, status="ONGOING")
    db_session.add(exp)
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="HPHT_TEST_970",
        reactor_number=5,
        experiment_type="HPHT",
    ))
    db_session.flush()

    assert _resolve_experiment_id(db_session, "R5") == "HPHT_TEST_970"
    assert _resolve_experiment_id(db_session, "r05") == "HPHT_TEST_970"


def test_resolve_experiment_id_does_not_cross_series(db_session: Session) -> None:
    """A Core Flood on rig 1 must not answer for R01."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from backend.services.notion_sync.import_ import _resolve_experiment_id

    exp = Experiment(experiment_id="CF_TEST_970", experiment_number=97602, status="ONGOING")
    db_session.add(exp)
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="CF_TEST_970",
        reactor_number=1,
        experiment_type="Core Flood",
    ))
    db_session.flush()

    assert _resolve_experiment_id(db_session, "CF01") == "CF_TEST_970"
    assert _resolve_experiment_id(db_session, "R01") is None


def test_resolve_experiment_id_ignores_null_experiment_type_rows(db_session: Session) -> None:
    """The old `experiment_type != 'Core Flood'` branch was NULL-unsafe in SQL: a
    row with a NULL type matched neither branch and could never be resolved as an
    R* occupant. It now has no reactor_slot at all — same outcome, stated reason.
    """
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from backend.services.notion_sync.import_ import _resolve_experiment_id

    exp = Experiment(experiment_id="HPHT_TEST_971", experiment_number=97603, status="ONGOING")
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="HPHT_TEST_971",
        reactor_number=4,
        experiment_type=None,
    )
    db_session.add(cond)
    db_session.flush()
    assert cond.reactor_slot is None

    assert _resolve_experiment_id(db_session, "R04") is None


def test_resolve_experiment_id_rejects_a_malformed_label(db_session: Session) -> None:
    from backend.services.notion_sync.import_ import _resolve_experiment_id

    assert _resolve_experiment_id(db_session, "X01") is None
    assert _resolve_experiment_id(db_session, "R00") is None
    assert _resolve_experiment_id(db_session, "") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest tests/api/test_dashboard.py tests/services/test_notion_sync_import.py -q`

Expected, precisely:
- `test_reactor_number_zero_never_reaches_the_grid` **FAILS** (`assert 'R00' not in labels`) — the old filter pair let an HPHT on `reactor_number = 0` onto the card list. This is the one new TDD driver here.
- `test_resolve_experiment_id_ignores_null_experiment_type_rows` **FAILS** at `assert cond.reactor_slot is None` only if Task 3's listener is missing; otherwise it passes already — the NULL-unsafe `!=` happened to produce the right answer for the wrong reason, and this test pins the reason.
- The two Serum tests, both unpadded-label tests, the cross-series test and the malformed-label test **pass already**. Serum is excluded today by `experiment_type.in_(["HPHT","Core Flood"])`, and `import_.py` was the one site that already scoped by series correctly. They are regression guards for the predicate swap in Step 3 — the swap is what could break them.

- [ ] **Step 3: Move the read paths onto the column**

**3a.** In `backend/api/routers/dashboard.py`, in the reactor-cards query (lines 94-124), add `ExperimentalConditions.reactor_slot` to the selected columns immediately after `ExperimentalConditions.reactor_number`, and replace these two `.where(...)` clauses:

```python
        .where(ExperimentalConditions.reactor_number.isnot(None))
        .where(ExperimentalConditions.experiment_type.in_(["HPHT", "Core Flood"]))
```

with:

```python
        # reactor_slot is NULL for anything that holds no physical vessel — a
        # non-occupancy type, a missing reactor_number, or reactor_number <= 0.
        # One predicate replaces the number-not-null + type-in pair, and it also
        # excludes the reactor_number = 0 rows the old pair let through
        # (issue #97).
        .where(ExperimentalConditions.reactor_slot.isnot(None))
```

Then replace the label derivation at lines 129-137:

```python
        rn = row.reactor_number
        exp_type = (
            row.experiment_type.value
            if hasattr(row.experiment_type, "value")
            else str(row.experiment_type)
            if row.experiment_type else None
        )
        is_cf = exp_type == "Core Flood" if exp_type else False
        label = f"CF{rn:02d}" if is_cf else f"R{rn:02d}"
```

with:

```python
        rn = row.reactor_number
        exp_type = (
            row.experiment_type.value
            if hasattr(row.experiment_type, "value")
            else str(row.experiment_type)
            if row.experiment_type else None
        )
        # Stored, not re-derived (issue #97). is_cf is still needed below to keep
        # REACTOR_SPECS off the Core Flood cards.
        label = row.reactor_slot
        is_cf = label.startswith("CF")
```

Leave the `exp_type` block alone — the issue puts removing those three `hasattr` blocks out of scope, and `exp_type` still populates `ReactorCardData.experiment_type`.

**3b.** Fix the stale comment at lines 144-147:

```python
        # REACTOR_SPECS is keyed by bare reactor_number and only covers the R01-R16
        # HPHT vessels. Core Flood reactors reuse the same 1/2 numbering (CF01/CF02),
        # so this must be skipped for CF or it silently inherits R01/R02's HPHT spec.
```

becomes:

```python
        # REACTOR_SPECS is keyed by bare reactor_number and only covers the R01-R16
        # HPHT vessels. Core Flood rigs reuse the same numbering (CF01-CF03), so
        # this must be skipped for CF or it silently inherits R01-R03's HPHT spec.
```

**3c.** Apply the same two changes to `GET /reactor-status` (lines 313-349): select `reactor_slot`, replace the two `.where` clauses with `.where(ExperimentalConditions.reactor_slot.isnot(None))`, and replace the `is_cf` / `label` lines with `label = row.reactor_slot`. Leave the `seen` dedup in place — deleting it is gated on the uniqueness constraint (see "Explicitly NOT in this plan").

**3d.** In `backend/services/notion_sync/import_.py`, replace `_resolve_experiment_id` (lines 43-68) with:

```python
def _resolve_experiment_id(db: Session, reactor_label: str) -> str | None:
    """Find the ONGOING experiment occupying a reactor slot, if any.

    Matches the stored reactor_slot directly. The previous implementation parsed
    the CF/R prefix and built a type filter whose `experiment_type != 'Core Flood'`
    branch was NULL-unsafe in SQL — a row with a NULL type matched neither branch
    and could never be resolved as an R* occupant (issue #97).
    """
    slot = canonical_slot_label(reactor_label)
    if slot is None:
        return None

    row = db.execute(
        select(Experiment.experiment_id)
        .join(ExperimentalConditions, ExperimentalConditions.experiment_fk == Experiment.id)
        .where(
            Experiment.status == ExperimentStatus.ONGOING,
            ExperimentalConditions.reactor_slot == slot,
        )
        .limit(1)
    ).scalar_one_or_none()
    return row
```

and add to its imports (after line 16):

```python
from database.reactor_slot import canonical_slot_label
```

**3e.** In `backend/services/notion_sync/export.py`, delete `_reactor_label_for` (lines 30-40) entirely. Then in `run_export`, replace the query filter (lines 72-75):

```python
        .filter(
            Experiment.status == ExperimentStatus.ONGOING,
            ExperimentalConditions.reactor_number.isnot(None),
        )
```

with:

```python
        .filter(
            Experiment.status == ExperimentStatus.ONGOING,
            # reactor_slot, not reactor_number: the old filter exported a Serum
            # vial carrying a stray reactor number to Notion as if it occupied
            # R0N (issue #97).
            ExperimentalConditions.reactor_slot.isnot(None),
        )
```

and replace line 82:

```python
        label = _reactor_label_for(cond.reactor_number, cond.experiment_type)
```

with:

```python
        label = cond.reactor_slot
```

Update the module docstring's second line from `Only writes for ONGOING experiments with a reactor_number assigned.` to `Only writes for ONGOING experiments occupying a physical reactor slot.`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/api/test_dashboard.py tests/services/test_notion_sync_import.py tests/services/test_notion_sync_export.py tests/services/test_notion_sync_integration.py -q`
Expected: all pass. `test_notion_sync_export.py` mocks the Notion client but seeds real rows — if a fixture there seeds conditions with no `experiment_type`, that row now has no slot and drops out of the export. That is the intended new behaviour; update the fixture to set `experiment_type="HPHT"` and note why in a comment.

Watch specifically that these keep passing: `tests/api/test_dashboard.py::test_cf01_does_not_inherit_hpht_reactor_1_hardware_specs` (~line 440), `::test_cf_and_hpht_in_same_reactor_number_each_get_own_slot` (~line 542), and #85's `summary.reactors` / `summary.core_floods` occupancy assertions.

Then the full backend suite: `.venv/Scripts/pytest tests/api tests/services tests/models tests/views -q`
Expected: zero failures.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/dashboard.py backend/services/notion_sync/import_.py backend/services/notion_sync/export.py tests/api/test_dashboard.py tests/services/test_notion_sync_import.py tests/services/test_notion_sync_export.py
git commit -m "[#97] Read stored reactor slot on all read paths

- Deletes three label re-derivations and a NULL-unsafe type filter
- Tests added: yes
- Docs updated: no"
```

---

## Task 8: Surface the 409 in the UI

**Files:**
- Modify: `frontend/src/pages/ReactorGrid.tsx:64-70`
- Modify: `frontend/src/pages/ExperimentList.tsx:313-317`
- Test: `frontend/src/pages/__tests__/ReactorGrid.test.tsx`, `frontend/src/pages/__tests__/ExperimentList.test.tsx`

**Interfaces:**
- Consumes: the 409 `detail` string from Task 6.
- Produces: nothing consumed downstream.

Both status mutations currently have **only** an `onSuccess` handler. A 409 would be swallowed entirely: the dropdown would snap back and the user would be told nothing. That makes the backend fix invisible, which is worse than the bug it replaces.

- [ ] **Step 1: Write the failing tests**

Neither file mocks the toast system — `ReactorGrid.test.tsx` renders a real `ToastProvider` from `@/components/ui` in its `renderGrid` helper (line 49), so asserting on rendered text is the file's own convention. `ExperimentList.test.tsx`'s `wrapper` (line 52) has **no** `ToastProvider` and must gain one.

In `ReactorGrid.tsx` the mutation lives in the `StatusBadge` component (line 55). Its trigger is a `title="Change status"` button that opens a dropdown of `STATUS_OPTIONS` buttons; clicking an option whose value differs from `card.status` calls `mutate(s)`. `renderGrid` already accepts a card list, and `makeCard` defaults to `status: 'ONGOING'` on `R05` — so seed the card as `QUEUED` and click `ONGOING`.

Add to `frontend/src/pages/__tests__/ReactorGrid.test.tsx`. It currently imports only `render, screen` from Testing Library — add `waitFor` and `fireEvent` to that import, and import the mocked api:

```tsx
// add to the existing imports at the top of the file:
//   import { render, screen, waitFor, fireEvent } from '@testing-library/react'
//   import { experimentsApi } from '@/api/experiments'

describe('StatusBadge — reactor occupancy 409 (issue #97)', () => {
  it('shows the server message when a status change is rejected as a double-booking', async () => {
    const detail =
      "Reactor R05 is already occupied by ONGOING experiment 'HPHT_222' (started 2026-07-24). Complete or cancel it before starting 'HPHT_MH_072'."
    vi.mocked(experimentsApi.patchStatus).mockRejectedValueOnce(
      Object.assign(new Error('Request failed with status code 409'), {
        response: { status: 409, data: { detail } },
      })
    )

    renderGrid([makeCard({ status: 'QUEUED' })])

    fireEvent.click(screen.getByTitle('Change status'))
    fireEvent.click(screen.getByRole('button', { name: 'ONGOING' }))

    await waitFor(() =>
      expect(
        screen.getByText(/already occupied by ONGOING experiment 'HPHT_222'/)
      ).toBeInTheDocument()
    )
  })

  it('falls back to a generic message when the error carries no detail', async () => {
    vi.mocked(experimentsApi.patchStatus).mockRejectedValueOnce(
      Object.assign(new Error('Network Error'), { response: undefined })
    )

    renderGrid([makeCard({ status: 'QUEUED' })])

    fireEvent.click(screen.getByTitle('Change status'))
    fireEvent.click(screen.getByRole('button', { name: 'ONGOING' }))

    await waitFor(() =>
      expect(screen.getByText('Could not update status')).toBeInTheDocument()
    )
  })
})
```

Add to `frontend/src/pages/__tests__/ExperimentList.test.tsx`. First extend its `wrapper` (line 52) to include the provider — this is a required change, not optional, because `ExperimentListPage` will now call `useToast()`:

```tsx
// add to the existing imports:
//   import { ToastProvider } from '@/components/ui'

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>{children}</ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>
  )
}
```

Then add the test. The inline control is `<select aria-label="Row status">` at `ExperimentList.tsx:344-361`, one per row, firing `statusMutation.mutate` on `onChange`. `makeItems` yields rows already at `ONGOING`, and a `<select>` `onChange` does not fire when the value is unchanged — so change the first row to `COMPLETED`, which still exercises the same mutation and the same `onError`. (Only the *server* gates the transition to ONGOING; the client sends whatever was picked.)

Note `statusReadOnly` (line 339) renders a plain badge instead of the select for a row standing for more than one vial. `makeItems` sets `base_experiment_id: null` and `replicate_label: null`, so the select renders — do not change those fields.

```tsx
describe('ExperimentList — inline status 409 (issue #97)', () => {
  it('shows the server message when an inline status change is rejected', async () => {
    const detail =
      "Reactor CF01 is already occupied by ONGOING experiment 'CF_018-3' (started 2026-07-24). Complete or cancel it before starting 'EXP_001'."
    vi.mocked(experimentsApi.patchStatus).mockRejectedValueOnce(
      Object.assign(new Error('Request failed with status code 409'), {
        response: { status: 409, data: { detail } },
      })
    )

    render(<ExperimentListPage />, { wrapper })
    await waitFor(() => expect(screen.getByText('EXP_001')).toBeInTheDocument())

    const selects = screen.getAllByLabelText('Row status')
    fireEvent.change(selects[0], { target: { value: 'COMPLETED' } })

    await waitFor(() =>
      expect(
        screen.getByText(/already occupied by ONGOING experiment 'CF_018-3'/)
      ).toBeInTheDocument()
    )
  })
})
```

This relies on the file's existing `beforeEach` already resolving `experimentsApi.list` — read it and reuse it rather than re-mocking `list` inside the test.

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npx vitest run src/pages/__tests__/ReactorGrid.test.tsx src/pages/__tests__/ExperimentList.test.tsx`
Expected: both new tests fail — nothing renders the message, because neither mutation has an `onError`.

- [ ] **Step 3: Add the error handlers**

In `frontend/src/pages/ReactorGrid.tsx`, replace lines 64-70:

```tsx
  const { mutate, isPending } = useMutation({
    mutationFn: (newStatus: ExperimentStatus) =>
      experimentsApi.patchStatus(card.experiment_id!, newStatus),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
```

with:

```tsx
  const { mutate, isPending } = useMutation({
    mutationFn: (newStatus: ExperimentStatus) =>
      experimentsApi.patchStatus(card.experiment_id!, newStatus),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    // Without this a 409 from the occupancy check (issue #97) is swallowed: the
    // dropdown snaps back and the user is told nothing. The server's detail
    // names the occupying experiment and its start date, so show it verbatim.
    onError: (err: Error) => {
      toastError('Update failed', err.message || 'Could not update status')
    },
  })
```

**Use the two-argument toast form.** `useToast`'s signature is
`error(title: string, message?: string)` (`frontend/src/components/ui/Toast.tsx:15`),
and the two neighbouring handlers in `ReactorGrid.tsx` (~`:309`, `:329`) both pass a
short title plus a descriptive body. A one-argument call renders the whole
~130-character server sentence as a bold title in a `max-w-[360px]` card. Put the
short label in the title and the server detail in the body.

**Test the real network-failure path, not an unreachable branch.** Axios never
produces an empty `.message` — a genuine failure carries `"Network Error"` or
`"timeout of Xms exceeded"`, and the interceptor leaves those untouched because
there is no `response.data.detail`. So `err.message || fallback` effectively never
reaches its fallback in production. Model a real network error in the test and
assert the user still gets an intelligible toast; keep the `||` as defensive code
but do not assert it as the contract.

**Do NOT write a detail-extraction helper.** `frontend/src/api/client.ts:11-23` already installs an
Axios response interceptor that copies FastAPI's `detail` onto `error.message`
(flattening a validation-error array to a comma-joined string). So by the time any
mutation's `onError` runs, the 409's detail is already `err.message`. The correct
handler is therefore just:

```tsx
    onError: (err: Error) => {
      toastError(err.message || 'Could not update status')
    },
```

An `extractErrorDetail` util would duplicate the interceptor and give two competing
answers to the same question. (Five components do extract `response.data.detail`
inline, but for non-toast purposes; none of them is a precedent to follow here.)

`ReactorGrid.tsx` already imports `useToast` at line 4 and destructures
`{ success, error: toastError }` at line 269 — but that is in a **different
component**. The mutation you are changing lives in `StatusBadge` (around line 64),
which has no `useToast()` call of its own; add one there. Do not reach for the
other component's binding.

`ExperimentList.tsx` has no `useToast` at all — add the import and the hook call to
that page.

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `frontend/`):
```bash
npx vitest run
npx tsc --noEmit
```
Expected: all tests pass (196 + 2 across 31 files before this task), `tsc` clean.

Run: `npx eslint src --ext .ts,.tsx`
Expected: exactly the 5 known pre-existing errors — `src/components/CompoundFormModal.tsx:41,57`, `src/pages/ExperimentDetail/__tests__/ConditionsTab.buttons.test.tsx:61,83`, `NotesTab.buttons.test.tsx:50`. No new ones. Do not fix the 5; they have their own ticket (`docs/issues/issue-eslint-baseline.md`).

**Do not touch `frontend/package.json`.** No new dependency is needed here, and `package.json` / `package-lock.json` must only ever move together (CLAUDE.md §5).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ReactorGrid.tsx frontend/src/pages/ExperimentList.tsx frontend/src/pages/__tests__/ReactorGrid.test.tsx frontend/src/pages/__tests__/ExperimentList.test.tsx
git commit -m "[#97] Surface reactor occupancy 409 in the UI

- Both status mutations had no onError at all
- Tests added: yes
- Docs updated: no"
```

---

## Task 9: Documentation and the follow-up issue for the constraint

**Files:**
- Modify: `.claude/rules/MODELS.md` (the `ExperimentalConditions` section)
- Modify: `docs/api/API_REFERENCE.md` (the `PATCH /api/experiments/{id}/status` entry)
- Modify: `docs/issues/issue-reactor-slot-identity-and-occupancy-uniqueness.md` (status header)
- Create: `docs/issues/issue-reactor-occupancy-uniqueness-trigger.md`
- Modify: `docs/working/issue-log.md` (append at the bottom)

The `PostToolUse` hook syncs every file written under `docs/` (except `docs/working/` and `docs/superpowers/`) into `docs/project_context/` automatically. Never write to `docs/project_context/` directly.

- [ ] **Step 1: Document the column in MODELS.md**

In the `### ExperimentalConditions` section of `.claude/rules/MODELS.md`, add under **Key Fields** after the `reactor_number` line:

```markdown
  - `reactor_slot` (String(8), nullable, indexed): canonical physical slot label — `R01`–`R16` (HPHT vessels) or `CF01`–`CF03` (Core Flood rigs). **`NULL` means the experiment holds no physical slot**: a non-occupancy `experiment_type` (Serum / Autoclave / Other), a missing `reactor_number`, or `reactor_number <= 0`.
    - **Derived — never set it by hand.** `database/reactor_slot.py::derive_reactor_slot` is the only definition of the mapping; the `before_insert`/`before_update` listener `set_reactor_slot` in `database/event_listeners.py` writes it on every ORM write. A direct assignment is overwritten on the next flush.
    - **This is the key for every occupancy comparison** (issue #97). `reactor_number` alone conflates `R01` with `CF01` — two different vessels sharing the number 1 — which let a Core Flood going ONGOING silently set a running HPHT to COMPLETED. Sites now keyed on it: `experiment_status.py` (both occupant queries and the same-file conflict map), `new_experiments.py` (both occupancy call sites), `PATCH /api/experiments/{id}/status`, `dashboard.py` (reactor cards and `/reactor-status`), `notion_sync/import_.py`, `notion_sync/export.py`.
    - **Pre-flush caveat:** the listener runs *during* flush, so code that has just assigned a new `reactor_number` must call `derive_reactor_slot(...)` rather than read `.reactor_slot`. Production `SessionLocal` sets `autoflush=False`.
    - **Bulk-update caveat:** the listener does NOT fire for a bulk `Query.update()` / Core `UPDATE`, which compiles to SQL without per-row mapper events. `database/data_migrations/swap_reactor_4_7_015.py:96-109` is the existing precedent for that idiom (it predates this column, and the Task 2 backfill left the DB self-consistent). Any future script changing `reactor_number` or `experiment_type` that way must either avoid `Query.update()` for those columns or recompute `reactor_slot` explicitly in the same script. Every other write path in the codebase loads an ORM instance and mutates attributes, which does fire the listener.
    - `reactor_number` is retained unchanged — Power BI views, `database/data_migrations/swap_reactor_4_7_015.py` and the `GET /api/experiments?reactor_number=` filter all read it.
    - **Still not enforced:** nothing prevents two ONGOING experiments sharing a `reactor_slot`. The one-ONGOING-per-slot trigger and `CHECK (reactor_number > 0)` are tracked in `docs/issues/issue-reactor-occupancy-uniqueness-trigger.md`, blocked on the cleanup in `docs/issues/audit-2026-07-28-results-and-cleanup.md`. Until then the `seen_labels` dedup at `dashboard.py:126-140` still hides a double-booked slot from the grid, and `summary.reactors.empty` reads one too high per double-booking.
```

- [ ] **Step 2: Document the 409 in API_REFERENCE.md**

Find the `PATCH /api/experiments/{experiment_id}/status` entry and add to its response list:

```markdown
- `409 Conflict` — the transition to `ONGOING` was rejected because another experiment is already `ONGOING` in the same physical reactor slot. `detail` names the slot, the occupying `experiment_id` and its start date, e.g. `Reactor R08 is already occupied by ONGOING experiment 'HPHT_222' (started 2026-07-24). Complete or cancel it before starting 'HPHT_230'.` The occupant is **not** demoted — this endpoint cannot distinguish advancing a sequential re-run from a mis-picked reactor. Only the transition *to* `ONGOING` is gated; `COMPLETED` / `CANCELLED` / `QUEUED` are never blocked, and an experiment with no physical slot (Serum, Autoclave, Other, or no `reactor_number`) is never blocked.
```

Also add `reactor_slot` to the documented `ConditionsResponse` fields wherever that schema is listed, marked read-only/derived.

- [ ] **Step 3: Mark the issue partially shipped**

At the top of `docs/issues/issue-reactor-slot-identity-and-occupancy-uniqueness.md`, immediately after the existing `> **Verified against** ...` blockquote, insert:

```markdown
> **Status 2026-07-29 — §1, §2 and §3 SHIPPED on `fix/issue-97-reactor-slot-identity`. §4 SPLIT OUT.**
> The `reactor_slot` column, its backfill, the event listener, all four occupancy
> comparison sites, both `new_experiments.py` gates and the `PATCH /status` 409 are
> done. **§4 (the PL/pgSQL uniqueness trigger and the `reactor_number > 0` CHECK) is
> NOT done** — it is tracked separately in
> `issue-reactor-occupancy-uniqueness-trigger.md`, blocked on the cleanup in
> `audit-2026-07-28-results-and-cleanup.md`. Two consequences of that split, both
> deliberate: the `seen_labels` dedup at `dashboard.py:126-140` is still in place
> (the issue says delete it only after the constraint is verified), and
> `summary.reactors.empty` still reads one too high per double-booked slot.
```

- [ ] **Step 4: File the follow-up issue**

Create `docs/issues/issue-reactor-occupancy-uniqueness-trigger.md` covering, at minimum:

- **Blocked on:** the Part A status changes (via the app UI) and Part B data migration `018` specified in `docs/issues/audit-2026-07-28-results-and-cleanup.md`. Neither has been done: `database/data_migrations/018*` does not exist, and as of 2026-07-29 the dev DB has 5 double-booked slots (`CF01`×6, `CF03`×5, `R00`×8, `R01`×6, `R06`×2) and 13 rows with `reactor_number = 0`. Prod had 2 slots and 11 zeros on 2026-07-28. **Both verification queries at the bottom of the audit file must return zero rows before this migration is written.**
- **Why the ordering is not optional:** `update.ps1` runs `alembic upgrade head` on the lab PC nightly. A migration that fails against live data breaks the deploy pipeline until someone fixes it on the lab PC by hand.
- **What #97 already delivered that this builds on:** `reactor_slot` is populated and is the key for every occupancy comparison, so the trigger is a one-column check. `reactor_slot` is already NULL for `reactor_number <= 0`, so the `R00` class is already excluded from occupancy logic — the CHECK constraint is now about data hygiene, not correctness.
- **The three implementation requirements** copied verbatim from §4 of the original issue: a loud comment in `database/models/conditions.py` pointing at the migration (a trigger is invisible to anyone reading the models); readable per-row bulk-upload errors catching `unique_violation` rather than a 500 on a 200-row upload; and `SELECT ... FOR UPDATE` on the candidate occupant rather than a bare `count(*)`.
- **The design constraint** that makes a partial unique index impossible: `Experiment.status` and `ExperimentalConditions.reactor_slot` are on different tables, and Postgres partial unique indexes and exclusion constraints are both single-table. Rejected alternatives (claim table, denormalizing `status`) recorded so they are not relitigated.
- **Pass `newer_than` on the new-experiments path, in the same change as the trigger.** #97 fixed the eligibility gate and the falsy-zero bug at `new_experiments.py` (both occupancy call sites) but deliberately left `newer_than` omitted, because the issue's own rationale for passing it is "let the trigger be the backstop" and there was no trigger. Doing it here is safe and is the last piece of §3. Expect `tests/services/bulk_uploads/test_new_experiments.py::test_reactivation_via_overwrite_demotes_prior_reactor_occupant` (line 79) to need updating when it lands — it seeds a dateless occupant and asserts demotion, which is exactly the case the guard changes.
- **Two cleanups gated on the constraint:** delete the `seen_labels` dedup at `dashboard.py:126-140` (dead once uniqueness is enforced, and while it exists it hides violations from `_occupancy`), and re-verify `summary.reactors.empty`.
- **The open question from the audit:** whether autoclave runs occupy the numbered HPHT vessels. Answered "no" for #97 (2026-07-29) and encoded in `_SERIES_BY_TYPE` in `database/reactor_slot.py`; it must be re-confirmed before the trigger scope is fixed, because a trigger scoped to two series will not stop an Autoclave and an HPHT both claiming R01.

Then file it:

```bash
gh issue create --title "bug: nothing enforces one ONGOING experiment per reactor slot" \
  --body-file docs/issues/issue-reactor-occupancy-uniqueness-trigger.md \
  --label bug --label data-integrity --label database
```

Record the returned issue number back into the file's header and into the status blockquote from Step 3. If any label does not exist on the repo, drop it rather than creating new labels.

- [ ] **Step 4b: Repair references to the two deleted helpers**

Task 4 deleted `_normalize_type` and `_is_eligible_for_occupancy` from
`experiment_status.py`, and `_OCCUPANCY_TYPES` with them. Three **live** docs still
name them as though they exist and will mislead whoever reads them next:

- `docs/issues/issue-reactor-slot-identity-and-occupancy-uniqueness.md` — the source
  issue for this branch. Note in the relevant passages that the eligibility gate is
  now `derive_reactor_slot(...) is None` in `database/reactor_slot.py`, not a local
  type set.
- `docs/issues/issue-experiment-type-enum-binding.md` — an **open** follow-up ticket.
  Most important of the three: whoever picks it up will go looking for functions that
  no longer exist.
- `docs/issues/audit-2026-07-28-results-and-cleanup.md` — its "settle before writing
  the trigger" open question is framed around `_OCCUPANCY_TYPES`. Point it at
  `_SERIES_BY_TYPE` in `database/reactor_slot.py` instead, and record that the
  autoclave question was answered "no" on 2026-07-29.

Do **not** rewrite these, which are historical records of completed work:
`docs/superpowers/plans/2026-07-22-issue-66-experiment-status-per-row.md` and
`docs/working/plan.md`. A finished plan describing the code as it was at the time is
not stale — it is a record.

- [ ] **Step 5: Append the issue-log entry**

Append a `## 2026-07-29 | issue #97 — ...` entry at the bottom of `docs/working/issue-log.md`, following the shape of the existing entries: files changed with one-line reasons, tests added with real counts from the final run, the scope boundary (what §4 covers and why it was split), the four decisions Mat made at scope confirmation, and anything discovered-but-not-fixed. State test numbers you actually observed — do not estimate.

- [ ] **Step 6: Commit**

```bash
git add .claude/rules/MODELS.md docs/api/API_REFERENCE.md docs/issues/ docs/working/issue-log.md docs/project_context/
git commit -m "[#97] Document reactor slot, split out the trigger

- Tests added: no
- Docs updated: yes"
```

---

## Final verification before merge

Run all of these and record the real output. Do not claim any of it passed without seeing it.

- [ ] **Backend suite:** `.venv/Scripts/pytest tests/api tests/services tests/models tests/views tests/test_reactor_slot.py -q`
      Expected: zero failures. (`tests/test_pg_backup_restore.py` has 3 known pre-existing failures caused by `drop_all()` wiping `experiments_test`; it is excluded above. If you run the whole suite, verify those 3 also fail on `develop` before dismissing them.)
- [ ] **Frontend:** from `frontend/`, `npx vitest run` and `npx tsc --noEmit` and `npx eslint src --ext .ts,.tsx` (5 pre-existing errors, no new).
- [ ] **Lint the changed Python:** `.venv/Scripts/flake8` on each modified file. `new_experiments.py` and `experiment_status.py` carry extensive pre-existing violations — check the added lines specifically via `git diff`, not by line-number range, since insertions shift the file (a lesson from #100).
- [ ] **Migration round-trip on a real DB:** `.venv/Scripts/alembic upgrade head` → `downgrade -1` → `upgrade head`, all clean.
- [ ] **Backfill sanity on the dev DB:** re-run the two queries from Task 2 Step 5. Zero occupancy-type rows with `reactor_number > 0` may be left with a NULL slot.
- [ ] **Recreate the reporting views** and confirm none broke: `.venv/Scripts/python -c "import database.event_listeners"` (view creation runs on import and logs failures). No view reads `reactor_slot`, so this is a smoke check, not a change.

### Manual verification in the running app

The server is already running on port 8000 — do not restart it. Previous sessions found real defects here that the automated suite could not (a 4×404 burst on delete, a "1 external analysises" plural bug), so this is not optional.

- [ ] Dashboard renders the reactor grid with the same occupied slots as before the change, and the R/CF split is unchanged.
- [ ] `summary.reactors` and `summary.core_floods` totals match what `/api/dashboard/` returned on `develop` for the same DB state.
- [ ] The eight `SERUM_JW_153`–`160` vials (`reactor_number = 0`, Serum) do **not** appear anywhere in the grid, and no `R00` card renders.
- [ ] Change a QUEUED HPHT to ONGOING on an occupied slot via the reactor pop-out: a toast appears naming the occupying experiment and its start date; the dropdown does not appear to have succeeded; the occupant is still ONGOING after a refresh.
- [ ] Do the same on an empty slot: it succeeds with no toast, and the card updates without a reload.
- [ ] Zero console errors and zero console warnings throughout.
- [ ] Open an experiment's Conditions tab, change the reactor number, save, and confirm the dashboard slot moves.

### What this branch does not fix, to state plainly in the PR

- Two ONGOING experiments can still share a slot — there is no constraint. The dashboard still hides the second one and `summary.reactors.empty` still reads one too high per double-booking. Tracked in the new follow-up issue.
- The **4** double-booked slots and 13 `reactor_number = 0` rows in the dev DB (and 2 / 11 in prod) are untouched. Cleaning them is Part A + Part B of `audit-2026-07-28-results-and-cleanup.md`, deliberately a separate human-run session. Note `R00` is not among the 4 — see the corrected figures above.
- `experiment_type` is still un-normalized (`SERUM` vs `Serum`), so the #85 Serum KPI is still undercounting by ~72%. `database/reactor_slot.py` tolerates every spelling, but the KPI predicate at `dashboard.py:212` is untouched. Tracked in `issue-experiment-type-enum-binding.md`.
