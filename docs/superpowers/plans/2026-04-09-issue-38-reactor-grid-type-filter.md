# Issue #38: Reactor Grid Type Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent non-HPHT experiments from overwriting HPHT slots in the dashboard reactor grid, and validate at the conditions API level that `reactor_number` can only be set for HPHT or Core Flood experiments.

**Architecture:** Two-layer fix. First, filter the dashboard reactor query so only HPHT populates R01-R16 and only Core Flood populates CF01-CF02. Second, add 422 validation in the conditions POST/PATCH endpoints so bad state cannot be written via the API. Existing tests that create reactor-assigned experiments without an experiment_type must be updated.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/api/routers/dashboard.py` | Modify (lines 115-134, 257-272) | Add `experiment_type` filter to both reactor queries |
| `backend/api/routers/conditions.py` | Modify (lines 45-58, 62-79) | Add reactor_number validation to POST and PATCH |
| `tests/api/test_dashboard.py` | Modify + add new tests | Update 6 existing tests, add 1 new regression test |
| `tests/api/test_conditions.py` | Add new tests | Add 4 validation tests |

---

### Task 1: Dashboard reactor grid — add experiment_type filter

**Files:**
- Modify: `tests/api/test_dashboard.py` (add new test at end of file)
- Modify: `backend/api/routers/dashboard.py:115-134` (get_dashboard reactor query)
- Modify: `backend/api/routers/dashboard.py:257-272` (get_reactor_status query)

- [ ] **Step 1: Write failing test — Serum experiment must not overwrite HPHT slot**

Add to `tests/api/test_dashboard.py`:

```python
def test_serum_experiment_does_not_overwrite_hpht_reactor_slot(client, db_session):
    """
    Issue #38: If both an HPHT and a Serum experiment share the same
    reactor_number and both are ONGOING, only the HPHT experiment must
    appear in the reactor grid. The Serum experiment is silently excluded.
    """
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    older = datetime.datetime.utcnow() - datetime.timedelta(days=10)
    newer = datetime.datetime.utcnow()

    hpht_exp = Experiment(
        experiment_id="HPHT_SLOT38_001",
        experiment_number=38001,
        status=ExperimentStatus.ONGOING,
        created_at=older,
    )
    serum_exp = Experiment(
        experiment_id="SERUM_SLOT38_001",
        experiment_number=38002,
        status=ExperimentStatus.ONGOING,
        created_at=newer,  # higher id / newer — would win old tiebreak
    )
    db_session.add_all([hpht_exp, serum_exp])
    db_session.flush()

    db_session.add(ExperimentalConditions(
        experiment_fk=hpht_exp.id,
        experiment_id="HPHT_SLOT38_001",
        reactor_number=5,
        experiment_type="HPHT",
    ))
    db_session.add(ExperimentalConditions(
        experiment_fk=serum_exp.id,
        experiment_id="SERUM_SLOT38_001",
        reactor_number=5,
        experiment_type="Serum",
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}

    assert "R05" in cards, "R05 slot must be populated by the HPHT experiment"
    assert cards["R05"]["experiment_id"] == "HPHT_SLOT38_001"
    # Serum experiment must NOT appear anywhere in reactors
    all_exp_ids = [c["experiment_id"] for c in resp.json()["reactors"]]
    assert "SERUM_SLOT38_001" not in all_exp_ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/MathewHearl/Documents/0x_Software/database_sandbox/experiment_tracking_sandbox && python -m pytest tests/api/test_dashboard.py::test_serum_experiment_does_not_overwrite_hpht_reactor_slot -v`

Expected: FAIL — Serum experiment currently displaces the HPHT experiment because the query doesn't filter on experiment_type.

- [ ] **Step 3: Fix get_dashboard() reactor query — add experiment_type filter**

In `backend/api/routers/dashboard.py`, add a `.where()` clause to the `reactor_rows` query (around line 132). Replace:

```python
        .where(ExperimentalConditions.reactor_number.isnot(None))
        .order_by(ExperimentalConditions.reactor_number, Experiment.created_at.desc())
```

with:

```python
        .where(ExperimentalConditions.reactor_number.isnot(None))
        .where(ExperimentalConditions.experiment_type.in_(["HPHT", "Core Flood"]))
        .order_by(ExperimentalConditions.reactor_number, Experiment.created_at.desc())
```

- [ ] **Step 4: Fix get_reactor_status() query — same filter**

In `backend/api/routers/dashboard.py`, add the same `.where()` clause to the `get_reactor_status` query (around line 271). Replace:

```python
        .where(ExperimentalConditions.reactor_number.isnot(None))
        .order_by(ExperimentalConditions.reactor_number, Experiment.created_at.desc())
```

with:

```python
        .where(ExperimentalConditions.reactor_number.isnot(None))
        .where(ExperimentalConditions.experiment_type.in_(["HPHT", "Core Flood"]))
        .order_by(ExperimentalConditions.reactor_number, Experiment.created_at.desc())
```

- [ ] **Step 5: Run the new test to verify it passes**

Run: `cd C:/Users/MathewHearl/Documents/0x_Software/database_sandbox/experiment_tracking_sandbox && python -m pytest tests/api/test_dashboard.py::test_serum_experiment_does_not_overwrite_hpht_reactor_slot -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/dashboard.py tests/api/test_dashboard.py
git commit -m "[#38] filter reactor grid to HPHT and Core Flood only

- Dashboard reactor queries now exclude non-HPHT/CF experiments
- Both get_dashboard() and get_reactor_status() updated
- Tests added: yes
- Docs updated: no"
```

---

### Task 2: Update existing dashboard tests for new experiment_type filter

Six existing tests create reactor-assigned experiments without setting `experiment_type` (or with `experiment_type="Serum"`). After Task 1's filter, these experiments no longer appear in the reactor grid, causing test failures. Each test needs a targeted fix.

**Files:**
- Modify: `tests/api/test_dashboard.py` (6 existing tests)

- [ ] **Step 1: Update `test_get_dashboard_reactor_cards_have_label` (line 144)**

The test creates an experiment with `reactor_number=3` but no `experiment_type`. Add `experiment_type="HPHT"` to the `ExperimentalConditions` constructor:

```python
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="DASH_LABEL_001",
        reactor_number=3,
        experiment_type="HPHT",
    )
```

- [ ] **Step 2: Update `test_get_dashboard_with_ongoing_experiment` (line 173)**

Add `experiment_type="HPHT"` to the conditions (around line 203):

```python
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="DASH_FULL_001",
        reactor_number=9,
        temperature_c=150.0,
        experiment_type="HPHT",
    )
```

- [ ] **Step 3: Update `test_reactor_card_includes_specs` (line 321)**

Add `experiment_type="HPHT"` to the conditions (around line 335):

```python
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="SPECS_TEST_001",
        reactor_number=5,
        experiment_type="HPHT",
    )
```

- [ ] **Step 4: Update `test_null_experiment_type_in_reactor_1_gets_r01_not_cf01` (line 469)**

This test now validates the *opposite* behavior: a null experiment_type must NOT appear in the reactor grid. Rename and rewrite:

```python
def test_null_experiment_type_excluded_from_reactor_grid(client, db_session):
    """Experiment with no experiment_type must NOT appear in the reactor grid."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="NULL_TYPE_R1_001",
        experiment_number=91004,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="NULL_TYPE_R1_001",
        reactor_number=1,
        experiment_type=None,
    )
    db_session.add(cond)
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    all_exp_ids = [c["experiment_id"] for c in resp.json()["reactors"]]
    assert "NULL_TYPE_R1_001" not in all_exp_ids, (
        "Experiments with NULL experiment_type must not appear in reactor grid"
    )
```

- [ ] **Step 5: Update `test_dashboard_performance_500_experiments` (line 564)**

Add `experiment_type="HPHT"` to each conditions record (around line 587):

```python
    conds = []
    for i, exp in enumerate(exps[:50]):
        cond = ExperimentalConditions(
            experiment_fk=exp.id,
            experiment_id=exp.experiment_id,
            reactor_number=(i % 16) + 1,
            experiment_type="HPHT",
        )
        conds.append(cond)
```

- [ ] **Step 6: Update `test_dashboard_started_at_reflects_patched_date` (line 604)**

Change `experiment_type` from `"Serum"` to `"HPHT"` and `reactor_number` from 99 to 15 (a valid HPHT reactor). Around line 619:

```python
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="DASH_DATE_001",
        reactor_number=15,
        experiment_type="HPHT",
    )
```

- [ ] **Step 7: Run full dashboard test suite**

Run: `cd C:/Users/MathewHearl/Documents/0x_Software/database_sandbox/experiment_tracking_sandbox && python -m pytest tests/api/test_dashboard.py -v`

Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add tests/api/test_dashboard.py
git commit -m "[#38] update dashboard tests for experiment_type filter

- Existing tests now set experiment_type=HPHT for reactor-assigned experiments
- Null experiment_type test updated to verify grid exclusion
- Serum experiment changed to HPHT in started_at test
- Tests added: no (existing tests updated)
- Docs updated: no"
```

---

### Task 3: Conditions validation — reactor_number restricted to HPHT/Core Flood

**Files:**
- Modify: `tests/api/test_conditions.py` (add new tests)
- Modify: `backend/api/routers/conditions.py:45-79` (add validation to POST and PATCH)

- [ ] **Step 1: Write failing tests for POST validation**

Add to `tests/api/test_conditions.py`:

```python
def test_create_conditions_rejects_reactor_number_for_serum(client, db_session):
    """POST /conditions: reactor_number with experiment_type='Serum' returns 422."""
    exp = _make_experiment(db_session, eid="REACTOR_VAL_001", num=38101)
    resp = client.post("/api/conditions", json={
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "reactor_number": 5,
        "experiment_type": "Serum",
    })
    assert resp.status_code == 422
    assert "reactor_number" in resp.json()["detail"].lower()


def test_create_conditions_rejects_reactor_number_with_no_type(client, db_session):
    """POST /conditions: reactor_number with no experiment_type returns 422."""
    exp = _make_experiment(db_session, eid="REACTOR_VAL_002", num=38102)
    resp = client.post("/api/conditions", json={
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "reactor_number": 3,
    })
    assert resp.status_code == 422
    assert "reactor_number" in resp.json()["detail"].lower()


def test_create_conditions_allows_reactor_number_for_hpht(client, db_session):
    """POST /conditions: reactor_number with experiment_type='HPHT' succeeds."""
    exp = _make_experiment(db_session, eid="REACTOR_VAL_003", num=38103)
    resp = client.post("/api/conditions", json={
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "reactor_number": 7,
        "experiment_type": "HPHT",
    })
    assert resp.status_code == 201
    assert resp.json()["reactor_number"] == 7


def test_create_conditions_allows_reactor_number_for_core_flood(client, db_session):
    """POST /conditions: reactor_number with experiment_type='Core Flood' succeeds."""
    exp = _make_experiment(db_session, eid="REACTOR_VAL_004", num=38104)
    resp = client.post("/api/conditions", json={
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "reactor_number": 1,
        "experiment_type": "Core Flood",
    })
    assert resp.status_code == 201
    assert resp.json()["reactor_number"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/MathewHearl/Documents/0x_Software/database_sandbox/experiment_tracking_sandbox && python -m pytest tests/api/test_conditions.py::test_create_conditions_rejects_reactor_number_for_serum tests/api/test_conditions.py::test_create_conditions_rejects_reactor_number_with_no_type -v`

Expected: FAIL — both reject tests get 201 instead of 422 (no validation exists yet).

- [ ] **Step 3: Write failing tests for PATCH validation**

Add to `tests/api/test_conditions.py`:

```python
def test_patch_conditions_rejects_adding_reactor_number_to_serum(client, db_session):
    """PATCH /conditions: adding reactor_number to a Serum experiment returns 422."""
    exp = _make_experiment(db_session, eid="REACTOR_PATCH_001", num=38201)
    created = client.post("/api/conditions", json={
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "experiment_type": "Serum",
    }).json()
    resp = client.patch(f"/api/conditions/{created['id']}", json={"reactor_number": 5})
    assert resp.status_code == 422
    assert "reactor_number" in resp.json()["detail"].lower()


def test_patch_conditions_rejects_changing_type_away_from_hpht_with_reactor(client, db_session):
    """PATCH /conditions: changing experiment_type from HPHT to Serum while reactor_number is set returns 422."""
    exp = _make_experiment(db_session, eid="REACTOR_PATCH_002", num=38202)
    created = client.post("/api/conditions", json={
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "experiment_type": "HPHT",
        "reactor_number": 3,
    }).json()
    resp = client.patch(f"/api/conditions/{created['id']}", json={"experiment_type": "Serum"})
    assert resp.status_code == 422
    assert "reactor_number" in resp.json()["detail"].lower()
```

- [ ] **Step 4: Run PATCH tests to verify they fail**

Run: `cd C:/Users/MathewHearl/Documents/0x_Software/database_sandbox/experiment_tracking_sandbox && python -m pytest tests/api/test_conditions.py::test_patch_conditions_rejects_adding_reactor_number_to_serum tests/api/test_conditions.py::test_patch_conditions_rejects_changing_type_away_from_hpht_with_reactor -v`

Expected: FAIL — both get 200 instead of 422.

- [ ] **Step 5: Implement validation in conditions router**

In `backend/api/routers/conditions.py`, add a validation helper and call it from both POST and PATCH. Add after the imports (around line 14):

```python
_REACTOR_ALLOWED_TYPES = {"HPHT", "Core Flood"}


def _validate_reactor_number(reactor_number: int | None, experiment_type: str | None) -> None:
    """Raise 422 if reactor_number is set for a non-HPHT, non-Core Flood experiment."""
    if reactor_number is not None and experiment_type not in _REACTOR_ALLOWED_TYPES:
        raise HTTPException(
            status_code=422,
            detail="reactor_number may only be set for HPHT or Core Flood experiments",
        )
```

In `create_conditions` (line 51), add before the `ExperimentalConditions(...)` call:

```python
    _validate_reactor_number(payload.reactor_number, payload.experiment_type)
    cond = ExperimentalConditions(**payload.model_dump())
```

In `update_conditions` (line 73), add after the `setattr` loop and before `db.flush()`:

```python
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(cond, field, value)
    _validate_reactor_number(cond.reactor_number, cond.experiment_type)
    db.flush()
```

- [ ] **Step 6: Run all conditions tests**

Run: `cd C:/Users/MathewHearl/Documents/0x_Software/database_sandbox/experiment_tracking_sandbox && python -m pytest tests/api/test_conditions.py -v`

Expected: ALL PASS

- [ ] **Step 7: Run full test suite to check for regressions**

Run: `cd C:/Users/MathewHearl/Documents/0x_Software/database_sandbox/experiment_tracking_sandbox && python -m pytest tests/api/ -v`

Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add backend/api/routers/conditions.py tests/api/test_conditions.py
git commit -m "[#38] validate reactor_number restricted to HPHT/Core Flood

- POST and PATCH /api/conditions return 422 if reactor_number is set
  for experiment_type other than HPHT or Core Flood
- Tests added: yes
- Docs updated: no"
```
