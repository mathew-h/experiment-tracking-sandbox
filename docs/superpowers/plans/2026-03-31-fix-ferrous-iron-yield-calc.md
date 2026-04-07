# Fix Ferrous Iron Yield Calculations — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `ferrous_iron_yield_h2_pct` and `ferrous_iron_yield_nh3_pct` returning NULL for qualifying experiments by correcting a wrong attribute name in the traversal and wiring the recalculation trigger after elemental uploads.

**Architecture:** Two independent bugs. Bug 1: `scalar_calcs.py` reads `conditions.total_ferrous_iron` (does not exist on the model) instead of `conditions.total_ferrous_iron_g`, causing the traversal to silently return `None` in production. Bug 2: `recalculate_conditions_for_samples` (already written in `elemental_composition_service.py`) is never called from the bulk upload services, so elemental uploads created after conditions are written leave `total_ferrous_iron_g` stale. Fixes are: rename the attribute read, then add one call to each bulk upload service.

**Tech Stack:** Python 3.11, SQLAlchemy 2.x, pytest

---

## File Map

| File | Change |
|------|--------|
| `backend/services/calculations/scalar_calcs.py` | Bug fix: line 86 `total_ferrous_iron` → `total_ferrous_iron_g` |
| `tests/services/calculations/test_scalar_calcs.py` | Fix `make_result_chain` helper + add 2 volume-priority tests |
| `backend/services/bulk_uploads/actlabs_titration_data.py` | Wire `recalculate_conditions_for_samples` in both `bulk_upsert_wide_from_excel` and `import_excel` |

---

## Background: Why the Existing Tests Pass Despite the Bug

`make_result_chain` in `test_scalar_calcs.py` builds a `SimpleNamespace` with the kwarg `total_ferrous_iron=...`. The production code reads `getattr(conditions, 'total_ferrous_iron', None)` — also the wrong name — so both the test fixture and the production code use the same wrong name, and the tests pass. The real SQLAlchemy model field is `total_ferrous_iron_g`.

Fix order: rename the test fixture first → tests fail → fix the production code → tests pass again.

---

### Task 1: Fix the attribute name — TDD

**Files:**
- Modify: `tests/services/calculations/test_scalar_calcs.py` (fix fixture, lines 16–25 and 361–401)
- Modify: `backend/services/calculations/scalar_calcs.py` (line 86)

- [ ] **Step 1.1: Rename the fixture attribute from `total_ferrous_iron` to `total_ferrous_iron_g` in the test helper**

In `tests/services/calculations/test_scalar_calcs.py`, replace `make_result_chain`:

```python
def make_result_chain(rock_mass_g=10.0, water_volume_mL=100.0, total_ferrous_iron_g=None):
    """Build a minimal result → experiment → conditions chain."""
    conditions = types.SimpleNamespace(
        rock_mass_g=rock_mass_g,
        water_volume_mL=water_volume_mL,
        total_ferrous_iron_g=total_ferrous_iron_g,
    )
    experiment = types.SimpleNamespace(conditions=conditions)
    result_entry = types.SimpleNamespace(experiment=experiment)
    return result_entry
```

Then update the four call sites that pass `total_ferrous_iron=...` (they appear in the four wiring tests at the bottom of the file):

```python
# test_recalculate_scalar_sets_h2_yield_when_total_fe_set
result_entry=make_result_chain(rock_mass_g=10.0, total_ferrous_iron_g=1.0),

# test_recalculate_scalar_h2_yield_none_when_no_total_fe
result_entry=make_result_chain(rock_mass_g=10.0, total_ferrous_iron_g=None),

# test_recalculate_scalar_sets_nh3_yield_when_total_fe_set
result_entry=make_result_chain(rock_mass_g=10.0, total_ferrous_iron_g=1.0),

# test_recalculate_scalar_nh3_yield_none_when_no_total_fe
result_entry=make_result_chain(rock_mass_g=10.0, total_ferrous_iron_g=None),
```

- [ ] **Step 1.2: Run tests to confirm they now fail**

```
pytest tests/services/calculations/test_scalar_calcs.py -x -q
```

Expected: 4 failures at the bottom of the file (`recalculate_scalar_sets_h2_yield_when_total_fe_set`, etc.) — the fixture now sets `total_ferrous_iron_g` but the production code still reads `total_ferrous_iron`.

- [ ] **Step 1.3: Fix the attribute read in `scalar_calcs.py`**

In `backend/services/calculations/scalar_calcs.py`, replace line 86:

```python
                total_ferrous_iron_g = getattr(conditions, 'total_ferrous_iron_g', None)
```

(was `total_ferrous_iron`, missing the `_g` suffix)

- [ ] **Step 1.4: Run tests to confirm they all pass**

```
pytest tests/services/calculations/test_scalar_calcs.py -v
```

Expected: all 27 tests pass.

- [ ] **Step 1.5: Commit**

```bash
git add backend/services/calculations/scalar_calcs.py \
        tests/services/calculations/test_scalar_calcs.py
git commit -m "[#21] fix total_ferrous_iron attribute name in scalar traversal

- Tests added: yes (fixture corrected; behaviour already tested)
- Docs updated: no"
```

---

### Task 2: Add missing NH3 volume-priority tests

These tests verify that `recalculate_scalar` feeds the right volume to `calculate_ferrous_iron_yield_nh3`: `sampling_volume_mL` when set, `water_volume_mL` from conditions when absent. The behaviour already exists — we are adding the explicit assertions.

**Files:**
- Modify: `tests/services/calculations/test_scalar_calcs.py` (append after line 401)

- [ ] **Step 2.1: Add two tests after the last test in the file**

Append to `tests/services/calculations/test_scalar_calcs.py`:

```python
def test_ferrous_iron_yield_nh3_uses_sampling_volume_over_water_volume():
    """sampling_volume_mL takes priority over water_volume_mL for NH3 yield.

    sampling = 100 mL, water = 500 mL — result must match 100 mL path.
    net = 10.0 - 0.2 = 9.8 mM
    NH3_mol = (9.8/1000) * (100/1000) = 0.00098
    Fe_g = 0.00098 * 4.5 * 55.845
    """
    s = make_scalar(
        gross_ammonium_concentration_mM=10.0,
        background_ammonium_concentration_mM=0.2,
        sampling_volume_mL=100.0,
        result_entry=make_result_chain(
            rock_mass_g=5.0,
            water_volume_mL=500.0,
            total_ferrous_iron_g=1.0,
        ),
    )
    recalculate_scalar(s, SESSION)
    expected = (9.8 / 1000.0) * (100.0 / 1000.0) * 4.5 * 55.845 / 1.0 * 100
    assert s.ferrous_iron_yield_nh3_pct == pytest.approx(expected, rel=1e-4)


def test_ferrous_iron_yield_nh3_falls_back_to_water_volume_when_sampling_volume_absent():
    """When sampling_volume_mL is None, water_volume_mL from conditions is used.

    water = 500 mL — result must match 500 mL path.
    net = 10.0 - 0.2 = 9.8 mM
    NH3_mol = (9.8/1000) * (500/1000) = 0.0049
    Fe_g = 0.0049 * 4.5 * 55.845
    """
    s = make_scalar(
        gross_ammonium_concentration_mM=10.0,
        background_ammonium_concentration_mM=0.2,
        sampling_volume_mL=None,
        result_entry=make_result_chain(
            rock_mass_g=5.0,
            water_volume_mL=500.0,
            total_ferrous_iron_g=1.0,
        ),
    )
    recalculate_scalar(s, SESSION)
    expected = (9.8 / 1000.0) * (500.0 / 1000.0) * 4.5 * 55.845 / 1.0 * 100
    assert s.ferrous_iron_yield_nh3_pct == pytest.approx(expected, rel=1e-4)
```

- [ ] **Step 2.2: Run the new tests**

```
pytest tests/services/calculations/test_scalar_calcs.py -v -k "sampling_volume"
```

Expected: both pass (behaviour already exists after Task 1 fix).

- [ ] **Step 2.3: Commit**

```bash
git add tests/services/calculations/test_scalar_calcs.py
git commit -m "[#21] add NH3 volume-priority tests for recalculate_scalar

- Tests added: yes
- Docs updated: no"
```

---

### Task 3: Wire recalc trigger in `ElementalCompositionService.bulk_upsert_wide_from_excel`

The integration test `test_wide_format_import_recalculates_linked_experiments` in `tests/services/bulk_uploads/test_elemental_upload_recalc.py` is already written. It currently fails because the trigger isn't wired.

**Files:**
- Modify: `backend/services/bulk_uploads/actlabs_titration_data.py` (inside `ElementalCompositionService.bulk_upsert_wide_from_excel`)

- [ ] **Step 3.1: Confirm the integration test currently fails**

```
pytest tests/services/bulk_uploads/test_elemental_upload_recalc.py::test_wide_format_import_recalculates_linked_experiments -v
```

Expected: FAIL — `assert None == pytest.approx(...)`.

- [ ] **Step 3.2: Add sample tracking and the recalc call to `bulk_upsert_wide_from_excel`**

In `backend/services/bulk_uploads/actlabs_titration_data.py`, inside `ElementalCompositionService.bulk_upsert_wide_from_excel`:

Locate the line `errors: List[str] = []` (line ~135) and add a tracking set below it:

```python
        errors: List[str] = []
        created = updated = skipped = 0
        affected_sample_ids: set[str] = set()
```

Locate where `canonical_id` is assigned (line ~205, after `canonical_id = sample.sample_id`) and add:

```python
                canonical_id = sample.sample_id
                affected_sample_ids.add(canonical_id)
```

Locate the `return created, updated, skipped, errors` statement (line ~230) and replace it with:

```python
        if affected_sample_ids:
            from backend.services.elemental_composition_service import recalculate_conditions_for_samples
            recalculate_conditions_for_samples(db, affected_sample_ids)

        return created, updated, skipped, errors
```

- [ ] **Step 3.3: Run the integration test**

```
pytest tests/services/bulk_uploads/test_elemental_upload_recalc.py::test_wide_format_import_recalculates_linked_experiments -v
```

Expected: PASS.

- [ ] **Step 3.4: Run the full elemental recalc test file**

```
pytest tests/services/bulk_uploads/test_elemental_upload_recalc.py -v
```

Expected: 6 pass, 1 fail (`test_actlabs_import_recalculates_linked_experiments` — still failing, fixed in Task 4).

- [ ] **Step 3.5: Commit**

```bash
git add backend/services/bulk_uploads/actlabs_titration_data.py
git commit -m "[#21] wire recalc trigger after wide-format elemental upload

- Tests added: no (pre-existing integration test now passes)
- Docs updated: no"
```

---

### Task 4: Wire recalc trigger in `ActlabsRockTitrationService.import_excel`

The integration test `test_actlabs_import_recalculates_linked_experiments` currently fails for the same reason.

**Files:**
- Modify: `backend/services/bulk_uploads/actlabs_titration_data.py` (inside `ActlabsRockTitrationService.import_excel`)

- [ ] **Step 4.1: Confirm the integration test currently fails**

```
pytest tests/services/bulk_uploads/test_elemental_upload_recalc.py::test_actlabs_import_recalculates_linked_experiments -v
```

Expected: FAIL.

- [ ] **Step 4.2: Add sample tracking and the recalc call to `import_excel`**

In `backend/services/bulk_uploads/actlabs_titration_data.py`, inside `ActlabsRockTitrationService.import_excel`:

Locate `errors: List[str] = []` (line ~447) and add a tracking set below it:

```python
        errors: List[str] = []
        results_created = results_updated = skipped = 0
        affected_sample_ids: set[str] = set()
```

Locate where `canonical_id = sample.sample_id` is assigned (line ~511) and add the tracking line immediately after:

```python
            canonical_id = sample.sample_id
            affected_sample_ids.add(canonical_id)
```

Locate the `return results_created, results_updated, skipped, errors` statement (line ~531) and replace it with:

```python
        if affected_sample_ids:
            from backend.services.elemental_composition_service import recalculate_conditions_for_samples
            recalculate_conditions_for_samples(db, affected_sample_ids)

        return results_created, results_updated, skipped, errors
```

- [ ] **Step 4.3: Run the full elemental recalc test file**

```
pytest tests/services/bulk_uploads/test_elemental_upload_recalc.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 4.4: Run the full calculation test suite**

```
pytest tests/services/calculations/ tests/services/bulk_uploads/test_elemental_upload_recalc.py -v
```

Expected: all pass, no failures.

- [ ] **Step 4.5: Commit**

```bash
git add backend/services/bulk_uploads/actlabs_titration_data.py
git commit -m "[#21] wire recalc trigger after actlabs titration upload

- Tests added: no (pre-existing integration test now passes)
- Docs updated: no"
```

---

## Notes

- **Background default:** `CALCULATIONS.md` documents the default as `0.2 mM`; the issue body mentions `0.3 mM` in the test name — this appears to be a typo. The code default of `0.2 mM` is correct and already tested by `test_ferrous_iron_yield_nh3_default_background`. Do not change the default.
- **Legacy `ferrous_iron_yield`:** The deprecated manual-entry column is not affected by any of these changes.
- **`v_results_scalar` view:** The issue confirms no view changes are needed — the view already exposes `ferrous_iron_yield_h2_pct` and `ferrous_iron_yield_nh3_pct`.
- **Admin recalculate endpoint:** `POST /api/admin/recalculate/conditions/{id}` already exists and correctly propagates through to scalar results (via `conditions_calcs.py` which calls `recalculate_scalar` in its loop). No changes needed there.
