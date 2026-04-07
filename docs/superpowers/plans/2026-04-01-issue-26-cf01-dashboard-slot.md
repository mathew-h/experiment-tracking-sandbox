# Issue #26 — CF01 Dashboard Slot Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Diagnose and prove the CF01/CF02 reactor slot derivation is correct, add tests that guard against regression, and deliver the E2E tests required by the acceptance criteria.

**Architecture:** The backend label derivation in `dashboard.py` is already correct — `reactor_label = "CF{rn:02d}"` when `experiment_type == "Core Flood"`. The root cause of the reported bug is data: the affected experiment has `experiment_type = NULL` (or a non-"Core Flood" string) in `ExperimentalConditions`, causing the backend to fall back to `"R01"`. No code changes are needed. Tasks 1–2 add the missing tests, and Task 3 is a manual data-investigation note.

**Tech Stack:** Python/pytest (backend integration tests), Playwright/TypeScript (E2E), PostgreSQL test DB (`experiments_test`)

---

## Pre-flight: environment check

Before starting, confirm the backend tests can reach the test DB:

```bash
cd /path/to/experiment_tracking_sandbox
pytest tests/api/test_dashboard.py -v --tb=short 2>&1 | tail -20
```

All existing tests should pass. If any fail, stop and investigate before adding new tests.

---

## File Map

| Action | File | What changes |
|--------|------|-------------|
| Modify | `tests/api/test_dashboard.py` | Add 4 new backend integration tests for CF label derivation |
| Create | `frontend/e2e/journeys/14-dashboard-cf-slots.spec.ts` | New E2E journey: CF01 active + HPHT regression |

---

## Task 1 — Backend integration tests for CF label derivation

**Files:**
- Modify: `tests/api/test_dashboard.py` (append after the `test_reactor_card_data_schema_includes_specs` test, before the performance test)

### Step 1.1 — Write the 4 failing tests (append to `tests/api/test_dashboard.py`)

Open `tests/api/test_dashboard.py` and append the following block immediately before the `# Performance test` section comment (line ~366):

```python
# ---------------------------------------------------------------------------
# CF slot label derivation tests (issue #26)
# ---------------------------------------------------------------------------

def test_core_flood_experiment_in_reactor_1_gets_cf01_label(client, db_session):
    """Core Flood experiment in reactor 1 must produce reactor_label = 'CF01'."""
    import datetime
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="CF_LABEL_R1_001",
        experiment_number=9101,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="CF_LABEL_R1_001",
        reactor_number=1,
        experiment_type="Core Flood",
    )
    db_session.add(cond)
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_number"]: c for c in resp.json()["reactors"]}
    assert 1 in cards, "reactor_number=1 not found in reactor cards"
    assert cards[1]["reactor_label"] == "CF01", (
        f"Expected CF01 but got {cards[1]['reactor_label']!r}. "
        "experiment_type='Core Flood' should produce label CF01."
    )
    assert cards[1]["experiment_id"] == "CF_LABEL_R1_001"


def test_core_flood_experiment_in_reactor_2_gets_cf02_label(client, db_session):
    """Core Flood experiment in reactor 2 must produce reactor_label = 'CF02'."""
    import datetime
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="CF_LABEL_R2_001",
        experiment_number=9102,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="CF_LABEL_R2_001",
        reactor_number=2,
        experiment_type="Core Flood",
    )
    db_session.add(cond)
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_number"]: c for c in resp.json()["reactors"]}
    assert 2 in cards
    assert cards[2]["reactor_label"] == "CF02", (
        f"Expected CF02 but got {cards[2]['reactor_label']!r}."
    )


def test_hpht_experiment_in_reactor_1_gets_r01_not_cf01(client, db_session):
    """HPHT experiment in reactor 1 must produce reactor_label = 'R01', not CF01."""
    import datetime
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="HPHT_LABEL_R1_001",
        experiment_number=9103,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="HPHT_LABEL_R1_001",
        reactor_number=1,
        experiment_type="HPHT",
    )
    db_session.add(cond)
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_number"]: c for c in resp.json()["reactors"]}
    assert 1 in cards
    assert cards[1]["reactor_label"] == "R01", (
        f"Expected R01 but got {cards[1]['reactor_label']!r}. "
        "Non-Core Flood experiments must not be mapped to CF slots."
    )


def test_null_experiment_type_in_reactor_1_gets_r01_not_cf01(client, db_session):
    """Experiment with no experiment_type in reactor 1 falls back to R01, not CF01."""
    import datetime
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="NULL_TYPE_R1_001",
        experiment_number=9104,
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
    cards = {c["reactor_number"]: c for c in resp.json()["reactors"]}
    assert 1 in cards
    assert cards[1]["reactor_label"] == "R01", (
        f"Expected R01 but got {cards[1]['reactor_label']!r}. "
        "NULL experiment_type should produce R-prefix label, not CF."
    )
```

- [ ] **Step 1.2 — Run the new tests to verify they pass**

```bash
pytest tests/api/test_dashboard.py::test_core_flood_experiment_in_reactor_1_gets_cf01_label \
       tests/api/test_dashboard.py::test_core_flood_experiment_in_reactor_2_gets_cf02_label \
       tests/api/test_dashboard.py::test_hpht_experiment_in_reactor_1_gets_r01_not_cf01 \
       tests/api/test_dashboard.py::test_null_experiment_type_in_reactor_1_gets_r01_not_cf01 \
       -v --tb=short
```

**Expected:** All 4 PASS.

If **`test_core_flood_experiment_in_reactor_1_gets_cf01_label` fails** (i.e., backend returns `"R01"` instead of `"CF01"`), there is an actual code bug in `dashboard.py`. Fix as follows:

> Inspect `dashboard.py` lines 143–149. The `hasattr(row.experiment_type, "value")` branch was written for SQLAlchemy enum types but `experiment_type` is `Column(String)`. The string `"Core Flood"` does not have `.value`, so it falls to `str(row.experiment_type)`. Verify this path returns `"Core Flood"` and the comparison on line 148 matches. If the column is returning a Python enum object instead of a string (e.g., due to a SQLAlchemy type coercion), change the column to explicitly use `String` mapping or adjust the comparison.

- [ ] **Step 1.3 — Run the full dashboard test suite**

```bash
pytest tests/api/test_dashboard.py -v --tb=short
```

**Expected:** All tests pass (no regressions).

- [ ] **Step 1.4 — Commit**

```bash
git add tests/api/test_dashboard.py
git commit -m "[#26] add backend tests for CF01/CF02 label derivation

- Tests added: yes
- Docs updated: no"
```

---

## Task 2 — E2E Playwright tests for CF slot acceptance criteria

**Files:**
- Create: `frontend/e2e/journeys/14-dashboard-cf-slots.spec.ts`

This E2E journey creates a real Core Flood experiment via the UI (reactor 1), then navigates to the dashboard to assert CF01 is populated. It also creates an HPHT experiment in reactor 1 (for the regression case, asserting it appears in R01 not CF01). Because these tests create real data, they clean up by cancelling the experiments afterward.

### Step 2.1 — Write the E2E test file

Create `frontend/e2e/journeys/14-dashboard-cf-slots.spec.ts`:

```typescript
/**
 * Journey 14 — Dashboard CF01/CF02 slot mapping (issue #26)
 *
 * Acceptance criteria:
 * - CF01 slot shows an active Core Flood experiment when reactor_number = 1
 * - CF02 slot shows an active Core Flood experiment when reactor_number = 2
 * - HPHT experiment in reactor 1 appears in R01, not CF01
 *
 * Approach:
 * - Create experiments via the UI (New Experiment wizard)
 * - Navigate to /dashboard and assert reactor grid slot contents
 * - Cancel created experiments in afterEach to avoid polluting other journeys
 */
import { test, expect } from '../fixtures/auth'

// Capture created experiment IDs so we can cancel them in afterEach
const createdIds: string[] = []

test.afterEach(async ({ page }) => {
  for (const expId of createdIds.splice(0)) {
    await page.goto(`/experiments/${expId}`)
    await page.waitForLoadState('networkidle')
    // Click the status badge to change to CANCELLED
    const badge = page.locator('button[title="Change status"]').first()
    if (await badge.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await badge.click()
      const cancelBtn = page.getByRole('button', { name: /^CANCELLED$/i })
      await cancelBtn.click()
      await page.waitForTimeout(500)
    }
  }
})

/**
 * Helper: create a new experiment via the wizard and return its assigned ID.
 * Fills only the fields needed to reach the dashboard reactor grid.
 */
async function createExperiment(
  page: Parameters<Parameters<typeof test>[1]>[0]['page'],
  opts: { type: string; reactorNumber: string }
): Promise<string> {
  await page.goto('/experiments/new')

  // Step 1: Basic Info — select experiment type
  await page.getByLabel(/experiment type/i).selectOption(opts.type)

  // Wait for the auto-assigned experiment ID
  const idInput = page.getByLabel(/experiment id/i)
  await expect(idInput).not.toHaveValue(/loading/i, { timeout: 10_000 })
  await expect(idInput).not.toHaveValue('', { timeout: 5_000 })
  const expId = await idInput.inputValue()
  expect(expId).toBeTruthy()

  await page.getByRole('button', { name: /next.*condition/i }).click()

  // Step 2: Conditions — set reactor number
  await page.getByLabel(/reactor number/i).fill(opts.reactorNumber)
  await page.getByRole('button', { name: /next.*additive/i }).click()

  // Step 3: Additives — skip
  await page.getByRole('button', { name: /next.*review/i }).click()

  // Step 4: Review — submit
  await page.getByRole('button', { name: /create experiment/i }).click()
  await expect(page).not.toHaveURL(/\/experiments\/new/, { timeout: 15_000 })

  return expId
}

test('CF01 slot is populated when Core Flood experiment with reactor_number=1 is ONGOING', async ({ page }) => {
  const expId = await createExperiment(page, { type: 'Core Flood', reactorNumber: '1' })
  createdIds.push(expId)

  await page.goto('/dashboard')
  await page.waitForLoadState('networkidle')

  // Find the CF01 label inside the Core Flood grid section
  const cfSection = page.locator('text=Core Flood (CF01–CF02)').locator('../..')
  await expect(cfSection).toBeVisible({ timeout: 10_000 })

  // CF01 card — the label "CF01" appears as a mono-data heading inside the section
  const cf01Label = cfSection.locator('p.font-mono-data').filter({ hasText: /^CF01$/ })
  await expect(cf01Label).toBeVisible({ timeout: 10_000 })

  // The experiment ID should appear in the same card
  const cf01Card = cf01Label.locator('../..')  // up to Card root
  await expect(cf01Card.locator(`text=${expId}`)).toBeVisible({ timeout: 5_000 })

  // The status badge should say ONGOING (not "Empty")
  await expect(cf01Card.locator('text=ONGOING')).toBeVisible()
})

test('HPHT experiment in reactor_number=1 appears in R01, not CF01', async ({ page }) => {
  const expId = await createExperiment(page, { type: 'HPHT', reactorNumber: '1' })
  createdIds.push(expId)

  await page.goto('/dashboard')
  await page.waitForLoadState('networkidle')

  // R01 card should contain the experiment
  const rSection = page.locator('text=Standard Reactors (R01–R16)').locator('../..')
  await expect(rSection).toBeVisible({ timeout: 10_000 })

  const r01Label = rSection.locator('p.font-mono-data').filter({ hasText: /^R01$/ })
  await expect(r01Label).toBeVisible({ timeout: 10_000 })
  const r01Card = r01Label.locator('../..')
  await expect(r01Card.locator(`text=${expId}`)).toBeVisible({ timeout: 5_000 })

  // CF01 must NOT contain this experiment
  const cfSection = page.locator('text=Core Flood (CF01–CF02)').locator('../..')
  const cf01Label = cfSection.locator('p.font-mono-data').filter({ hasText: /^CF01$/ })
  await expect(cf01Label).toBeVisible({ timeout: 5_000 })
  const cf01Card = cf01Label.locator('../..')
  await expect(cf01Card.locator(`text=${expId}`)).not.toBeVisible()
})
```

- [ ] **Step 2.2 — Run E2E tests against the running app**

Ensure the app is running (backend on port 8000, Vite on port 5173). Then:

```bash
cd frontend
npx playwright test e2e/journeys/14-dashboard-cf-slots.spec.ts --headed
```

**Expected:** Both tests pass.

**If `CF01 slot is populated` fails with "CF01 is empty":**
This means the backend returned `reactor_label = "R01"` instead of `"CF01"` for the experiment. This confirms the experiment was stored with `experiment_type = NULL` (a data bug, not a code bug). The backend code is correct. To fix existing experiments:
1. Navigate to `/experiments/<id>`
2. Open the Conditions tab
3. Click "Edit Conditions"
4. Set "Type" to "Core Flood"
5. Save

**If `CF01 slot is populated` fails with "element not found" on `cf01Card.locator(`text=${expId}`)`:**
The locator traversal `../..` may not reach the Card root. Adjust by using `cf01Label.locator('xpath=ancestor::*[contains(@class,"rounded")]').first()` instead.

- [ ] **Step 2.3 — Run the full E2E suite (smoke + journey 14)**

```bash
npx playwright test e2e/journeys/00-smoke.spec.ts e2e/journeys/14-dashboard-cf-slots.spec.ts
```

**Expected:** All pass.

- [ ] **Step 2.4 — Commit**

```bash
git add frontend/e2e/journeys/14-dashboard-cf-slots.spec.ts
git commit -m "[#26] add E2E tests for CF01/CF02 reactor slot mapping

- Tests added: yes
- Docs updated: no"
```

---

## Task 3 — Data investigation note (no code change)

This task is **manual investigation** to find and fix the affected experiment in the database. It produces no committed files.

- [ ] **Step 3.1 — Query the database to find the affected experiment**

Run against the dev/prod PostgreSQL instance:

```sql
SELECT
    e.experiment_id,
    e.status,
    ec.reactor_number,
    ec.experiment_type
FROM experiments e
JOIN experimental_conditions ec ON ec.experiment_fk = e.id
WHERE e.status = 'ONGOING'
  AND ec.reactor_number IN (1, 2)
ORDER BY ec.reactor_number;
```

Any row where `reactor_number = 1` and `experiment_type IS NULL` (or `experiment_type != 'Core Flood'`) is the root-cause record.

- [ ] **Step 3.2 — Fix the data via the UI**

For each affected experiment:
1. Navigate to `/experiments/<experiment_id>`
2. Open the Conditions tab
3. Click "Edit Conditions"
4. Set the "Type" dropdown to "Core Flood"
5. Save

After saving, navigate to `/dashboard` and confirm CF01 now shows the experiment.

- [ ] **Step 3.3 — Confirm the fix**

```sql
SELECT
    e.experiment_id,
    ec.experiment_type,
    ec.reactor_number
FROM experiments e
JOIN experimental_conditions ec ON ec.experiment_fk = e.id
WHERE e.status = 'ONGOING'
  AND ec.reactor_number IN (1, 2);
```

All rows should have `experiment_type = 'Core Flood'` if they're Core Flood reactors.

---

## Task 4 — Complete the issue

- [ ] **Step 4.1 — Run the full backend test suite**

```bash
pytest tests/api/ -v --tb=short 2>&1 | tail -30
```

**Expected:** All pass.

- [ ] **Step 4.2 — Run the verification skill**

Use `superpowers:verification-before-completion` before closing the issue.

- [ ] **Step 4.3 — Run `/complete-task`**

---

## Self-review against acceptance criteria

| Acceptance criterion | Covered by |
|---------------------|-----------|
| CF01 shows active Core Flood in reactor 1 | Task 1 test 1 (backend) + Task 2 test 1 (E2E) |
| CF02 correct for reactor_number=2 | Task 1 test 2 (backend) |
| Non-Core Flood in reactors 1/2 not mapped to CF slots | Task 1 test 3 (HPHT) + Task 2 test 2 (E2E) |
| `reactor_label = "CF01"` in API response | Task 1 test 1 asserts this directly |
| E2E: seed ONGOING Core Flood in reactor 1, assert CF01 populated | Task 2 test 1 |
| E2E regression: HPHT in reactor 1 → R01 not CF01 | Task 2 test 2 |
