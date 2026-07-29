# Issue #98 — `-t<days>` Vial Replicate Collapsing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every replicate-group UI surface treat a set of sacrificial-timepoint vials (`SERUM_001a-t1`, `SERUM_001a-t3`, `SERUM_001b-t1`, `SERUM_001b-t3`) as 2 replicates rather than 4, and never render the internal `-t<days>` token on the Experiments list.

**Architecture:** Rows that differ **only** by a trailing `-t<days>` token are collapsed on the timepoint-stripped `experiment_id` (the "stem"). Collapsing happens in SQL in the list endpoint, because `total` and pagination are computed server-side. The group endpoint keeps its per-vial `members` contract and gains an additive per-letter `replicates` array. The frontend renders a new `group_display_id` field instead of `experiment_id` and drops the `day N` chip.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (`select()` style) + Postgres 16; React 18 + TypeScript + React Query + Recharts; pytest; vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-07-29-issue-98-t-vial-replicate-collapsing-design.md` — decisions are referenced below as **D1**–**D12**.

## Global Constraints

- **No schema change, no Alembic migration, no view change.** The `-t` parser grammar, `v_results_scalar_rollup`, and `v_results_scalar`'s cumulative partition are all correct and out of scope.
- **The collapse key is the timepoint-stripped `experiment_id`, never `(base_experiment_id, replicate_label)`** (D1). `parse_lineage_fields("SERUM_001a-2")` returns `("SERUM_001", 2, None, "a")`, so a sequential re-run shares base *and* letter with `SERUM_001a`.
- **Python-side stripping reuses `database.experiment_id_parser.split_timepoint_token`.** Do not write a new Python regex. The only new copy of the pattern is the POSIX one for Postgres.
- **`members` and `member_count` on the group response keep their per-vial meaning** (D4). Add fields; never redefine one.
- **Single-vial letters and stems must render exactly as today** (D10) — linked ID, `T+N`, result count, divergent cells, no expand affordance.
- **Never start or stop the uvicorn or Vite servers** (`backend/CLAUDE.md`, `frontend/CLAUDE.md`). Assume ports 8000 / 5173 are already up.
- Commit format is `[#98] <imperative description under 50 chars>` followed by `- Tests added: yes/no` and `- Docs updated: yes/no` (`.claude/CLAUDE.md` §8).
- Backend commands run from the project root with `.venv/Scripts/python -m pytest …`; frontend commands run from `frontend/`.

## File Structure

| File | Responsibility |
|---|---|
| `backend/services/replicate_collapse.py` | **Create.** The stem key: the POSIX pattern, the SQL expression, and the Python-side row collapser. Nothing else. |
| `tests/services/test_replicate_collapse.py` | **Create.** Unit tests for the module, incl. a SQL-vs-Python agreement test. |
| `backend/api/schemas/experiments.py` | **Modify.** 3 additive `ExperimentListItem` fields; `ReplicateLetterGroup`; 2 additive `ReplicateGroupDetailResponse` fields; widen `parent`. |
| `backend/api/routers/experiments.py` | **Modify.** Ungrouped collapse window; grouped bucket-key fix, rank ordering, and per-letter `replicates`; group-response wiring. |
| `backend/services/replicate_groups.py` | **Modify.** `group_vials_by_letter`; `_compare_conditions` NULL fix. |
| `tests/api/test_experiments.py` | **Modify.** New list tests; 2 existing tests updated. |
| `tests/api/test_experiment_rollup.py` | **Modify.** Group-response letter/vial tests; wrapper ordering determinism. |
| `frontend/src/api/experiments.ts` | **Modify.** Type the new fields. |
| `frontend/src/pages/ExperimentList.tsx` | **Modify.** Stem rendering, chip removal, badge, group link, read-only status. |
| `frontend/src/pages/ReplicateGroup/index.tsx` | **Modify.** Nested members table, header count, parent detail cells. |
| `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx` | **Modify.** Per-letter series. |
| `frontend/src/pages/__tests__/ExperimentList.test.tsx` | **Modify.** New tests; the `id_timepoint_days chip` block is replaced. |
| `frontend/src/pages/ReplicateGroup/__tests__/ReplicateGroupPage.test.tsx` | **Modify.** Nesting tests. |
| `frontend/src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx` | **Modify.** Series-count tests. |
| `.claude/rules/MODELS.md`, `docs/api/API_REFERENCE.md` | **Modify.** Letter-vs-vial grain; new response fields. |

---

## Task 1: The stem key module

**Files:**
- Create: `backend/services/replicate_collapse.py`
- Test: `tests/services/test_replicate_collapse.py`

**Interfaces:**
- Consumes: `database.experiment_id_parser.split_timepoint_token`, `database.models.experiments.Experiment`.
- Produces:
  - `TIMEPOINT_TOKEN_SQL_PATTERN: str`
  - `timepoint_stem_expr(col) -> ColumnElement[str]` — `col` is the `Experiment` class **or** a subquery's `.c` collection.
  - `@dataclass StemGroup(stem: str, representative: Experiment, vial_count: int)`
  - `collapse_by_stem(rows: Sequence[Experiment]) -> list[StemGroup]`

- [ ] **Step 1: Write the failing tests**

Create `tests/services/test_replicate_collapse.py`:

```python
"""Unit tests for the issue #98 timepoint-stem collapse key."""
from __future__ import annotations

from sqlalchemy import func, literal, select

from database.experiment_id_parser import split_timepoint_token
from database.models.enums import ExperimentStatus
from database.models.experiments import Experiment
from backend.services.replicate_collapse import (
    TIMEPOINT_TOKEN_SQL_PATTERN,
    collapse_by_stem,
    timepoint_stem_expr,
)

# IDs spanning every shape the grammar produces. Used by both the SQL test and
# the Python-agreement test so the two implementations cannot drift (D1).
STEM_CASES = [
    ("SERUM_001a-t1", "SERUM_001a"),
    ("SERUM_001a-t3", "SERUM_001a"),
    ("SERUM_001a-t0.5", "SERUM_001a"),
    ("SERUM_001a-t0", "SERUM_001a"),
    ("SERUM_001a", "SERUM_001a"),      # no token -> unchanged
    ("SERUM_001", "SERUM_001"),
    ("SERUM_001-t7", "SERUM_001"),     # letterless -t vial
    ("SERUM_001a-2", "SERUM_001a-2"),  # sequential re-run: NOT a timepoint
    ("CF-015", "CF-015"),              # trailing -NNN is not a token
    ("SERUM_001a_Desorption", "SERUM_001a_Desorption"),
    ("SERUM_001a-T7", "SERUM_001a-T7"),  # uppercase T is not the token
]


def timepoint_stem_expr_literal(experiment_id: str):
    """timepoint_stem_expr applied to a literal, so the agreement test does not
    depend on the ID grammar accepting every case above as a real row."""
    return func.regexp_replace(literal(experiment_id), TIMEPOINT_TOKEN_SQL_PATTERN, "")


def _add(db, experiment_id: str, number: int, **kw) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=number,
        status=ExperimentStatus.ONGOING,
        **kw,
    )
    db.add(exp)
    return exp


class TestTimepointStemExpr:
    def test_sql_strips_the_token(self, db_session):
        for i, (experiment_id, _) in enumerate(STEM_CASES):
            _add(db_session, f"RC1_{i}_{experiment_id}", 8100 + i)
        db_session.commit()
        # Query the expression directly against literal IDs rather than rows, so
        # the test does not depend on the ID grammar accepting the prefixes above.
        for experiment_id, expected in STEM_CASES:
            got = db_session.execute(
                select(timepoint_stem_expr(Experiment))
                .select_from(Experiment)
                .where(Experiment.experiment_id == experiment_id)
            ).scalar_one_or_none()
            if got is not None:
                assert got == expected

    def test_sql_and_python_agree(self, db_session):
        """The POSIX pattern and split_timepoint_token must never diverge."""
        for experiment_id, expected in STEM_CASES:
            sql_stem = db_session.execute(
                select(timepoint_stem_expr_literal(experiment_id))
            ).scalar_one()
            py_stem, _ = split_timepoint_token(experiment_id)
            assert sql_stem == py_stem == expected, experiment_id

    def test_pattern_is_anchored(self):
        assert TIMEPOINT_TOKEN_SQL_PATTERN.endswith("$")


class TestCollapseByStem:
    def test_groups_timepoint_vials_and_keeps_rerun_separate(self, db_session):
        a = _add(db_session, "RC2_001a", 8200, replicate_label="a")
        a_t1 = _add(db_session, "RC2_001a-t1", 8201, replicate_label="a", id_timepoint_days=1.0)
        a_2 = _add(db_session, "RC2_001a-2", 8202, replicate_label="a")
        db_session.commit()

        groups = collapse_by_stem([a, a_t1, a_2])

        assert [g.stem for g in groups] == ["RC2_001a", "RC2_001a-2"]
        assert groups[0].vial_count == 2
        assert groups[1].vial_count == 1

    def test_representative_prefers_clean_earliest_vial(self, db_session):
        """is_outlier leads the ordering (D7), then timepoint NULLS FIRST."""
        outlier = _add(db_session, "RC3_001a-t1", 8300, replicate_label="a",
                       id_timepoint_days=1.0, is_outlier=True)
        clean = _add(db_session, "RC3_001a-t3", 8301, replicate_label="a",
                     id_timepoint_days=3.0)
        db_session.commit()

        (group,) = collapse_by_stem([outlier, clean])

        assert group.representative.experiment_id == "RC3_001a-t3"
        assert group.vial_count == 2

    def test_null_timepoint_sorts_before_a_day_value(self, db_session):
        bare = _add(db_session, "RC4_001a", 8400, replicate_label="a")
        t0 = _add(db_session, "RC4_001a-t0", 8401, replicate_label="a", id_timepoint_days=0.0)
        db_session.commit()

        (group,) = collapse_by_stem([t0, bare])

        assert group.representative.experiment_id == "RC4_001a"

    def test_empty_input(self):
        assert collapse_by_stem([]) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```
.venv/Scripts/python -m pytest tests/services/test_replicate_collapse.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'backend.services.replicate_collapse'`.

- [ ] **Step 3: Create the module**

Create `backend/services/replicate_collapse.py`:

```python
"""Timepoint-vial collapsing (issue #98).

A sacrificial-timepoint vial differs from its siblings ONLY by the trailing
'-t<days>' token (issue #81): SERUM_001a, SERUM_001a-t1 and SERUM_001a-t3 are
the same logical replicate sampled at different times. Collapsing rows that
differ solely by that token is what lets the Experiments list show replicate
identity instead of one row per destroyed vial.

The collapse key is the experiment_id with the token stripped -- the "stem".
It is deliberately NOT (base_experiment_id, replicate_label):
parse_lineage_fields("SERUM_001a-2") returns ("SERUM_001", 2, None, "a"), so a
sequential re-run of a lettered replicate shares BOTH base and letter with
SERUM_001a and would be wrongly merged into it. There is no persisted
derivation-number column to separate them. See decision D1 in
docs/superpowers/specs/2026-07-29-issue-98-t-vial-replicate-collapsing-design.md.

PATTERN DUPLICATION -- the '-t<days>' pattern exists in three places and they
must stay aligned. tests/services/test_replicate_collapse.py::
TestTimepointStemExpr::test_sql_and_python_agree is the guard:
  1. database/experiment_id_parser.py::_TIMEPOINT_TOKEN_RE  (canonical, Python)
  2. frontend/src/utils/experimentId.ts::TIMEPOINT_TOKEN_RE  (TypeScript)
  3. TIMEPOINT_TOKEN_SQL_PATTERN below                       (POSIX, for Postgres)
Python-side stripping always reuses (1) via split_timepoint_token -- never add
a fourth copy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import func

from database.experiment_id_parser import split_timepoint_token
from database.models.experiments import Experiment

# POSIX-ERE equivalent of database/experiment_id_parser.py::_TIMEPOINT_TOKEN_RE:
# '-t' + digits + an optional decimal part, anchored to end-of-string. Lowercase
# 't' only. Anchoring means regexp_replace can match at most once, so its
# replace-first-only default is what we want.
TIMEPOINT_TOKEN_SQL_PATTERN = r"-t[0-9]+(\.[0-9]+)?$"


def timepoint_stem_expr(col):
    """SQL expression: `experiment_id` with a trailing '-t<days>' token stripped.

    A no-op for IDs without the token, so this is safe to apply unconditionally.

    `col` is either the ``Experiment`` class or a subquery's ``.c`` collection,
    matching the ``_bucket_key_expr(col)`` convention in
    ``backend/api/routers/experiments.py``.
    """
    return func.regexp_replace(col.experiment_id, TIMEPOINT_TOKEN_SQL_PATTERN, "")


@dataclass
class StemGroup:
    """Rows sharing one timepoint-stripped experiment_id."""
    stem: str
    representative: Experiment
    vial_count: int


def _representative_sort_key(exp: Experiment):
    """Clean vials before flagged ones (D7), then earliest timepoint with NULL
    first (a bare vial precedes its own -t vials), then lowest number."""
    return (
        bool(exp.is_outlier),
        exp.id_timepoint_days is not None,
        exp.id_timepoint_days if exp.id_timepoint_days is not None else 0.0,
        exp.experiment_number,
    )


def collapse_by_stem(rows: Sequence[Experiment]) -> list[StemGroup]:
    """Group rows by stem, preserving first-appearance order of the stems.

    Each group's `representative` is chosen by _representative_sort_key, so it
    is the earliest non-outlier vial. `vial_count` is the number of rows the
    group stands for.
    """
    buckets: dict[str, list[Experiment]] = {}
    order: list[str] = []
    for row in rows:
        stem, _days = split_timepoint_token(row.experiment_id)
        if stem not in buckets:
            buckets[stem] = []
            order.append(stem)
        buckets[stem].append(row)
    return [
        StemGroup(
            stem=stem,
            representative=min(buckets[stem], key=_representative_sort_key),
            vial_count=len(buckets[stem]),
        )
        for stem in order
    ]
```

- [ ] **Step 4: Run the tests to verify they pass**

```
.venv/Scripts/python -m pytest tests/services/test_replicate_collapse.py -v
```

Expected: PASS. If `test_sql_and_python_agree` fails on `SERUM_001a-t0.5`, the
POSIX pattern's decimal group is wrong — Postgres ARE treats `\.` as a literal
dot, so the pattern must be exactly `-t[0-9]+(\.[0-9]+)?$`.

- [ ] **Step 5: Commit**

```bash
git add backend/services/replicate_collapse.py tests/services/test_replicate_collapse.py
git commit -m "[#98] Add timepoint-stem collapse key module

- SQL expression, Python row collapser, SQL/Python agreement guard
- Tests added: yes
- Docs updated: no"
```

---

## Task 2: Ungrouped list mode collapses timepoint vials

**Files:**
- Modify: `backend/api/schemas/experiments.py:43-71`
- Modify: `backend/api/routers/experiments.py:225-227` (the `else` branch) and `:229-268` (the item loop)
- Test: `tests/api/test_experiments.py`

**Interfaces:**
- Consumes: `timepoint_stem_expr` from Task 1.
- Produces: `ExperimentListItem.group_display_id: Optional[str]`, `.vial_count: int = 1`, `.replicate_letters: Optional[list[str]]` (populated in Task 3).

- [ ] **Step 1: Write the failing tests**

Append to the grouping test class in `tests/api/test_experiments.py` (the class
containing `test_orphan_lettered_set_collapses_to_one_row`):

```python
    def _make_2x2(self, db_session, prefix: str, start: int) -> None:
        """2 letters x 2 timepoints, no parent row and no bare lettered rows --
        the issue #98 repro shape."""
        n = start
        for letter in ("a", "b"):
            for day in (1, 3):
                db_session.add(Experiment(
                    experiment_id=f"{prefix}_001{letter}-t{day}",
                    experiment_number=n,
                    status=ExperimentStatus.ONGOING,
                ))
                n += 1
        db_session.commit()

    def test_ungrouped_collapses_timepoint_vials_per_letter(self, client, db_session):
        """Issue #98 AC3: the 2x2 set renders exactly two rows, one per letter."""
        self._make_2x2(db_session, "T98UG", 9800)
        resp = client.get("/api/experiments?search=T98UG_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert {i["group_display_id"] for i in data["items"]} == {
            "T98UG_001a", "T98UG_001b",
        }
        assert all(i["vial_count"] == 2 for i in data["items"])

    def test_ungrouped_no_timepoint_data_is_unchanged(self, client, db_session):
        """Issue #98 AC4 regression guard: no -t vials -> identical to today."""
        for i, letter in enumerate("abc"):
            db_session.add(Experiment(
                experiment_id=f"T98PLAIN_001{letter}", experiment_number=9810 + i,
                status=ExperimentStatus.ONGOING,
            ))
        db_session.commit()
        resp = client.get("/api/experiments?search=T98PLAIN_001")
        data = resp.json()
        assert data["total"] == 3
        assert {i["experiment_id"] for i in data["items"]} == {
            "T98PLAIN_001a", "T98PLAIN_001b", "T98PLAIN_001c",
        }
        assert all(i["vial_count"] == 1 for i in data["items"])
        # group_display_id equals the ID itself when there is nothing to strip.
        assert all(i["group_display_id"] == i["experiment_id"] for i in data["items"])

    def test_ungrouped_sequential_rerun_is_not_collapsed_into_its_letter(self, client, db_session):
        """D1: SERUM_001a-2 shares base AND letter with SERUM_001a but is a
        re-run, not a timepoint variant. It must stay its own row."""
        db_session.add(Experiment(experiment_id="T98RR_001a", experiment_number=9820,
                                  status=ExperimentStatus.ONGOING))
        db_session.add(Experiment(experiment_id="T98RR_001a-t5", experiment_number=9821,
                                  status=ExperimentStatus.ONGOING))
        db_session.add(Experiment(experiment_id="T98RR_001a-2", experiment_number=9822,
                                  status=ExperimentStatus.ONGOING))
        db_session.commit()
        resp = client.get("/api/experiments?search=T98RR_001a")
        data = resp.json()
        assert data["total"] == 2
        assert {i["group_display_id"] for i in data["items"]} == {
            "T98RR_001a", "T98RR_001a-2",
        }

    def test_ungrouped_collapse_respects_filters(self, client, db_session):
        """Unlike grouped mode, ungrouped collapsing sees only matched rows, so a
        filter never yields a row claiming vials it excluded."""
        self._make_2x2(db_session, "T98FLT", 9830)
        resp = client.get("/api/experiments?search=T98FLT_001a-t3")
        data = resp.json()
        assert data["total"] == 1
        (item,) = data["items"]
        assert item["group_display_id"] == "T98FLT_001a"
        assert item["vial_count"] == 1

    def test_ungrouped_representative_skips_outlier_vial(self, client, db_session):
        """D7: an is_outlier vial never represents a collapsed row."""
        db_session.add(Experiment(experiment_id="T98OUT_001a-t1", experiment_number=9840,
                                  status=ExperimentStatus.ONGOING, is_outlier=True))
        db_session.add(Experiment(experiment_id="T98OUT_001a-t3", experiment_number=9841,
                                  status=ExperimentStatus.ONGOING))
        db_session.commit()
        resp = client.get("/api/experiments?search=T98OUT_001a")
        data = resp.json()
        assert data["total"] == 1
        (item,) = data["items"]
        assert item["experiment_id"] == "T98OUT_001a-t3"
        assert item["group_display_id"] == "T98OUT_001a"

    def test_ungrouped_pagination_counts_collapsed_rows(self, client, db_session):
        """Gap 7: pagination must page over collapsed rows, not raw vials."""
        self._make_2x2(db_session, "T98PAGE", 9850)
        resp = client.get("/api/experiments?search=T98PAGE_001&limit=1")
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

```
.venv/Scripts/python -m pytest tests/api/test_experiments.py -k "ungrouped" -v
```

Expected: FAIL — `KeyError: 'group_display_id'` / `total == 4` instead of `2`.

- [ ] **Step 3: Add the schema fields**

In `backend/api/schemas/experiments.py`, inside `ExperimentListItem`, replace:

```python
    # Grouped-list mode only (group_replicates=true): lettered children of this
    # group parent, ordered by replicate_label. None in flat mode / for non-parents.
    replicates: Optional[list["ExperimentListItem"]] = None
```

with:

```python
    # Issue #98. What the ID column should render: the group stem in grouped
    # mode, the timepoint-stripped stem in flat mode. `experiment_id` above
    # continues to name the real representative row -- do not conflate them.
    group_display_id: Optional[str] = None
    # Number of experiment rows this row stands for (1 = an ordinary row).
    vial_count: int = 1
    # Grouped mode only: the group's DISTINCT replicate letters, for the badge.
    # None in flat mode and for rows that are not groups.
    replicate_letters: Optional[list[str]] = None
    # Grouped-list mode only (group_replicates=true): one entry per replicate
    # letter-row of this group, collapsed on the timepoint stem (issue #98 D8 --
    # this includes the representative's own letter). None in flat mode and for
    # rows that are not groups.
    replicates: Optional[list["ExperimentListItem"]] = None
```

- [ ] **Step 4: Rewrite the ungrouped branch**

Add to the imports at the top of `backend/api/routers/experiments.py`:

```python
from database.experiment_id_parser import split_timepoint_token
from backend.services.replicate_collapse import collapse_by_stem, timepoint_stem_expr
```

Replace `backend/api/routers/experiments.py:225-227`:

```python
    else:
        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = db.execute(stmt.offset(skip).limit(limit)).scalars().all()
```

with:

```python
    else:
        # Flat mode: collapse rows that differ ONLY by the trailing '-t<days>'
        # token (issue #98 D1). SERUM_001a-t1 / SERUM_001a-t3 are one replicate
        # sampled twice, so they render as ONE row labeled SERUM_001a.
        #
        # Unlike the grouped branch above -- which resolves bucket membership
        # from the UNFILTERED table so that filtering to "b" still resolves
        # representative "a" -- this collapses only rows that PASSED the
        # filters. A filter therefore never produces a row claiming vials it
        # excluded, and vial_count always describes visible data.
        matched_sq = stmt.subquery()
        stem = timepoint_stem_expr(matched_sq.c)
        ranked_sq = select(
            matched_sq.c.id.label("id"),
            stem.label("stem"),
            func.row_number().over(
                partition_by=stem,
                order_by=(
                    matched_sq.c.is_outlier.asc(),
                    matched_sq.c.id_timepoint_days.asc().nulls_first(),
                    matched_sq.c.experiment_number.asc(),
                ),
            ).label("rn"),
            func.count().over(partition_by=stem).label("vial_count"),
        ).subquery()
        reps_sq = (
            select(ranked_sq.c.id, ranked_sq.c.stem, ranked_sq.c.vial_count)
            .where(ranked_sq.c.rn == 1)
            .subquery()
        )
        total = db.execute(select(func.count()).select_from(reps_sq)).scalar_one()
        rep_rows = db.execute(
            select(Experiment, reps_sq.c.stem, reps_sq.c.vial_count)
            .join(reps_sq, reps_sq.c.id == Experiment.id)
            .order_by(Experiment.experiment_number.desc())
            .offset(skip)
            .limit(limit)
        ).all()
        rows = [row[0] for row in rep_rows]
        flat_collapse = {row[0].id: (row[1], row[2]) for row in rep_rows}
```

- [ ] **Step 5: Populate the fields in the item loop**

In the item loop at `backend/api/routers/experiments.py:229-268`, replace:

```python
    items = []
    for exp in rows:
        item_data = _build_list_item(db, exp)
        if group_replicates:
```

with:

```python
    items = []
    for exp in rows:
        item_data = _build_list_item(db, exp)
        if not group_replicates:
            # Issue #98: label the row by its timepoint stem so the internal
            # '-t<days>' token never reaches the UI.
            stem, vial_count = flat_collapse[exp.id]
            item_data["group_display_id"] = stem
            item_data["vial_count"] = vial_count
        if group_replicates:
```

- [ ] **Step 6: Run the tests to verify they pass**

```
.venv/Scripts/python -m pytest tests/api/test_experiments.py -k "ungrouped" -v
```

Expected: PASS, all 6.

- [ ] **Step 7: Run the whole list-endpoint suite for regressions**

```
.venv/Scripts/python -m pytest tests/api/test_experiments.py -v
```

Expected: PASS. The grouped tests are untouched at this point because the
`group_replicates` branch has not changed.

- [ ] **Step 8: Commit**

```bash
git add backend/api/schemas/experiments.py backend/api/routers/experiments.py tests/api/test_experiments.py
git commit -m "[#98] Collapse timepoint vials in flat list mode

- Stem window in the ungrouped branch; group_display_id + vial_count
- Tests added: yes
- Docs updated: no"
```

---

## Task 3: Grouped list mode labels by stem and counts letters

**Files:**
- Modify: `backend/api/routers/experiments.py:178-192` (`_bucket_key_expr`), `:199-215` (rank), `:232-267` (grouped item block)
- Test: `tests/api/test_experiments.py`

**Interfaces:**
- Consumes: `collapse_by_stem`, `timepoint_stem_expr`, `split_timepoint_token`, and the Task 2 schema fields.
- Produces: grouped items carrying `group_display_id`, `replicate_letters`, `vial_count`, and a per-letter `replicates` array.

- [ ] **Step 1: Write the failing tests**

Append to the same grouping test class:

```python
    def test_grouped_2x2_is_one_row_labeled_by_stem(self, client, db_session):
        """Issue #98 AC2: one row, badge data for 2 letters, 4 vials."""
        self._make_2x2(db_session, "T98GR", 9860)
        resp = client.get("/api/experiments?group_replicates=true&search=T98GR_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        (item,) = data["items"]
        assert item["group_display_id"] == "T98GR_001"
        assert item["replicate_letters"] == ["a", "b"]
        assert item["vial_count"] == 4
        # One child row per letter -- not per vial.
        assert [r["group_display_id"] for r in item["replicates"]] == [
            "T98GR_001a", "T98GR_001b",
        ]
        assert all(r["vial_count"] == 2 for r in item["replicates"])

    def test_grouped_lone_timepoint_vial_shows_its_own_stem(self, client, db_session):
        """A single -t vial is not a group: it keeps its own letter identity
        rather than being relabeled with the bare base stem."""
        db_session.add(Experiment(experiment_id="T98LONE_001a-t1", experiment_number=9870,
                                  status=ExperimentStatus.ONGOING))
        db_session.commit()
        resp = client.get("/api/experiments?group_replicates=true&search=T98LONE_001")
        data = resp.json()
        assert data["total"] == 1
        (item,) = data["items"]
        assert item["group_display_id"] == "T98LONE_001a"
        assert item["vial_count"] == 1
        assert item["replicates"] is None
        assert item["replicate_letters"] is None

    def test_grouped_letterless_timepoint_vial_joins_its_parent_row(self, client, db_session):
        """A letterless -t vial buckets on its stem, so it joins the real parent
        row instead of becoming a second row with the same displayed label."""
        _make_experiment(db_session, experiment_id="T98LL_001", number=9880)
        db_session.add(Experiment(experiment_id="T98LL_001-t7", experiment_number=9881,
                                  status=ExperimentStatus.ONGOING))
        db_session.commit()
        resp = client.get("/api/experiments?group_replicates=true&search=T98LL_001")
        data = resp.json()
        assert data["total"] == 1
        (item,) = data["items"]
        assert item["group_display_id"] == "T98LL_001"
        assert item["vial_count"] == 2

    def test_grouped_no_timepoint_data_is_unchanged(self, client, db_session):
        """Issue #98 AC4 regression guard for grouped mode."""
        _make_experiment(db_session, experiment_id="T98GPLAIN_001", number=9890)
        for i, letter in enumerate("ab"):
            db_session.add(Experiment(
                experiment_id=f"T98GPLAIN_001{letter}", experiment_number=9891 + i,
                status=ExperimentStatus.ONGOING,
            ))
        db_session.commit()
        resp = client.get("/api/experiments?group_replicates=true&search=T98GPLAIN_001")
        data = resp.json()
        assert data["total"] == 1
        (item,) = data["items"]
        assert item["experiment_id"] == "T98GPLAIN_001"
        assert item["group_display_id"] == "T98GPLAIN_001"
        assert item["replicate_letters"] == ["a", "b"]
        assert item["vial_count"] == 3
        assert [r["experiment_id"] for r in item["replicates"]] == [
            "T98GPLAIN_001a", "T98GPLAIN_001b",
        ]

    def test_grouped_representative_skips_outlier_vial(self, client, db_session):
        """Gap 8 / D7: an outlier vial must not supply the row's Sample and
        Additives columns while a clean sibling exists."""
        db_session.add(Experiment(experiment_id="T98GOUT_001a", experiment_number=9900,
                                  status=ExperimentStatus.ONGOING, is_outlier=True))
        db_session.add(Experiment(experiment_id="T98GOUT_001b", experiment_number=9901,
                                  status=ExperimentStatus.ONGOING))
        db_session.commit()
        resp = client.get("/api/experiments?group_replicates=true&search=T98GOUT_001")
        data = resp.json()
        (item,) = data["items"]
        assert item["experiment_id"] == "T98GOUT_001b"
        assert item["replicate_letters"] == ["a", "b"]

    def test_grouped_pagination_with_multi_timepoint_set(self, client, db_session):
        """Gap 7: a 2x2 set plus a standalone row is 2 pages of 1, not 5 rows."""
        self._make_2x2(db_session, "T98GPAGE", 9700)
        _make_experiment(db_session, experiment_id="T98GPAGE_SOLO_001", number=9709)
        resp = client.get(
            "/api/experiments?group_replicates=true&search=T98GPAGE&limit=1"
        )
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 1

    def test_grouped_letter_plus_rerun_expands_to_three_rows(self, client, db_session):
        """D12 consequence, made explicit: the badge counts LETTERS while the
        expansion has one row per STEM, so a letter with a sequential re-run
        yields "2 replicates: a, b" expanding to three child rows. Rare, and
        deliberate -- SERUM_001a-2 is not a timepoint variant of SERUM_001a."""
        for i, suffix in enumerate(("a", "a-2", "b")):
            db_session.add(Experiment(
                experiment_id=f"T98D12_001{suffix}", experiment_number=9690 + i,
                status=ExperimentStatus.ONGOING,
            ))
        db_session.commit()
        resp = client.get("/api/experiments?group_replicates=true&search=T98D12_001")
        data = resp.json()
        assert data["total"] == 1
        (item,) = data["items"]
        assert item["replicate_letters"] == ["a", "b"]
        assert [r["group_display_id"] for r in item["replicates"]] == [
            "T98D12_001a", "T98D12_001a-2", "T98D12_001b",
        ]
```

Then update the two existing tests. Replace the last line of
`test_orphan_lettered_set_collapses_to_one_row`:

```python
        assert [r["replicate_label"] for r in item["replicates"]] == ["b", "c"]
```

with:

```python
        # Issue #98 D8: `replicates` lists ALL letter-rows, including the
        # representative's own letter, because the row is now labeled by stem
        # and the badge must be able to read "3 replicates: a, b, c".
        assert [r["replicate_label"] for r in item["replicates"]] == ["a", "b", "c"]
        assert item["group_display_id"] == "GRP_ORPHSET_001"
        assert item["replicate_letters"] == ["a", "b", "c"]
```

Replace `test_timepoint_variant_shares_letter_no_dedupe` entirely:

```python
    def test_timepoint_variant_collapses_into_its_letter(self, client, db_session):
        """Issue #98: a '-t<days>' vial shares its letter with its parent vial
        and must COLLAPSE into that letter's single row -- superseding the
        pre-#98 behavior where both attached as separate replicates."""
        _make_experiment(db_session, experiment_id="GRPT_001", number=9730)
        db_session.add(Experiment(experiment_id="GRPT_001a", experiment_number=9731,
                                   status=ExperimentStatus.ONGOING))
        db_session.add(Experiment(experiment_id="GRPT_001a-t7", experiment_number=9732,
                                   status=ExperimentStatus.ONGOING))
        db_session.commit()
        resp = client.get("/api/experiments?group_replicates=true&search=GRPT_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["experiment_id"] == "GRPT_001"
        assert item["group_display_id"] == "GRPT_001"
        assert item["replicate_letters"] == ["a"]
        assert item["vial_count"] == 3
        # ONE letter-row, represented by the bare vial (NULLS FIRST on timepoint).
        assert [r["experiment_id"] for r in item["replicates"]] == ["GRPT_001a"]
        assert item["replicates"][0]["vial_count"] == 2
        assert item["replicates"][0]["group_display_id"] == "GRPT_001a"
```

- [ ] **Step 2: Run the tests to verify they fail**

```
.venv/Scripts/python -m pytest tests/api/test_experiments.py -k "grouped or timepoint_variant or orphan_lettered" -v
```

Expected: FAIL — `group_display_id` is `None`, `replicate_letters` is `None`,
and the letterless-`-t` test returns `total == 2`.

- [ ] **Step 3: Fix the bucket key so letterless `-t` vials join their stem**

In `_bucket_key_expr` (`backend/api/routers/experiments.py:178-192`), change the
final line from `else_=col.experiment_id` to the stem expression, and extend the
docstring comment. The `else_` branch becomes:

```python
                # Issue #98: strip a trailing '-t<days>' token here. Without
                # this, a letterless timepoint vial (SERUM_001-t7) buckets on
                # its own raw ID and renders as a SECOND top-level row carrying
                # the same displayed label as the real SERUM_001 row. A no-op
                # for every ID without the token, so no existing bucket moves.
                else_=timepoint_stem_expr(col),
```

- [ ] **Step 4: Put `is_outlier` first in the representative ranking**

In the `ranked_sq` window (`backend/api/routers/experiments.py:200-215`), change
the `order_by` tuple to:

```python
                    order_by=(
                        is_parent_like,
                        # D7 / gap 8: a flagged vial must never represent the
                        # group while a clean sibling exists -- the
                        # representative supplies the row's Sample, Reactor,
                        # Date, Description and Additives columns.
                        Experiment.is_outlier.asc(),
                        Experiment.replicate_label.asc(),
                        Experiment.id_timepoint_days.asc().nulls_first(),
                        Experiment.experiment_number.asc(),
                    ),
```

- [ ] **Step 5: Rewrite the grouped item block**

Replace `backend/api/routers/experiments.py:250-267` — from the `members = db.execute(` line through the `item_data["replicates"] = [...]` assignment — with:

```python
            # Every row in this bucket, resolved from the UNFILTERED table so a
            # filtered query still describes the whole group. Matching on the
            # bucket-key expression (rather than base_experiment_id) is what
            # picks up letterless '-t' vials; it costs a scan per page row,
            # which is fine at this table's size and matches the existing
            # per-row queries in _build_list_item.
            bucket_rows = db.execute(
                select(Experiment)
                .where(_bucket_key_expr(Experiment) == bucket_key)
                .order_by(
                    Experiment.replicate_label.asc().nulls_first(),
                    Experiment.id_timepoint_days.asc().nulls_first(),
                    Experiment.experiment_number.asc(),
                )
            ).scalars().all()
            members = [m for m in bucket_rows if m.replicate_label is not None]
            item_data["vial_count"] = len(bucket_rows)

            if len(bucket_rows) > 1 and members:
                # A real group: label the row by the group stem (issue #98 D2).
                item_data["group_display_id"] = bucket_key
                item_data["replicate_letters"] = sorted(
                    {m.replicate_label for m in members}
                )
                # One child per letter-row, collapsed on the timepoint stem
                # (D1/D12) -- so SERUM_001a + SERUM_001a-t3 is one child, while
                # SERUM_001a-2 stays its own. Includes the representative's own
                # letter (D8), unlike the pre-#98 siblings-only list.
                item_data["replicates"] = []
                for group in collapse_by_stem(members):
                    child = _build_list_item(db, group.representative)
                    child["group_display_id"] = group.stem
                    child["vial_count"] = group.vial_count
                    item_data["replicates"].append(
                        ExperimentListItem.model_validate(child)
                    )
            else:
                # Not a group (standalone row, or a lone vial): show this row's
                # own stem so the '-t' token still never reaches the UI.
                item_data["group_display_id"] = split_timepoint_token(
                    exp.experiment_id
                )[0]
```

- [ ] **Step 6: Run the tests to verify they pass**

```
.venv/Scripts/python -m pytest tests/api/test_experiments.py -v
```

Expected: PASS, including the two rewritten tests and
`test_orphan_member_stays_top_level` / `test_standalone_experiment_has_no_replicates`
(both still get `replicates is None`, because their buckets hold one row).

- [ ] **Step 7: Commit**

```bash
git add backend/api/routers/experiments.py tests/api/test_experiments.py
git commit -m "[#98] Label grouped rows by stem, count letters

- Bucket key strips -t; is_outlier leads ranking; per-letter replicates
- Tests added: yes
- Docs updated: no"
```

---

## Task 4: Group endpoint exposes letters and stops NULL-conditions amplification

**Files:**
- Modify: `backend/services/replicate_groups.py:94-125` (`_compare_conditions`), plus a new `group_vials_by_letter`
- Modify: `backend/api/schemas/experiments.py:126-171`
- Modify: `backend/api/routers/experiments.py:321-351` (mappers), `:493-511` (wrapper ordering)
- Test: `tests/api/test_experiment_rollup.py`

**Interfaces:**
- Produces:
  - `replicate_groups.LetterGroupData(replicate_label: str, vials: list[GroupMemberData])`
  - `replicate_groups.group_vials_by_letter(members: Sequence[GroupMemberData]) -> list[LetterGroupData]`
  - `GroupData.replicates: list[LetterGroupData]`
  - Schema `ReplicateLetterGroup(replicate_label: str, vials: list[ReplicateGroupMemberDetail])`
  - `ReplicateGroupDetailResponse.replicates: list[ReplicateLetterGroup]`, `.replicate_count: int`
  - `ReplicateGroupDetailResponse.parent: Optional[ReplicateGroupMemberDetail]` (widened)

- [ ] **Step 1: Write the failing tests**

Add to `tests/api/test_experiment_rollup.py`:

```python
class TestGroupLettersVsVials:
    """Issue #98: the group response must distinguish replicates from vials."""

    def _make_2x2(self, db_session, prefix: str, start: int):
        n = start
        for letter in ("a", "b"):
            for day in (1, 3):
                db_session.add(Experiment(
                    experiment_id=f"{prefix}_001{letter}-t{day}",
                    experiment_number=n, status=ExperimentStatus.ONGOING,
                ))
                n += 1
        db_session.commit()

    def test_reports_two_replicates_and_four_vials(self, client, db_session):
        """Issue #98 AC5."""
        self._make_2x2(db_session, "G98AC5", 9910)
        resp = client.get("/api/experiments/groups/G98AC5_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["replicate_count"] == 2
        assert data["member_count"] == 4          # unchanged per-vial meaning
        assert len(data["members"]) == 4
        assert [r["replicate_label"] for r in data["replicates"]] == ["a", "b"]
        assert [
            [v["experiment_id"] for v in r["vials"]] for r in data["replicates"]
        ] == [
            ["G98AC5_001a-t1", "G98AC5_001a-t3"],
            ["G98AC5_001b-t1", "G98AC5_001b-t3"],
        ]

    def test_vials_carry_timepoint_and_result_count(self, client, db_session):
        """Gap 6: result_count is per vial, not per letter."""
        self._make_2x2(db_session, "G98RC", 9920)
        vial = db_session.execute(
            select(Experiment).where(Experiment.experiment_id == "G98RC_001a-t1")
        ).scalar_one()
        db_session.add(ExperimentalResults(
            experiment_fk=vial.id, experiment_id=vial.experiment_id,
            time_post_reaction_days=1.0, time_post_reaction_bucket_days=1.0,
            is_primary_timepoint_result=True, description="t1",
        ))
        db_session.commit()

        resp = client.get("/api/experiments/groups/G98RC_001")
        letter_a = resp.json()["replicates"][0]
        by_id = {v["experiment_id"]: v for v in letter_a["vials"]}
        assert by_id["G98RC_001a-t1"]["result_count"] == 1
        assert by_id["G98RC_001a-t1"]["id_timepoint_days"] == 1.0
        assert by_id["G98RC_001a-t3"]["result_count"] == 0

    def test_single_vial_letters_still_produce_one_vial_each(self, client, db_session):
        """D10 regression guard: a plain a/b/c set nests one vial per letter."""
        for i, letter in enumerate("abc"):
            db_session.add(Experiment(
                experiment_id=f"G98PLAIN_001{letter}", experiment_number=9930 + i,
                status=ExperimentStatus.ONGOING,
            ))
        db_session.commit()
        data = client.get("/api/experiments/groups/G98PLAIN_001").json()
        assert data["replicate_count"] == 3
        assert data["member_count"] == 3
        assert all(len(r["vials"]) == 1 for r in data["replicates"])


class TestGroupConditionsDivergence:
    """Issue #98 AC8 / D5: a vial with no conditions row must not push every
    field into divergent_fields."""

    def test_missing_conditions_row_does_not_amplify_divergence(self, client, db_session):
        a = Experiment(experiment_id="G98DIV_001a-t1", experiment_number=9940,
                       status=ExperimentStatus.ONGOING)
        b = Experiment(experiment_id="G98DIV_001b-t1", experiment_number=9941,
                       status=ExperimentStatus.ONGOING)
        no_cond = Experiment(experiment_id="G98DIV_001b-t3", experiment_number=9942,
                             status=ExperimentStatus.ONGOING)
        db_session.add_all([a, b, no_cond])
        db_session.flush()
        for exp in (a, b):
            db_session.add(ExperimentalConditions(
                experiment_fk=exp.id, experiment_id=exp.experiment_id,
                temperature_c=90.0, experiment_type="Serum", rock_mass_g=5.0,
            ))
        db_session.commit()

        data = client.get("/api/experiments/groups/G98DIV_001").json()

        assert data["shared_conditions"]["temperature_c"] == 90.0
        assert data["shared_conditions"]["rock_mass_g"] == 5.0
        assert "temperature_c" not in data["divergent_fields"]
        assert "rock_mass_g" not in data["divergent_fields"]

    def test_real_divergence_is_still_reported(self, db_session, client):
        """D6: the comparison grain stays per-vial, so genuinely differing
        values still surface -- including between two vials of one letter."""
        a1 = Experiment(experiment_id="G98REAL_001a-t1", experiment_number=9950,
                        status=ExperimentStatus.ONGOING)
        a3 = Experiment(experiment_id="G98REAL_001a-t3", experiment_number=9951,
                        status=ExperimentStatus.ONGOING)
        db_session.add_all([a1, a3])
        db_session.flush()
        db_session.add(ExperimentalConditions(
            experiment_fk=a1.id, experiment_id=a1.experiment_id, rock_mass_g=5.0))
        db_session.add(ExperimentalConditions(
            experiment_fk=a3.id, experiment_id=a3.experiment_id, rock_mass_g=5.4))
        db_session.commit()

        data = client.get("/api/experiments/groups/G98REAL_001").json()

        assert "rock_mass_g" in data["divergent_fields"]
        vials = data["replicates"][0]["vials"]
        assert {v["conditions"]["rock_mass_g"] for v in vials} == {5.0, 5.4}

    def test_all_vials_missing_conditions_yields_empty_scan(self, client, db_session):
        for i, letter in enumerate("ab"):
            db_session.add(Experiment(
                experiment_id=f"G98NONE_001{letter}", experiment_number=9960 + i,
                status=ExperimentStatus.ONGOING,
            ))
        db_session.commit()
        data = client.get("/api/experiments/groups/G98NONE_001").json()
        assert data["divergent_fields"] == []
        assert data["shared_conditions"] == {}


class TestReplicateGroupWrapperOrdering:
    """Gap 5: /{experiment_id}/replicate-group ordered by replicate_label only,
    so member order was nondeterministic for duplicate labels."""

    def test_member_order_is_deterministic_for_duplicate_labels(self, client, db_session):
        db_session.add(Experiment(experiment_id="G98ORD_001a-t3", experiment_number=9971,
                                   status=ExperimentStatus.ONGOING))
        db_session.add(Experiment(experiment_id="G98ORD_001a-t1", experiment_number=9970,
                                   status=ExperimentStatus.ONGOING))
        db_session.commit()
        data = client.get("/api/experiments/G98ORD_001a-t1/replicate-group").json()
        assert [m["experiment_id"] for m in data["members"]] == [
            "G98ORD_001a-t1", "G98ORD_001a-t3",
        ]
```

Ensure the file's imports include `ExperimentalConditions`, `ExperimentalResults`,
and `select` — add any that are missing.

- [ ] **Step 2: Run the tests to verify they fail**

```
.venv/Scripts/python -m pytest tests/api/test_experiment_rollup.py -k "GroupLettersVsVials or GroupConditionsDivergence or WrapperOrdering" -v
```

Expected: FAIL — `KeyError: 'replicate_count'`, and
`temperature_c` present in `divergent_fields`.

- [ ] **Step 3: Add letter grouping and fix `_compare_conditions`**

In `backend/services/replicate_groups.py`, add after the `GroupMemberData`
dataclass:

```python
@dataclass
class LetterGroupData:
    """One replicate letter and the vials carrying it, in display order.

    A letter maps to several vials when the set is sacrificed per timepoint
    (issue #98): letter "a" of SERUM_001 is SERUM_001a-t1 plus SERUM_001a-t3.
    """
    replicate_label: str
    vials: list[GroupMemberData] = field(default_factory=list)
```

Add `replicates: list[LetterGroupData]` to `GroupData` (after `members`), then
add this function below `_fetch_members`:

```python
def group_vials_by_letter(members: Sequence[GroupMemberData]) -> list[LetterGroupData]:
    """Group members by replicate_label, preserving input order (issue #98).

    `members` arrives already ordered by _fetch_members (replicate_label,
    id_timepoint_days NULLS FIRST, experiment_number), so letters come out
    alphabetically and each letter's vials come out in timepoint order.
    Members with a NULL label are skipped -- the group parent is carried
    separately on GroupData.parent.
    """
    groups: dict[str, LetterGroupData] = {}
    order: list[str] = []
    for member in members:
        label = member.experiment.replicate_label
        if label is None:
            continue
        if label not in groups:
            groups[label] = LetterGroupData(replicate_label=label)
            order.append(label)
        groups[label].vials.append(member)
    return [groups[label] for label in order]
```

Add `Sequence` to the `typing` import on line 18.

**Do NOT add `is_outlier` to `_fetch_members`'s `order_by` (`:86-90`).** The
issue's test gap 8 names that clause alongside the list-endpoint one, but it feeds
the members table's *display* order, not a representative choice — and under D10
the group page never picks a canonical vial (a single-vial letter renders that
vial; a multi-vial letter renders the letter with its vials nested). Leading with
`is_outlier` would sort every flagged vial to the end and break letter adjacency;
placing it after `replicate_label` would shuffle a letter's vials out of day
order. Leave the clause exactly as it is. See spec D7.

Replace the body of `_compare_conditions` (`:94-125`) with:

```python
def _compare_conditions(
    members: list[Experiment],
) -> tuple[dict[str, Any], list[str], dict[int, dict[str, Any]]]:
    """Compare each condition field across members. Identical value across
    every compared member -> shared. Any field that differs -> divergent_fields,
    with each member's own value carried in the returned per-member map.

    Issue #98 (D5): a member with NO `conditions` row is EXCLUDED from the
    scan rather than contributing None for every field. Sacrificial-timepoint
    vials frequently have no conditions row of their own, and treating them as
    all-None pushed nearly every field out of shared_conditions and into
    "varies -- see members table". A NULL field WITHIN an existing conditions
    row still counts as a real value that can differ (D5); the grain stays
    per-vial rather than per-letter (D6).

    Excluded members still receive an entry in the per-member map (all
    divergent fields -> None) so their table cells render as em dashes.
    """
    if not members:
        return {}, [], {}

    fields = _condition_field_names()
    compared = [m for m in members if m.conditions is not None]

    values_by_member_id: dict[int, dict[str, Any]] = {}
    for member in members:
        cond = member.conditions
        values_by_member_id[member.id] = {
            f: getattr(cond, f, None) if cond is not None else None for f in fields
        }

    shared_conditions: dict[str, Any] = {}
    divergent_fields: list[str] = []
    if compared:
        for f in fields:
            values = [values_by_member_id[m.id][f] for m in compared]
            if all(v == values[0] for v in values):
                shared_conditions[f] = values[0]
            else:
                divergent_fields.append(f)

    per_member_divergent = {
        m.id: {f: values_by_member_id[m.id][f] for f in divergent_fields}
        for m in members
    }
    return shared_conditions, divergent_fields, per_member_divergent
```

Finally, in `resolve_group`, populate the new field — after `member_data` is
built, change the `return GroupData(` call to include:

```python
        replicates=group_vials_by_letter(member_data),
```

- [ ] **Step 4: Add the schemas**

In `backend/api/schemas/experiments.py`, insert after `ReplicateGroupMemberDetail`:

```python
class ReplicateLetterGroup(BaseModel):
    """One replicate letter and its vials (issue #98).

    A letter maps to several vials when the replicate set is sacrificed per
    timepoint: letter "a" of SERUM_001 is SERUM_001a-t1 plus SERUM_001a-t3.
    """
    replicate_label: str
    vials: list[ReplicateGroupMemberDetail] = []
```

In `ReplicateGroupDetailResponse`, change `parent` and add the two fields:

```python
    # Widened from ReplicateGroupMember (issue #98) so a parent that has its own
    # results can render its Timepoint / Results / divergent cells instead of
    # hard-coding em dashes.
    parent: Optional[ReplicateGroupMemberDetail] = None
    members: list[ReplicateGroupMemberDetail] = []
    # Per-VIAL count -- unchanged meaning, still equal to len(members).
    member_count: int = 0
    # Issue #98: the same members grouped by replicate letter, plus the count of
    # LETTERS. `member_count` above stays per-vial; these are additive.
    replicates: list[ReplicateLetterGroup] = []
    replicate_count: int = 0
```

- [ ] **Step 5: Wire the router mappers**

In `backend/api/routers/experiments.py`, add `ReplicateLetterGroup` to the schema
import block, then replace `_group_data_to_detail_response` (`:340-351`):

```python
def _group_data_to_detail_response(group: GroupData) -> ReplicateGroupDetailResponse:
    return ReplicateGroupDetailResponse(
        base_experiment_id=group.base_experiment_id,
        parent=(
            _group_member_to_detail(GroupMemberData(experiment=group.parent))
            if group.parent else None
        ),
        members=[_group_member_to_detail(m) for m in group.members],
        member_count=len(group.members),
        replicates=[
            ReplicateLetterGroup(
                replicate_label=letter.replicate_label,
                vials=[_group_member_to_detail(v) for v in letter.vials],
            )
            for letter in group.replicates
        ],
        replicate_count=len(group.replicates),
        shared_conditions=group.shared_conditions,
        divergent_fields=group.divergent_fields,
        additives_summary=group.additives_summary,
        additive_names=group.additive_names,
        additives_diverge=group.additives_diverge,
    )
```

Add `GroupMemberData` to the `backend.services.replicate_groups` import block.
The parent is wrapped in a bare `GroupMemberData` because `resolve_group` returns
it as a plain `Experiment`; its `result_count` is therefore `0` and its
`conditions` `{}` — acceptable, since the parent's own values are not part of the
group's divergence scan.

Then add a timepoint tiebreak to **both** `order_by` clauses in
`get_replicate_group` (`:500` and `:510`), replacing
`.order_by(Experiment.replicate_label.asc())` with:

```python
            .order_by(
                Experiment.replicate_label.asc(),
                # Gap 5: labels are not unique -- a '-t<days>' vial shares its
                # letter with its parent vial, so without this tiebreak member
                # order is nondeterministic.
                Experiment.id_timepoint_days.asc().nulls_first(),
                Experiment.experiment_number.asc(),
            )
```

- [ ] **Step 6: Run the tests to verify they pass**

```
.venv/Scripts/python -m pytest tests/api/test_experiment_rollup.py -v
```

Expected: PASS, including the pre-existing
`TestReplicateGroupWrapperShapes` regression class.

- [ ] **Step 7: Run the full backend API and view suites**

```
.venv/Scripts/python -m pytest tests/api tests/views tests/services -q
```

Expected: PASS. Do **not** run a bare `pytest -q` to judge this: the full-suite
run has 3 pre-existing failures in `tests/test_pg_backup_restore.py` caused by
another file's `drop_all()` teardown, unrelated to this branch.

- [ ] **Step 8: Commit**

```bash
git add backend/services/replicate_groups.py backend/api/schemas/experiments.py backend/api/routers/experiments.py tests/api/test_experiment_rollup.py
git commit -m "[#98] Expose replicate letters on the group response

- replicates/replicate_count, parent widened, NULL-conditions scan fix
- Tests added: yes
- Docs updated: no"
```

---

## Task 5: Experiments list page hides the token and links to the group

**Files:**
- Modify: `frontend/src/api/experiments.ts:5-25`
- Modify: `frontend/src/pages/ExperimentList.tsx:209-241` (badge + expansion), `:287-352` (`ExperimentRow`)
- Test: `frontend/src/pages/__tests__/ExperimentList.test.tsx`

**Interfaces:**
- Consumes: `group_display_id`, `vial_count`, `replicate_letters`, `replicates` from Tasks 2–3.

- [ ] **Step 1: Type the new fields**

In `frontend/src/api/experiments.ts`, inside `ExperimentListItem`, replace the
`replicates` line with:

```typescript
  /** Issue #98: what the ID column renders — the group stem in grouped mode,
   *  the timepoint-stripped stem in flat mode. `experiment_id` above still
   *  names the real representative row. */
  group_display_id?: string | null
  /** Number of experiment rows this row stands for (1 = an ordinary row). */
  vial_count?: number
  /** Grouped mode only: the group's distinct replicate letters, for the badge. */
  replicate_letters?: string[] | null
  /** Grouped-list mode only: one entry per replicate letter-row of this group. */
  replicates?: ExperimentListItem[] | null
```

- [ ] **Step 2: Write the failing tests**

In `frontend/src/pages/__tests__/ExperimentList.test.tsx`, add
`group_display_id`, `vial_count`, and `replicate_letters` to `makeGroupedItem`'s
returned object so the fixture matches the backend contract:

```typescript
  return {
    ...base, id: 1, experiment_id: 'SERUM_001', experiment_number: 100,
    group_display_id: 'SERUM_001', vial_count: 4,
    replicate_letters: ['a', 'b', 'c'],
    replicates: ['a', 'b', 'c'].map((letter, i) => ({
      ...base, id: 10 + i, experiment_id: `SERUM_001${letter}`, experiment_number: 101 + i,
      base_experiment_id: 'SERUM_001', parent_experiment_fk: 1, replicate_label: letter,
      group_display_id: `SERUM_001${letter}`, vial_count: 1,
    })),
  }
```

**Replace the entire `describe('ExperimentListPage — id_timepoint_days chip', …)`
block** (`:261-288`) — it asserts the exact behavior issue #98 removes — with:

```typescript
describe('ExperimentListPage — issue #98: the -t token is never rendered', () => {
  const base = {
    status: 'ONGOING' as const, researcher: null, date: null, sample_id: null,
    created_at: '2026-07-01T00:00:00Z', experiment_type: 'Serum', reactor_number: null,
    additives_summary: null, condition_note: null,
    base_experiment_id: null as string | null, parent_experiment_fk: null as number | null,
    replicate_label: null as string | null, is_outlier: false,
  }

  afterEach(() => { vi.clearAllMocks() })

  it('renders group_display_id instead of the raw -t id, with no day chip', async () => {
    vi.mocked(experimentsApi.list).mockResolvedValue({
      items: [
        { ...base, id: 1, experiment_id: 'SERUM_001a-t7', experiment_number: 100,
          id_timepoint_days: 7, group_display_id: 'SERUM_001a', vial_count: 1 },
        { ...base, id: 2, experiment_id: 'SERUM_002', experiment_number: 101,
          id_timepoint_days: null, group_display_id: 'SERUM_002', vial_count: 1 },
      ],
      total: 2, skip: 0, limit: 25,
    })

    const { container } = render(<ExperimentListPage />, { wrapper })

    await waitFor(() => expect(screen.getByText('SERUM_001a')).toBeInTheDocument())
    expect(screen.getByText('SERUM_002')).toBeInTheDocument()
    // AC1: no -t substring and no day chip anywhere on the page.
    expect(container.textContent).not.toMatch(/-t\d/)
    expect(screen.queryByText(/^day /)).not.toBeInTheDocument()
  })

  it('falls back to experiment_id when group_display_id is absent', async () => {
    vi.mocked(experimentsApi.list).mockResolvedValue({
      items: [{ ...base, id: 1, experiment_id: 'SERUM_003', experiment_number: 102,
                id_timepoint_days: null }],
      total: 1, skip: 0, limit: 25,
    })
    render(<ExperimentListPage />, { wrapper })
    await waitFor(() => expect(screen.getByText('SERUM_003')).toBeInTheDocument())
  })
})

describe('ExperimentListPage — issue #98: group rows', () => {
  const base = {
    status: 'ONGOING' as const, researcher: null, date: null, sample_id: null,
    created_at: '2026-07-01T00:00:00Z', experiment_type: 'Serum', reactor_number: null,
    additives_summary: null, condition_note: null,
    base_experiment_id: 'SERUM_001' as string | null,
    parent_experiment_fk: null as number | null,
    replicate_label: 'a' as string | null, is_outlier: false,
    id_timepoint_days: 1 as number | null,
  }

  function twoByTwo(): ExperimentListItem {
    return {
      ...base, id: 1, experiment_id: 'SERUM_001a-t1', experiment_number: 100,
      group_display_id: 'SERUM_001', vial_count: 4, replicate_letters: ['a', 'b'],
      replicates: [
        { ...base, id: 2, experiment_id: 'SERUM_001a-t1', experiment_number: 100,
          replicate_label: 'a', group_display_id: 'SERUM_001a', vial_count: 2 },
        { ...base, id: 3, experiment_id: 'SERUM_001b-t1', experiment_number: 102,
          replicate_label: 'b', group_display_id: 'SERUM_001b', vial_count: 2 },
      ],
    }
  }

  beforeEach(() => {
    vi.mocked(experimentsApi.list).mockResolvedValue({
      items: [twoByTwo()], total: 1, skip: 0, limit: 25,
    })
  })
  afterEach(() => { vi.clearAllMocks() })

  it('badge counts distinct letters, not sibling rows', async () => {
    render(<ExperimentListPage />, { wrapper })
    await waitFor(() => expect(screen.getByText('SERUM_001')).toBeInTheDocument())
    expect(screen.getByText('2 replicates: a, b')).toBeInTheDocument()
  })

  it('expands to one row per letter, still with no -t token', async () => {
    const user = userEvent.setup()
    const { container } = render(<ExperimentListPage />, { wrapper })
    await waitFor(() => expect(screen.getByText('SERUM_001')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /expand replicates/i }))
    expect(screen.getByText('SERUM_001a')).toBeInTheDocument()
    expect(screen.getByText('SERUM_001b')).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/-t\d/)
  })

  it('renders status read-only on a multi-vial row', async () => {
    render(<ExperimentListPage />, { wrapper })
    await waitFor(() => expect(screen.getByText('SERUM_001')).toBeInTheDocument())
    // The editable dropdown must be absent while the row stands for 4 vials.
    expect(screen.queryByRole('combobox', { name: /row status/i })).not.toBeInTheDocument()
  })

  it('keeps the status dropdown on a single-vial row', async () => {
    vi.mocked(experimentsApi.list).mockResolvedValue({
      items: [{ ...base, id: 9, experiment_id: 'SERUM_009', experiment_number: 109,
                replicate_label: null, id_timepoint_days: null,
                group_display_id: 'SERUM_009', vial_count: 1 }],
      total: 1, skip: 0, limit: 25,
    })
    render(<ExperimentListPage />, { wrapper })
    await waitFor(() => expect(screen.getByText('SERUM_009')).toBeInTheDocument())
    expect(screen.getByRole('combobox', { name: /row status/i })).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run the tests to verify they fail**

```
cd frontend
npx vitest run src/pages/__tests__/ExperimentList.test.tsx
```

Expected: FAIL — `SERUM_001a` not found (raw `-t` ID rendered), badge reads
`2 replicates: a, b` only by accident of array length, and no accessible name
`row status` exists yet.

- [ ] **Step 4: Update `ExperimentRow`**

In `frontend/src/pages/ExperimentList.tsx`, change the `ExperimentRow` signature
and body. Replace the props type and the `TableRow` opening through the ID cell:

```tsx
function ExperimentRow({ exp, child, groupBadge }: { exp: ExperimentListItem; child?: boolean; groupBadge?: ReactNode }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Issue #98: a row that stands for more than one experiment must not offer an
  // inline status edit -- the PATCH would silently hit only the representative
  // vial (D3). Grouped rows carry `replicates`; collapsed flat rows carry a
  // vial_count above 1.
  const isGroupRow = !!exp.replicates?.length
  const isMultiVial = isGroupRow || (exp.vial_count ?? 1) > 1
  // AC1: the '-t<days>' token is an internal encoding and never reaches this page.
  const displayId = exp.group_display_id ?? exp.experiment_id
  const target = isGroupRow
    ? `/experiments/groups/${encodeURIComponent(displayId)}`
    : `/experiments/${encodeURIComponent(exp.experiment_id)}`

  const statusMutation = useMutation({
    mutationFn: ({ experimentId, status }: { experimentId: string; status: ExperimentStatus }) =>
      experimentsApi.patchStatus(experimentId, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['experiments'] }),
  })

  return (
    <TableRow className="cursor-pointer" onClick={() => navigate(target)}>
      <Td className={`font-mono-data text-ink-muted ${child ? 'pl-6' : ''}`}>{exp.experiment_number}</Td>
      <Td>
        <span className={`font-mono-data text-red-400 hover:text-red-300 ${child ? 'pl-6 inline-flex items-center gap-1' : ''}`}>
          {child && <span className="text-ink-muted">↳ {exp.replicate_label}</span>}
          {displayId}
        </span>
        {groupBadge}
      </Td>
```

The `id_timepoint_days` chip block that sat between the ID span and `{groupBadge}`
is deleted outright.

- [ ] **Step 5: Make the status cell conditional**

Replace the Status `<Td>` (formerly `:324-345`) with:

```tsx
      <Td onClick={(e) => e.stopPropagation()}>
        {isMultiVial ? (
          // Read-only: this row stands for several experiments (issue #98 D3).
          exp.status ? <StatusBadge status={exp.status} /> : <span className="text-ink-muted">—</span>
        ) : (
          <div className="relative inline-block">
            <select
              aria-label="Row status"
              className={[
                'appearance-none bg-surface-overlay border border-surface-border rounded',
                'pl-2 pr-6 py-0.5 text-xs font-medium focus:outline-none focus:ring-1 focus:ring-brand-red/50',
                STATUS_TEXT_CLASS[exp.status ?? ''] ?? 'text-ink-secondary',
              ].join(' ')}
              value={exp.status ?? ''}
              onMouseDown={(e) => e.stopPropagation()}
              onPointerDown={(e) => e.stopPropagation()}
              onChange={(e) =>
                statusMutation.mutate({ experimentId: exp.experiment_id, status: e.target.value as ExperimentStatus })
              }
            >
              {STATUS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <span className="pointer-events-none absolute inset-y-0 right-1.5 flex items-center text-ink-muted text-2xs">▾</span>
          </div>
        )}
      </Td>
```

Add `StatusBadge` to the `@/components/ui` import at the top of the file.

- [ ] **Step 6: Read the badge from `replicate_letters`**

At `frontend/src/pages/ExperimentList.tsx:232`, replace the badge text:

```tsx
                              {exp.replicate_letters?.length ?? exp.replicates!.length}
                              {' '}replicates:{' '}
                              {(exp.replicate_letters
                                ?? exp.replicates!.map((r) => r.replicate_label)
                              ).join(', ')}
```

The `?? exp.replicates` fallback keeps the component correct if a caller supplies
`replicates` without `replicate_letters`.

- [ ] **Step 7: Run the tests, typecheck, and lint**

```
cd frontend
npx vitest run src/pages/__tests__/ExperimentList.test.tsx
npx tsc --noEmit
npx eslint src --ext .ts,.tsx
```

Expected: all PASS with zero warnings. If `tsc` flags a fixture in another test
file missing the new fields, they were declared optional — so the error is
something else; read it rather than adding fields blindly.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/experiments.ts frontend/src/pages/ExperimentList.tsx frontend/src/pages/__tests__/ExperimentList.test.tsx
git commit -m "[#98] Hide -t token and link grouped rows to groups

- Renders group_display_id, letter badge, read-only multi-vial status
- Tests added: yes
- Docs updated: no"
```

---

## Task 6: Group page nests vials under letters

**Files:**
- Modify: `frontend/src/api/experiments.ts` (`ReplicateGroupDetail`)
- Modify: `frontend/src/pages/ReplicateGroup/index.tsx:59-153`
- Test: `frontend/src/pages/ReplicateGroup/__tests__/ReplicateGroupPage.test.tsx`

**Interfaces:**
- Consumes: `replicates`, `replicate_count`, and the widened `parent` from Task 4.

- [ ] **Step 1: Type the new fields**

In `frontend/src/api/experiments.ts`, add:

```typescript
/** Issue #98: one replicate letter and its timepoint vials. */
export interface ReplicateLetterGroup {
  replicate_label: string
  vials: ReplicateGroupMemberDetail[]
}
```

In `ReplicateGroupDetail`, change `parent` to `ReplicateGroupMemberDetail | null`
and add:

```typescript
  /** Issue #98: `members` grouped by letter. `member_count` stays per-vial. */
  replicates: ReplicateLetterGroup[]
  replicate_count: number
```

- [ ] **Step 2: Update the existing fixture, then write the failing tests**

`replicates` and `replicate_count` are **required** on `ReplicateGroupDetail`, so
the existing `ORPHAN_GROUP` const (`:34-57`) will fail `tsc` until it carries
them. Add both, mirroring its three members one-per-letter:

```typescript
  member_count: 3,
  replicate_count: 3,
  replicates: [
    { replicate_label: 'a', vials: [ORPHAN_MEMBERS[0]] },
    { replicate_label: 'b', vials: [ORPHAN_MEMBERS[1]] },
    { replicate_label: 'c', vials: [ORPHAN_MEMBERS[2]] },
  ],
```

To avoid repeating the three member literals, first hoist them out of
`ORPHAN_GROUP` into a const above it and reference it from `members`:

```typescript
const ORPHAN_MEMBERS: ReplicateGroupMemberDetail[] = [
  {
    id: 2, experiment_id: 'SERUM_001a', replicate_label: 'a', status: 'ONGOING', is_outlier: false,
    id_timepoint_days: null, researcher: 'MH', date: null, result_count: 2, conditions: {},
  },
  {
    id: 3, experiment_id: 'SERUM_001b', replicate_label: 'b', status: 'ONGOING', is_outlier: false,
    id_timepoint_days: null, researcher: 'MH', date: null, result_count: 2, conditions: {},
  },
  {
    id: 4, experiment_id: 'SERUM_001c', replicate_label: 'c', status: 'COMPLETED', is_outlier: false,
    id_timepoint_days: null, researcher: 'MH', date: null, result_count: 2, conditions: {},
  },
]
```

Add `ReplicateGroupMemberDetail` and `ReplicateLetterGroup` to the type import on
line 16, and `userEvent` to the imports (the file does not currently use it):

```typescript
import userEvent from '@testing-library/user-event'
```

Then append the new tests, using the file's own `renderAtBase` helper:

```typescript
describe('ReplicateGroupPage — issue #98 letter nesting', () => {
  function vial(
    id: number, experimentId: string, day: number | null,
  ): ReplicateGroupMemberDetail {
    return {
      id, experiment_id: experimentId, replicate_label: 'a',
      status: 'ONGOING', is_outlier: false,
      id_timepoint_days: day, researcher: null, date: null,
      result_count: 1, conditions: {},
    }
  }

  function groupWith(
    baseId: string, replicates: ReplicateLetterGroup[],
  ): ReplicateGroupDetail {
    const members = replicates.flatMap((r) => r.vials)
    return {
      base_experiment_id: baseId, parent: null, members,
      member_count: members.length, replicates,
      replicate_count: replicates.length,
      shared_conditions: {}, divergent_fields: [],
      additives_summary: null, additive_names: null, additives_diverge: false,
    }
  }

  it('header counts letters, not vials', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(
      groupWith('SERUM_001', [
        { replicate_label: 'a', vials: [vial(1, 'SERUM_001a-t1', 1), vial(2, 'SERUM_001a-t3', 3)] },
      ]),
    )
    renderAtBase('SERUM_001')
    // 2 vials, 1 letter -> the header must say "1 replicate".
    await waitFor(() => expect(screen.getByText('1 replicate')).toBeInTheDocument())
  })

  it('a multi-vial letter is one collapsed row that expands to its vials', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(
      groupWith('SERUM_001', [
        { replicate_label: 'a', vials: [vial(1, 'SERUM_001a-t1', 1), vial(2, 'SERUM_001a-t3', 3)] },
      ]),
    )
    renderAtBase('SERUM_001')

    await waitFor(() => expect(screen.getByText('2 vials')).toBeInTheDocument())
    expect(screen.queryByText('SERUM_001a-t1')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /expand replicate a/i }))
    expect(screen.getByRole('link', { name: 'SERUM_001a-t1' })).toBeInTheDocument()
    expect(screen.getByText('T+3')).toBeInTheDocument()
  })

  it('a single-vial letter renders as a plain row with no expander (D10)', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(
      groupWith('SERUM_002', [
        { replicate_label: 'a', vials: [vial(1, 'SERUM_002a', null)] },
      ]),
    )
    renderAtBase('SERUM_002')
    await waitFor(() =>
      expect(screen.getByRole('link', { name: 'SERUM_002a' })).toBeInTheDocument()
    )
    expect(screen.queryByRole('button', { name: /expand replicate/i })).not.toBeInTheDocument()
  })

  it('a parent with its own results renders real cells, not em dashes', async () => {
    const group = groupWith('SERUM_003', [
      { replicate_label: 'a', vials: [vial(2, 'SERUM_003a', null)] },
    ])
    vi.mocked(experimentsApi.getGroup).mockResolvedValue({
      ...group,
      parent: {
        id: 1, experiment_id: 'SERUM_003', replicate_label: null, status: 'ONGOING',
        is_outlier: false, id_timepoint_days: 5, researcher: 'MH', date: null,
        result_count: 4, conditions: {},
      },
    })
    renderAtBase('SERUM_003')
    await waitFor(() => expect(screen.getByText('0 (parent)')).toBeInTheDocument())
    // Previously hard-coded '—' because `parent` was the narrow member type.
    expect(screen.getByText('T+5')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run the tests to verify they fail**

```
cd frontend
npx vitest run src/pages/ReplicateGroup/__tests__/ReplicateGroupPage.test.tsx
```

Expected: FAIL — `1 replicate` not found (header reads `2 replicates` from
`member_count`), no `2 vials` text, no expander button.

- [ ] **Step 4: Add a letter row and a vial row**

In `frontend/src/pages/ReplicateGroup/index.tsx`, add above `MemberRow`:

```tsx
interface LetterRowsProps {
  letter: ReplicateLetterGroup
  divergentFields: string[]
  expanded: boolean
  onToggle: () => void
}

/** One replicate letter. A letter with a single vial renders exactly as it did
 *  before issue #98 — a plain member row with no expander. A letter sacrificed
 *  across several timepoints renders a collapsed summary row that expands into
 *  one row per vial, so `T+N` and result counts stay per vial. */
function LetterRows({ letter, divergentFields, expanded, onToggle }: LetterRowsProps) {
  if (letter.vials.length === 1) {
    return (
      <MemberRow
        member={letter.vials[0]}
        isParent={false}
        divergentFields={divergentFields}
      />
    )
  }
  return (
    <>
      <TableRow>
        <Td className="font-mono-data">{letter.replicate_label}</Td>
        <Td>
          <button
            aria-label={`Expand replicate ${letter.replicate_label}`}
            onClick={onToggle}
            className="inline-flex items-center gap-1 text-ink-secondary hover:text-ink-primary"
          >
            <span className={`transition-transform ${expanded ? 'rotate-90' : ''}`}>▸</span>
            {letter.vials.length} vials
          </button>
        </Td>
        <Td className="font-mono-data text-ink-muted">—</Td>
        <Td className="text-ink-muted">—</Td>
        <Td className="text-ink-muted">—</Td>
        <Td className="font-mono-data">
          {letter.vials.reduce((sum, v) => sum + v.result_count, 0)}
        </Td>
        {divergentFields.map((field) => (
          <Td key={field} className="font-mono-data text-ink-muted">—</Td>
        ))}
      </TableRow>
      {expanded && letter.vials.map((v) => (
        <MemberRow key={v.id} member={v} isParent={false} divergentFields={divergentFields} child />
      ))}
    </>
  )
}
```

`LetterRows` depends on `MemberRow` accepting a `child` flag and on `member` being
a `ReplicateGroupMemberDetail` unconditionally — `parent` is now that type too
(Task 4), so the union and the `isMemberDetail` type guard are dead. Replace
`MemberRowProps`, `MemberRow`, **and** `isMemberDetail` (`:53-93`) with:

```tsx
interface MemberRowProps {
  member: ReplicateGroupMemberDetail
  isParent: boolean
  divergentFields: string[]
  /** Rendered as a nested vial beneath its letter row (issue #98). */
  child?: boolean
}

/** One members-table row. Keyed by `id` at the call site — never by
 *  `replicate_label`, since a `-t` timepoint vial shares its letter with its
 *  parent vial. */
function MemberRow({ member, isParent, divergentFields, child }: MemberRowProps) {
  return (
    <TableRow>
      <Td className={`font-mono-data ${child ? 'pl-6' : ''}`}>
        {isParent ? '0 (parent)' : (member.replicate_label ?? '—')}
      </Td>
      <Td>
        <Link
          to={`/experiments/${member.experiment_id}`}
          className="font-mono-data text-red-400 hover:text-red-300"
        >
          {member.experiment_id}
        </Link>
      </Td>
      <Td className="font-mono-data">
        {member.id_timepoint_days != null ? `T+${member.id_timepoint_days}` : '—'}
      </Td>
      <Td>{member.status ? <StatusBadge status={member.status} /> : '—'}</Td>
      <Td>{member.is_outlier ? <Badge variant="warning">Outlier</Badge> : '—'}</Td>
      <Td className="font-mono-data">{member.result_count}</Td>
      {divergentFields.map((field) => (
        <Td key={field} className="font-mono-data">
          {formatValue(member.conditions[field])}
        </Td>
      ))}
    </TableRow>
  )
}
```

Drop `ReplicateGroupMember` from the type import at the top of the file — nothing
references it once the union is gone.

- [ ] **Step 5: Render letters instead of a flat member list**

In `ReplicateGroupContent`, replace the `rows` constant and the `<TableBody>`
contents. Add the expansion state at the top of the component:

```tsx
  const [expandedLetters, setExpandedLetters] = useState<Set<string>>(new Set())
```

and the body:

```tsx
        <TableBody>
          {group.parent && (
            <MemberRow
              key={group.parent.id}
              member={group.parent}
              isParent
              divergentFields={group.divergent_fields}
            />
          )}
          {group.replicates.map((letter) => (
            <LetterRows
              key={letter.replicate_label}
              letter={letter}
              divergentFields={group.divergent_fields}
              expanded={expandedLetters.has(letter.replicate_label)}
              onToggle={() =>
                setExpandedLetters((prev) => {
                  const next = new Set(prev)
                  if (next.has(letter.replicate_label)) next.delete(letter.replicate_label)
                  else next.add(letter.replicate_label)
                  return next
                })
              }
            />
          ))}
        </TableBody>
```

Change the header count (`:118-120`) to read `replicate_count`:

```tsx
          <span className="text-xs text-ink-muted">
            {group.replicate_count} {group.replicate_count === 1 ? 'replicate' : 'replicates'}
          </span>
```

Add `useState` to the `react` import and `ReplicateLetterGroup` to the type
import. The `rows` constant that flattened parent + members (`:102-105`) is now
unused — delete it. Because the parent is rendered through the rewritten
`MemberRow` (Step 4), its Timepoint / Results / divergent cells now show real
values instead of the hard-coded em dashes at the old `:81,85,88`.

- [ ] **Step 6: Run the tests, typecheck, and lint**

```
cd frontend
npx vitest run src/pages/ReplicateGroup/__tests__/ReplicateGroupPage.test.tsx
npx tsc --noEmit
npx eslint src --ext .ts,.tsx
```

Expected: PASS with zero warnings. The pre-existing tests in this file that
assert shared-condition formatting and suppression must still pass untouched.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/experiments.ts frontend/src/pages/ReplicateGroup/index.tsx frontend/src/pages/ReplicateGroup/__tests__/ReplicateGroupPage.test.tsx
git commit -m "[#98] Nest timepoint vials under replicate letters

- Letter rows expand to vials; header counts letters; parent cells filled
- Tests added: yes
- Docs updated: no"
```

---

## Task 7: Chart draws one series per replicate, not per vial

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx:60-97`, `:126-137`, `:159-167`
- Test: `frontend/src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx`

**Interfaces:**
- Consumes: `group.replicates` from Task 4.

- [ ] **Step 1: Update the existing fixture, then write the failing tests**

The `getGroup` mock in this file's `beforeEach` (`:48-67`) needs three fixes to
typecheck against Task 4's schema:

1. `parent` is now a `ReplicateGroupMemberDetail`, so its literal (`:50`) must
   gain `id_timepoint_days`, `researcher`, `date`, `result_count`, `conditions`.
2. `replicates` and `replicate_count` are required.

Replace that `mockResolvedValue` argument with:

```typescript
  vi.mocked(experimentsApi.getGroup).mockResolvedValue(
    groupOf('SERUM_001', [
      { replicate_label: 'a', vials: [detailVial(2, 'SERUM_001a', null, false)] },
      { replicate_label: 'b', vials: [detailVial(3, 'SERUM_001b', null, true)] },
    ], {
      id: 1, experiment_id: 'SERUM_001', replicate_label: null, status: 'ONGOING',
      is_outlier: false, id_timepoint_days: null, researcher: null, date: null,
      result_count: 1, conditions: {},
    }),
  )
```

and add these two builders above `beforeEach`:

```typescript
function detailVial(
  id: number, experimentId: string, day: number | null, isOutlier: boolean,
): ReplicateGroupMemberDetail {
  return {
    id, experiment_id: experimentId,
    replicate_label: experimentId.match(/_\d+([a-z])/)?.[1] ?? null,
    status: 'ONGOING', is_outlier: isOutlier,
    id_timepoint_days: day, researcher: null, date: null,
    result_count: 1, conditions: {},
  }
}

function groupOf(
  baseId: string,
  replicates: ReplicateLetterGroup[],
  parent: ReplicateGroupMemberDetail | null = null,
): ReplicateGroupDetail {
  const members = replicates.flatMap((r) => r.vials)
  return {
    base_experiment_id: baseId, parent, members, member_count: members.length,
    replicates, replicate_count: replicates.length,
    shared_conditions: {}, divergent_fields: [],
    additives_summary: null, additive_names: null, additives_diverge: false,
  }
}
```

Extend the type import on line 17 to
`import type { ReplicateGroupDetail, ReplicateGroupMemberDetail, ReplicateLetterGroup, RollupTimepoint } from '@/api/experiments'`.

Then append the new tests:

```typescript
describe('GroupedResultsView — issue #98 per-letter series', () => {
  it('draws one series per letter for a 2x2 set, not one per vial', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(
      groupOf('SERUM_001', [
        { replicate_label: 'a', vials: [
          detailVial(1, 'SERUM_001a-t1', 1, false),
          detailVial(2, 'SERUM_001a-t3', 3, false),
        ] },
        { replicate_label: 'b', vials: [
          detailVial(3, 'SERUM_001b-t1', 1, false),
          detailVial(4, 'SERUM_001b-t3', 3, false),
        ] },
      ]),
    )
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })

    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    // AC7: the legend carries two replicate series for four vials.
    expect(screen.getAllByText(/^replicate [ab]$/)).toHaveLength(2)
  })

  it('keeps an outlier vial reachable while excluding it from the series', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(
      groupOf('SERUM_002', [
        { replicate_label: 'a', vials: [
          detailVial(1, 'SERUM_002a-t1', 1, true),
          detailVial(2, 'SERUM_002a-t3', 3, false),
        ] },
      ]),
    )
    render(<GroupedResultsView baseExperimentId="SERUM_002" />, { wrapper })

    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    // One letter -> one series, even though one of its two vials is flagged.
    expect(screen.getAllByText(/^replicate a$/)).toHaveLength(1)
    // D11: the flagged vial contributes no points but stays linked.
    const link = screen.getByRole('link', { name: /SERUM_002a-t1/ })
    expect(link).toBeInTheDocument()
    expect(link.className).toContain('line-through')
  })
})
```

Note the assertions read the **legend**, not the SVG paths: Recharts renders
`<Line>` names into the legend, which is queryable in jsdom, whereas the plotted
paths are not reliably measurable there.

- [ ] **Step 2: Run the tests to verify they fail**

```
cd frontend
npx vitest run src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx
```

Expected: FAIL — series are named from `m.replicate_label` per vial, so four
`replicate a` / `replicate b` labels appear.

- [ ] **Step 3: Build series per letter**

Replace `seriesEntities` and `memberResults` (`:60-76`) with:

```tsx
  // Issue #98: one series per REPLICATE LETTER, not per vial. A letter
  // sacrificed across timepoints is several rows whose single result each form
  // one time course. Outlier vials contribute no points, matching
  // v_results_scalar_rollup's exclusion so the overlay and the mean agree (D11).
  const seriesLetters = useMemo(() => {
    const letters = [
      ...(group?.parent ? [{ key: 'parent', label: 'replicate 0', vials: [group.parent] }] : []),
      ...(group?.replicates ?? []).map((r) => ({
        key: r.replicate_label,
        label: `replicate ${r.replicate_label}`,
        vials: r.vials,
      })),
    ]
    return letters.slice(0, chartColors.series.length)
  }, [group])

  // One fetch per vial (results are stored per experiment row), flattened into
  // its letter's series below.
  const allVials = useMemo(
    () => seriesLetters.flatMap((l) => l.vials.map((v) => ({ letterKey: l.key, vial: v }))),
    [seriesLetters],
  )

  const vialResults = useQueries({
    queries: allVials.map(({ vial }) => ({
      queryKey: ['experiment-results', vial.experiment_id],
      queryFn: () => experimentsApi.getResults(vial.experiment_id),
      enabled: showIndividual,
    })),
  })
```

Replace the `seriesEntities.forEach` block inside `chartData` (`:88-95`) with:

```tsx
        seriesLetters.forEach((letter) => {
          let value: number | null = null
          allVials.forEach(({ letterKey, vial }, i) => {
            if (letterKey !== letter.key || vial.is_outlier) return
            const match = (vialResults[i]?.data ?? []).find(
              (res) => res.time_post_reaction_bucket_days === r.time_post_reaction_bucket_days
            )
            if (match) {
              const v = metric.individual(match)
              if (v != null) value = v
            }
          })
          row[letter.key] = value
        })
```

and change the `chartData` dependency array to
`[rollup, metric, seriesLetters, allVials, vialResults]`.

- [ ] **Step 4: Update the legend lines and the drill-in links**

Replace the `<Line>` map (`:159-167`) with:

```tsx
            {showIndividual &&
              seriesLetters.map((letter, i) => (
                <Line
                  key={letter.key} dataKey={letter.key} name={letter.label}
                  stroke={chartColors.series[i]} strokeWidth={1.5}
                  dot={{ r: 4, fill: chartColors.series[i] }} connectNulls
                />
              ))}
```

Replace the drill-in link row (`:126-137`) with a per-vial list, so every vial
stays reachable even when it contributes no points:

```tsx
        <div className="ml-auto flex flex-wrap items-center gap-2 text-xs text-ink-secondary pb-2">
          {allVials.map(({ vial }) => (
            <Link
              key={vial.id}
              to={`/experiments/${vial.experiment_id}`}
              className={`font-mono-data ${vial.is_outlier ? 'text-ink-muted line-through hover:text-ink-secondary' : 'text-red-400 hover:text-red-300'}`}
            >
              {vial.experiment_id}
              {vial.is_outlier ? ' (outlier)' : ''}
            </Link>
          ))}
        </div>
```

- [ ] **Step 5: Run the tests, typecheck, and lint**

```
cd frontend
npx vitest run
npx tsc --noEmit
npx eslint src --ext .ts,.tsx
```

Expected: the whole frontend suite PASSES with zero warnings.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx frontend/src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx
git commit -m "[#98] Build chart series per letter, drop outlier vials

- 2x5 study uses 2 series instead of 10; vial links preserved
- Tests added: yes
- Docs updated: no"
```

---

## Task 8: Documentation and the deferred follow-up

**Files:**
- Modify: `.claude/rules/MODELS.md` (the `id_timepoint_days` bullet and the `v_results_scalar_rollup` section)
- Modify: `docs/api/API_REFERENCE.md`

- [ ] **Step 1: Document the letter-vs-vial grain in MODELS.md**

Append to the `id_timepoint_days` bullet under `Experiment`:

```markdown
  - **Letter vs vial (issue #98):** a replicate *letter* is the scientific unit; a
    `-t<days>` *vial* is one destructively-sampled instance of it. The two are
    surfaced at different grains, and the collapse key is the timepoint-stripped
    `experiment_id` — never `(base_experiment_id, replicate_label)`, because
    `SERUM_001a-2` (a sequential re-run) shares both base and letter with
    `SERUM_001a` and must stay a separate row.
    - `GET /api/experiments` flat mode: one row per stem. `group_display_id`
      carries the label; `experiment_id` still names the representative row
      (the earliest non-outlier vial), which also supplies the Sample, Reactor,
      Date, Description and Additives columns.
    - `GET /api/experiments` grouped mode: one row per group, labeled by the
      stem, with `replicate_letters` for the badge and `vial_count` for the
      total row count.
    - `GET /api/experiments/groups/{base_id}`: `members`/`member_count` stay
      **per vial**; `replicates`/`replicate_count` are **per letter**.
    - The `-t` token is never rendered on `/experiments`, and a row standing for
      more than one vial shows status read-only, since an inline PATCH would
      reach only the representative.
```

- [ ] **Step 2: Note the rollup grain agreement**

Append to the `v_results_scalar_rollup` section:

```markdown
- **Letter vs vial (issue #98):** this view's `n_replicates` counts experiment
  ROWS in the bucket, so a 2-letter × 2-timepoint set yields
  `n_replicates = 2` per day bucket (one vial per letter contributes to each
  bucket) — which happens to match the letter count. The group page's
  individual-replicate overlay draws one series per letter and excludes
  `is_outlier` vials, so the overlay and this view's mean agree on membership.
  **Known gap:** a *letterless* `-t` vial (`SERUM_001-t7`) is counted here but
  is absent from the group page's members table, which requires
  `replicate_label IS NOT NULL`. Tracked separately.
```

- [ ] **Step 3: Document the API fields**

In `docs/api/API_REFERENCE.md`, add to the `GET /api/experiments` response field
list (match the surrounding table or bullet style — do not introduce a new one):

```markdown
- `group_display_id` (string, nullable) — what the UI should render as this row's
  ID. Grouped mode: the group stem (`SERUM_001`). Flat mode: the
  timepoint-stripped stem (`SERUM_001a`). `experiment_id` continues to name the
  real representative row, which is the earliest non-outlier vial and also
  supplies `sample_id`, `reactor_number`, `date`, `condition_note` and
  `additives_summary`.
- `vial_count` (integer, default 1) — how many experiment rows this row stands
  for. Flat mode counts matched rows sharing the stem; grouped mode counts every
  row in the bucket, parent included. A row with `vial_count > 1` must not offer
  an inline status edit — the PATCH would reach only the representative.
- `replicate_letters` (array of string, nullable) — grouped mode only: the
  group's DISTINCT replicate letters, for the "N replicates: a, b" badge. Null
  in flat mode and for rows that are not groups.
- `replicates` (array, nullable) — grouped mode only: one entry per replicate
  letter-row, collapsed on the timepoint stem, **including the representative's
  own letter**. Because the collapse key is the stem rather than the letter, a
  letter that also has a sequential re-run (`SERUM_001a` plus `SERUM_001a-2`)
  contributes two entries while `replicate_letters` counts one.
```

and to the `GET /api/experiments/groups/{base_id}` response:

```markdown
- `members` / `member_count` — **per vial**, unchanged. `member_count` always
  equals `len(members)`.
- `replicates` (array of `{replicate_label, vials[]}`) — the same members grouped
  by replicate letter. A letter holds several vials when the set is sacrificed
  per timepoint.
- `replicate_count` (integer) — number of LETTERS. This is what the group page
  header reports; a 2-letter × 2-timepoint set gives `replicate_count = 2` and
  `member_count = 4`.
- `parent` — now a full `ReplicateGroupMemberDetail` (was the narrower
  `ReplicateGroupMember`), so a parent with its own results reports
  `id_timepoint_days`, `result_count`, and `conditions`.
- `divergent_fields` — vials with no `conditions` row are excluded from the
  comparison rather than counting as all-null, so conditions shared across the
  vials that do have rows stay in `shared_conditions`.
```

- [ ] **Step 4: Verify the docs sync hook fired**

```
git status --short docs/project_context/
```

Expected: a modified `docs/project_context/API_REFERENCE.md`. `.claude/rules/`
files are not synced there. Never edit `docs/project_context/` by hand.

- [ ] **Step 5: File the deferred follow-up issue**

```bash
gh issue create --title "Letterless -t vials are counted in the rollup but absent from the group page" --body "Split out of #98.

\`_fetch_members\` (\`backend/services/replicate_groups.py:80-91\`) requires \`replicate_label IS NOT NULL\`, so a letterless timepoint vial such as \`SERUM_001-t7\` never appears in the group page's members table. But \`v_results_scalar_rollup\` groups on \`COALESCE(base_experiment_id, experiment_id)\`, which resolves to \`SERUM_001\`, so the vial IS counted in \`n_replicates\`. The rollup table and the members table therefore disagree about who is in the group.

Issue #98 fixed the list-page half of this (the bucket key now strips the \`-t\` token, so a letterless vial joins its parent's row instead of rendering as a second row with the same label). The group-page half needs a decision first: is a letterless \`-t\` vial a group parent, an unlettered replicate, or something else?

Out of scope for #98 — see \`docs/superpowers/specs/2026-07-29-issue-98-t-vial-replicate-collapsing-design.md\` §6."
```

- [ ] **Step 6: Commit**

```bash
git add .claude/rules/MODELS.md docs/api/API_REFERENCE.md docs/project_context/
git commit -m "[#98] Document letter-vs-vial grain and new fields

- MODELS.md id_timepoint_days + rollup sections; API reference
- Tests added: no
- Docs updated: yes"
```

---

## Final verification

- [ ] `.venv/Scripts/python -m pytest tests/api tests/views tests/services tests/models -q` — PASS. (A bare `pytest -q` has 3 pre-existing `tests/test_pg_backup_restore.py` failures from another file's `drop_all()` teardown; confirm against `develop` before treating any as a regression.)
- [ ] `cd frontend && npx vitest run` — PASS.
- [ ] `cd frontend && npx tsc --noEmit && npx eslint src --ext .ts,.tsx` — clean.
- [ ] Walk the 8 acceptance criteria in the spec §7 against the running app on port 5173, using a real 2×2 set with H2 GC data.
- [ ] Then use `superpowers:finishing-a-development-branch`.
