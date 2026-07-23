# Issue #70 P2 — Replicate Grouped UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make replicates usable in the UI: lettered replicate sets (`SERUM_001a/b/c`) collapse into expandable groups in the experiments list, a grouped results mode plots mean ± std per timepoint from `v_results_scalar_rollup` with individual-series overlay, and a "create N replicates" action spawns correctly-linked siblings copying the parent's conditions **and chemical additives**.

**Architecture:** Backend-first. The P1 `before_flush` listener already wires all lineage (`base_experiment_id`, `parent_experiment_fk`, `replicate_label`) on flush, so creation code only sets `experiment_id` and flushes. Grouping is server-side (a `group_replicates` query param re-paginates over "top-level rows": non-members plus parents of matched members) so grouping and pagination compose. The rollup endpoint is the **first API consumer of a reporting view** (`v_results_scalar_rollup`, via `text()`), and the grouped results chart is the **first chart in the app** (Recharts, user-approved new dependency).

**Tech Stack:** FastAPI + SQLAlchemy 2.x + Pydantic v2 (backend), React 18 + TypeScript + TanStack Query v5 + Tailwind + **Recharts (new)** (frontend), pytest against the `experiments_test` PostgreSQL DB, vitest + RTL.

## Global Constraints

- **Task-mode:** issue #70. Every commit message: `[#70] <imperative, ≤50 chars>` + `- Tests added: yes/no` + `- Docs updated: yes/no` lines.
- **Branch:** all tasks on `feat/issue-70-replicate-p2-grouped-ui` (already created from `develop`). PR at the end with `gh pr create --base develop`.
- **No schema change in P2.** `database/models/` is locked and untouched (the outlier flag is P4). No Alembic migration in this plan. `backend/services/bulk_uploads/` parsers untouched.
- **Locked decisions (issue #70, do not revisit):** replicate marker = single lowercase `[a-z]` after the numeric index; bare base = replicate 0 = group parent (also spelled `S-0`/`S-1`); grouping key `COALESCE(base_experiment_id, experiment_id)`; creation conflicts return a clear, non-fatal message.
- **User decisions for P2 (confirmed 2026-07-23):** (1) list grouping collapses **lettered replicate sets only** — sequential re-runs (`HPHT_001-2`) and treatment variants stay flat; (2) grouped results = **Recharts chart** (approved new dependency) plus an accessible rollup table; (3) create-replicates ships **both** as a detail-page modal and a New-Experiment-wizard count option, backed by one batch endpoint that copies conditions **and** chemical additives.
- **Frontend dependency rule (deployment-critical):** `frontend/package.json` and `frontend/package-lock.json` must change together via `npm install` and be committed **in the same commit** (lab PC runs `npm ci`).
- **Chart tokens:** series colors live in `frontend/src/assets/brand.ts`, never hardcoded in components. The palette below was validated with the dataviz six-check script on the app surface `#05172B` (dark mode): mean `#FD4437` (brand red), members `#0284c7`, `#b45309`, `#8b5cf6`, `#059669` — all checks PASS (lightness band L 0.48–0.67, chroma ≥ 0.1, worst adjacent CVD ΔE 10.8, normal ΔE 28.4, contrast ≥ 3:1). Never cycle hues; ≥ 2 series always get a legend; single y-axis only; text wears ink tokens.
- **Calculation engine:** every write path calls `registry.recalculate(instance, session)` after the write (pattern: `backend/api/routers/conditions.py:67`, `chemicals.py:142`).
- **Tests:** backend `.venv/Scripts/python -m pytest tests/ -q` (Postgres `experiments_test` DB must be up; 3 pre-existing `tests/test_pg_backup_restore.py` failures are known and unrelated). Frontend `npx vitest run src` from `frontend/` (e2e specs excluded per #65), `npx eslint <changed files>` clean.
- **Server rule:** never start/stop uvicorn or Vite; assume running.
- **Docs sync:** write docs under `docs/` normally; a PostToolUse hook copies them to `docs/project_context/`. Never write `docs/project_context/` directly. `docs/working/plan.md` is NOT updated until `/complete-task`.
- **Route ordering:** static collection routes must be declared before dynamic `/{experiment_id}` routes in `backend/api/routers/experiments.py` (existing convention: `/next-id`, `/next-ids` before line 569's `GET /{experiment_id}`). Suffixed dynamic routes (`/{experiment_id}/rollup`) cannot collide and may go with the other `/{experiment_id}/...` routes.
- **P1 facts to rely on (do not re-derive):** `Experiment.replicate_label` exists (nullable String, indexed). The `before_flush` listener (`database/event_listeners.py:676`) calls `update_experiment_lineage` for every new `Experiment`, setting `base_experiment_id`, `parent_experiment_fk` (via the `.parent` relationship, pending-safe), and `replicate_label`, and back-links orphans when a parent appears. `v_results_scalar_rollup` exists in `database/event_listeners.py` `_VIEWS` (lines ~519–550) keyed on `(COALESCE(base_experiment_id, experiment_id), time_post_reaction_bucket_days)` with quoted mixed-case column aliases (`"mean_gross_ammonium_mM"` etc.).

---

### Task 1: Backend — expose replicate lineage fields in response schemas

**Files:**
- Modify: `backend/api/schemas/experiments.py` (ExperimentListItem ~line 35, ExperimentResponse ~line 63)
- Test: `tests/api/test_experiments.py`

**Interfaces:**
- Consumes: `Experiment.base_experiment_id`, `.parent_experiment_fk`, `.replicate_label` (ORM columns, P1).
- Produces: `ExperimentListItem.base_experiment_id: Optional[str]`, `.parent_experiment_fk: Optional[int]`, `.replicate_label: Optional[str]`; `ExperimentResponse.replicate_label: Optional[str]`. Task 2 nests `ExperimentListItem` recursively; Tasks 5–8 read these from the frontend.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_experiments.py` (reuse the module's existing `_make_experiment` helper and `client`/`db_session` fixtures):

```python
class TestReplicateFieldsExposed:
    def test_list_items_include_replicate_lineage_fields(self, client, db_session):
        parent = _make_experiment(db_session, experiment_id="RFLD_001", number=9700)
        db_session.add(Experiment(experiment_id="RFLD_001a", experiment_number=9701,
                                  status=ExperimentStatus.ONGOING))
        db_session.commit()
        resp = client.get("/api/experiments?search=RFLD_001")
        assert resp.status_code == 200
        by_id = {i["experiment_id"]: i for i in resp.json()["items"]}
        member = by_id["RFLD_001a"]
        assert member["replicate_label"] == "a"
        assert member["base_experiment_id"] == "RFLD_001"
        assert member["parent_experiment_fk"] == parent.id
        assert by_id["RFLD_001"]["replicate_label"] is None

    def test_detail_includes_replicate_label(self, client, db_session):
        _make_experiment(db_session, experiment_id="RFLD_002", number=9702)
        db_session.add(Experiment(experiment_id="RFLD_002a", experiment_number=9703,
                                  status=ExperimentStatus.ONGOING))
        db_session.commit()
        resp = client.get("/api/experiments/RFLD_002a")
        assert resp.status_code == 200
        assert resp.json()["replicate_label"] == "a"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/api/test_experiments.py -k ReplicateFieldsExposed -v`
Expected: FAIL — `KeyError: 'replicate_label'` (fields absent from responses).

- [ ] **Step 3: Add the schema fields**

In `backend/api/schemas/experiments.py`, add to `ExperimentListItem` (after `created_at`):

```python
    base_experiment_id: Optional[str] = None
    parent_experiment_fk: Optional[int] = None
    replicate_label: Optional[str] = None
```

Add to `ExperimentResponse` (after `parent_experiment_fk`):

```python
    replicate_label: Optional[str] = None
```

No router change needed: `list_experiments` already copies every `Experiment.__table__.columns` entry into `item_data` (`backend/api/routers/experiments.py:111`), and the detail/create endpoints use `model_validate(exp)` with `from_attributes=True`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/api/test_experiments.py -v`
Expected: new tests PASS; all pre-existing tests in the file still PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/schemas/experiments.py tests/api/test_experiments.py
git commit -m "[#70] Expose replicate lineage in API schemas

- ExperimentListItem/ExperimentResponse gain base/parent/replicate fields
- Tests added: yes
- Docs updated: no"
```

---

### Task 2: Backend — `group_replicates` list mode

**Files:**
- Modify: `backend/api/routers/experiments.py:46-140` (`list_experiments`)
- Modify: `backend/api/schemas/experiments.py` (`ExperimentListItem` gains self-referencing `replicates`)
- Test: `tests/api/test_experiments.py`

**Interfaces:**
- Consumes: Task 1 schema fields.
- Produces: `GET /api/experiments?group_replicates=true`. Semantics: a **top-level row** is any experiment that is not a linked replicate member (`replicate_label IS NULL OR parent_experiment_fk IS NULL`); a filter matching only a member pulls in that member's parent as the top-level row. `total`, `skip`, `limit` count/page **top-level rows**. Each top-level item carries `replicates: list[ExperimentListItem] | None` — all lettered children of that row ordered by `replicate_label`, populated whether or not the children individually matched the filters. Default (`false`) is byte-identical to today's flat behavior. Orphan members (parent not created yet) appear as their own top-level rows with `replicates=None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_experiments.py`:

```python
class TestGroupedListMode:
    def _make_set(self, db):
        parent = _make_experiment(db, experiment_id="GRP_001", number=9710)
        for i, letter in enumerate("abc"):
            db.add(Experiment(experiment_id=f"GRP_001{letter}", experiment_number=9711 + i,
                              status=ExperimentStatus.ONGOING))
        db.commit()
        return parent

    def test_grouped_collapses_lettered_set(self, client, db_session):
        self._make_set(db_session)
        resp = client.get("/api/experiments?group_replicates=true&search=GRP_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        (item,) = data["items"]
        assert item["experiment_id"] == "GRP_001"
        assert [r["replicate_label"] for r in item["replicates"]] == ["a", "b", "c"]

    def test_flat_mode_unchanged(self, client, db_session):
        self._make_set(db_session)
        resp = client.get("/api/experiments?search=GRP_001")
        assert resp.json()["total"] == 4
        assert all(i.get("replicates") is None for i in resp.json()["items"])

    def test_filter_matching_only_member_pulls_group(self, client, db_session):
        self._make_set(db_session)
        resp = client.get("/api/experiments?group_replicates=true&search=GRP_001b")
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["experiment_id"] == "GRP_001"
        assert len(data["items"][0]["replicates"]) == 3

    def test_orphan_member_stays_top_level(self, client, db_session):
        db_session.add(Experiment(experiment_id="GRP_ORPH_001a", experiment_number=9720,
                                  status=ExperimentStatus.ONGOING))
        db_session.commit()
        resp = client.get("/api/experiments?group_replicates=true&search=GRP_ORPH_001a")
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["experiment_id"] == "GRP_ORPH_001a"
        assert data["items"][0]["replicates"] is None

    def test_sequential_derivation_stays_flat_in_grouped_mode(self, client, db_session):
        _make_experiment(db_session, experiment_id="GRPSEQ_001", number=9730)
        db_session.add(Experiment(experiment_id="GRPSEQ_001-2", experiment_number=9731,
                                  status=ExperimentStatus.ONGOING))
        db_session.commit()
        resp = client.get("/api/experiments?group_replicates=true&search=GRPSEQ_001")
        assert resp.json()["total"] == 2  # base and -2 are separate top-level rows

    def test_grouped_pagination_counts_groups(self, client, db_session):
        self._make_set(db_session)                                    # 1 group
        _make_experiment(db_session, experiment_id="GRP_SOLO_001", number=9740)  # 1 flat
        resp = client.get("/api/experiments?group_replicates=true&search=GRP_&limit=1")
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/api/test_experiments.py -k GroupedListMode -v`
Expected: FAIL — grouped assertions see flat behavior (`total == 4`), `replicates` key absent.

- [ ] **Step 3: Add the self-referencing schema field**

In `backend/api/schemas/experiments.py`, add to `ExperimentListItem` (after `condition_note`):

```python
    # Grouped-list mode only (group_replicates=true): lettered children of this
    # group parent, ordered by replicate_label. None in flat mode / for non-parents.
    replicates: Optional[list["ExperimentListItem"]] = None
```

and after the class definition add:

```python
ExperimentListItem.model_rebuild()
```

- [ ] **Step 4: Implement grouped pagination in `list_experiments`**

In `backend/api/routers/experiments.py`: add `case` and `and_` to the `sqlalchemy` import on line 4 (`from sqlalchemy import select, func, text, update, case, and_`). Add the query param after `description` (line 58):

```python
    group_replicates: bool = Query(False),
```

Extract the per-row build (lines 109–138's loop body) into a module-level helper so children reuse it:

```python
def _build_list_item(db: Session, exp: Experiment) -> dict:
    """Build the ExperimentListItem payload dict for one experiment row."""
    item_data = {c.key: getattr(exp, c.key) for c in Experiment.__table__.columns}
    cond = db.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
    ).scalar_one_or_none()
    item_data["experiment_type"] = cond.experiment_type if cond else None
    item_data["reactor_number"] = cond.reactor_number if cond else None
    additive_row = db.execute(
        text("""
            SELECT string_agg(c.name || ' ' || CAST(a.amount AS TEXT) || ' ' || a.unit, '; ')
            FROM chemical_additives a
            JOIN experimental_conditions ec ON ec.id = a.experiment_id
            JOIN compounds c ON c.id = a.compound_id
            WHERE ec.experiment_fk = :exp_fk
        """),
        {"exp_fk": exp.id},
    ).fetchone()
    item_data["additives_summary"] = additive_row[0] if additive_row else None
    first_note = db.execute(
        select(ExperimentNotes)
        .where(ExperimentNotes.experiment_fk == exp.id)
        .order_by(ExperimentNotes.id.asc())
        .limit(1)
    ).scalar_one_or_none()
    item_data["condition_note"] = first_note.note_text if first_note else None
    return item_data
```

Replace lines 106–140 (total/rows/loop/return) with:

```python
    if group_replicates:
        # Grouped mode: paginate over "top-level rows". A matched replicate member
        # (lettered + linked to a parent) is represented by its parent; everything
        # else (parents, non-replicates, sequential/treatment derivations, orphan
        # members) represents itself. Lettered children of each page row are
        # attached in full regardless of whether they matched the filters.
        matched_sq = stmt.subquery()
        top_id_expr = case(
            (
                and_(
                    matched_sq.c.replicate_label.isnot(None),
                    matched_sq.c.parent_experiment_fk.isnot(None),
                ),
                matched_sq.c.parent_experiment_fk,
            ),
            else_=matched_sq.c.id,
        )
        top_ids_sq = select(top_id_expr.label("top_id")).distinct().subquery()
        total = db.execute(select(func.count()).select_from(top_ids_sq)).scalar_one()
        page_stmt = (
            select(Experiment)
            .where(Experiment.id.in_(select(top_ids_sq.c.top_id)))
            .order_by(Experiment.experiment_number.desc())
        )
        rows = db.execute(page_stmt.offset(skip).limit(limit)).scalars().all()
    else:
        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = db.execute(stmt.offset(skip).limit(limit)).scalars().all()

    items = []
    for exp in rows:
        item_data = _build_list_item(db, exp)
        if group_replicates:
            children = db.execute(
                select(Experiment)
                .where(
                    Experiment.parent_experiment_fk == exp.id,
                    Experiment.replicate_label.isnot(None),
                )
                .order_by(Experiment.replicate_label.asc())
            ).scalars().all()
            if children:
                item_data["replicates"] = [
                    ExperimentListItem.model_validate(_build_list_item(db, ch))
                    for ch in children
                ]
        items.append(ExperimentListItem.model_validate(item_data))

    return ExperimentListResponse(items=items, total=total, skip=skip, limit=limit)
```

(Per-row N+1 lookups match the endpoint's existing pattern — 8 LAN users, page ≤ 500; do not "optimize" beyond this here.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/api/test_experiments.py -v`
Expected: all `GroupedListMode` tests PASS **and** every pre-existing list test (including the #64 pagination-regression trio) still PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/experiments.py backend/api/schemas/experiments.py tests/api/test_experiments.py
git commit -m "[#70] Add group_replicates list mode

- Server-side group pagination; lettered children nested per parent
- Tests added: yes
- Docs updated: no"
```

---

### Task 3: Backend — rollup + replicate-group endpoints

**Files:**
- Modify: `backend/api/routers/experiments.py` (two new GET routes in the `/{experiment_id}/...` block, e.g. after `get_experiment_results` ~line 245)
- Modify: `backend/api/schemas/results.py` (add `RollupTimepointResponse`)
- Modify: `backend/api/schemas/experiments.py` (add `ReplicateGroupMember`, `ReplicateGroupResponse`)
- Create: `tests/api/test_experiment_rollup.py`

**Interfaces:**
- Consumes: `v_results_scalar_rollup` (P1 view, `database/event_listeners.py` `_VIEWS`); `Experiment.parent` relationship / `parent_experiment_fk`.
- Produces:
  - `GET /api/experiments/{experiment_id}/rollup` → `list[RollupTimepointResponse]` ordered by bucket; resolves the group key as `exp.base_experiment_id or exp.experiment_id`, so any member or the parent returns the same series.
  - `GET /api/experiments/{experiment_id}/replicate-group` → `ReplicateGroupResponse{base_experiment_id: str, parent: ReplicateGroupMember | None, members: list[ReplicateGroupMember]}` where `ReplicateGroupMember = {id: int, experiment_id: str, replicate_label: str | None, status: ExperimentStatus | None}`. `members` is empty when the experiment has no lettered replicates (frontend uses `members.length > 0` to show grouped mode).

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_experiment_rollup.py`:

```python
"""API tests for /rollup and /replicate-group (issue #70 P2).

Views are DDL created inside the test transaction (rolled back per test),
mirroring tests/views/test_v_results_scalar_rollup.py's view_db fixture.
"""
import pytest
from sqlalchemy import text

from database.models import Experiment, ExperimentalResults, ScalarResults
from database.models.enums import ExperimentStatus


@pytest.fixture()
def reporting_views(db_session):
    from database.event_listeners import _VIEWS
    for view_name, _ in _VIEWS:
        db_session.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
    for _, view_sql in _VIEWS:
        db_session.execute(text(view_sql))
    db_session.flush()
    yield


def _make_experiment(db, experiment_id, number):
    exp = Experiment(experiment_id=experiment_id, experiment_number=number,
                     status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _add_primary_scalar(db, exp, bucket, gross_nh4):
    result = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=bucket, time_post_reaction_bucket_days=bucket,
        is_primary_timepoint_result=True, description=f"t={bucket}",
    )
    db.add(result)
    db.flush()
    db.add(ScalarResults(result_id=result.id,
                         gross_ammonium_concentration_mM=gross_nh4))
    db.flush()
    return result


class TestRollupEndpoint:
    def test_rollup_stats_for_replicate_set(self, client, db_session, reporting_views):
        _make_experiment(db_session, "RUP_001", 9750)
        for i, letter in enumerate("abc"):
            member = _make_experiment(db_session, f"RUP_001{letter}", 9751 + i)
            _add_primary_scalar(db_session, member, 7.0, float(i + 1))  # 1, 2, 3
        db_session.commit()
        resp = client.get("/api/experiments/RUP_001a/rollup")
        assert resp.status_code == 200
        (row,) = resp.json()
        assert row["base_experiment_id"] == "RUP_001"
        assert row["n_replicates"] == 3
        assert row["mean_gross_ammonium_mM"] == pytest.approx(2.0)
        assert row["sd_gross_ammonium_mM"] == pytest.approx(1.0)

    def test_rollup_same_series_from_parent_and_member(self, client, db_session, reporting_views):
        _make_experiment(db_session, "RUP_002", 9760)
        member = _make_experiment(db_session, "RUP_002a", 9761)
        _add_primary_scalar(db_session, member, 3.0, 5.0)
        db_session.commit()
        from_parent = client.get("/api/experiments/RUP_002/rollup").json()
        from_member = client.get("/api/experiments/RUP_002a/rollup").json()
        assert from_parent == from_member

    def test_rollup_404_unknown_experiment(self, client, db_session, reporting_views):
        assert client.get("/api/experiments/NOPE_999/rollup").status_code == 404


class TestReplicateGroupEndpoint:
    def test_group_from_parent_and_member(self, client, db_session):
        parent = _make_experiment(db_session, "RGRP_001", 9770)
        for i, letter in enumerate("ab"):
            _make_experiment(db_session, f"RGRP_001{letter}", 9771 + i)
        db_session.commit()
        for query_id in ("RGRP_001", "RGRP_001b"):
            data = client.get(f"/api/experiments/{query_id}/replicate-group").json()
            assert data["base_experiment_id"] == "RGRP_001"
            assert data["parent"]["id"] == parent.id
            assert [m["replicate_label"] for m in data["members"]] == ["a", "b"]

    def test_group_empty_for_non_replicate(self, client, db_session):
        _make_experiment(db_session, "RGRP_SOLO_001", 9780)
        db_session.commit()
        data = client.get("/api/experiments/RGRP_SOLO_001/replicate-group").json()
        assert data["members"] == []
        assert data["parent"]["experiment_id"] == "RGRP_SOLO_001"

    def test_group_orphan_member_lists_siblings(self, client, db_session):
        _make_experiment(db_session, "RGRP_ORPH_001a", 9790)
        _make_experiment(db_session, "RGRP_ORPH_001b", 9791)
        db_session.commit()
        data = client.get("/api/experiments/RGRP_ORPH_001a/replicate-group").json()
        assert data["parent"] is None
        assert [m["replicate_label"] for m in data["members"]] == ["a", "b"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/api/test_experiment_rollup.py -v`
Expected: FAIL — 404s from both new paths (routes don't exist; FastAPI matches `/{experiment_id}` = `"RUP_001a"` then `"rollup"` finds no sub-route → 404 or 405).

- [ ] **Step 3: Add the response schemas**

In `backend/api/schemas/results.py` append:

```python
class RollupTimepointResponse(BaseModel):
    """One row of v_results_scalar_rollup: cross-replicate stats per timepoint bucket.

    Field names match the view's (quoted, mixed-case) column aliases exactly.
    """
    base_experiment_id: str
    time_post_reaction_bucket_days: Optional[float] = None
    n_replicates: int
    mean_gross_ammonium_mM: Optional[float] = None
    median_gross_ammonium_mM: Optional[float] = None
    sd_gross_ammonium_mM: Optional[float] = None
    mean_net_ammonium_mM: Optional[float] = None
    sd_net_ammonium_mM: Optional[float] = None
    mean_h2_micromoles: Optional[float] = None
    sd_h2_micromoles: Optional[float] = None
    mean_h2_grams_per_ton: Optional[float] = None
    sd_h2_grams_per_ton: Optional[float] = None
    mean_fe_yield_h2_pct: Optional[float] = None
    sd_fe_yield_h2_pct: Optional[float] = None
    mean_fe_yield_nh3_pct: Optional[float] = None
    sd_fe_yield_nh3_pct: Optional[float] = None
    mean_grams_per_ton_yield: Optional[float] = None
    sd_grams_per_ton_yield: Optional[float] = None
    mean_final_ph: Optional[float] = None
```

In `backend/api/schemas/experiments.py` append:

```python
class ReplicateGroupMember(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    experiment_id: str
    replicate_label: Optional[str] = None
    status: Optional[ExperimentStatus] = None


class ReplicateGroupResponse(BaseModel):
    base_experiment_id: str
    parent: Optional[ReplicateGroupMember] = None
    members: list[ReplicateGroupMember] = []
```

- [ ] **Step 4: Add the two routes**

In `backend/api/routers/experiments.py`, after `get_experiment_results` (~line 245), add (import `RollupTimepointResponse` alongside the other results-schema imports, and `ReplicateGroupMember`, `ReplicateGroupResponse` with the experiments-schema imports):

```python
@router.get("/{experiment_id}/rollup", response_model=list[RollupTimepointResponse])
def get_experiment_rollup(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[RollupTimepointResponse]:
    """Cross-replicate mean/median/std per timepoint from v_results_scalar_rollup."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    base = exp.base_experiment_id or exp.experiment_id
    rows = db.execute(
        text("""
            SELECT * FROM v_results_scalar_rollup
            WHERE base_experiment_id = :base
            ORDER BY time_post_reaction_bucket_days
        """),
        {"base": base},
    ).mappings().all()
    return [RollupTimepointResponse(**dict(r)) for r in rows]


@router.get("/{experiment_id}/replicate-group", response_model=ReplicateGroupResponse)
def get_replicate_group(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ReplicateGroupResponse:
    """The lettered replicate set this experiment belongs to (empty members if none)."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    base = exp.base_experiment_id or exp.experiment_id
    parent = exp if exp.replicate_label is None else exp.parent
    if parent is not None:
        members = db.execute(
            select(Experiment)
            .where(
                Experiment.parent_experiment_fk == parent.id,
                Experiment.replicate_label.isnot(None),
            )
            .order_by(Experiment.replicate_label.asc())
        ).scalars().all()
    else:
        # Orphan member: parent row doesn't exist yet; list siblings by base stem.
        members = db.execute(
            select(Experiment)
            .where(
                Experiment.base_experiment_id == base,
                Experiment.replicate_label.isnot(None),
            )
            .order_by(Experiment.replicate_label.asc())
        ).scalars().all()
    return ReplicateGroupResponse(
        base_experiment_id=base,
        parent=ReplicateGroupMember.model_validate(parent) if parent else None,
        members=[ReplicateGroupMember.model_validate(m) for m in members],
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/api/test_experiment_rollup.py tests/api/test_experiments.py -v`
Expected: PASS (both new test classes and no regression).

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/experiments.py backend/api/schemas/results.py backend/api/schemas/experiments.py tests/api/test_experiment_rollup.py
git commit -m "[#70] Add rollup and replicate-group endpoints

- First API consumer of v_results_scalar_rollup (text() pattern)
- Tests added: yes
- Docs updated: no"
```

---

### Task 4: Backend — batch replicate creation (service + endpoint)

**Files:**
- Modify: `database/lineage_utils.py` (extract conditions-copy helper; add `create_replicate_experiments`)
- Modify: `backend/api/routers/experiments.py` (add `POST /api/experiments/replicates` right after `create_experiment`, ~line 641)
- Modify: `backend/api/schemas/experiments.py` (request/response schemas)
- Test: `tests/test_replicate_creation_service.py` (create), `tests/api/test_experiments.py` (router tests)

**Interfaces:**
- Consumes: `find_replicate_group_parent(db, base_id)`, `parse_experiment_id` (P1); `auto_create_treatment_experiment`'s reserved/blacklist copy rules; `registry.recalculate`.
- Produces:
  - `create_replicate_experiments(db: Session, base_experiment_id: str, count: int) -> tuple[list[Experiment], list[str]]` in `database/lineage_utils.py` — returns `(created, skipped_messages)`; raises `LookupError` when no parent/template exists. Flushes but does **not** commit (router owns the transaction).
  - `POST /api/experiments/replicates` body `{"base_experiment_id": str, "count": int (1-25, default 3)}` → 201 `{"created": [ExperimentResponse...], "skipped": [str...]}`; 404 when no parent exists.
- Copy semantics: each new replicate copies the parent's `sample_id`, `researcher`, `date`; `status=ONGOING`; conditions copied with the same reserved/blacklist sets as `auto_create_treatment_experiment`; **chemical additives copied too** (unlike the treatment helper); per-vial actuals stay editable afterwards. Letters continue after existing members (parent with `a`,`b` existing + count 2 → creates `c`,`d`).

- [ ] **Step 1: Write the failing service tests**

Create `tests/test_replicate_creation_service.py` (uses the root-conftest Postgres `test_db` fixture):

```python
"""Service tests for create_replicate_experiments (issue #70 P2)."""
import pytest

from database.lineage_utils import create_replicate_experiments
from database.models import (
    ChemicalAdditive, Compound, Experiment, ExperimentalConditions,
)
from database.models.enums import ExperimentStatus


def _make_parent(db, experiment_id="CRS_001", number=9800, with_additive=True):
    parent = Experiment(experiment_id=experiment_id, experiment_number=number,
                        status=ExperimentStatus.ONGOING, researcher="MH",
                        sample_id=None)
    db.add(parent)
    db.flush()
    cond = ExperimentalConditions(
        experiment_id=parent.experiment_id, experiment_fk=parent.id,
        experiment_type="Serum", rock_mass_g=10.0, water_volume_mL=50.0,
        temperature_c=90.0,
    )
    db.add(cond)
    db.flush()
    if with_additive:
        compound = Compound(name=f"NiCl2-{number}", formula="NiCl2")
        db.add(compound)
        db.flush()
        db.add(ChemicalAdditive(experiment_id=cond.id, compound_id=compound.id,
                                amount=5.0, unit="mg"))
        db.flush()
    return parent


class TestCreateReplicateExperiments:
    def test_creates_linked_replicates_with_conditions_and_additives(self, test_db):
        parent = _make_parent(test_db)
        created, skipped = create_replicate_experiments(test_db, "CRS_001", count=3)
        test_db.flush()
        assert skipped == []
        assert [e.experiment_id for e in created] == ["CRS_001a", "CRS_001b", "CRS_001c"]
        for e in created:
            assert e.parent_experiment_fk == parent.id
            assert e.base_experiment_id == "CRS_001"
            assert e.replicate_label in ("a", "b", "c")
            assert e.status == ExperimentStatus.ONGOING
            assert e.researcher == "MH"
            assert e.conditions is not None
            assert e.conditions.rock_mass_g == 10.0
            assert e.conditions.temperature_c == 90.0
            additives = e.conditions.chemical_additives
            assert len(additives) == 1
            assert additives[0].amount == 5.0
            assert additives[0].unit == "mg"
            # Copied additive must be a new row, not the parent's
            assert additives[0].id != parent.conditions.chemical_additives[0].id

    def test_letters_continue_after_existing_members(self, test_db):
        _make_parent(test_db, "CRS_002", 9810)
        test_db.add(Experiment(experiment_id="CRS_002a", experiment_number=9811,
                               status=ExperimentStatus.ONGOING))
        test_db.flush()
        created, skipped = create_replicate_experiments(test_db, "CRS_002", count=2)
        assert [e.experiment_id for e in created] == ["CRS_002b", "CRS_002c"]
        assert skipped == []

    def test_missing_parent_raises_lookup_error(self, test_db):
        with pytest.raises(LookupError):
            create_replicate_experiments(test_db, "CRS_MISSING_001", count=3)

    def test_lettered_input_resolves_to_stem(self, test_db):
        _make_parent(test_db, "CRS_003", 9820)
        created, _ = create_replicate_experiments(test_db, "CRS_003a", count=1)
        # Passing a lettered ID targets the same group: next free letter is "a"
        assert [e.experiment_id for e in created] == ["CRS_003a"]

    def test_parent_without_conditions_still_creates_experiments(self, test_db):
        exp = Experiment(experiment_id="CRS_004", experiment_number=9830,
                         status=ExperimentStatus.ONGOING)
        test_db.add(exp)
        test_db.flush()
        created, skipped = create_replicate_experiments(test_db, "CRS_004", count=2)
        assert len(created) == 2
        assert all(e.conditions is None for e in created)
        assert skipped == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_replicate_creation_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'create_replicate_experiments'`.

- [ ] **Step 3: Extract the conditions-copy helper and add the service**

In `database/lineage_utils.py`:

**(a)** Add module-level constants above `auto_create_treatment_experiment` and a copy helper (these sets are moved verbatim from inside `auto_create_treatment_experiment` — do not change their contents):

```python
# Fields never copied when cloning conditions from a parent experiment.
_CONDITIONS_COPY_RESERVED = {"id", "experiment_id", "experiment_fk", "created_at", "updated_at"}
_CONDITIONS_COPY_BLACKLIST = {
    "catalyst", "catalyst_mass",
    "buffer_system", "buffer_concentration",
    "surfactant_type", "surfactant_concentration",
    "catalyst_percentage", "catalyst_ppm",
    "water_to_rock_ratio",  # Calculated field
    "ammonium_chloride_concentration",
}

# Derived/identity additive columns owned by the calc engine or the DB, never copied.
_ADDITIVE_COPY_RESERVED = {
    "id", "experiment_id", "created_at", "updated_at",
    "mass_in_grams", "moles_added", "final_concentration", "concentration_units",
    "elemental_metal_mass", "catalyst_percentage", "catalyst_ppm",
}


def _copy_conditions_from_parent(db: Session, parent, new_experiment, include_additives: bool):
    """Clone parent's ExperimentalConditions (and optionally chemical additives)
    onto new_experiment. Flushes; does not commit. Returns the new conditions
    row or None when the parent has no conditions."""
    from .models import ExperimentalConditions, ChemicalAdditive

    if not parent.conditions:
        return None

    updatable_attrs = {
        col.name for col in ExperimentalConditions.__table__.columns
        if col.name not in _CONDITIONS_COPY_RESERVED
        and col.name not in _CONDITIONS_COPY_BLACKLIST
    }
    new_conditions = ExperimentalConditions(
        experiment_id=new_experiment.experiment_id,
        experiment_fk=new_experiment.id,
    )
    for attr in updatable_attrs:
        parent_value = getattr(parent.conditions, attr, None)
        if parent_value is not None:
            setattr(new_conditions, attr, parent_value)
    db.add(new_conditions)
    db.flush()

    if include_additives:
        additive_attrs = {
            col.name for col in ChemicalAdditive.__table__.columns
            if col.name not in _ADDITIVE_COPY_RESERVED
        }
        for parent_additive in parent.conditions.chemical_additives:
            new_additive = ChemicalAdditive(experiment_id=new_conditions.id)
            for attr in additive_attrs:
                value = getattr(parent_additive, attr, None)
                if value is not None:
                    setattr(new_additive, attr, value)
            db.add(new_additive)
        db.flush()

    return new_conditions
```

**(b)** Inside `auto_create_treatment_experiment`, replace the whole "Copy conditions from parent" block (the `if parent.conditions:` block defining `reserved`/`blacklist`/`updatable_attrs` through its `db.flush()`) with:

```python
    _copy_conditions_from_parent(db, parent, new_experiment, include_additives=False)
```

This is a pure refactor — the treatment helper's behavior (no additive copy) is unchanged; `tests/test_lineage_migration.py` and the existing treatment tests pin it.

**(c)** Add the new service function after `auto_create_treatment_experiment`:

```python
def create_replicate_experiments(
    db: Session, base_experiment_id: str, count: int
) -> tuple[list['Experiment'], list[str]]:
    """Create `count` lettered replicate experiments under a base experiment.

    The base (replicate 0) experiment acts as the template: sample, researcher,
    date, conditions, and chemical additives are copied to each new replicate;
    per-vial actuals stay editable afterwards. Letters continue after any
    existing members (a, b already present -> c, d, ...). Lineage fields are
    wired by the before_flush listener. Flushes; the caller owns the commit.

    Returns (created_experiments, skipped_messages). Conflicting IDs are
    skipped with a message, not fatal (issue #70 locked decision 3).
    Raises LookupError when no parent/template experiment exists.
    """
    from .models import Experiment

    stem, _seq, _treat, _label = parse_experiment_id(base_experiment_id)
    stem = stem or base_experiment_id

    parent = find_replicate_group_parent(db, stem)
    if parent is None:
        raise LookupError(
            f"No parent experiment found for base '{stem}' — create the base experiment first"
        )

    existing_labels = {
        label for (label,) in db.query(Experiment.replicate_label)
        .filter(Experiment.base_experiment_id == stem,
                Experiment.replicate_label.isnot(None))
        .all()
    }

    candidates = [c for c in "abcdefghijklmnopqrstuvwxyz" if c not in existing_labels]
    created: list[Experiment] = []
    skipped: list[str] = []
    if len(candidates) < count:
        skipped.append(
            f"Only {len(candidates)} replicate letters remain for '{stem}' "
            f"(requested {count}); creating {len(candidates)}."
        )

    last = db.query(Experiment).order_by(Experiment.experiment_number.desc()).first()
    next_number = 1 if last is None else int(last.experiment_number or 0) + 1

    for letter in candidates[:count]:
        new_id = f"{stem}{letter}"
        if _find_experiment_by_exact_spelling(db, new_id) is not None:
            skipped.append(f"'{new_id}' already exists — skipped, not overwritten.")
            continue
        new_experiment = Experiment(
            experiment_number=next_number,
            experiment_id=new_id,
            sample_id=parent.sample_id,
            researcher=parent.researcher,
            status=parent.status,
            date=parent.date,
        )
        next_number += 1
        db.add(new_experiment)
        db.flush()  # assigns PK + triggers lineage wiring via before_flush

        new_conditions = _copy_conditions_from_parent(
            db, parent, new_experiment, include_additives=True
        )
        if new_conditions is not None:
            from backend.services.calculations.registry import recalculate
            recalculate(new_conditions, db)
            for additive in new_conditions.chemical_additives:
                recalculate(additive, db)
            db.flush()

        created.append(new_experiment)

    return created, skipped
```

Note on `status`: copy `parent.status` (a QUEUED template spawns QUEUED vials; an ONGOING one spawns ONGOING).

- [ ] **Step 4: Run service tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_replicate_creation_service.py tests/test_replicate_lineage.py tests/test_lineage_migration.py -v`
Expected: new tests PASS; all existing lineage/treatment tests still PASS (refactor is behavior-neutral).

- [ ] **Step 5: Write the failing router tests**

Append to `tests/api/test_experiments.py`:

```python
class TestCreateReplicatesEndpoint:
    def test_create_replicates_batch(self, client, db_session):
        _make_experiment(db_session, experiment_id="CRE_001", number=9850)
        db_session.commit()
        resp = client.post("/api/experiments/replicates",
                           json={"base_experiment_id": "CRE_001", "count": 3})
        assert resp.status_code == 201
        data = resp.json()
        assert [e["experiment_id"] for e in data["created"]] == ["CRE_001a", "CRE_001b", "CRE_001c"]
        assert all(e["replicate_label"] in ("a", "b", "c") for e in data["created"])
        assert data["skipped"] == []

    def test_create_replicates_404_without_parent(self, client, db_session):
        resp = client.post("/api/experiments/replicates",
                           json={"base_experiment_id": "CRE_MISSING_001", "count": 3})
        assert resp.status_code == 404

    def test_create_replicates_count_bounds(self, client, db_session):
        _make_experiment(db_session, experiment_id="CRE_002", number=9860)
        db_session.commit()
        assert client.post("/api/experiments/replicates",
                           json={"base_experiment_id": "CRE_002", "count": 0}).status_code == 422
        assert client.post("/api/experiments/replicates",
                           json={"base_experiment_id": "CRE_002", "count": 26}).status_code == 422
```

- [ ] **Step 6: Run router tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/api/test_experiments.py -k CreateReplicatesEndpoint -v`
Expected: FAIL with 404/405 (route absent).

- [ ] **Step 7: Add schemas + endpoint**

In `backend/api/schemas/experiments.py` append (add `Field` to the pydantic import):

```python
class ReplicateCreateRequest(BaseModel):
    base_experiment_id: str
    count: int = Field(3, ge=1, le=25)


class ReplicateCreateResponse(BaseModel):
    created: list[ExperimentResponse]
    skipped: list[str] = []
```

In `backend/api/routers/experiments.py`, immediately after `create_experiment` (~line 641), add (import `ReplicateCreateRequest`, `ReplicateCreateResponse` with the other experiments-schema imports):

```python
@router.post("/replicates", response_model=ReplicateCreateResponse, status_code=201)
def create_replicates(
    payload: ReplicateCreateRequest,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ReplicateCreateResponse:
    """Batch-create lettered replicates copying the base experiment's setup."""
    from database.lineage_utils import create_replicate_experiments

    try:
        created, skipped = create_replicate_experiments(
            db, payload.base_experiment_id, payload.count
        )
        db.commit()
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Replicate ID conflict on creation")
    for exp in created:
        db.refresh(exp)
    log.info(
        "replicates_created",
        base_experiment_id=payload.base_experiment_id,
        created=[e.experiment_id for e in created],
        skipped=skipped,
        user=current_user.email,
    )
    return ReplicateCreateResponse(
        created=[ExperimentResponse.model_validate(e) for e in created],
        skipped=skipped,
    )
```

FastAPI note: no `POST /{experiment_id}` route exists, so `/replicates` cannot be shadowed; placing it with `create_experiment` matches file organization.

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/api/test_experiments.py tests/test_replicate_creation_service.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add database/lineage_utils.py backend/api/routers/experiments.py backend/api/schemas/experiments.py tests/test_replicate_creation_service.py tests/api/test_experiments.py
git commit -m "[#70] Add batch replicate creation

- Service copies conditions + additives from base; POST /replicates
- Tests added: yes
- Docs updated: no"
```

---

### Task 5: Frontend — Recharts dependency + API layer

**Files:**
- Modify: `frontend/package.json` + `frontend/package-lock.json` (via `npm install recharts` — never hand-edit)
- Modify: `frontend/src/api/experiments.ts`
- Test: `frontend/src/api/__tests__/experiments.replicates.test.ts` (create)

**Interfaces:**
- Consumes: Task 2's `group_replicates` param; Task 3's `/rollup`, `/replicate-group`; Task 4's `POST /replicates`.
- Produces (consumed by Tasks 6–8):
  - `ExperimentListItem` gains `base_experiment_id: string | null`, `parent_experiment_fk: number | null`, `replicate_label: string | null`, `replicates?: ExperimentListItem[] | null`.
  - `ExperimentDetail` gains `replicate_label: string | null`. `ResultWithFlags` gains `background_ammonium_concentration_mM: number | null` (backend already returns it — closes a pre-existing interface gap).
  - `ExperimentListParams` gains `group_replicates?: boolean`.
  - New types + functions on `experimentsApi`: `RollupTimepoint`, `ReplicateGroupMember`, `ReplicateGroup`, `CreateReplicatesResponse`; `getRollup(experimentId): Promise<RollupTimepoint[]>`, `getReplicateGroup(experimentId): Promise<ReplicateGroup>`, `createReplicates(payload: { base_experiment_id: string; count: number }): Promise<CreateReplicatesResponse>`.

- [ ] **Step 1: Install Recharts**

```bash
cd frontend
npm install recharts
git status --short   # MUST show BOTH package.json and package-lock.json modified
```

- [ ] **Step 2: Commit the dependency alone (both files, one commit)**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "[#70] Add recharts for grouped results chart

- User-approved new frontend dependency (2026-07-23)
- Tests added: no
- Docs updated: no"
```

- [ ] **Step 3: Write the failing API-layer test**

Create `frontend/src/api/__tests__/experiments.replicates.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

import { experimentsApi } from '../experiments'
import { apiClient } from '../client'

beforeEach(() => vi.clearAllMocks())

describe('experimentsApi replicate functions', () => {
  it('getRollup hits /experiments/:id/rollup', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [] })
    await experimentsApi.getRollup('SERUM_001a')
    expect(apiClient.get).toHaveBeenCalledWith('/experiments/SERUM_001a/rollup')
  })

  it('getReplicateGroup hits /experiments/:id/replicate-group', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { base_experiment_id: 'SERUM_001', parent: null, members: [] } })
    await experimentsApi.getReplicateGroup('SERUM_001')
    expect(apiClient.get).toHaveBeenCalledWith('/experiments/SERUM_001/replicate-group')
  })

  it('createReplicates posts base + count', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { created: [], skipped: [] } })
    await experimentsApi.createReplicates({ base_experiment_id: 'SERUM_001', count: 3 })
    expect(apiClient.post).toHaveBeenCalledWith('/experiments/replicates', {
      base_experiment_id: 'SERUM_001',
      count: 3,
    })
  })
})
```

(Check how the existing `frontend/src/api/__tests__/experiments.deleteNote.test.ts` mocks the client module and mirror its exact import path for `apiClient` — if it mocks `'../client'` differently, follow that file.)

- [ ] **Step 4: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/__tests__/experiments.replicates.test.ts`
Expected: FAIL — `getRollup is not a function`.

- [ ] **Step 5: Extend `frontend/src/api/experiments.ts`**

Add to `ExperimentListItem`:

```ts
  base_experiment_id: string | null
  parent_experiment_fk: number | null
  replicate_label: string | null
  /** Grouped-list mode only: lettered children of this group parent. */
  replicates?: ExperimentListItem[] | null
```

Add to `ExperimentDetail` (after `parent_experiment_fk`): `replicate_label: string | null`.
Add to `ResultWithFlags` (after `gross_ammonium_concentration_mM`): `background_ammonium_concentration_mM: number | null`.
Add to `ExperimentListParams`: `group_replicates?: boolean`.

Add the new types:

```ts
export interface RollupTimepoint {
  base_experiment_id: string
  time_post_reaction_bucket_days: number | null
  n_replicates: number
  mean_gross_ammonium_mM: number | null
  median_gross_ammonium_mM: number | null
  sd_gross_ammonium_mM: number | null
  mean_net_ammonium_mM: number | null
  sd_net_ammonium_mM: number | null
  mean_h2_micromoles: number | null
  sd_h2_micromoles: number | null
  mean_h2_grams_per_ton: number | null
  sd_h2_grams_per_ton: number | null
  mean_fe_yield_h2_pct: number | null
  sd_fe_yield_h2_pct: number | null
  mean_fe_yield_nh3_pct: number | null
  sd_fe_yield_nh3_pct: number | null
  mean_grams_per_ton_yield: number | null
  sd_grams_per_ton_yield: number | null
  mean_final_ph: number | null
}

export interface ReplicateGroupMember {
  id: number
  experiment_id: string
  replicate_label: string | null
  status: ExperimentStatus | null
}

export interface ReplicateGroup {
  base_experiment_id: string
  parent: ReplicateGroupMember | null
  members: ReplicateGroupMember[]
}

// Mirrors backend ReplicateCreateResponse: created items are ExperimentResponse-shaped
// (no conditions/notes/modifications). [Amended during Task 5 review — the original
// ExperimentDetail[] typing did not match the backend response.]
export interface CreatedReplicate {
  id: number
  experiment_id: string
  experiment_number: number
  status: ExperimentStatus | null
  researcher: string | null
  date: string | null
  sample_id: string | null
  base_experiment_id: string | null
  parent_experiment_fk: number | null
  replicate_label: string | null
  created_at: string
  updated_at: string | null
}

export interface CreateReplicatesResponse {
  created: CreatedReplicate[]
  skipped: string[]
}
```

Add to the `experimentsApi` object:

```ts
  getRollup: (experimentId: string) =>
    apiClient.get<RollupTimepoint[]>(`/experiments/${experimentId}/rollup`).then((r) => r.data),
  getReplicateGroup: (experimentId: string) =>
    apiClient.get<ReplicateGroup>(`/experiments/${experimentId}/replicate-group`).then((r) => r.data),
  createReplicates: (payload: { base_experiment_id: string; count: number }) =>
    apiClient.post<CreateReplicatesResponse>('/experiments/replicates', payload).then((r) => r.data),
```

- [ ] **Step 6: Run tests + typecheck to verify they pass**

Run: `cd frontend && npx vitest run src/api && npx tsc --noEmit`
Expected: PASS, no type errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/experiments.ts frontend/src/api/__tests__/experiments.replicates.test.ts
git commit -m "[#70] Add replicate API layer to frontend

- Rollup, replicate-group, createReplicates + lineage fields on types
- Tests added: yes
- Docs updated: no"
```

---

### Task 6: Frontend — grouped experiments list UI

**Files:**
- Modify: `frontend/src/pages/ExperimentList.tsx`
- Test: `frontend/src/pages/__tests__/ExperimentList.test.tsx`

**Interfaces:**
- Consumes: `experimentsApi.list({ group_replicates })`, `ExperimentListItem.replicates` (Task 5).
- Produces: grouped list default ON with a "Group replicates" toggle; group rows expand/collapse to show lettered children; children navigate to their own detail pages.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/pages/__tests__/ExperimentList.test.tsx` (reuse the file's existing `wrapper`, `queryClient`, and mock plumbing; extend its item factory so every `ExperimentListItem` includes the new fields — `base_experiment_id: null, parent_experiment_fk: null, replicate_label: null` defaults):

```tsx
function makeGroupedItem(): ExperimentListItem {
  const base = {
    status: 'ONGOING' as const, researcher: null, date: null, sample_id: null,
    created_at: '2026-07-01T00:00:00Z', experiment_type: 'Serum', reactor_number: null,
    additives_summary: null, condition_note: null,
    base_experiment_id: null as string | null, parent_experiment_fk: null as number | null,
    replicate_label: null as string | null,
  }
  return {
    ...base, id: 1, experiment_id: 'SERUM_001', experiment_number: 100,
    replicates: ['a', 'b', 'c'].map((letter, i) => ({
      ...base, id: 10 + i, experiment_id: `SERUM_001${letter}`, experiment_number: 101 + i,
      base_experiment_id: 'SERUM_001', parent_experiment_fk: 1, replicate_label: letter,
    })),
  }
}

describe('ExperimentListPage — replicate grouping', () => {
  beforeEach(() => {
    vi.mocked(experimentsApi.list).mockResolvedValue({
      items: [makeGroupedItem()], total: 1, skip: 0, limit: 25,
    })
  })
  afterEach(() => vi.clearAllMocks())

  it('sends group_replicates=true by default and renders the group summary', async () => {
    render(<ExperimentListPage />, { wrapper })
    await waitFor(() => expect(screen.getByText('SERUM_001')).toBeInTheDocument())
    expect(vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]?.group_replicates).toBe(true)
    expect(screen.getByText('3 replicates: a, b, c')).toBeInTheDocument()
    expect(screen.queryByText('SERUM_001a')).not.toBeInTheDocument()
  })

  it('expands a group to show child rows', async () => {
    const user = userEvent.setup()
    render(<ExperimentListPage />, { wrapper })
    await waitFor(() => expect(screen.getByText('SERUM_001')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /expand replicates/i }))
    expect(screen.getByText('SERUM_001a')).toBeInTheDocument()
    expect(screen.getByText('SERUM_001c')).toBeInTheDocument()
  })

  it('turning the toggle off sends group_replicates undefined', async () => {
    const user = userEvent.setup()
    render(<ExperimentListPage />, { wrapper })
    await waitFor(() => expect(screen.getByText('SERUM_001')).toBeInTheDocument())
    await user.click(screen.getByRole('checkbox', { name: /group replicates/i }))
    await waitFor(() => {
      expect(vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]?.group_replicates).toBeUndefined()
    })
  })
})
```

Then fix any existing tests in this file that break only because the item factory lacks the three new required fields — add the defaults to the factory, nothing else.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/__tests__/ExperimentList.test.tsx`
Expected: new tests FAIL (no toggle, no group summary, param not sent).

- [ ] **Step 3: Implement grouping in `ExperimentList.tsx`**

Changes (see current file structure at the top of this plan's research; line refs are pre-change):

1. State (after `limit`, line 45): `const [groupReplicates, setGroupReplicates] = useState(true)` and `const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set())`.
2. Query key (line 47): append `groupReplicates`. Query fn params: add `group_replicates: groupReplicates || undefined,`.
3. Filters row (after the date-to input, before the Clear button): a labelled checkbox toggle:

```tsx
        <label className="flex items-center gap-1.5 text-xs text-ink-secondary pb-2 cursor-pointer select-none">
          <input
            type="checkbox"
            aria-label="Group replicates"
            checked={groupReplicates}
            onChange={(e) => { setGroupReplicates(e.target.checked); resetPage() }}
            className="accent-brand-red"
          />
          Group replicates
        </label>
```

4. Row rendering (lines 203–251): extract the existing `<TableRow>` body into a local component `ExperimentRow({ exp, child })` inside the file so parent and child rows share it (`child` adds `pl-6` indent + a `↳ a` letter badge on the ID cell instead of the plain ID). Then map:

```tsx
data.items.map((exp) => {
  const hasReplicates = !!exp.replicates?.length
  const expanded = expandedGroups.has(exp.id)
  return (
    <Fragment key={exp.id}>
      <ExperimentRow
        exp={exp}
        groupBadge={
          hasReplicates ? (
            <button
              aria-label="Expand replicates"
              onClick={(e) => {
                e.stopPropagation()
                setExpandedGroups((prev) => {
                  const next = new Set(prev)
                  if (next.has(exp.id)) next.delete(exp.id)
                  else next.add(exp.id)
                  return next
                })
              }}
              className="ml-2 inline-flex items-center gap-1 rounded bg-surface-raised px-1.5 py-0.5 text-2xs text-ink-secondary hover:text-ink-primary"
            >
              <span className={`transition-transform ${expanded ? 'rotate-90' : ''}`}>▸</span>
              {exp.replicates!.length} replicates: {exp.replicates!.map((r) => r.replicate_label).join(', ')}
            </button>
          ) : null
        }
      />
      {hasReplicates && expanded &&
        exp.replicates!.map((rep) => <ExperimentRow key={rep.id} exp={rep} child />)}
    </Fragment>
  )
})
```

`ExperimentRow` keeps the whole existing cell set (number, ID, description, sample, reactor, status `<select>` with the `statusMutation`, date, additives); the group badge renders inside the Experiment ID `<Td>` after the ID span. Import `Fragment` from `react`. Child rows keep `onClick={() => navigate(...)}` to their own page.

5. The status `<select>` stays functional on both parent and child rows (it already stops propagation).

- [ ] **Step 4: Run tests + lint to verify they pass**

Run: `cd frontend && npx vitest run src/pages/__tests__/ExperimentList.test.tsx && npx eslint src/pages/ExperimentList.tsx`
Expected: PASS, zero lint warnings.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ExperimentList.tsx frontend/src/pages/__tests__/ExperimentList.test.tsx
git commit -m "[#70] Group replicates in experiments list

- Expandable group rows, default-on toggle, child navigation
- Tests added: yes
- Docs updated: no"
```

---

### Task 7: Frontend — grouped results view (chart + rollup table)

**Files:**
- Modify: `frontend/src/assets/brand.ts` (chart tokens)
- Create: `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx`
- Modify: `frontend/src/pages/ExperimentDetail/ResultsTab.tsx` (mode toggle)
- Test: `frontend/src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx` (create)

**Interfaces:**
- Consumes: `experimentsApi.getRollup`, `.getReplicateGroup`, `.getResults` (Task 5); `Modal`/`Table`/`Select`/`Button` UI components; Recharts.
- Produces: `<GroupedResultsView experimentId={string} />`; `chartColors` export in `brand.ts`. ResultsTab shows an `Individual | Grouped (n)` toggle whenever the experiment's replicate group has ≥1 lettered member.

- [ ] **Step 1: Add chart tokens to `brand.ts`**

Append to `frontend/src/assets/brand.ts` (reference existing `colors` entries where they exist):

```ts
/**
 * Chart series tokens (issue #70). Validated with the dataviz six-check
 * palette validator on surface #05172B (dark): lightness band, chroma,
 * CVD separation (worst adjacent dE 10.8), normal-vision floor, contrast
 * all PASS for the order [mean, ...series]. Assign by entity in fixed
 * order (replicate 0 -> series[0], a -> series[1], ...); never cycle hues.
 */
export const chartColors = {
  mean: colors.redPrimary,           // #FD4437 — the aggregate/mean series
  series: ['#0284c7', '#b45309', '#8b5cf6', '#059669'],
  grid: colors.navyBorder,           // recessive gridlines
  axis: colors.inkMuted,             // axis lines + ticks
  label: colors.inkSecondary,        // axis/legend text
  tooltipBg: '#0a2540',              // tooltip surface (raised navy)
} as const
```

(If `colors` keys differ from `redPrimary`/`navyBorder`/`inkMuted`/`inkSecondary`, use the file's actual key names — the hex values are `#FD4437`, `#1a3a5c`, `#4d6e8a`, `#8BACC8`.)

- [ ] **Step 2: Write the failing tests**

Create `frontend/src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    getRollup: vi.fn(),
    getReplicateGroup: vi.fn(),
    getResults: vi.fn(),
  },
}))

import { GroupedResultsView } from '../GroupedResultsView'
import { experimentsApi } from '@/api/experiments'
import type { RollupTimepoint } from '@/api/experiments'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 0 } },
})
function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </MemoryRouter>
  )
}

const ROLLUP: RollupTimepoint[] = [
  {
    base_experiment_id: 'SERUM_001', time_post_reaction_bucket_days: 7, n_replicates: 3,
    mean_gross_ammonium_mM: 2.0, median_gross_ammonium_mM: 2.0, sd_gross_ammonium_mM: 1.0,
    mean_net_ammonium_mM: 1.5, sd_net_ammonium_mM: 0.5,
    mean_h2_micromoles: null, sd_h2_micromoles: null,
    mean_h2_grams_per_ton: null, sd_h2_grams_per_ton: null,
    mean_fe_yield_h2_pct: null, sd_fe_yield_h2_pct: null,
    mean_fe_yield_nh3_pct: null, sd_fe_yield_nh3_pct: null,
    mean_grams_per_ton_yield: 40.0, sd_grams_per_ton_yield: 4.0, mean_final_ph: 8.1,
  },
]

beforeEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
  vi.mocked(experimentsApi.getRollup).mockResolvedValue(ROLLUP)
  vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
    base_experiment_id: 'SERUM_001',
    parent: { id: 1, experiment_id: 'SERUM_001', replicate_label: null, status: 'ONGOING' },
    members: [
      { id: 2, experiment_id: 'SERUM_001a', replicate_label: 'a', status: 'ONGOING' },
      { id: 3, experiment_id: 'SERUM_001b', replicate_label: 'b', status: 'ONGOING' },
    ],
  })
  vi.mocked(experimentsApi.getResults).mockResolvedValue([])
})

describe('GroupedResultsView', () => {
  it('renders rollup stats table with mean ± sd and n', async () => {
    render(<GroupedResultsView experimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByText('2.00 ± 1.00')).toBeInTheDocument()
  })

  it('links to each replicate page for drill-in', async () => {
    render(<GroupedResultsView experimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'SERUM_001a' })).toHaveAttribute(
      'href', '/experiments/SERUM_001a'
    )
  })

  it('changes plotted metric via the selector', async () => {
    const user = userEvent.setup()
    render(<GroupedResultsView experimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    await user.selectOptions(screen.getByLabelText(/metric/i), 'ph')
    expect(screen.getByText('8.10')).toBeInTheDocument()
  })
})
```

If `frontend/src/test/setup.ts` doesn't already stub `ResizeObserver` (Recharts' `ResponsiveContainer` needs it in jsdom), add there:

```ts
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
if (!('ResizeObserver' in globalThis)) {
  // @ts-expect-error jsdom lacks ResizeObserver
  globalThis.ResizeObserver = ResizeObserverStub
}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx`
Expected: FAIL — module `../GroupedResultsView` not found.

- [ ] **Step 4: Implement `GroupedResultsView.tsx`**

Create `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx`:

```tsx
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueries } from '@tanstack/react-query'
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ErrorBar, ResponsiveContainer,
} from 'recharts'
import { experimentsApi } from '@/api/experiments'
import type { ResultWithFlags, RollupTimepoint } from '@/api/experiments'
import { chartColors } from '@/assets/brand'
import { Table, TableHead, TableBody, TableRow, Th, Td, Select, Spinner } from '@/components/ui'

interface MetricDef {
  key: string
  label: string
  mean: keyof RollupTimepoint
  sd: keyof RollupTimepoint | null
  individual: (r: ResultWithFlags) => number | null
}

const METRICS: MetricDef[] = [
  { key: 'gross_nh4', label: 'Gross NH₄ (mM)', mean: 'mean_gross_ammonium_mM', sd: 'sd_gross_ammonium_mM',
    individual: (r) => r.gross_ammonium_concentration_mM },
  { key: 'net_nh4', label: 'Net NH₄ (mM)', mean: 'mean_net_ammonium_mM', sd: 'sd_net_ammonium_mM',
    individual: (r) =>
      r.gross_ammonium_concentration_mM != null && r.background_ammonium_concentration_mM != null
        ? Math.max(0, r.gross_ammonium_concentration_mM - r.background_ammonium_concentration_mM)
        : null },
  { key: 'nh4_gpt', label: 'NH₄ (g/t)', mean: 'mean_grams_per_ton_yield', sd: 'sd_grams_per_ton_yield',
    individual: (r) => r.grams_per_ton_yield },
  { key: 'h2_umol', label: 'H₂ (µmol)', mean: 'mean_h2_micromoles', sd: 'sd_h2_micromoles',
    individual: (r) => r.h2_micromoles },
  { key: 'h2_gpt', label: 'H₂ (g/t)', mean: 'mean_h2_grams_per_ton', sd: 'sd_h2_grams_per_ton',
    individual: (r) => r.h2_grams_per_ton_yield },
  { key: 'fe_h2', label: 'Fe²⁺ → H₂ (%)', mean: 'mean_fe_yield_h2_pct', sd: 'sd_fe_yield_h2_pct',
    individual: (r) => r.ferrous_iron_yield_h2_pct },
  { key: 'fe_nh3', label: 'Fe²⁺ → NH₃ (%)', mean: 'mean_fe_yield_nh3_pct', sd: 'sd_fe_yield_nh3_pct',
    individual: (r) => r.ferrous_iron_yield_nh3_pct },
  { key: 'ph', label: 'pH', mean: 'mean_final_ph', sd: null, individual: (r) => r.final_ph },
]

const fmt = (v: number | null | undefined, digits = 2) =>
  v == null ? '—' : v.toFixed(digits)

interface GroupedResultsViewProps {
  experimentId: string
}

/** Base-level grouped results: mean ± std per timepoint from the rollup view,
 *  with individual replicate series overlay and drill-in links. */
export function GroupedResultsView({ experimentId }: GroupedResultsViewProps) {
  const [metricKey, setMetricKey] = useState('gross_nh4')
  const [showIndividual, setShowIndividual] = useState(true)
  const metric = METRICS.find((m) => m.key === metricKey)!

  const { data: group } = useQuery({
    queryKey: ['replicate-group', experimentId],
    queryFn: () => experimentsApi.getReplicateGroup(experimentId),
  })
  const { data: rollup, isLoading } = useQuery({
    queryKey: ['rollup', experimentId],
    queryFn: () => experimentsApi.getRollup(experimentId),
  })

  // Series entities in fixed order: parent (replicate 0) first, then a, b, c…
  // Only the first chartColors.series.length entities are overlaid (never cycle hues).
  const seriesEntities = useMemo(() => {
    const entities = [
      ...(group?.parent ? [group.parent] : []),
      ...(group?.members ?? []),
    ]
    return entities.slice(0, chartColors.series.length)
  }, [group])

  const memberResults = useQueries({
    queries: seriesEntities.map((m) => ({
      queryKey: ['experiment-results', m.experiment_id],
      queryFn: () => experimentsApi.getResults(m.experiment_id),
      enabled: showIndividual,
    })),
  })

  const chartData = useMemo(() => {
    if (!rollup) return []
    return rollup
      .filter((r) => r.time_post_reaction_bucket_days != null)
      .map((r) => {
        const row: Record<string, number | null> = {
          bucket: r.time_post_reaction_bucket_days,
          mean: r[metric.mean] as number | null,
          sd: metric.sd ? ((r[metric.sd] as number | null) ?? 0) : 0,
        }
        seriesEntities.forEach((m, i) => {
          const results = memberResults[i]?.data ?? []
          const match = results.find(
            (res) => res.time_post_reaction_bucket_days === r.time_post_reaction_bucket_days
          )
          row[m.experiment_id] = match ? metric.individual(match) : null
        })
        return row
      })
  }, [rollup, metric, seriesEntities, memberResults])

  if (isLoading) return <Spinner />
  if (!rollup?.length) {
    return <p className="text-sm text-ink-muted py-4">No primary results to aggregate yet.</p>
  }

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-48">
          <Select
            label="Metric"
            aria-label="Metric"
            value={metricKey}
            onChange={(e) => setMetricKey(e.target.value)}
            options={METRICS.map((m) => ({ value: m.key, label: m.label }))}
          />
        </div>
        <label className="flex items-center gap-1.5 text-xs text-ink-secondary pb-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={showIndividual}
            onChange={(e) => setShowIndividual(e.target.checked)}
            className="accent-brand-red"
          />
          Show individual replicates
        </label>
        <div className="ml-auto flex items-center gap-2 text-xs text-ink-secondary pb-2">
          {seriesEntities.map((m) => (
            <Link
              key={m.id}
              to={`/experiments/${m.experiment_id}`}
              className="font-mono-data text-red-400 hover:text-red-300"
            >
              {m.experiment_id}
            </Link>
          ))}
        </div>
      </div>

      {/* Chart — single y-axis; mean emphasized, members thin; legend always on */}
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid stroke={chartColors.grid} strokeDasharray="3 3" />
            <XAxis
              dataKey="bucket" type="number" domain={['dataMin', 'dataMax']}
              stroke={chartColors.axis} tick={{ fill: chartColors.label, fontSize: 11 }}
              label={{ value: 'Time post-reaction (days)', position: 'insideBottom', offset: -4, fill: chartColors.label, fontSize: 11 }}
            />
            <YAxis
              stroke={chartColors.axis} tick={{ fill: chartColors.label, fontSize: 11 }}
              width={56}
            />
            <Tooltip
              contentStyle={{ backgroundColor: chartColors.tooltipBg, border: `1px solid ${chartColors.grid}`, fontSize: 12 }}
              labelFormatter={(v) => `Day ${v}`}
            />
            <Legend wrapperStyle={{ fontSize: 11, color: chartColors.label }} />
            {showIndividual &&
              seriesEntities.map((m, i) => (
                <Line
                  key={m.id} dataKey={m.experiment_id}
                  name={m.replicate_label ? `replicate ${m.replicate_label}` : 'replicate 0'}
                  stroke={chartColors.series[i]} strokeWidth={1.5}
                  dot={{ r: 4, fill: chartColors.series[i] }} connectNulls
                />
              ))}
            <Line
              dataKey="mean" name={`mean ± sd (${metric.label})`}
              stroke={chartColors.mean} strokeWidth={2}
              dot={{ r: 5, fill: chartColors.mean }} connectNulls
            >
              <ErrorBar dataKey="sd" stroke={chartColors.mean} strokeWidth={1.5} width={6} />
            </Line>
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Accessible table view of the rollup */}
      <Table>
        <TableHead>
          <tr>
            <Th>Time (d)</Th>
            <Th>n</Th>
            <Th>Gross NH₄ (mM)</Th>
            <Th>Net NH₄ (mM)</Th>
            <Th>NH₄ (g/t)</Th>
            <Th>H₂ (µmol)</Th>
            <Th>Fe²⁺ → NH₃ (%)</Th>
            <Th>pH</Th>
          </tr>
        </TableHead>
        <TableBody>
          {rollup.map((r) => (
            <TableRow key={`${r.base_experiment_id}-${r.time_post_reaction_bucket_days}`}>
              <Td className="font-mono-data">{fmt(r.time_post_reaction_bucket_days, 1)}</Td>
              <Td className="font-mono-data text-ink-muted">n = {r.n_replicates}</Td>
              <Td className="font-mono-data">
                {r.mean_gross_ammonium_mM == null
                  ? '—'
                  : `${fmt(r.mean_gross_ammonium_mM)} ± ${fmt(r.sd_gross_ammonium_mM ?? 0)}`}
              </Td>
              <Td className="font-mono-data">
                {r.mean_net_ammonium_mM == null
                  ? '—'
                  : `${fmt(r.mean_net_ammonium_mM)} ± ${fmt(r.sd_net_ammonium_mM ?? 0)}`}
              </Td>
              <Td className="font-mono-data">
                {r.mean_grams_per_ton_yield == null
                  ? '—'
                  : `${fmt(r.mean_grams_per_ton_yield, 1)} ± ${fmt(r.sd_grams_per_ton_yield ?? 0, 1)}`}
              </Td>
              <Td className="font-mono-data">
                {r.mean_h2_micromoles == null
                  ? '—'
                  : `${fmt(r.mean_h2_micromoles, 1)} ± ${fmt(r.sd_h2_micromoles ?? 0, 1)}`}
              </Td>
              <Td className="font-mono-data">
                {r.mean_fe_yield_nh3_pct == null
                  ? '—'
                  : `${fmt(r.mean_fe_yield_nh3_pct)} ± ${fmt(r.sd_fe_yield_nh3_pct ?? 0)}`}
              </Td>
              <Td className="font-mono-data">{fmt(r.mean_final_ph)}</Td>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
```

- [ ] **Step 5: Wire the mode toggle into `ResultsTab.tsx`**

In `frontend/src/pages/ExperimentDetail/ResultsTab.tsx`: add a replicate-group query and a `mode` state at the top of the component:

```tsx
const [mode, setMode] = useState<'individual' | 'grouped'>('individual')
const { data: replicateGroup } = useQuery({
  queryKey: ['replicate-group', experimentId],
  queryFn: () => experimentsApi.getReplicateGroup(experimentId),
})
const hasGroup = (replicateGroup?.members.length ?? 0) > 0
```

Render a two-button segmented toggle in the tab's existing action bar (next to "Background NH₄" / "+ Add Results"), only when `hasGroup`:

```tsx
{hasGroup && (
  <div className="flex items-center rounded border border-surface-border overflow-hidden text-xs">
    <button
      className={`px-2.5 py-1 ${mode === 'individual' ? 'bg-surface-raised text-ink-primary' : 'text-ink-secondary hover:text-ink-primary'}`}
      onClick={() => setMode('individual')}
    >
      Individual
    </button>
    <button
      className={`px-2.5 py-1 ${mode === 'grouped' ? 'bg-surface-raised text-ink-primary' : 'text-ink-secondary hover:text-ink-primary'}`}
      onClick={() => setMode('grouped')}
    >
      Grouped (n={replicateGroup!.members.length})
    </button>
  </div>
)}
```

Below the action bar: `{mode === 'grouped' && hasGroup ? <GroupedResultsView experimentId={experimentId} /> : (<existing individual results grid unchanged>)}` — wrap the existing grid rendering, do not modify it.

- [ ] **Step 6: Run tests + lint to verify they pass**

Run: `cd frontend && npx vitest run src && npx eslint src/pages/ExperimentDetail/GroupedResultsView.tsx src/pages/ExperimentDetail/ResultsTab.tsx src/assets/brand.ts`
Expected: PASS (including the pre-existing `ResultsTab.columns.test.tsx` — the individual grid is untouched), zero lint warnings.

- [ ] **Step 7: Visual check (only if dev servers are reachable — never start them)**

If `http://localhost:5173` responds, open an experiment with replicates, switch to Grouped, and eyeball: no label collisions, error bars visible, legend readable, member links navigate. Otherwise state in the task report that the visual check was skipped because the dev server was not running.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/assets/brand.ts frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx frontend/src/pages/ExperimentDetail/ResultsTab.tsx frontend/src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx frontend/src/test/setup.ts
git commit -m "[#70] Add grouped results chart and rollup table

- Recharts mean±sd with replicate overlay; validated chart tokens
- Tests added: yes
- Docs updated: no"
```

---

### Task 8: Frontend — Create Replicates modal + wizard option

**Files:**
- Create: `frontend/src/components/experiments/CreateReplicatesModal.tsx`
- Modify: `frontend/src/pages/ExperimentDetail/index.tsx` (header action)
- Modify: `frontend/src/pages/NewExperiment/index.tsx` + `frontend/src/pages/NewExperiment/Step4Review.tsx` (replicate count)
- Test: `frontend/src/components/experiments/CreateReplicatesModal.test.tsx` (create)

**Interfaces:**
- Consumes: `experimentsApi.createReplicates`, `.getReplicateGroup` (Task 5); `Modal`, `Button`, `Input`, `useToast` from `@/components/ui`.
- Produces: `<CreateReplicatesModal open onClose baseExperimentId />`; a "Create Replicates" button on non-replicate experiment detail pages; a "replicates to create" count (0–25, default 0) on the wizard review step that calls the batch endpoint after the parent is fully created.

- [ ] **Step 1: Write the failing modal tests**

Create `frontend/src/components/experiments/CreateReplicatesModal.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/api/experiments', () => ({
  experimentsApi: { createReplicates: vi.fn(), getReplicateGroup: vi.fn() },
}))

import { CreateReplicatesModal } from './CreateReplicatesModal'
import { experimentsApi } from '@/api/experiments'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
})
function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
  vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
    base_experiment_id: 'SERUM_001',
    parent: { id: 1, experiment_id: 'SERUM_001', replicate_label: null, status: 'ONGOING' },
    members: [{ id: 2, experiment_id: 'SERUM_001a', replicate_label: 'a', status: 'ONGOING' }],
  })
})

describe('CreateReplicatesModal', () => {
  it('previews the next letters after existing members', async () => {
    render(
      <CreateReplicatesModal open onClose={() => {}} baseExperimentId="SERUM_001" />,
      { wrapper },
    )
    // "a" exists, so count=3 previews b, c, d
    await waitFor(() =>
      expect(screen.getByText(/SERUM_001b, SERUM_001c, SERUM_001d/)).toBeInTheDocument()
    )
  })

  it('submits base + count and reports created IDs', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.createReplicates).mockResolvedValue({
      created: [], skipped: [],
    })
    render(
      <CreateReplicatesModal open onClose={() => {}} baseExperimentId="SERUM_001" />,
      { wrapper },
    )
    await user.click(screen.getByRole('button', { name: /create replicates/i }))
    await waitFor(() =>
      expect(experimentsApi.createReplicates).toHaveBeenCalledWith({
        base_experiment_id: 'SERUM_001',
        count: 3,
      })
    )
  })
})
```

(If the shared `ToastProvider` is required by `useToast`, wrap it into `wrapper` the same way other modal tests in the repo do — check `frontend/src/components/experiments/AddResultModal.test.tsx` and mirror it.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/experiments/CreateReplicatesModal.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the modal**

Create `frontend/src/components/experiments/CreateReplicatesModal.tsx`:

```tsx
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { Modal, Button, Input, useToast } from '@/components/ui'

const LETTERS = 'abcdefghijklmnopqrstuvwxyz'

interface CreateReplicatesModalProps {
  open: boolean
  onClose: () => void
  baseExperimentId: string
}

/** Batch-create lettered replicates of a base experiment (issue #70 P2).
 *  Conditions and chemical additives are copied server-side from the base. */
export function CreateReplicatesModal({ open, onClose, baseExperimentId }: CreateReplicatesModalProps) {
  const [count, setCount] = useState(3)
  const toast = useToast()
  const queryClient = useQueryClient()

  const { data: group } = useQuery({
    queryKey: ['replicate-group', baseExperimentId],
    queryFn: () => experimentsApi.getReplicateGroup(baseExperimentId),
    enabled: open,
  })

  const previewIds = useMemo(() => {
    const existing = new Set((group?.members ?? []).map((m) => m.replicate_label))
    const base = group?.base_experiment_id ?? baseExperimentId
    return LETTERS.split('')
      .filter((l) => !existing.has(l))
      .slice(0, count)
      .map((l) => `${base}${l}`)
  }, [group, baseExperimentId, count])

  const mutation = useMutation({
    mutationFn: () =>
      experimentsApi.createReplicates({ base_experiment_id: baseExperimentId, count }),
    onSuccess: (data) => {
      const ids = data.created.map((e) => e.experiment_id)
      toast.success(
        ids.length ? `Created ${ids.join(', ')}` : 'No replicates created',
      )
      data.skipped.forEach((msg) => toast.error(msg))
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
      queryClient.invalidateQueries({ queryKey: ['replicate-group', baseExperimentId] })
      onClose()
    },
    onError: () => toast.error('Failed to create replicates'),
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Create Replicates"
      description="Copies this experiment's conditions and additives to new lettered replicate vials. Per-vial actuals (e.g. actual rock mass) stay editable on each replicate."
      size="sm"
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={mutation.isPending || count < 1}
          >
            Create Replicates
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <div className="w-28">
          <Input
            label="How many?"
            type="number"
            min={1}
            max={25}
            value={String(count)}
            onChange={(e) => setCount(Math.max(1, Math.min(25, Number(e.target.value) || 1)))}
          />
        </div>
        <p className="text-xs text-ink-secondary">
          Will create:{' '}
          <span className="font-mono-data text-ink-primary">{previewIds.join(', ') || '—'}</span>
        </p>
      </div>
    </Modal>
  )
}
```

(Match the repo's actual `useToast` API — if it exposes `toast({ title, variant })` or `showToast(...)` instead of `.success/.error`, follow the pattern in `AddResultsModal.tsx`.)

- [ ] **Step 4: Mount on the experiment detail page**

In `frontend/src/pages/ExperimentDetail/index.tsx`: add `const [replicatesOpen, setReplicatesOpen] = useState(false)`, import the modal, and in the page header's action area (beside the existing inline editors/actions) render — only for non-replicate experiments:

```tsx
{experiment.replicate_label === null && (
  <Button variant="secondary" size="sm" onClick={() => setReplicatesOpen(true)}>
    Create Replicates
  </Button>
)}
<CreateReplicatesModal
  open={replicatesOpen}
  onClose={() => setReplicatesOpen(false)}
  baseExperimentId={experiment.experiment_id}
/>
```

Also add, under the experiment ID heading, a small lineage hint for replicate members so grouped data is one click away:

```tsx
{experiment.replicate_label !== null && experiment.base_experiment_id && (
  <p className="text-xs text-ink-muted">
    Replicate {experiment.replicate_label} of{' '}
    <Link to={`/experiments/${experiment.base_experiment_id}`} className="text-red-400 hover:text-red-300 font-mono-data">
      {experiment.base_experiment_id}
    </Link>
  </p>
)}
```

(This link targets the bare stem; when the parent was spelled `-0`/`-1` the stem page may 404 — acceptable rare case, the list group still reaches it.)

- [ ] **Step 5: Add the wizard replicate count**

In `frontend/src/pages/NewExperiment/index.tsx`:
1. State: `const [replicateCount, setReplicateCount] = useState(0)`.
2. The submit mutation's `mutationFn`, after the additives loop and before returning `exp`, add:

```ts
if (replicateCount > 0) {
  const res = await experimentsApi.createReplicates({
    base_experiment_id: exp.experiment_id,
    count: replicateCount,
  })
  return { exp, replicates: res }
}
return { exp, replicates: null }
```

3. Adjust `onSuccess` to the new return shape; extend the success toast with `, plus ${replicates.created.length} replicates` when present, and surface `replicates.skipped` messages as warning/error toasts. Navigation stays to the parent detail page.
4. Pass `replicateCount`/`setReplicateCount` to `Step4Review` and render there, near the submit summary — hidden when the entered ID itself is lettered:

```tsx
{!/\d+[a-z]$/.test(step1.experimentId.trim()) && (
  <div className="w-40">
    <Input
      label="Replicates to create"
      type="number"
      min={0}
      max={25}
      value={String(replicateCount)}
      onChange={(e) => setReplicateCount(Math.max(0, Math.min(25, Number(e.target.value) || 0)))}
      hint="0 = none. Creates lettered vials (a, b, c…) copying these conditions and additives."
    />
  </div>
)}
```

(Adapt prop names to `Step4Review`'s actual props interface; if `Input` has no `hint` prop, render the hint as a `<p className="text-2xs text-ink-muted">` below it, matching Step1's idiom.)

- [ ] **Step 6: Run tests + lint to verify they pass**

Run: `cd frontend && npx vitest run src && npx eslint src/components/experiments/CreateReplicatesModal.tsx src/pages/ExperimentDetail/index.tsx "src/pages/NewExperiment/index.tsx" src/pages/NewExperiment/Step4Review.tsx`
Expected: PASS, zero lint warnings.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/experiments/CreateReplicatesModal.tsx frontend/src/components/experiments/CreateReplicatesModal.test.tsx frontend/src/pages/ExperimentDetail/index.tsx frontend/src/pages/NewExperiment/index.tsx frontend/src/pages/NewExperiment/Step4Review.tsx
git commit -m "[#70] Add create-replicates modal and wizard count

- Detail-page action + wizard option share the batch endpoint
- Tests added: yes
- Docs updated: no"
```

---

### Task 9: Documentation + full verification

**Files:**
- Modify: `docs/api/API_REFERENCE.md`
- Create: `docs/user_guide/REPLICATES.md`
- (Hook auto-syncs both to `docs/project_context/` — do not write there directly.)

**Interfaces:**
- Consumes: everything shipped in Tasks 1–8.
- Produces: docs current; whole-branch verification evidence for the PR.

- [ ] **Step 1: Update `docs/api/API_REFERENCE.md`**

Add to the experiments section (follow the file's existing endpoint-entry format):
- `GET /api/experiments` — new `group_replicates` (bool, default false) param with the top-level-row pagination semantics and the nested `replicates` array; new `base_experiment_id`/`parent_experiment_fk`/`replicate_label` fields on list items.
- `GET /api/experiments/{experiment_id}/rollup` — response fields (the 19 rollup columns), the `COALESCE(base_experiment_id, experiment_id)` key, and the MODELS.md caveat that the key does not distinguish lettered replicates from sequential derivations.
- `GET /api/experiments/{experiment_id}/replicate-group` — response shape, empty-members semantics, orphan behavior.
- `POST /api/experiments/replicates` — request/response, copy semantics (conditions + additives, per-vial actuals editable), letter continuation, non-fatal per-ID conflict skipping, 404 when no base experiment.

- [ ] **Step 2: Write `docs/user_guide/REPLICATES.md`**

Short guide (≤1 page, match the tone of `docs/user_guide/BULK_UPLOADS.md`): what replicate IDs look like (`SERUM_001a/b/c`, bare base = replicate 0/parent), the grouped experiments list (toggle, expanding a set), grouped results (mean ± std chart + table, drill-in), creating replicates from the detail page or the New Experiment wizard, and the note that per-vial actuals should be edited on each replicate after creation.

- [ ] **Step 3: Full verification**

```bash
.venv/Scripts/python -m pytest tests/ -q
cd frontend && npx vitest run src && npx tsc --noEmit && npm run build
```

Expected: backend green except the 3 known pre-existing `tests/test_pg_backup_restore.py` failures (confirm they're the same 3); frontend tests green; build succeeds. Also confirm reporting views recreate on import: `.venv/Scripts/python -c "import database.event_listeners"` exits 0.

- [ ] **Step 4: Commit docs**

```bash
git add docs/api/API_REFERENCE.md docs/user_guide/REPLICATES.md docs/project_context/
git commit -m "[#70] Document replicate endpoints and UI

- Tests added: no
- Docs updated: yes"
```

- [ ] **Step 5: PR**

Create the PR with `gh pr create --base develop`, listing which issue-#70 P2 acceptance boxes are covered (grouped list collapses/expands + paginates; grouped results mean ± std + n + drill-in; helper creates linked replicates with editable per-vial conditions). P3–P5 are explicitly not in this PR.

---

## Self-Review Notes

- **P2 acceptance coverage:** grouped list (Tasks 2+6), grouped results with mean±std/n/drill-in (Tasks 3+7), create-N helper with correct linkage + copied conditions (Tasks 4+8), pagination composition (Task 2's top-level-row semantics + Task 6 tests). Issue's "coordinate with pagination work" — #64 already shipped; Task 2 builds on its SQL-side pagination and keeps its regression tests green.
- **Deliberate scope choices:** grouping collapses lettered sets only (user decision 1); mixed groups (a base with both lettered replicates and `-2` sequential re-runs) keep the sequential rows flat by construction (`replicate_label IS NULL`). Grouped-mode child rows are attached even when they didn't match filters (that's the point of grouping). Chart overlays cap at 4 individual series (`chartColors.series` length) — hue cycling is prohibited; in practice sets are a/b/c.
- **Known accepted trade-offs:** list endpoint keeps its existing N+1 per-row enrichment pattern (LAN, 8 users); searching an exact member ID in grouped mode returns the parent row (children attached) rather than the member row itself; the member-page "part of set" link targets the bare stem and may 404 for `-0`/`-1`-spelled parents.
