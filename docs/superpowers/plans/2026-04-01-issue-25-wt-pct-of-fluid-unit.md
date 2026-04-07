# [Issue #25] Add "wt% of fluid" Additive Unit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `wt% of fluid` as a selectable unit for chemical additives, wiring it end-to-end from the PostgreSQL enum through the calculation engine to both frontend entry forms.

**Architecture:** Three-layer change — (1) enum + migration adds the new PostgreSQL type value, (2) the calculation engine gains a new branch using the same `(amount / 100) × water_volume_mL` formula as `wt%` (fluid density ≈ 1 g/mL for dilute solutions), (3) both frontend unit dropdowns gain the new option.

**Tech Stack:** Python 3.13, SQLAlchemy 2.x, Alembic, FastAPI, React 18, TypeScript, pytest, Playwright

---

## Context and Pre-flight Notes

### Enum storage in PostgreSQL
`ChemicalAdditive.unit` uses `Column(Enum(AmountUnit))` with native PostgreSQL enum type named `amountunit`. SQLAlchemy stores the **Python member name** (e.g. `WEIGHT_PERCENT`), not the string value (`wt%`). The migration must add member names to the type.

### Pre-existing gap: PERCENT and WEIGHT_PERCENT
The Python `AmountUnit` enum already defines `PERCENT = "%"` and `WEIGHT_PERCENT = "wt%"`, but no Alembic migration ever added `PERCENT` or `WEIGHT_PERCENT` to the PostgreSQL `amountunit` type. The migration in Task 1 adds all three missing values (`PERCENT`, `WEIGHT_PERCENT`, `WT_PCT_FLUID`) using `IF NOT EXISTS` so it is safe to run on DBs that may already have them from a schema re-bootstrap.

### Formula decision
`wt% of fluid` = mass_solute / mass_fluid × 100. Rearranged: `mass_in_grams = (amount / 100) × mass_fluid_g`. Assuming dilute aqueous solution (ρ ≈ 1 g/mL): `mass_in_grams = (amount / 100) × water_volume_mL`. This is numerically identical to the existing `WEIGHT_PERCENT` formula. The new enum value adds semantic clarity. The `additive_calcs.py` branch for `WT_PCT_FLUID` documents this explicitly.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `database/models/enums.py` | Modify | Add `WT_PCT_FLUID = "wt% of fluid"` to `AmountUnit` |
| `alembic/versions/<hash>_add_wt_pct_fluid_to_amountunit.py` | Create | `ALTER TYPE amountunit ADD VALUE IF NOT EXISTS` for PERCENT, WEIGHT_PERCENT, WT_PCT_FLUID |
| `backend/services/calculations/additive_calcs.py` | Modify | New branch for `WT_PCT_FLUID` unit in `recalculate_additive` |
| `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx` | Modify | Add `wt% of fluid` to `ADDITIVE_UNIT_OPTIONS` |
| `frontend/src/pages/NewExperiment/Step3Additives.tsx` | Modify | Add `'wt% of fluid'` to `AMOUNT_UNITS` |
| `docs/CALCULATIONS.md` | Modify | Document `wt% of fluid` formula |
| `tests/services/calculations/test_additive_calcs.py` | Modify | Two new tests for `WT_PCT_FLUID` calculation |
| `frontend/e2e/journeys/15-wt-pct-fluid-additive.spec.ts` | Create | E2E: create additive with `wt% of fluid`, verify save + display |

---

## Task 1: Add `WT_PCT_FLUID` to the Python enum

**Files:**
- Modify: `database/models/enums.py`

- [ ] **Step 1: Open the enum file and add the new value**

In `database/models/enums.py`, the `AmountUnit` class ends at line 133 with `PERCENT_OF_ROCK = "% of Rock"`. Add one line after it:

```python
class AmountUnit(enum.Enum):
    """Units for mass and volume measurements"""
    GRAM = "g"
    MILLIGRAM = "mg"
    MICROGRAM = "μg"
    KILOGRAM = "kg"
    MICROLITER = "μL"
    MILLILITER = "mL"
    LITER = "L"
    MICROMOLE = "μmol"
    MILLIMOLE = "mmol"
    MOLE = "mol"
    # Added concentration-style units for additive entry convenience
    PPM = "ppm"
    MILLIMOLAR = "mM"
    MOLAR = "M"
    PERCENT = "%"
    WEIGHT_PERCENT = "wt%"
    PERCENT_OF_ROCK = "% of Rock"
    WT_PCT_FLUID = "wt% of fluid"
```

- [ ] **Step 2: Verify the enum value is importable**

```bash
cd C:\Users\MathewHearl\Documents\0x_Software\database_sandbox\experiment_tracking_sandbox
.venv/Scripts/python -c "from database.models.enums import AmountUnit; print(AmountUnit.WT_PCT_FLUID.value)"
```

Expected output: `wt% of fluid`

---

## Task 2: Create Alembic migration for PostgreSQL enum

**Files:**
- Create: `alembic/versions/<hash>_add_wt_pct_fluid_to_amountunit.py`

- [ ] **Step 1: Generate the migration file**

```bash
.venv/Scripts/alembic revision -m "add_wt_pct_fluid_to_amountunit"
```

Note the generated filename (e.g. `alembic/versions/abc123_add_wt_pct_fluid_to_amountunit.py`).

- [ ] **Step 2: Replace the migration body**

Open the generated file and replace its `upgrade` and `downgrade` functions:

```python
"""add_wt_pct_fluid_to_amountunit

Revision ID: <generated-id>
Revises: <previous-head>
Create Date: 2026-04-01

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '<generated-id>'
down_revision = '<previous-head>'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add missing AmountUnit values to the PostgreSQL native enum type.
    # PERCENT and WEIGHT_PERCENT were in the Python enum but never migrated.
    # WT_PCT_FLUID is new (issue #25).
    # IF NOT EXISTS is safe on databases already bootstrapped from Base.metadata.create_all.
    # On SQLite, Enum columns are VARCHAR — these statements are no-ops.
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        op.execute("ALTER TYPE amountunit ADD VALUE IF NOT EXISTS 'PERCENT'")
        op.execute("ALTER TYPE amountunit ADD VALUE IF NOT EXISTS 'WEIGHT_PERCENT'")
        op.execute("ALTER TYPE amountunit ADD VALUE IF NOT EXISTS 'WT_PCT_FLUID'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    # Downgrade is a no-op. Remove any rows using WT_PCT_FLUID before rolling back.
    pass
```

- [ ] **Step 3: Apply the migration**

```bash
.venv/Scripts/alembic upgrade head
```

Expected: `Running upgrade <previous> -> <new>, add_wt_pct_fluid_to_amountunit` with no errors.

- [ ] **Step 4: Verify the migration applied**

```bash
.venv/Scripts/alembic current
```

Expected: shows the new revision as `(head)`.

- [ ] **Step 5: Commit**

```bash
git add database/models/enums.py alembic/versions/<hash>_add_wt_pct_fluid_to_amountunit.py
git commit -m "[#25] add WT_PCT_FLUID to AmountUnit enum and migration

- Tests added: no
- Docs updated: no"
```

---

## Task 3: Add calculation branch for `WT_PCT_FLUID`

**Files:**
- Modify: `backend/services/calculations/additive_calcs.py`
- Test: `tests/services/calculations/test_additive_calcs.py`

- [ ] **Step 1: Write the failing tests first**

Open `tests/services/calculations/test_additive_calcs.py`. The existing helpers `make_compound`, `make_experiment`, `make_additive`, and `SESSION` are already defined at the top. Add two new tests at the end of the file:

```python
def test_wt_pct_fluid_mass_computed_from_water_volume():
    """mass_in_grams = (amount / 100) × water_volume_mL (density ≈ 1 g/mL)."""
    compound = make_compound(molecular_weight_g_mol=40.0)
    experiment = make_experiment(water_volume_mL=500.0, rock_mass_g=10.0)
    additive = make_additive(amount=2.0, unit=AmountUnit.WT_PCT_FLUID,
                              compound=compound, experiment=experiment)
    recalculate_additive(additive, SESSION)
    assert additive.mass_in_grams == pytest.approx(10.0)  # 2/100 × 500
    assert additive.moles_added == pytest.approx(10.0 / 40.0)
    assert additive.final_concentration == pytest.approx(2.0)
    assert additive.concentration_units == 'wt% of fluid'


def test_wt_pct_fluid_no_mass_when_water_volume_missing():
    """mass_in_grams stays None when water_volume_mL is not set."""
    compound = make_compound(molecular_weight_g_mol=40.0)
    experiment = make_experiment(water_volume_mL=None, rock_mass_g=10.0)
    additive = make_additive(amount=5.0, unit=AmountUnit.WT_PCT_FLUID,
                              compound=compound, experiment=experiment)
    recalculate_additive(additive, SESSION)
    assert additive.mass_in_grams is None
    assert additive.moles_added is None
    assert additive.final_concentration == pytest.approx(5.0)
    assert additive.concentration_units == 'wt% of fluid'
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
pytest tests/services/calculations/test_additive_calcs.py::test_wt_pct_fluid_mass_computed_from_water_volume tests/services/calculations/test_additive_calcs.py::test_wt_pct_fluid_no_mass_when_water_volume_missing -v
```

Expected: both FAIL — `AmountUnit.WT_PCT_FLUID` hits the `else` branch and produces wrong results.

- [ ] **Step 3: Add the calculation branch**

In `backend/services/calculations/additive_calcs.py`, the existing `elif unit in (AmountUnit.PERCENT, AmountUnit.WEIGHT_PERCENT):` block is at around line 55. Add a new `elif` immediately after it (before the `elif unit == AmountUnit.PPM:` line):

```python
    elif unit in (AmountUnit.PERCENT, AmountUnit.WEIGHT_PERCENT):
        if water_volume_ml is not None and water_volume_ml > 0:
            instance.mass_in_grams = (amount / 100.0) * water_volume_ml
        if instance.mass_in_grams is not None and molecular_weight:
            instance.moles_added = instance.mass_in_grams / molecular_weight
        instance.final_concentration = amount
        instance.concentration_units = unit.value

    elif unit == AmountUnit.WT_PCT_FLUID:
        # wt% of fluid: mass_solute = (amount / 100) × mass_fluid_g
        # For dilute aqueous solutions (ρ_fluid ≈ 1 g/mL), mass_fluid_g ≈ water_volume_mL.
        # Formula is numerically identical to WEIGHT_PERCENT; the unit adds semantic clarity.
        if water_volume_ml is not None and water_volume_ml > 0:
            instance.mass_in_grams = (amount / 100.0) * water_volume_ml
        if instance.mass_in_grams is not None and molecular_weight:
            instance.moles_added = instance.mass_in_grams / molecular_weight
        instance.final_concentration = amount
        instance.concentration_units = 'wt% of fluid'

    elif unit == AmountUnit.PPM:
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
pytest tests/services/calculations/test_additive_calcs.py -v
```

Expected: all tests PASS including the two new ones.

- [ ] **Step 5: Commit**

```bash
git add backend/services/calculations/additive_calcs.py tests/services/calculations/test_additive_calcs.py
git commit -m "[#25] add WT_PCT_FLUID calculation branch in additive_calcs

- Tests added: yes — 2 unit tests (mass from water volume, no-mass guard)
- Docs updated: no"
```

---

## Task 4: Update frontend unit dropdowns

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx` (line 14–20)
- Modify: `frontend/src/pages/NewExperiment/Step3Additives.tsx` (line 7)

- [ ] **Step 1: Add `wt% of fluid` to the ConditionsTab dropdown**

In `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx`, replace `ADDITIVE_UNIT_OPTIONS` (lines 14–20):

```typescript
const ADDITIVE_UNIT_OPTIONS = [
  { value: 'g', label: 'g' }, { value: 'mg', label: 'mg' },
  { value: 'mM', label: 'mM' }, { value: 'ppm', label: 'ppm' },
  { value: '% of Rock', label: '% of Rock' }, { value: 'mL', label: 'mL' },
  { value: 'μL', label: 'μL' }, { value: 'mol', label: 'mol' },
  { value: 'mmol', label: 'mmol' }, { value: 'wt% of fluid', label: 'wt% of fluid' },
]
```

- [ ] **Step 2: Add `wt% of fluid` to the New Experiment wizard dropdown**

In `frontend/src/pages/NewExperiment/Step3Additives.tsx`, replace line 7:

```typescript
const AMOUNT_UNITS = ['g', 'mg', 'mL', 'μL', 'mM', 'M', 'ppm', 'mmol', 'mol', '% of Rock', 'wt%', 'wt% of fluid']
```

- [ ] **Step 3: Verify TypeScript compiles with no errors**

```bash
cd frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: no output (zero errors).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/ConditionsTab.tsx frontend/src/pages/NewExperiment/Step3Additives.tsx
git commit -m "[#25] add wt% of fluid to unit dropdowns in ConditionsTab and Step3Additives

- Tests added: no
- Docs updated: no"
```

---

## Task 5: Document the formula in CALCULATIONS.md

**Files:**
- Modify: `docs/CALCULATIONS.md`

- [ ] **Step 1: Open CALCULATIONS.md and locate the additive units table**

The additive units table is at approximately line 60 and contains a row:

```
| %, wt% | `(amount / 100) × water_volume_mL` |
```

- [ ] **Step 2: Add a new row for `wt% of fluid`**

Replace that row with two rows:

```markdown
| %, wt% | `(amount / 100) × water_volume_mL` |
| wt% of fluid | `(amount / 100) × water_volume_mL` — identical to `wt%`; assumes fluid density ≈ 1 g/mL for dilute aqueous solutions |
```

- [ ] **Step 3: Commit**

```bash
git add docs/CALCULATIONS.md docs/project_context/CALCULATIONS.md
git commit -m "[#25] document wt% of fluid formula in CALCULATIONS.md

- Tests added: no
- Docs updated: yes"
```

Note: `docs/project_context/CALCULATIONS.md` is synced automatically by the PostToolUse hook when `docs/CALCULATIONS.md` is saved. Include it in the commit only if it was actually modified by the hook.

---

## Task 6: E2E journey — create and verify `wt% of fluid` additive

**Files:**
- Create: `frontend/e2e/journeys/15-wt-pct-fluid-additive.spec.ts`

- [ ] **Step 1: Review the most recent E2E journey for the established pattern**

Read `frontend/e2e/journeys/14-dashboard-cf-slots.spec.ts` and `frontend/e2e/fixtures/auth.ts` to understand the `test` import and `page` usage before writing anything.

Expected imports pattern:
```typescript
import { test, expect } from '../fixtures/auth'
```

- [ ] **Step 2: Write the E2E spec**

Create `frontend/e2e/journeys/15-wt-pct-fluid-additive.spec.ts`:

```typescript
import { test, expect } from '../fixtures/auth'

test.describe('wt% of fluid additive unit (issue #25)', () => {
  test('wt% of fluid appears in unit dropdown and saves correctly in ConditionsTab', async ({ page }) => {
    // Navigate to the first available experiment detail page
    await page.goto('/')
    await page.getByRole('link', { name: /experiment/i }).first().click()
    await page.getByRole('tab', { name: /conditions/i }).click()

    // Open the Add Additive modal (button labelled "+ Add Additive" or similar)
    await page.getByRole('button', { name: /add additive/i }).click()

    // Verify the unit dropdown contains "wt% of fluid"
    const unitSelect = page.getByLabel(/unit/i)
    await expect(unitSelect).toBeVisible()
    const options = await unitSelect.locator('option').allTextContents()
    expect(options).toContain('wt% of fluid')
  })

  test('selecting wt% of fluid and saving persists to the database', async ({ page }) => {
    // Navigate to an experiment that has conditions set up with a water_volume_mL value
    await page.goto('/')
    await page.getByRole('link', { name: /experiment/i }).first().click()
    await page.getByRole('tab', { name: /conditions/i }).click()

    // Open the Add Additive modal
    await page.getByRole('button', { name: /add additive/i }).click()

    // Fill compound: type in a known compound name from the test database
    const compoundInput = page.getByPlaceholder(/compound/i)
    await compoundInput.fill('Mag')
    await page.getByRole('option', { name: /magnetite/i }).first().click()

    // Fill amount
    await page.getByLabel(/amount/i).fill('2')

    // Select wt% of fluid
    await page.getByLabel(/unit/i).selectOption('wt% of fluid')

    // Save
    await page.getByRole('button', { name: /save/i }).click()

    // The modal should close and the additive row should appear in the conditions list
    await expect(page.getByText('wt% of fluid')).toBeVisible()
  })
})
```

- [ ] **Step 2: Run the E2E tests**

```bash
cd frontend
npx playwright test e2e/journeys/15-wt-pct-fluid-additive.spec.ts --reporter=line
```

Expected: both tests PASS. If the first test fails because no experiment exists in the test environment, adapt the navigation to use a known experiment ID (check your E2E setup / seed data).

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/journeys/15-wt-pct-fluid-additive.spec.ts
git commit -m "[#25] add E2E tests for wt% of fluid unit

- Tests added: yes — 2 Playwright E2E tests (dropdown presence, save + display)
- Docs updated: no"
```

---

## Task 7: Full test run and log issue completion

**Files:**
- Modify: `docs/working/issue-log.md`

- [ ] **Step 1: Run all backend tests**

```bash
pytest tests/services/calculations/test_additive_calcs.py tests/api/test_additives.py -v
```

Expected: all existing tests plus the 2 new `WT_PCT_FLUID` tests PASS.

- [ ] **Step 2: TypeScript compile check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 3: Log issue completion in issue-log.md**

Append to `docs/working/issue-log.md`:

```markdown
## 2026-04-01 | issue #25 — Add "wt% of fluid" as a selectable additive unit
- **Files changed:**
  - `database/models/enums.py` — added `WT_PCT_FLUID = "wt% of fluid"` to `AmountUnit`
  - `alembic/versions/<hash>_add_wt_pct_fluid_to_amountunit.py` — new migration: `ALTER TYPE amountunit ADD VALUE IF NOT EXISTS` for PERCENT, WEIGHT_PERCENT, WT_PCT_FLUID
  - `backend/services/calculations/additive_calcs.py` — new `elif unit == AmountUnit.WT_PCT_FLUID` branch; formula `(amount / 100) × water_volume_mL`
  - `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx` — added `wt% of fluid` to `ADDITIVE_UNIT_OPTIONS`
  - `frontend/src/pages/NewExperiment/Step3Additives.tsx` — added `wt% of fluid` to `AMOUNT_UNITS`
  - `docs/CALCULATIONS.md` — documented `wt% of fluid` formula
  - `tests/services/calculations/test_additive_calcs.py` — 2 new unit tests
  - `frontend/e2e/journeys/15-wt-pct-fluid-additive.spec.ts` — 2 new Playwright E2E tests
- **Tests added:** yes — 2 backend unit tests, 2 Playwright E2E tests
- **Decision logged:** `wt% of fluid` uses formula identical to `wt%` (assumes dilute aqueous solution ρ ≈ 1 g/mL); implemented as a distinct branch for semantic clarity
```

- [ ] **Step 4: Final commit and push**

```bash
git add docs/working/issue-log.md docs/project_context/issue-log.md
git commit -m "[#25] log issue completion in issue-log

- Tests added: no
- Docs updated: yes"
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Task |
|-------------|------|
| `wt% of fluid` appears in unit dropdown (New Experiment) | Task 4, Step 2 |
| `wt% of fluid` appears in unit dropdown (edit modal) | Task 4, Step 1 |
| Selecting and saving correctly persists to DB | Task 2 (migration) + Task 6 (E2E) |
| Calculation engine computes `mass_in_grams` correctly | Task 3 |
| Formula documented in CALCULATIONS.md | Task 5 |
| No existing unit options broken | Task 7 (full test run) |
| E2E: create additive, verify save + display + derived fields | Task 6 |

**Gaps / Notes:**
- The E2E test in Task 6, Step 2 uses `Magnetite` as a test compound. If the E2E test database does not contain a compound matching `Mag`, adapt the compound name to whatever exists. Check the chemicals page in the running app.
- The CALCULATIONS.md sync (docs/project_context/) is handled by the PostToolUse hook automatically. Include it in the commit only if the hook wrote it.
