# Issue #69 — Replicate Handling Core (P1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support lowercase-letter replicate IDs (`SERUM_001a/b/c`), link them to a shared parent ("replicate 0"), and expose cross-replicate mean/median/std through a new reporting view — without touching the per-row calculation engine.

**Architecture:** Extend the existing string-parsing lineage system (`database/lineage_utils.py` and `backend/services/experiment_validation.py`) to recognize a trailing lowercase letter bound to the numeric index, add one nullable `replicate_label` column to `Experiment`, and add a `v_results_scalar_rollup` SQL view that aggregates by `COALESCE(base_experiment_id, experiment_id)` + timepoint bucket. Everything else (UI grouping, bulk-upload routing, outlier flags) is out of scope.

**Tech Stack:** Python 3.13, SQLAlchemy 2.x ORM, Alembic, PostgreSQL (`percentile_cont`, `stddev_samp` window/aggregate functions), pytest, React/TypeScript (help-text only, no logic change).

## Global Constraints

- Replicate marker: a single lowercase letter `[a-z]` immediately following the numeric index (`SERUM_001a`). Never `aa`/`ab`. Only `a`, `b`, `c` occur in practice but the grammar allows any single letter.
- Replicate 0 = the parent = the bare stem `TYPE_[TAG_]NUMBER`. `S-0` and `S-1` are also accepted spellings of "the group parent" — this redefines what `-0`/`-1` suffixes mean across the *entire* lineage system, not just for replicates (locked decision from the issue, do not revisit).
- Grouping key for reporting: `COALESCE(base_experiment_id, experiment_id)` (existing pattern, unchanged) — except the `v_results_scalar` cumulative window, which changes to `PARTITION BY e.experiment_id` only (per-vial, not cross-replicate).
- Conflict handling on creation: existing IDs must fail with a clear, non-fatal message — never crash, never silently overwrite.
- All Alembic migrations must be additive with a working `upgrade` and `downgrade`.
- `backend/services/bulk_uploads/new_experiments.py` is a locked component; this issue explicitly authorizes only a mechanical tuple-arity fix inside it (no parser logic changes). `database/models/experiments.py` gets exactly one additive nullable column (single model — no cross-model schema change, no escalation needed per `db-architect.md`).
- **Do not start P2–P5** (experiments-list grouping UI, bulk-upload replicate-column routing, outlier flag, parser consolidation, full letter+sequential parent-wiring for `SERUM_001a-2`). Stop once every acceptance box below is green and the work is committed.
- Verification commands (run before claiming done): `.venv/Scripts/python -m pytest tests/ -q`, `.venv/Scripts/alembic upgrade head`, `.venv/Scripts/alembic downgrade -1 && .venv/Scripts/alembic upgrade head`.

---

### Task 1: Add `replicate_label` column to `Experiment` + migration

**Files:**
- Modify: `database/models/experiments.py:20-23`
- Create: `alembic/versions/<autogen>_add_replicate_label_to_experiments.py`
- Test: `tests/models/test_replicate_label_column.py`

**Interfaces:**
- Produces: `Experiment.replicate_label: Optional[str]` — nullable, indexed String column. Later tasks (2, 3) read/write this attribute directly.

- [ ] **Step 1: Write the failing model test**

Create `tests/models/test_replicate_label_column.py`:

```python
"""Tests for the Experiment.replicate_label column (issue #69)."""
import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from database.models import Experiment

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(TEST_DB_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


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


def test_replicate_label_defaults_to_null(db):
    exp = Experiment(
        experiment_id="RLBL_COL_001",
        experiment_number=900001,
        status="ONGOING",
        date=datetime.date(2026, 1, 1),
    )
    db.add(exp)
    db.flush()
    assert exp.replicate_label is None


def test_replicate_label_accepts_single_letter(db):
    exp = Experiment(
        experiment_id="RLBL_COL_002a",
        experiment_number=900002,
        status="ONGOING",
        date=datetime.date(2026, 1, 1),
        replicate_label="a",
    )
    db.add(exp)
    db.flush()
    assert exp.replicate_label == "a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/models/test_replicate_label_column.py -v`
Expected: FAIL — `TypeError: 'replicate_label' is an invalid keyword argument for Experiment` (column doesn't exist yet).

- [ ] **Step 3: Add the column to the model**

In `database/models/experiments.py`, find:

```python
    # Lineage tracking fields
    base_experiment_id = Column(String, nullable=True, index=True)  # Base experiment ID (e.g., "HPHT_MH_001" for "HPHT_MH_001-2")
    parent_experiment_fk = Column(Integer, ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True)  # FK to parent experiment
```

Replace with:

```python
    # Lineage tracking fields
    base_experiment_id = Column(String, nullable=True, index=True)  # Base experiment ID (e.g., "HPHT_MH_001" for "HPHT_MH_001-2")
    parent_experiment_fk = Column(Integer, ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True)  # FK to parent experiment
    replicate_label = Column(String, nullable=True, index=True)  # "a", "b", "c"; NULL = not a replicate. is_replicate == (replicate_label IS NOT NULL)
```

- [ ] **Step 4: Generate the Alembic migration**

Run: `.venv/Scripts/alembic revision --autogenerate -m "add replicate_label to experiments"`

This creates `alembic/versions/<hash>_add_replicate_label_to_experiments.py` with `down_revision = 'ca5d57c6b272'` (current head). Open it and confirm/edit it to read exactly:

```python
"""add replicate_label to experiments

Revision ID: <hash>
Revises: ca5d57c6b272
Create Date: <autogenerated>

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '<hash>'
down_revision: Union[str, None] = 'ca5d57c6b272'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('experiments', sa.Column('replicate_label', sa.String(), nullable=True))
    op.create_index(op.f('ix_experiments_replicate_label'), 'experiments', ['replicate_label'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_experiments_replicate_label'), table_name='experiments')
    op.drop_column('experiments', 'replicate_label')
```

- [ ] **Step 5: Apply and round-trip the migration**

Run: `.venv/Scripts/alembic upgrade head`
Expected: applies cleanly, no errors.

Run: `.venv/Scripts/alembic downgrade -1 && .venv/Scripts/alembic upgrade head`
Expected: both succeed with no errors (clean round-trip).

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/models/test_replicate_label_column.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add database/models/experiments.py alembic/versions/*_add_replicate_label_to_experiments.py tests/models/test_replicate_label_column.py
git commit -m "$(cat <<'EOF'
[#69] Add replicate_label column to Experiment

- Additive migration, upgrade/downgrade round-trip verified
- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 2: `lineage_utils.parse_experiment_id` — 4-tuple with replicate-letter grammar

**Files:**
- Modify: `database/lineage_utils.py:22-90`
- Test: `tests/test_replicate_lineage.py` (new file — parsing section)

**Interfaces:**
- Produces: `parse_experiment_id(experiment_id: str) -> Tuple[Optional[str], Optional[int], Optional[str], Optional[str]]` returning `(base_experiment_id, derivation_num, treatment_variant, replicate_label)`. Task 3 consumes this 4-tuple in `get_or_find_parent_experiment`, `update_experiment_lineage`, `auto_create_treatment_experiment`, and the `find_replicate_group_parent` helper it adds.

- [ ] **Step 1: Write the failing parsing tests**

Create `tests/test_replicate_lineage.py`:

```python
"""Tests for replicate-letter support in experiment ID lineage parsing (issue #69)."""
import pytest

from database.lineage_utils import parse_experiment_id


class TestParseExperimentIdReplicateGrammar:
    """4-tuple (base_experiment_id, derivation_num, treatment_variant, replicate_label)."""

    def test_bare_stem(self):
        assert parse_experiment_id("SERUM_001") == ("SERUM_001", None, None, None)

    def test_explicit_parent_dash_0(self):
        assert parse_experiment_id("SERUM_001-0") == ("SERUM_001", 0, None, None)

    def test_explicit_parent_dash_1(self):
        assert parse_experiment_id("SERUM_001-1") == ("SERUM_001", 1, None, None)

    def test_replicate_letter_two_part(self):
        assert parse_experiment_id("SERUM_001a") == ("SERUM_001", None, None, "a")

    def test_replicate_letter_three_part(self):
        assert parse_experiment_id("Serum_MH_101a") == ("Serum_MH_101", None, None, "a")

    def test_replicate_letter_does_not_degrade_to_treatment(self):
        # Regression guard: must NOT parse as base="Serum_MH", treatment="101a"
        result = parse_experiment_id("Serum_MH_101a")
        assert result[0] == "Serum_MH_101"
        assert result[2] is None

    def test_replicate_letter_plus_sequential(self):
        assert parse_experiment_id("SERUM_001a-2") == ("SERUM_001", 2, None, "a")

    def test_type_prefixed_id_unaffected(self):
        assert parse_experiment_id("CF-015") == ("CF-015", None, None, None)

    def test_existing_sequential_unaffected(self):
        assert parse_experiment_id("HPHT_MH_001-2") == ("HPHT_MH_001", 2, None, None)

    def test_existing_treatment_unaffected(self):
        assert parse_experiment_id("HPHT_MH_001_Desorption") == ("HPHT_MH_001", None, "Desorption", None)

    def test_existing_combined_sequential_treatment_unaffected(self):
        assert parse_experiment_id("HPHT_MH_001-2_Desorption") == ("HPHT_MH_001", 2, "Desorption", None)

    def test_empty_and_none(self):
        assert parse_experiment_id("") == (None, None, None, None)
        assert parse_experiment_id(None) == (None, None, None, None)
        assert parse_experiment_id("   ") == (None, None, None, None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_replicate_lineage.py -v`
Expected: FAIL — `ValueError: not enough values to unpack` is NOT what happens here (the function returns a 3-tuple and we're comparing to a 4-tuple literal, so these are plain `assert ... == ...` failures, e.g. `AssertionError: assert ('SERUM_001', None, None) == ('SERUM_001', None, None, None)`).

- [ ] **Step 3: Rewrite `parse_experiment_id` in `database/lineage_utils.py`**

Replace the entire function (lines 22-90) with:

```python
_REPLICATE_LETTER_RE = re.compile(r'^(\d+)([a-z])$')
_REPLICATE_GUARD_RE = re.compile(r'^\d+[a-z]$')


def parse_experiment_id(experiment_id: str) -> Tuple[Optional[str], Optional[int], Optional[str], Optional[str]]:
    """
    Parse an experiment ID to extract the base ID, derivation number, treatment variant,
    and replicate label.

    Uses hybrid delimiter system:
    - Hyphen-NUMBER for sequential lineage (e.g., -2, -3), but ONLY when the prefix
      itself ends in a numeric segment (_NNN or -NNN, optionally letter-suffixed).
    - Underscore-TEXT for treatment variants (e.g., _Desorption).
    - A single trailing lowercase letter bound to the numeric index for replicates
      (e.g., _001a). Extracted last so a letter-suffixed index is never mistaken
      for a treatment name.

    TYPE-NNN IDs (e.g., CF-015, CF-04) are treated as standalone base experiments
    because their prefix ("CF") does not end in digits.

    -0 and -1 are valid derivation numbers (they denote the explicit "group parent"
    spelling of a replicate set — see database/lineage_utils.py::update_experiment_lineage).

    Args:
        experiment_id: The experiment ID to parse

    Returns:
        A tuple of (base_experiment_id, derivation_number, treatment_variant, replicate_label)

    Examples:
        >>> parse_experiment_id("CF-015")
        ("CF-015", None, None, None)
        >>> parse_experiment_id("CF-015-2")
        ("CF-015", 2, None, None)
        >>> parse_experiment_id("HPHT_MH_001-2")
        ("HPHT_MH_001", 2, None, None)
        >>> parse_experiment_id("HPHT_MH_001-2_Desorption")
        ("HPHT_MH_001", 2, "Desorption", None)
        >>> parse_experiment_id("HPHT_MH_001")
        ("HPHT_MH_001", None, None, None)
        >>> parse_experiment_id("HPHT_MH_001_Desorption")
        ("HPHT_MH_001", None, "Desorption", None)
        >>> parse_experiment_id("SERUM_001-0")
        ("SERUM_001", 0, None, None)
        >>> parse_experiment_id("SERUM_001a")
        ("SERUM_001", None, None, "a")
        >>> parse_experiment_id("Serum_MH_101a")
        ("Serum_MH_101", None, None, "a")
        >>> parse_experiment_id("SERUM_001a-2")
        ("SERUM_001", 2, None, "a")
    """
    if not experiment_id or not isinstance(experiment_id, str):
        return None, None, None, None

    experiment_id = experiment_id.strip()
    if not experiment_id:
        return None, None, None, None

    treatment_variant = None
    derivation_num = None
    replicate_label = None
    base_id = experiment_id

    # Step 1: Extract treatment variant (trailing _TEXT segment).
    # A trailing underscore segment is a treatment only when:
    #   - it is not a letter-suffixed numeric index (e.g. "101a") — replicate guard
    #   - it contains no hyphens (so "001-2" is not mistaken for a treatment)
    #   - it is not all digits (so "001" index segments are left alone)
    #   - removing it still leaves a structured ID with >= 2 underscore-segments
    #     (prevents "CF_Desorption" from stripping "Desorption" off a 1-part base)
    parts = experiment_id.split('_')
    if len(parts) >= 2:
        last = parts[-1]
        if not _REPLICATE_GUARD_RE.match(last) and not last.isdigit() and '-' not in last:
            remaining = '_'.join(parts[:-1])
            if len(remaining.split('_')) >= 2:
                treatment_variant = last
                base_id = remaining

    # Step 2: Extract sequential derivation number (trailing -N).
    # Only treat -N as a derivation when the prefix already ends in _NNN or -NNN
    # (optionally letter-suffixed, e.g. "_001a"), confirming it carries a numeric index.
    # This prevents TYPE-NNN IDs like CF-015 from being parsed as deriv=15 of "CF".
    # -0 and -1 are valid derivation numbers (see docstring).
    if '-' in base_id:
        prefix, _, suffix = base_id.rpartition('-')
        if suffix.isdigit() and re.search(r'[_-]\d+[a-z]?$', prefix):
            derivation_num = int(suffix)
            base_id = prefix

    # Step 3: Extract the replicate letter bound to the numeric index and rebuild
    # base_id with the numeric-only index (e.g. "SERUM_001a" -> "SERUM_001").
    id_parts = base_id.split('_')
    letter_match = _REPLICATE_LETTER_RE.match(id_parts[-1])
    if letter_match:
        replicate_label = letter_match.group(2)
        id_parts[-1] = letter_match.group(1)
        base_id = '_'.join(id_parts)

    return base_id, derivation_num, treatment_variant, replicate_label
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_replicate_lineage.py -v`
Expected: 12 passed.

Note: this change breaks every other caller of `lineage_utils.parse_experiment_id` (they still unpack 3 values) and two existing test files that assert 3-tuple equality. Task 3 fixes the lineage-wiring callers; Task 4 fixes the remaining mechanical unpack sites and existing test assertions. **Do not run the full test suite yet** — it will fail until Tasks 3 and 4 land.

- [ ] **Step 5: Commit**

```bash
git add database/lineage_utils.py tests/test_replicate_lineage.py
git commit -m "$(cat <<'EOF'
[#69] Parse replicate letter in lineage_utils.parse_experiment_id

- 4-tuple return: adds replicate_label
- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 3: Lineage wiring — parent resolution, orphan back-linking, before_flush listener

**Files:**
- Modify: `database/lineage_utils.py` (`get_or_find_parent_experiment`, `update_experiment_lineage`, `update_orphaned_derivations`, `auto_create_treatment_experiment`; add `find_replicate_group_parent`)
- Modify: `database/event_listeners.py:636-666` (`update_experiment_lineage_on_flush`)
- Test: `tests/test_replicate_lineage.py` (new sections, DB-backed)

**Interfaces:**
- Consumes: `parse_experiment_id` (4-tuple, from Task 2), `Experiment.replicate_label` (from Task 1).
- Produces: `find_replicate_group_parent(db: Session, base_id: str) -> Optional[Experiment]` — resolves the group parent in precedence order (bare stem, `-0`, `-1`). Used by `update_experiment_lineage` and `update_orphaned_derivations`.

- [ ] **Step 1: Write the failing DB-backed lineage tests**

Append to `tests/test_replicate_lineage.py`:

```python
import os
import sys
import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import Base
from database.models import Experiment
from database.models.enums import ExperimentStatus
from database.lineage_utils import update_experiment_lineage, find_replicate_group_parent


@pytest.fixture
def sqlite_session():
    """In-memory SQLite session with JSONB columns patched to JSON (SQLite has no JSONB)."""
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB

    original_types = {}
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                original_types[(table.name, col.name)] = col.type
                col.type = JSON()

    engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        for table in Base.metadata.tables.values():
            for col in table.columns:
                key = (table.name, col.name)
                if key in original_types:
                    col.type = original_types[key]


def _make_exp(session, experiment_id, number, replicate_label=None):
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=number,
        status=ExperimentStatus.ONGOING,
        date=datetime.date(2026, 1, 1),
    )
    session.add(exp)
    session.flush()  # before_flush listener sets base_experiment_id/parent_experiment_fk/replicate_label
    return exp


class TestReplicateLineageWiring:
    def test_replicate_gets_base_and_label_no_parent_yet(self, sqlite_session):
        rep_a = _make_exp(sqlite_session, "REP1_001a", 910001)
        assert rep_a.base_experiment_id == "REP1_001"
        assert rep_a.replicate_label == "a"
        assert rep_a.parent_experiment_fk is None

    def test_replicate_links_to_existing_bare_stem_parent(self, sqlite_session):
        parent = _make_exp(sqlite_session, "REP2_001", 910010)
        rep_a = _make_exp(sqlite_session, "REP2_001a", 910011)
        rep_b = _make_exp(sqlite_session, "REP2_001b", 910012)
        assert rep_a.parent_experiment_fk == parent.id
        assert rep_b.parent_experiment_fk == parent.id
        assert parent.base_experiment_id == "REP2_001"
        assert parent.parent_experiment_fk is None

    def test_replicate_links_to_existing_dash0_parent(self, sqlite_session):
        parent = _make_exp(sqlite_session, "REP3_001-0", 910020)
        rep_a = _make_exp(sqlite_session, "REP3_001a", 910021)
        assert parent.base_experiment_id == "REP3_001"
        assert parent.parent_experiment_fk is None
        assert rep_a.parent_experiment_fk == parent.id

    def test_replicate_links_to_existing_dash1_parent(self, sqlite_session):
        parent = _make_exp(sqlite_session, "REP4_001-1", 910030)
        rep_a = _make_exp(sqlite_session, "REP4_001a", 910031)
        assert parent.base_experiment_id == "REP4_001"
        assert parent.parent_experiment_fk is None
        assert rep_a.parent_experiment_fk == parent.id

    def test_bare_stem_takes_precedence_over_dash1(self, sqlite_session):
        dash1_parent = _make_exp(sqlite_session, "REP5_001-1", 910040)
        bare_parent = _make_exp(sqlite_session, "REP5_001", 910041)
        rep_a = _make_exp(sqlite_session, "REP5_001a", 910042)
        assert rep_a.parent_experiment_fk == bare_parent.id
        assert rep_a.parent_experiment_fk != dash1_parent.id

    def test_orphan_replicates_backlink_when_bare_stem_parent_created_later(self, sqlite_session):
        rep_a = _make_exp(sqlite_session, "REP6_001a", 910050)
        rep_b = _make_exp(sqlite_session, "REP6_001b", 910051)
        assert rep_a.parent_experiment_fk is None
        assert rep_b.parent_experiment_fk is None

        parent = _make_exp(sqlite_session, "REP6_001", 910052)

        assert rep_a.parent_experiment_fk == parent.id
        assert rep_b.parent_experiment_fk == parent.id

    def test_orphan_replicates_backlink_when_dash0_parent_created_later(self, sqlite_session):
        rep_a = _make_exp(sqlite_session, "REP7_001a", 910060)
        assert rep_a.parent_experiment_fk is None

        parent = _make_exp(sqlite_session, "REP7_001-0", 910061)

        assert rep_a.parent_experiment_fk == parent.id

    def test_letter_plus_sequential_does_not_crash(self, sqlite_session):
        rep_a2 = _make_exp(sqlite_session, "REP8_001a-2", 910070)
        assert rep_a2.base_experiment_id == "REP8_001"
        assert rep_a2.replicate_label == "a"

    def test_dash0_row_is_a_parent_row_not_a_child(self, sqlite_session):
        parent = _make_exp(sqlite_session, "REP9_001-0", 910080)
        assert parent.base_experiment_id == "REP9_001"
        assert parent.parent_experiment_fk is None
        assert parent.replicate_label is None

    def test_find_replicate_group_parent_precedence(self, sqlite_session):
        bare = _make_exp(sqlite_session, "REP10_001", 910090)
        found = find_replicate_group_parent(sqlite_session, "REP10_001")
        assert found is not None
        assert found.id == bare.id

    def test_other_parent_alias_not_relinked_when_bare_stem_created_later(self, sqlite_session):
        """Regression guard: when both a '-1' parent-alias and (later) the bare stem
        exist, resolving the bare stem as the winning parent must NOT back-link the
        '-1' row as if it were an orphaned child — it is a parent alias, not a child."""
        dash1_parent = _make_exp(sqlite_session, "REP11_001-1", 910100)
        assert dash1_parent.parent_experiment_fk is None

        bare_parent = _make_exp(sqlite_session, "REP11_001", 910101)

        assert dash1_parent.parent_experiment_fk is None, (
            "a '-1' parent-alias row must never be back-linked to the bare-stem parent"
        )
        assert bare_parent.parent_experiment_fk is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_replicate_lineage.py::TestReplicateLineageWiring -v`
Expected: FAIL — `ImportError: cannot import name 'find_replicate_group_parent'`.

- [ ] **Step 3: Add `find_replicate_group_parent` and rewrite lineage wiring in `database/lineage_utils.py`**

Add this new function immediately after `parse_experiment_id` (before `get_or_find_parent_experiment`):

```python
def find_replicate_group_parent(db: Session, base_id: str):
    """
    Resolve the group parent for a replicate member, in precedence order:
    bare stem (S), then the explicit parent spellings S-0 and S-1.

    Args:
        db: Database session
        base_id: The stem (e.g. "SERUM_001") to resolve a parent for

    Returns:
        The parent Experiment object if found, None otherwise
    """
    from .models import Experiment

    if not base_id:
        return None

    for candidate_id in (base_id, f"{base_id}-0", f"{base_id}-1"):
        candidate_norm = ''.join(ch for ch in candidate_id.lower() if ch not in ['-', '_', ' '])
        parent = db.query(Experiment).filter(
            func.lower(
                func.replace(
                    func.replace(
                        func.replace(Experiment.experiment_id, '-', ''),
                        '_', ''
                    ),
                    ' ', ''
                )
            ) == candidate_norm
        ).first()
        if parent:
            return parent
    return None
```

In `get_or_find_parent_experiment`, replace:

```python
    base_id, derivation_num, treatment_variant = parse_experiment_id(experiment_id)
```

with:

```python
    base_id, derivation_num, treatment_variant, _replicate_label = parse_experiment_id(experiment_id)
```

Replace the entire `update_experiment_lineage` function body with:

```python
def update_experiment_lineage(db: Session, experiment):
    """
    Update the lineage fields (base_experiment_id, parent_experiment_fk, replicate_label)
    for an experiment.

    Args:
        db: Database session
        experiment: The Experiment object to update

    Returns:
        True if lineage was updated, False if no update was needed

    Note:
        This function modifies the experiment object but does not commit the session.
        Treatment variants are tracked in the experiment_id but do not affect parent relationships.

        Classification:
        - Bare stem, or explicit "-0"/"-1" parent spelling (no treatment, no replicate
          letter): this row IS a group parent. base_experiment_id = stem,
          parent_experiment_fk = NULL.
        - Replicate member (replicate_label set): base_experiment_id = stem, parent
          resolved via find_replicate_group_parent (bare stem, then -0, then -1).
        - Everything else (sequential >= 2, treatment variants): unchanged existing
          behavior via get_or_find_parent_experiment.
    """
    if not experiment or not experiment.experiment_id:
        return False

    base_id, derivation_num, treatment_variant, replicate_label = parse_experiment_id(experiment.experiment_id)

    updated = False
    if experiment.replicate_label != replicate_label:
        experiment.replicate_label = replicate_label
        updated = True

    is_parent_row = (
        treatment_variant is None
        and replicate_label is None
        and (derivation_num is None or derivation_num in (0, 1))
    )

    if is_parent_row:
        self_base_id = base_id or experiment.experiment_id
        if experiment.base_experiment_id != self_base_id:
            experiment.base_experiment_id = self_base_id
            updated = True
        if experiment.parent_experiment_fk is not None:
            experiment.parent_experiment_fk = None
            updated = True
        return updated

    # This is a derivation (sequential, treatment, and/or replicate)
    experiment.base_experiment_id = base_id

    if replicate_label is not None:
        parent = find_replicate_group_parent(db, base_id)
    else:
        parent = get_or_find_parent_experiment(db, experiment.experiment_id)

    experiment.parent_experiment_fk = parent.id if parent else None

    return True
```

Replace the entire `update_orphaned_derivations` function body with:

```python
def update_orphaned_derivations(db: Session, base_experiment_id: str):
    """
    Update any derivations that reference this base experiment but don't have parent_experiment_fk set.

    This is called after a group parent is inserted (bare stem, or explicit -0/-1 spelling)
    to link any pre-existing derivations, including lettered replicates.

    Args:
        db: Database session
        base_experiment_id: The stem (e.g. "HPHT_MH_001") of the newly created group parent

    Returns:
        The number of derivations updated
    """
    from .models import Experiment

    if not base_experiment_id:
        return 0

    base_experiment = find_replicate_group_parent(db, base_experiment_id)
    if not base_experiment:
        return 0

    # A stem can have up to three parent spellings (bare, -0, -1) that may all
    # exist simultaneously. Whichever one wins precedence in find_replicate_group_parent
    # must not cause the OTHER spellings to be back-linked as if they were orphaned
    # children — they are all "the group parent", just written differently.
    parent_alias_ids = {base_experiment.id}
    for alias_id in (base_experiment_id, f"{base_experiment_id}-0", f"{base_experiment_id}-1"):
        alias_norm = ''.join(ch for ch in alias_id.lower() if ch not in ['-', '_', ' '])
        alias_row = db.query(Experiment).filter(
            func.lower(
                func.replace(
                    func.replace(
                        func.replace(Experiment.experiment_id, '-', ''),
                        '_', ''
                    ),
                    ' ', ''
                )
            ) == alias_norm
        ).first()
        if alias_row:
            parent_alias_ids.add(alias_row.id)

    # Find orphaned derivations (those with base_experiment_id matching but parent_experiment_fk
    # is NULL), excluding every parent-alias row for this stem.
    orphaned = db.query(Experiment).filter(
        Experiment.base_experiment_id == base_experiment_id,
        Experiment.parent_experiment_fk.is_(None),
        Experiment.id.notin_(parent_alias_ids)
    ).all()

    count = 0
    for derivation in orphaned:
        derivation.parent_experiment_fk = base_experiment.id
        count += 1

    return count
```

In `auto_create_treatment_experiment`, replace:

```python
    base_id, derivation_num, treatment_variant = parse_experiment_id(experiment_id)
```

with:

```python
    base_id, derivation_num, treatment_variant, _replicate_label = parse_experiment_id(experiment_id)
```

- [ ] **Step 4: Fix the before_flush listener's unpack and parent-row detection in `database/event_listeners.py`**

Replace (lines 636-666):

```python
@event.listens_for(Session, 'before_flush')
def update_experiment_lineage_on_flush(session, flush_context, instances):
    """
    Automatically update experiment lineage fields before flushing.
    
    This listener:
    1. Parses experiment IDs for new experiments
    2. Sets base_experiment_id and parent_experiment_fk
    3. Updates orphaned derivations when a base experiment is created
    """
    from .models import Experiment
    
    # Track base experiments being inserted to update their derivations
    new_base_experiments = []
    
    # Process new experiments
    for obj in session.new:
        if isinstance(obj, Experiment) and obj.experiment_id:
            # Update lineage for this experiment
            update_experiment_lineage(session, obj)
            
            # Track if this is a potential base experiment (no derivation number)
            from .lineage_utils import parse_experiment_id
            _, derivation_num, _ = parse_experiment_id(obj.experiment_id)
            if derivation_num is None:
                new_base_experiments.append(obj.experiment_id)
    
    # After processing new experiments, update any orphaned derivations
    # This handles the case where a derivation was created before its base
    for base_exp_id in new_base_experiments:
        update_orphaned_derivations(session, base_exp_id)
```

with:

```python
@event.listens_for(Session, 'before_flush')
def update_experiment_lineage_on_flush(session, flush_context, instances):
    """
    Automatically update experiment lineage fields before flushing.

    This listener:
    1. Parses experiment IDs for new experiments
    2. Sets base_experiment_id, parent_experiment_fk, and replicate_label
    3. Updates orphaned derivations when a group parent (bare stem, or an
       explicit -0/-1 spelling) is created
    """
    from .models import Experiment
    from .lineage_utils import parse_experiment_id

    # Track group-parent stems being inserted, to update their derivations
    new_parent_stems = []

    # Process new experiments
    for obj in session.new:
        if isinstance(obj, Experiment) and obj.experiment_id:
            # Update lineage for this experiment
            update_experiment_lineage(session, obj)

            # Track if this row is a group parent (bare stem, or explicit -0/-1
            # spelling) so any pre-existing orphaned derivations can be linked.
            base_id, derivation_num, treatment_variant, replicate_label = parse_experiment_id(obj.experiment_id)
            is_parent_row = (
                treatment_variant is None
                and replicate_label is None
                and (derivation_num is None or derivation_num in (0, 1))
            )
            if is_parent_row:
                new_parent_stems.append(base_id or obj.experiment_id)

    # After processing new experiments, update any orphaned derivations
    # This handles the case where a derivation was created before its parent
    for stem in new_parent_stems:
        update_orphaned_derivations(session, stem)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_replicate_lineage.py -v`
Expected: all pass (12 parsing + 12 wiring tests).

- [ ] **Step 6: Commit**

```bash
git add database/lineage_utils.py database/event_listeners.py tests/test_replicate_lineage.py
git commit -m "$(cat <<'EOF'
[#69] Wire replicate parent resolution and orphan back-linking

- find_replicate_group_parent resolves bare-stem/-0/-1 precedence
- update_experiment_lineage and update_orphaned_derivations replicate-aware
- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 4: Mechanical 3→4 tuple-unpack fixes elsewhere

**Files:**
- Modify: `database/lineage_utils.py:271` (`get_or_find_parent_experiment`'s candidate-matching loop — missed by the original Task 3 file list; discovered during Task 3's review)
- Modify: `database/data_migrations/establish_experiment_lineage_006.py:70,182`
- Modify: `tests/check_lineage_integrity.py:39`
- Modify: `tests/test_lineage_migration.py:139-176`
- Modify: `tests/test_experiment_rename.py:163-165`
- Modify: `backend/services/bulk_uploads/new_experiments.py:43`

**Interfaces:**
- Consumes: `lineage_utils.parse_experiment_id` 4-tuple (Task 2).
- No new interfaces produced — this task only prevents `ValueError: too many values to unpack` crashes and stale test assertions after Task 2/3 landed.

- [ ] **Step 1: Confirm these are the only remaining broken call sites**

Run: `.venv/Scripts/python -m pytest tests/ -q 2>&1 | tail -60`
Expected: failures only in the 5 files listed above (plus whatever Tasks 2/3 already added, which now pass). Note the exact error for each (`ValueError: too many values to unpack (expected 3)` or `AssertionError` on tuple equality) to confirm scope before editing.

- [ ] **Step 2: Fix `database/lineage_utils.py::get_or_find_parent_experiment`'s second unpack site**

This function has TWO `parse_experiment_id` call sites. Task 3 already fixed the top-level one (`base_id, derivation_num, treatment_variant, _replicate_label = parse_experiment_id(experiment_id)`). This step fixes the second one, inside the candidate-matching loop in the sequential-derivation branch. Find:

```python
        for candidate in candidates:
            cand_base, cand_seq, cand_treatment = parse_experiment_id(candidate.experiment_id)
```

Replace with:

```python
        for candidate in candidates:
            cand_base, cand_seq, cand_treatment, _cand_replicate_label = parse_experiment_id(candidate.experiment_id)
```

- [ ] **Step 3: Fix `database/data_migrations/establish_experiment_lineage_006.py`**

Line ~70, inside `establish_experiment_lineage`, replace:

```python
                base_id, derivation_num, treatment_variant = parse_experiment_id(exp.experiment_id)
```

with:

```python
                base_id, derivation_num, treatment_variant, _replicate_label = parse_experiment_id(exp.experiment_id)
```

Line ~182, inside `fix_stale_lineage`, replace:

```python
                base_id, derivation_num, treatment_variant = parse_experiment_id(exp.experiment_id)
```

with:

```python
                base_id, derivation_num, treatment_variant, _replicate_label = parse_experiment_id(exp.experiment_id)
```

(This is a mechanical arity fix only — this legacy one-off backfill/repair script's classification logic is not made replicate-aware; that is out of scope for P1 per the issue's file list, which calls for exactly this unpack fix.)

- [ ] **Step 4: Fix `tests/check_lineage_integrity.py`**

Line 39, replace:

```python
            base_id, derivation_num, treatment_variant = parse_experiment_id(exp.experiment_id)
```

with:

```python
            base_id, derivation_num, treatment_variant, _replicate_label = parse_experiment_id(exp.experiment_id)
```

- [ ] **Step 5: Fix `tests/test_lineage_migration.py::test_parse_experiment_id`**

Replace the entire method body (lines 136-176) with:

```python
    def test_parse_experiment_id(self):
        """Test parsing of experiment IDs to identify derivations and treatments."""
        # Base experiments — underscore-index format
        assert parse_experiment_id("HPHT_MH_001") == ("HPHT_MH_001", None, None, None)
        assert parse_experiment_id("LEACH_TEST") == ("LEACH_TEST", None, None, None)

        # Sequential derivations — prefix must end in _digits or -digits
        assert parse_experiment_id("HPHT_MH_001-2") == ("HPHT_MH_001", 2, None, None)
        assert parse_experiment_id("HPHT_MH_001-10") == ("HPHT_MH_001", 10, None, None)
        assert parse_experiment_id("HPHT_001-2") == ("HPHT_001", 2, None, None)

        # CF-style IDs: TYPE-NNN — the prefix ("CF") does NOT end in digits,
        # so these are standalone base experiments, not derivations.
        assert parse_experiment_id("CF-015") == ("CF-015", None, None, None)
        assert parse_experiment_id("CF-12") == ("CF-12", None, None, None)
        assert parse_experiment_id("CF-04") == ("CF-04", None, None, None)

        # CF-015-2 IS a derivation because its prefix "CF-015" ends in -015 (digits)
        assert parse_experiment_id("CF-015-2") == ("CF-015", 2, None, None)

        # Former synthetic test cases — now recognised as base experiments
        # (their prefixes don't end in digits, so trailing -N is not a derivation)
        assert parse_experiment_id("COMPLEX-ID-TEST-3") == ("COMPLEX-ID-TEST-3", None, None, None)
        assert parse_experiment_id("TEST-SAMPLE-001") == ("TEST-SAMPLE-001", None, None, None)

        # Non-derivations with hyphens (last part is NOT numeric)
        assert parse_experiment_id("TEST-SAMPLE-ABC") == ("TEST-SAMPLE-ABC", None, None, None)
        assert parse_experiment_id("HPHT-HIGH-TEMP") == ("HPHT-HIGH-TEMP", None, None, None)

        # Treatment variants (underscore-TEXT suffix)
        assert parse_experiment_id("HPHT_MH_001_Desorption") == ("HPHT_MH_001", None, "Desorption", None)
        assert parse_experiment_id("Serum_MH_101_Annealing") == ("Serum_MH_101", None, "Annealing", None)

        # Combined sequential + treatment — treatment stripped first, then sequential detected
        assert parse_experiment_id("HPHT_MH_001-2_Desorption") == ("HPHT_MH_001", 2, "Desorption", None)
        assert parse_experiment_id("Serum_MH_101-3_Annealing") == ("Serum_MH_101", 3, "Annealing", None)

        # Explicit parent spellings (issue #69)
        assert parse_experiment_id("HPHT_MH_001-0") == ("HPHT_MH_001", 0, None, None)
        assert parse_experiment_id("HPHT_MH_001-1") == ("HPHT_MH_001", 1, None, None)

        # Replicate letters (issue #69)
        assert parse_experiment_id("SERUM_001a") == ("SERUM_001", None, None, "a")
        assert parse_experiment_id("Serum_MH_101a") == ("Serum_MH_101", None, None, "a")
        assert parse_experiment_id("SERUM_001a-2") == ("SERUM_001", 2, None, "a")

        # Edge cases
        assert parse_experiment_id("") == (None, None, None, None)
        assert parse_experiment_id(None) == (None, None, None, None)
        assert parse_experiment_id("   ") == (None, None, None, None)
```

- [ ] **Step 6: Fix `tests/test_experiment_rename.py`**

Line 163-165, replace:

```python
        base_id, deriv_num, treatment = parse_experiment_id(renamed.experiment_id)
        assert base_id == "HPHT_MH_036"
        assert deriv_num is None
```

with:

```python
        base_id, deriv_num, treatment, replicate_label = parse_experiment_id(renamed.experiment_id)
        assert base_id == "HPHT_MH_036"
        assert deriv_num is None
        assert replicate_label is None
```

- [ ] **Step 7: Fix `backend/services/bulk_uploads/new_experiments.py::find_parent_for_copy`**

Line 43, replace:

```python
    base_id, sequential_num, treatment_variant = extract_lineage_info(experiment_id)
```

with:

```python
    base_id, sequential_num, treatment_variant, _replicate_label = extract_lineage_info(experiment_id)
```

Note: `extract_lineage_info`'s arity change lands in Task 5 below — this line must be updated in the same commit as Task 5, or the import will succeed but this line will raise `ValueError: too many values to unpack` the moment `extract_lineage_info` starts returning 4 values. Since this task runs before Task 5, this specific edit will not yet be exercised correctly until Task 5 lands; that is expected — do not run the full suite as a completion gate for *this* task alone, only `tests/test_lineage_migration.py`, `tests/test_experiment_rename.py`, `tests/check_lineage_integrity.py`-adjacent tests, and the data-migration test.

- [ ] **Step 8: Run the affected test files to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_lineage_migration.py tests/test_experiment_rename.py tests/test_replicate_lineage.py -v`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add database/lineage_utils.py database/data_migrations/establish_experiment_lineage_006.py tests/check_lineage_integrity.py tests/test_lineage_migration.py tests/test_experiment_rename.py backend/services/bulk_uploads/new_experiments.py
git commit -m "$(cat <<'EOF'
[#69] Fix remaining 3-tuple unpack sites for parse_experiment_id

- Mechanical arity fix only, no behavior change
- Tests added: no (existing tests updated)
- Docs updated: no
EOF
)"
```

---

### Task 5: `experiment_validation.py` — `extract_lineage_info` 4-tuple + `ParsedExperimentID.replicate_label`

**Files:**
- Modify: `backend/services/experiment_validation.py`
- Test: `tests/services/test_experiment_validation_replicates.py` (new file)

**Interfaces:**
- Produces: `extract_lineage_info(experiment_id: str) -> Tuple[str, Optional[int], Optional[str], Optional[str]]` (adds `replicate_label`), `ParsedExperimentID.replicate_label: Optional[str] = None` (defaulted field), `parse_experiment_id(...)` populates it.
- Consumes: nothing new (pure string parsing).

- [ ] **Step 1: Write the failing tests**

Create `tests/services/test_experiment_validation_replicates.py`:

```python
"""Tests for replicate-letter support in experiment_validation (issue #69)."""
from backend.services.experiment_validation import (
    extract_lineage_info, parse_experiment_id,
)


class TestExtractLineageInfoReplicateGrammar:
    def test_bare_stem(self):
        assert extract_lineage_info("HPHT_001") == ("HPHT_001", None, None, None)

    def test_replicate_letter_two_part(self):
        assert extract_lineage_info("SERUM_001a") == ("SERUM_001", None, None, "a")

    def test_replicate_letter_three_part(self):
        assert extract_lineage_info("Serum_MH_101a") == ("Serum_MH_101", None, None, "a")

    def test_replicate_letter_plus_sequential(self):
        assert extract_lineage_info("SERUM_001a-2") == ("SERUM_001", 2, None, "a")

    def test_existing_sequential_unaffected(self):
        assert extract_lineage_info("HPHT_001-2") == ("HPHT_001", 2, None, None)

    def test_existing_treatment_unaffected(self):
        assert extract_lineage_info("HPHT_001_Desorption") == ("HPHT_001", None, "Desorption", None)

    def test_existing_combined_unaffected(self):
        assert extract_lineage_info("Serum_MH_101-2_Desorption") == ("Serum_MH_101", 2, "Desorption", None)

    def test_empty(self):
        assert extract_lineage_info("") == ("", None, None, None)


class TestParseExperimentIdReplicateLabel:
    def test_two_part_replicate_is_valid(self):
        result = parse_experiment_id("SERUM_001a")
        assert result.is_valid is True
        assert result.replicate_label == "a"
        assert result.index == "001"
        assert result.experiment_type is not None

    def test_three_part_replicate_does_not_degrade_to_wrong_treatment(self):
        result = parse_experiment_id("Serum_MH_101a")
        assert result.is_valid is True
        assert result.replicate_label == "a"
        assert result.index == "101"
        assert result.researcher_initials == "MH"
        assert result.base_id == "Serum_MH_101"

    def test_non_replicate_id_has_null_replicate_label(self):
        result = parse_experiment_id("HPHT_001")
        assert result.replicate_label is None

    def test_invalid_id_has_null_replicate_label(self):
        result = parse_experiment_id("")
        assert result.replicate_label is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/services/test_experiment_validation_replicates.py -v`
Expected: FAIL — `ValueError: not enough values to unpack (expected 4, got 3)` on the `extract_lineage_info` tests, `AttributeError: 'ParsedExperimentID' object has no attribute 'replicate_label'` on the `parse_experiment_id` tests.

- [ ] **Step 3: Add `replicate_label` to `ParsedExperimentID`**

In `backend/services/experiment_validation.py`, replace:

```python
@dataclass
class ParsedExperimentID:
    """Result of parsing an experiment ID."""
    experiment_type: Optional[ExperimentType]
    researcher_initials: Optional[str]
    index: Optional[str]
    sequential_number: Optional[int]
    treatment_variant: Optional[str]
    base_id: str  # The ID without sequential/treatment suffixes
    original_id: str
    is_valid: bool
    warnings: List[str]
```

with:

```python
@dataclass
class ParsedExperimentID:
    """Result of parsing an experiment ID."""
    experiment_type: Optional[ExperimentType]
    researcher_initials: Optional[str]
    index: Optional[str]
    sequential_number: Optional[int]
    treatment_variant: Optional[str]
    base_id: str  # The ID without sequential/treatment suffixes
    original_id: str
    is_valid: bool
    warnings: List[str]
    replicate_label: Optional[str] = None  # "a", "b", "c"; None = not a replicate
```

- [ ] **Step 4: Rewrite `extract_lineage_info`**

Replace the whole function body with:

```python
def extract_lineage_info(experiment_id: str) -> Tuple[str, Optional[int], Optional[str], Optional[str]]:
    """
    Extract base ID, sequential number, treatment variant, and replicate label from
    experiment ID.

    Uses hybrid delimiter system:
    - Hyphen-NUMBER for sequential lineage (e.g., -2, -3)
    - Underscore-TEXT for treatment variants (e.g., _Desorption)
    - A single trailing lowercase letter bound to the numeric index for replicates
      (e.g., _001a), extracted before treatment detection so a letter-suffixed
      index is never mistaken for a treatment name.

    Supports both 2-part (TYPE_INDEX) and 3-part (TYPE_INITIALS_INDEX) formats.

    Args:
        experiment_id: The full experiment ID

    Returns:
        Tuple of (base_id, sequential_number, treatment_variant, replicate_label)

    Examples:
        >>> extract_lineage_info("Serum_MH_101")
        ("Serum_MH_101", None, None, None)
        >>> extract_lineage_info("HPHT_001")
        ("HPHT_001", None, None, None)
        >>> extract_lineage_info("Serum_MH_101-2")
        ("Serum_MH_101", 2, None, None)
        >>> extract_lineage_info("HPHT_001-2")
        ("HPHT_001", 2, None, None)
        >>> extract_lineage_info("Serum_MH_101_Desorption")
        ("Serum_MH_101", None, "Desorption", None)
        >>> extract_lineage_info("HPHT_001_Desorption")
        ("HPHT_001", None, "Desorption", None)
        >>> extract_lineage_info("Serum_MH_101-2_Desorption")
        ("Serum_MH_101", 2, "Desorption", None)
        >>> extract_lineage_info("HPHT_001-2_Desorption")
        ("HPHT_001", 2, "Desorption", None)
        >>> extract_lineage_info("SERUM_001a")
        ("SERUM_001", None, None, "a")
        >>> extract_lineage_info("Serum_MH_101a")
        ("Serum_MH_101", None, None, "a")
        >>> extract_lineage_info("SERUM_001a-2")
        ("SERUM_001", 2, None, "a")
    """
    if not experiment_id:
        return "", None, None, None

    treatment_variant = None
    sequential_number = None
    replicate_label = None
    base_id = experiment_id

    # First, extract sequential number (hyphen-NUMBER pattern from the end)
    # This must be done before treatment detection to avoid confusion
    if '-' in experiment_id:
        hyphen_parts = experiment_id.rsplit('-', 1)
        if len(hyphen_parts) == 2 and hyphen_parts[-1].isdigit():
            sequential_number = int(hyphen_parts[-1])
            base_id = hyphen_parts[0]

    # Extract the replicate letter bound to the numeric index (e.g. "101a" -> "101" + "a").
    # Must run before treatment detection below, or a letter-suffixed index would be
    # mistaken for a treatment name (e.g. "Serum_MH_101a" -> base "Serum_MH", treatment "101a").
    parts = base_id.split('_')
    letter_match = re.match(r'^(\d+)([a-z])$', parts[-1])
    if letter_match:
        replicate_label = letter_match.group(2)
        parts[-1] = letter_match.group(1)
        base_id = '_'.join(parts)

    # Now check for treatment variant in the remaining base_id
    # Split by underscore to detect if last part is a treatment
    parts = base_id.split('_')

    # Determine expected base format by checking part count
    # After removing sequential, we should have:
    # - 2 parts for TYPE_INDEX format (e.g., HPHT_001)
    # - 3 parts for TYPE_INITIALS_INDEX format (e.g., Serum_MH_101)
    # If we have more parts than expected, the last part is likely a treatment

    if len(parts) > 2:
        # Could be 2-part format with treatment, or 3-part format (with or without treatment)
        potential_treatment = parts[-1]

        # Check if last part looks like a treatment (not all numeric)
        if not potential_treatment.isdigit():
            # Last part is not numeric, likely a treatment
            # But we need to distinguish between:
            # - HPHT_001_Desorption (2-part + treatment, len=3)
            # - Serum_MH_101_Desorption (3-part + treatment, len=4)
            # - Serum_MH_101 (3-part base, len=3)

            # If we have exactly 3 parts and last is non-numeric, it could be:
            # - TYPE_INDEX + treatment (HPHT_001_Desorption)
            # - TYPE_INITIALS_INDEX base (Serum_MH_101) - but 101 is numeric, so this won't match

            # If we have 4+ parts, definitely a treatment (TYPE_INITIALS_INDEX + treatment)
            # If we have 3 parts and last is non-numeric, it's TYPE_INDEX + treatment
            if len(parts) >= 3:
                treatment_variant = potential_treatment
                base_id = '_'.join(parts[:-1])
        # If last part is numeric and we have exactly 3 parts, it's TYPE_INITIALS_INDEX base format
        # If last part is numeric and we have exactly 2 parts, it's TYPE_INDEX base format

    return base_id, sequential_number, treatment_variant, replicate_label
```

- [ ] **Step 5: Wire `replicate_label` into `parse_experiment_id`**

Replace:

```python
    original_id = experiment_id.strip()
    
    # Extract lineage info first
    base_id, sequential_number, treatment_variant = extract_lineage_info(original_id)
```

with:

```python
    original_id = experiment_id.strip()
    
    # Extract lineage info first
    base_id, sequential_number, treatment_variant, replicate_label = extract_lineage_info(original_id)
```

Replace the final `return ParsedExperimentID(...)` at the bottom of `parse_experiment_id`:

```python
    return ParsedExperimentID(
        experiment_type=experiment_type,
        researcher_initials=researcher_initials,
        index=index,
        sequential_number=sequential_number,
        treatment_variant=treatment_variant,
        base_id=base_id,
        original_id=original_id,
        is_valid=is_valid,
        warnings=warnings
    )
```

with:

```python
    return ParsedExperimentID(
        experiment_type=experiment_type,
        researcher_initials=researcher_initials,
        index=index,
        sequential_number=sequential_number,
        treatment_variant=treatment_variant,
        base_id=base_id,
        original_id=original_id,
        is_valid=is_valid,
        warnings=warnings,
        replicate_label=replicate_label,
    )
```

(The early-return failure-path `ParsedExperimentID(...)` for empty/invalid input does not need a `replicate_label=` kwarg — the dataclass default `None` covers it.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/services/test_experiment_validation_replicates.py -v`
Expected: 12 passed.

- [ ] **Step 7: Run the full lineage-adjacent regression set**

Run: `.venv/Scripts/python -m pytest tests/test_replicate_lineage.py tests/test_lineage_migration.py tests/test_experiment_rename.py tests/services/ -v`
Expected: all pass. (`tests/services/bulk_uploads/test_new_experiments.py` exercises `find_parent_for_copy`, which now receives the 4-tuple from Task 4's fix — confirm no regression there.)

- [ ] **Step 8: Commit**

```bash
git add backend/services/experiment_validation.py tests/services/test_experiment_validation_replicates.py
git commit -m "$(cat <<'EOF'
[#69] Parse replicate letter in experiment_validation

- extract_lineage_info 4-tuple, ParsedExperimentID.replicate_label
- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 6: Reporting views — fix `v_results_scalar` cumulative window, add `v_results_scalar_rollup`

**Files:**
- Modify: `database/event_listeners.py:473-510` (`v_results_scalar`), `_VIEWS` list (add new view)
- Modify: `tests/views/test_v_results_scalar_cum_fe.py` (rewrite the cross-chain test)
- Test: `tests/views/test_v_results_scalar_rollup.py` (new file)

**Interfaces:**
- Consumes: `Experiment.base_experiment_id`/`replicate_label` (Tasks 1-3), `ScalarResults` fields (existing, unchanged).
- Produces: `v_results_scalar_rollup` SQL view — one row per `(base_experiment_id, time_post_reaction_bucket_days)`.

- [ ] **Step 1: Rewrite the cross-chain cumulative test to match per-experiment_id partitioning**

In `tests/views/test_v_results_scalar_cum_fe.py`, replace the entire `TestChainPartitioning` class:

```python
class TestChainPartitioning:
    def test_derived_experiment_shares_cumulative_with_root(self, view_db):
        """Root and derived experiments in the same chain accumulate into one running sum."""
        # Root experiment: base_experiment_id is NULL (COALESCE resolves to 'CTEST_001').
        # Use a digit-suffix ID so the lineage parser recognises 'CTEST_001-2' as derived.
        root = _make_experiment(view_db, "CTEST_001", 20)
        view_db.flush()  # Ensure root is persisted before derived is created
        # Derived experiment: base_experiment_id = 'CTEST_001' (COALESCE resolves to 'CTEST_001')
        derived = _make_experiment(view_db, "CTEST_001-2", 21, base_id="CTEST_001")

        er_root = _make_result(view_db, root, cumulative_days=1.0)
        er_derived = _make_result(view_db, derived, cumulative_days=30.0)

        _make_scalar(view_db, er_root, fe_h2_pct=10.0)
        _make_scalar(view_db, er_derived, fe_h2_pct=5.0)
        view_db.commit()

        rows = view_db.execute(
            text("""
                SELECT experiment_id, cumulative_ferrous_iron_yield_h2_pct
                FROM v_results_scalar
                WHERE experiment_id IN ('CTEST_001', 'CTEST_001-2')
                ORDER BY cumulative_time_post_reaction_days
            """)
        ).fetchall()

        assert len(rows) == 2
        # Root timepoint: cumulative = 10.0 (only timepoint for CTEST_001)
        assert rows[0][0] == "CTEST_001"
        assert rows[0][1] == pytest.approx(10.0)
        # Derived timepoint: partitioned by its OWN experiment_id (not the shared base),
        # so it does NOT accumulate the root's 10.0 — cumulative = 5.0, not 15.0.
        assert rows[1][0] == "CTEST_001-2"
        assert rows[1][1] == pytest.approx(5.0)

    def test_replicate_set_does_not_cross_sum(self, view_db):
        """Three replicates sharing a base_experiment_id each accumulate independently."""
        exp_a = _make_experiment(view_db, "REPCUM_001a", 22, base_id="REPCUM_001")
        exp_b = _make_experiment(view_db, "REPCUM_001b", 23, base_id="REPCUM_001")
        exp_c = _make_experiment(view_db, "REPCUM_001c", 24, base_id="REPCUM_001")

        er_a = _make_result(view_db, exp_a, cumulative_days=7.0)
        er_b = _make_result(view_db, exp_b, cumulative_days=7.0)
        er_c = _make_result(view_db, exp_c, cumulative_days=7.0)

        _make_scalar(view_db, er_a, fe_h2_pct=10.0)
        _make_scalar(view_db, er_b, fe_h2_pct=20.0)
        _make_scalar(view_db, er_c, fe_h2_pct=30.0)
        view_db.commit()

        rows = view_db.execute(
            text("""
                SELECT experiment_id, cumulative_ferrous_iron_yield_h2_pct
                FROM v_results_scalar
                WHERE experiment_id IN ('REPCUM_001a', 'REPCUM_001b', 'REPCUM_001c')
                ORDER BY experiment_id
            """)
        ).fetchall()

        by_exp = {r[0]: r[1] for r in rows}
        assert by_exp["REPCUM_001a"] == pytest.approx(10.0)
        assert by_exp["REPCUM_001b"] == pytest.approx(20.0)
        assert by_exp["REPCUM_001c"] == pytest.approx(30.0)
```

- [ ] **Step 2: Run the view test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/views/test_v_results_scalar_cum_fe.py -v`
Expected: `test_derived_experiment_shares_cumulative_with_root` FAILS (`assert 15.0 == 5.0` — currently still partitions by `COALESCE(base_experiment_id, experiment_id)`); `test_replicate_set_does_not_cross_sum` FAILS too (currently sums to 60.0/60.0/60.0 across the shared base instead of 10/20/30).

- [ ] **Step 3: Fix the `v_results_scalar` window in `database/event_listeners.py`**

Replace:

```python
            SUM(COALESCE(sr.ferrous_iron_yield_h2_pct, 0)) OVER (
                PARTITION BY COALESCE(e.base_experiment_id, e.experiment_id)
                ORDER BY er.cumulative_time_post_reaction_days, er.id
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS cumulative_ferrous_iron_yield_h2_pct,
```

with:

```python
            SUM(COALESCE(sr.ferrous_iron_yield_h2_pct, 0)) OVER (
                PARTITION BY e.experiment_id
                ORDER BY er.cumulative_time_post_reaction_days, er.id
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS cumulative_ferrous_iron_yield_h2_pct,
```

- [ ] **Step 4: Run the view test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/views/test_v_results_scalar_cum_fe.py -v`
Expected: all pass (including the 3 pre-existing single-experiment tests, unaffected by this change since a single experiment's own `experiment_id` partition is identical to its old `COALESCE` partition when it has no replicate siblings).

- [ ] **Step 5: Write the failing rollup-view tests**

Create `tests/views/test_v_results_scalar_rollup.py`:

```python
"""Tests for the v_results_scalar_rollup reporting view (issue #69)."""
import datetime
import pytest
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker, Session

from database import Base
from database.models import (
    Experiment, ExperimentalConditions, ExperimentalResults, ScalarResults
)

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"


@pytest.fixture(scope="module")
def view_engine():
    engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def view_db(view_engine):
    connection = view_engine.connect()
    transaction = connection.begin()

    from database.event_listeners import _VIEWS
    for view_name, view_sql in _VIEWS:
        try:
            connection.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
            connection.execute(text(view_sql))
        except Exception:
            pass

    TestSession = sessionmaker(bind=connection)
    db = TestSession()
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()


def _make_experiment(db: Session, exp_id: str, number: int) -> Experiment:
    """Creates a bare Experiment row. The before_flush lineage listener sets
    base_experiment_id/replicate_label automatically from exp_id on flush."""
    exp = Experiment(
        experiment_id=exp_id,
        experiment_number=number,
        status="ONGOING",
        date=datetime.date(2026, 1, 1),
    )
    cond = ExperimentalConditions(
        experiment_id=exp_id,
        rock_mass_g=100.0,
        water_volume_mL=500.0,
    )
    exp.conditions = cond
    db.add(exp)
    db.flush()
    cond.experiment_fk = exp.id
    return exp


def _make_result(db: Session, experiment: Experiment, bucket_days: float) -> ExperimentalResults:
    er = ExperimentalResults(
        experiment_fk=experiment.id,
        time_post_reaction_days=bucket_days,
        time_post_reaction_bucket_days=bucket_days,
        cumulative_time_post_reaction_days=bucket_days,
        is_primary_timepoint_result=True,
        description=f"Result at {bucket_days}d",
    )
    db.add(er)
    db.flush()
    return er


def _make_scalar(db: Session, result: ExperimentalResults, gross_nh4: float) -> ScalarResults:
    sr = ScalarResults(
        result_id=result.id,
        gross_ammonium_concentration_mM=gross_nh4,
        background_ammonium_concentration_mM=0.2,
    )
    db.add(sr)
    db.flush()
    return sr


class TestRollupThreeReplicates:
    def test_mean_median_stddev_and_n_replicates(self, view_db):
        exp_a = _make_experiment(view_db, "ROLL_001a", 1)
        exp_b = _make_experiment(view_db, "ROLL_001b", 2)
        exp_c = _make_experiment(view_db, "ROLL_001c", 3)

        er_a = _make_result(view_db, exp_a, bucket_days=7.0)
        er_b = _make_result(view_db, exp_b, bucket_days=7.0)
        er_c = _make_result(view_db, exp_c, bucket_days=7.0)

        _make_scalar(view_db, er_a, gross_nh4=1.0)
        _make_scalar(view_db, er_b, gross_nh4=2.0)
        _make_scalar(view_db, er_c, gross_nh4=3.0)
        view_db.commit()

        row = view_db.execute(
            text("""
                SELECT n_replicates, mean_gross_ammonium_mM, median_gross_ammonium_mM, sd_gross_ammonium_mM
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_001' AND time_post_reaction_bucket_days = 7.0
            """)
        ).fetchone()

        assert row is not None
        mapping = row._mapping
        assert mapping["n_replicates"] == 3
        assert mapping["mean_gross_ammonium_mM"] == pytest.approx(2.0)
        assert mapping["median_gross_ammonium_mM"] == pytest.approx(2.0)
        assert mapping["sd_gross_ammonium_mM"] == pytest.approx(1.0)


class TestRollupLoneExperiment:
    def test_lone_experiment_gives_n_1_and_null_sd(self, view_db):
        exp = _make_experiment(view_db, "ROLL_LONE_001", 4)
        er = _make_result(view_db, exp, bucket_days=7.0)
        _make_scalar(view_db, er, gross_nh4=5.0)
        view_db.commit()

        row = view_db.execute(
            text("""
                SELECT n_replicates, mean_gross_ammonium_mM, sd_gross_ammonium_mM
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_LONE_001' AND time_post_reaction_bucket_days = 7.0
            """)
        ).fetchone()

        assert row is not None
        mapping = row._mapping
        assert mapping["n_replicates"] == 1
        assert mapping["mean_gross_ammonium_mM"] == pytest.approx(5.0)
        assert mapping["sd_gross_ammonium_mM"] is None


class TestRollupOneRowPerBaseAndBucket:
    def test_two_buckets_produce_two_rows(self, view_db):
        exp_a = _make_experiment(view_db, "ROLL_BKT_001a", 5)
        exp_b = _make_experiment(view_db, "ROLL_BKT_001b", 6)

        er_a1 = _make_result(view_db, exp_a, bucket_days=1.0)
        er_b1 = _make_result(view_db, exp_b, bucket_days=1.0)
        er_a2 = _make_result(view_db, exp_a, bucket_days=7.0)

        _make_scalar(view_db, er_a1, gross_nh4=1.0)
        _make_scalar(view_db, er_b1, gross_nh4=3.0)
        _make_scalar(view_db, er_a2, gross_nh4=9.0)
        view_db.commit()

        rows = view_db.execute(
            text("""
                SELECT time_post_reaction_bucket_days, n_replicates
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_BKT_001'
                ORDER BY time_post_reaction_bucket_days
            """)
        ).fetchall()

        assert len(rows) == 2
        assert rows[0]._mapping["time_post_reaction_bucket_days"] == pytest.approx(1.0)
        assert rows[0]._mapping["n_replicates"] == 2
        assert rows[1]._mapping["time_post_reaction_bucket_days"] == pytest.approx(7.0)
        assert rows[1]._mapping["n_replicates"] == 1
```

- [ ] **Step 6: Run the rollup tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/views/test_v_results_scalar_rollup.py -v`
Expected: FAIL — `sqlalchemy.exc.ProgrammingError: relation "v_results_scalar_rollup" does not exist`.

- [ ] **Step 7: Add the `v_results_scalar_rollup` view to `_VIEWS`**

In `database/event_listeners.py`, immediately after the `v_results_scalar` entry (after its closing `"""),` and before the `v_results_h2` comment block), insert:

```python
    # ------------------------------------------------------------------
    # v_results_scalar_rollup
    # One row per (base_experiment_id, timepoint bucket). Cross-replicate
    # mean/median/std for a replicate set (or a single non-replicate
    # experiment, which yields n_replicates=1 and NULL std). No outlier
    # filter and no ICP aggregation in P1 (see issue #69 P4).
    # ------------------------------------------------------------------
    ("v_results_scalar_rollup", """
        CREATE VIEW v_results_scalar_rollup AS
        SELECT
            COALESCE(e.base_experiment_id, e.experiment_id)              AS base_experiment_id,
            er.time_post_reaction_bucket_days,
            COUNT(sr.result_id)                                          AS n_replicates,
            AVG(sr."gross_ammonium_concentration_mM")                   AS mean_gross_ammonium_mM,
            percentile_cont(0.5) WITHIN GROUP (
                ORDER BY sr."gross_ammonium_concentration_mM")          AS median_gross_ammonium_mM,
            stddev_samp(sr."gross_ammonium_concentration_mM")           AS sd_gross_ammonium_mM,
            AVG(GREATEST(0, sr."gross_ammonium_concentration_mM" - sr."background_ammonium_concentration_mM"))
                                                                        AS mean_net_ammonium_mM,
            stddev_samp(GREATEST(0, sr."gross_ammonium_concentration_mM" - sr."background_ammonium_concentration_mM"))
                                                                        AS sd_net_ammonium_mM,
            AVG(sr.h2_micromoles)                                       AS mean_h2_micromoles,
            stddev_samp(sr.h2_micromoles)                               AS sd_h2_micromoles,
            AVG(sr.h2_grams_per_ton_yield)                              AS mean_h2_grams_per_ton,
            stddev_samp(sr.h2_grams_per_ton_yield)                      AS sd_h2_grams_per_ton,
            AVG(sr.ferrous_iron_yield_h2_pct)                           AS mean_fe_yield_h2_pct,
            stddev_samp(sr.ferrous_iron_yield_h2_pct)                   AS sd_fe_yield_h2_pct,
            AVG(sr.ferrous_iron_yield_nh3_pct)                          AS mean_fe_yield_nh3_pct,
            stddev_samp(sr.ferrous_iron_yield_nh3_pct)                  AS sd_fe_yield_nh3_pct,
            AVG(sr.grams_per_ton_yield)                                 AS mean_grams_per_ton_yield,
            stddev_samp(sr.grams_per_ton_yield)                         AS sd_grams_per_ton_yield,
            AVG(sr.final_ph)                                            AS mean_final_ph
        FROM experimental_results er
        JOIN experiments e         ON e.id  = er.experiment_fk
        LEFT JOIN scalar_results sr ON sr.result_id = er.id
        WHERE er.is_primary_timepoint_result = TRUE
        GROUP BY COALESCE(e.base_experiment_id, e.experiment_id),
                 er.time_post_reaction_bucket_days
    """),

```

- [ ] **Step 8: Run the rollup tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/views/test_v_results_scalar_rollup.py -v`
Expected: 4 passed.

- [ ] **Step 9: Run the full views test directory**

Run: `.venv/Scripts/python -m pytest tests/views/ -v`
Expected: all pass, including `test_v_results_scalar_cum_fe.py` and `test_additive_names_summary.py`.

- [ ] **Step 10: Update `MODELS.md`'s Reporting Views section**

In `.claude/rules/MODELS.md`, after the `v_primary_experiment_results` section (or the last documented view), add:

```markdown
### `v_results_scalar_rollup`

One row per `(base_experiment_id, time_post_reaction_bucket_days)`: cross-replicate mean/median/std for a replicate set (or `n_replicates = 1` with `NULL` std for a single non-replicate experiment).

- **Purpose:** Power BI dashboards can show replicate-set statistics (e.g. mean +/- std NH₄⁺ across `SERUM_001a/b/c`) without an application-layer aggregation step.
- **Grouping key:** `COALESCE(e.base_experiment_id, e.experiment_id)`, matching the existing pattern in `v_results_scalar` and `v_experiment_additives_summary`.
- **Statistics:** `stddev_samp` (n-1); returns `NULL` for `n_replicates = 1`. Median via `percentile_cont(0.5) WITHIN GROUP`.
- **Scope:** gross/net ammonium, H2 (micromoles, grams/ton), ferrous iron yield (H2% and NH3%), grams/ton yield, final pH. No outlier filter (P4) and no ICP element aggregation (permanently out of scope).
- **Columns:** `base_experiment_id`, `time_post_reaction_bucket_days`, `n_replicates`, `mean_gross_ammonium_mM`, `median_gross_ammonium_mM`, `sd_gross_ammonium_mM`, `mean_net_ammonium_mM`, `sd_net_ammonium_mM`, `mean_h2_micromoles`, `sd_h2_micromoles`, `mean_h2_grams_per_ton`, `sd_h2_grams_per_ton`, `mean_fe_yield_h2_pct`, `sd_fe_yield_h2_pct`, `mean_fe_yield_nh3_pct`, `sd_fe_yield_nh3_pct`, `mean_grams_per_ton_yield`, `sd_grams_per_ton_yield`, `mean_final_ph`.
```

Also update the `v_results_scalar` section's note about `cumulative_ferrous_iron_yield_h2_pct` to say it partitions by `experiment_id` (per-vial), not by `COALESCE(base_experiment_id, experiment_id)` — find the sentence describing that column and replace "partition" wording accordingly if present, or add one line noting the per-experiment_id partition if the column isn't otherwise described in that file.

Also update the `Experiment` model section to list `replicate_label` alongside `base_experiment_id`/`parent_experiment_fk` under "Lineage Tracking":

```markdown
  - `replicate_label`: Single lowercase letter (`"a"`, `"b"`, `"c"`) identifying this row as a replicate member of a base experiment; `NULL` if this experiment is not a replicate. The bare base ID (or its explicit `S-0`/`S-1` spelling) is "replicate 0" — the group parent — and always has `replicate_label = NULL`.
```

- [ ] **Step 11: Commit**

```bash
git add database/event_listeners.py tests/views/test_v_results_scalar_cum_fe.py tests/views/test_v_results_scalar_rollup.py .claude/rules/MODELS.md
git commit -m "$(cat <<'EOF'
[#69] Fix v_results_scalar cumulative window, add rollup view

- cumulative_ferrous_iron_yield_h2_pct now partitions per experiment_id
- v_results_scalar_rollup: cross-replicate mean/median/std per (base, bucket)
- Tests added: yes
- Docs updated: yes
EOF
)"
```

---

### Task 7: Conflict-safe creation regression tests

**Files:**
- Modify: `tests/services/bulk_uploads/test_new_experiments.py`
- Modify: `tests/api/test_experiments.py`

**Interfaces:**
- Consumes: existing conflict-handling code in `NewExperimentsUploadService.bulk_upsert_from_excel` (`backend/services/bulk_uploads/new_experiments.py:326-329`, already returns a warning and skips — no source change) and `create_experiment` (`backend/api/routers/experiments.py:634-638`, already catches `IntegrityError` → 409 — no source change).
- No new interfaces — this task is pure regression-test coverage confirming the existing conflict-safe behavior holds for lettered replicate IDs now that lineage parsing recognizes them.

- [ ] **Step 1: Add a bulk-upload conflict regression test**

Append to `tests/services/bulk_uploads/test_new_experiments.py`:

```python
def test_duplicate_replicate_id_skips_with_clear_warning_not_crash(db_session: Session):
    """Creating a replicate ID that already exists (overwrite=False) must produce a
    clear warning and skip the row — never raise or silently overwrite."""
    _seed_experiment(db_session, "HPHT_I69_001a", 69001, status=ExperimentStatus.ONGOING)

    xlsx = _experiments_excel([
        ["HPHT_I69_001a", None, None, "MH", "2026-02-01", "ONGOING", None, False],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == []
    assert created == 0
    assert updated == 0
    assert any("already exists" in w and "HPHT_I69_001a" in w for w in warnings), (
        f"expected a clear conflict warning naming the ID, got: {warnings}"
    )


def test_creating_three_replicates_via_bulk_upload(db_session: Session):
    """Creating SERUM_001a/b/c in one upload yields three experiments sharing a base."""
    xlsx = _experiments_excel([
        ["HPHT_I69_010a", None, None, "MH", "2026-02-01", "ONGOING", "Replicate a", False],
        ["HPHT_I69_010b", None, None, "MH", "2026-02-01", "ONGOING", "Replicate b", False],
        ["HPHT_I69_010c", None, None, "MH", "2026-02-01", "ONGOING", "Replicate c", False],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == []
    assert created == 3

    rep_a = db_session.query(Experiment).filter_by(experiment_id="HPHT_I69_010a").first()
    rep_b = db_session.query(Experiment).filter_by(experiment_id="HPHT_I69_010b").first()
    rep_c = db_session.query(Experiment).filter_by(experiment_id="HPHT_I69_010c").first()

    assert rep_a.base_experiment_id == "HPHT_I69_010"
    assert rep_b.base_experiment_id == "HPHT_I69_010"
    assert rep_c.base_experiment_id == "HPHT_I69_010"
    assert {rep_a.replicate_label, rep_b.replicate_label, rep_c.replicate_label} == {"a", "b", "c"}
```

- [ ] **Step 2: Add an API-level conflict regression test**

Append to `tests/api/test_experiments.py`:

```python
def test_create_experiment_duplicate_replicate_id_fails(client, db_session):
    _make_experiment(db_session, "DUP_REP_001a", 8100)
    payload = {"experiment_id": "DUP_REP_001a", "experiment_number": 8101}
    resp = client.post("/api/experiments", json=payload)
    assert resp.status_code == 409


def test_create_replicate_experiment_sets_lineage(client, db_session):
    _make_experiment(db_session, "LINE_REP_001", 8102)
    payload = {"experiment_id": "LINE_REP_001a", "experiment_number": 8103}
    resp = client.post("/api/experiments", json=payload)
    assert resp.status_code == 201

    created = db_session.query(Experiment).filter_by(experiment_id="LINE_REP_001a").first()
    parent = db_session.query(Experiment).filter_by(experiment_id="LINE_REP_001").first()
    assert created.base_experiment_id == "LINE_REP_001"
    assert created.replicate_label == "a"
    assert created.parent_experiment_fk == parent.id
```

Confirm `Experiment` is already imported at the top of `tests/api/test_experiments.py` (it is, per the existing `_make_experiment` helper) — no new import needed.

- [ ] **Step 3: Run both new test files to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/test_new_experiments.py tests/api/test_experiments.py -v`
Expected: all pass, including the 4 new tests.

- [ ] **Step 4: Commit**

```bash
git add tests/services/bulk_uploads/test_new_experiments.py tests/api/test_experiments.py
git commit -m "$(cat <<'EOF'
[#69] Add conflict-safe creation regression tests for replicate IDs

- Confirms existing skip/409 behavior extends to lettered IDs
- No source change — coverage only
- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 8: UI help text for replicate ID format

**Files:**
- Modify: `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx:85-89`
- Modify: `frontend/src/pages/BulkUploads.tsx:260-269`

**Interfaces:**
- None — copy-only change, no props/types affected.

- [ ] **Step 1: Update the New Experiment form's ID field hint**

In `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx`, replace:

```tsx
        hint={
          idValidation.status !== 'taken'
            ? 'Auto-generated. Edit to use a custom ID (e.g., HPHT_100-2, HPHT_100_Desorption).'
            : undefined
        }
```

with:

```tsx
        hint={
          idValidation.status !== 'taken'
            ? 'Auto-generated. Edit to use a custom ID (e.g., HPHT_100-2, HPHT_100_Desorption, or a replicate letter like SERUM_001a/b/c — the bare SERUM_001 is replicate 0, the parent).'
            : undefined
        }
```

- [ ] **Step 2: Update the New Experiments bulk-upload tile's help text**

In `frontend/src/pages/BulkUploads.tsx`, find the "New Experiments" `UploadRow` (id `"new-experiments"`) and replace:

```tsx
          helpText="Use the template for correct column formatting. The file must have an 'experiments' sheet; a 'conditions' sheet is optional."
```

with:

```tsx
          helpText="Use the template for correct column formatting. The file must have an 'experiments' sheet; a 'conditions' sheet is optional. Replicates: write a lowercase letter after the number (SERUM_001a, _001b, _001c) — the bare SERUM_001 (or SERUM_001-0) is replicate 0, the group parent."
```

- [ ] **Step 3: Verify in the browser**

Confirm the dev server is already running (per `frontend/CLAUDE.md` — never start/stop it yourself; report if unreachable). Navigate to `/experiments/new` and confirm the updated hint renders under the Experiment ID field; open the Bulk Uploads page and expand "New Experiments" to confirm the updated help text renders.

- [ ] **Step 4: Run frontend lint and unit tests**

Run: `cd frontend && npx eslint src/pages/NewExperiment/Step1BasicInfo.tsx src/pages/BulkUploads.tsx`
Expected: 0 errors, 0 warnings.

Run: `cd frontend && npx vitest run src`
Expected: all existing tests still pass (copy-only change, no test assertions reference this exact string).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/NewExperiment/Step1BasicInfo.tsx frontend/src/pages/BulkUploads.tsx
git commit -m "$(cat <<'EOF'
[#69] Add replicate ID format help text to new-experiment UI

- Step1BasicInfo hint + New Experiments upload tile help text
- Tests added: no (copy-only)
- Docs updated: no
EOF
)"
```

---

### Task 9: Full verification pass

**Files:** none (verification only, plus a possible small `docs/working/plan.md` / `docs/working/issue-log.md` entry per `docs/project_context/` sync conventions — handled by `/complete-task`, not this task).

- [ ] **Step 1: Run the full backend test suite**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: all pass except the 3 pre-existing, unrelated `tests/test_pg_backup_restore.py` failures (documented in the issue log as requiring a live restore-test PostgreSQL instance) — confirm no *other* failures.

- [ ] **Step 2: Verify the migration round-trips cleanly from a clean state**

Run: `.venv/Scripts/alembic downgrade -1 && .venv/Scripts/alembic upgrade head`
Expected: both succeed with no errors.

- [ ] **Step 3: Confirm reporting views recreate without error on import**

Run: `.venv/Scripts/python -c "import database.event_listeners"`
Expected: no exception, no `logger.error` output for view creation (check stdout/stderr for "Failed to create view" or "Reporting view creation failed").

- [ ] **Step 4: Re-check every acceptance box from the issue**

Confirm each of the 9 acceptance criteria in issue #69 is satisfied by the work in Tasks 1-8:
- Both parsers recognize the replicate letter (Task 2, Task 5).
- Existing sequential/treatment/type-prefixed IDs parse exactly as before (Task 2, Task 4, Task 5 tests).
- Creating `SERUM_001a/b/c` yields three experiments sharing a base (Task 3, Task 7).
- Parent linking with precedence bare-stem → `-0` → `-1`, including create-after-replicate orphan back-linking (Task 3).
- `v_results_scalar_rollup` stats correct, including `n=1`/`sd=NULL` (Task 6).
- `v_results_scalar.cumulative_ferrous_iron_yield_h2_pct` partitioned per `experiment_id` (Task 6).
- Conflict on creation is clear and non-fatal (Task 7).
- Migration is additive, upgrade/downgrade round-trips (Task 1, Step 2 above).
- No calc-engine change, no regression on the non-replicate path (confirmed by the full suite in Step 1).

- [ ] **Step 5: Stop**

Per the issue: **do not** begin P2 (experiments-list grouping UI), P3 (bulk-upload replicate-column routing), P4 (outlier flag), or P5 (parser consolidation, full letter+sequential parent-wiring). Those are the separate Fable ticket `issue-replicate-P2-P5-fable.md`. Report completion and hand off via `/complete-task`.
