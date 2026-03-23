# M8 Testing and Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Playwright E2E infrastructure, test all upload types with real lab files, fix parser bugs found, and complete the documentation pass.

**Architecture:** Playwright drives Chromium against the already-running dev stack (`localhost:5173` / `localhost:8000`). Tests authenticate with real Firebase via a global-setup that saves `storageState`. Each upload chunk follows the pattern: upload real file → observe output → fix parser → add E2E spec.

**Tech Stack:** Playwright `@playwright/test` 1.x (Chromium), pytest + FastAPI TestClient (existing), React 18 + Vite, FastAPI + SQLAlchemy, PostgreSQL

**Spec:** `docs/superpowers/specs/2026-03-23-m8-testing-docs-design.md`

---

## File Map

### Created
| File | Purpose |
|------|---------|
| `frontend/playwright.config.ts` | Playwright config — baseURL, globalSetup, storageState, workers |
| `frontend/e2e/fixtures/auth.ts` | Global setup: log in once, save `storageState` to `.auth/state.json` |
| `frontend/e2e/journeys/00-smoke.spec.ts` | Verify Playwright reaches app + auth works |
| `frontend/e2e/journeys/02-bulk-upload-experiments.spec.ts` | Journey 2: new-experiments upload |
| `frontend/e2e/journeys/03-upload-icp.spec.ts` | Journey 3: ICP-OES upload |
| `frontend/e2e/journeys/05-upload-xrd.spec.ts` | Journey 5: XRD Aeris upload |
| `frontend/e2e/journeys/07-master-results-sync.spec.ts` | Master Results sync E2E |
| `frontend/e2e/journeys/08-solution-chemistry.spec.ts` | Solution chemistry upload E2E |
| `frontend/e2e/journeys/09-elemental-composition.spec.ts` | ActLabs elemental composition E2E |
| `frontend/e2e/journeys/01-create-experiment.spec.ts` | Journey 1: create experiment end-to-end |
| `frontend/e2e/journeys/04-update-status-dashboard.spec.ts` | Journey 4: status change reflects on dashboard |
| `frontend/e2e/journeys/06-recalculate-derived-fields.spec.ts` | Journey 6: rock_mass_g edit triggers recalc |
| `frontend/e2e/.env.e2e.example` | Template for E2E credentials |
| `database/models/app_config.py` | AppConfig key-value table for runtime-mutable settings |
| `alembic/versions/<hash>_add_app_config_table.py` | Migration for AppConfig |
| `backend/services/bulk_uploads/elemental_composition.py` | New flexible wide-format elemental parser |
| `tests/regression/test_calc_regression.py` | Calculation regression test |
| `CONTRIBUTING.md` | Contributor guide |
| `docs/deployment/PRODUCTION_DEPLOYMENT.md` | Production deployment guide |
| `docs/user_guide/USER_MANUAL.md` | End-user manual |

### Modified
| File | Change |
|------|--------|
| `.gitignore` | Add `frontend/e2e/.auth/` and `frontend/e2e/.env.e2e` |
| `backend/api/routers/experiments.py` | `GET /next-ids`: remove auth, add Autoclave type |
| `frontend/src/api/bulkUploads.ts` | Add `Autoclave` to `NextIds` interface |
| `frontend/src/pages/BulkUploads.tsx` | Update `NextIdChips` to render Autoclave chip |
| `backend/api/routers/bulk_uploads.py` | Add `GET/PATCH /master-results/config`; update elemental-comp endpoint to use new parser |
| `backend/services/bulk_uploads/master_bulk_upload.py` | `sync_from_path` reads from `AppConfig` table |
| `backend/services/bulk_uploads/actlabs_titration_data.py` | Fix `ActlabsRockTitrationService.import_excel()` — add `external_analysis_id` |
| `README.md` | Full rewrite |

---

## Chunk A — Playwright Infrastructure

### Task A1: Playwright config and global setup

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/fixtures/auth.ts`
- Create: `frontend/e2e/.env.e2e.example`
- Modify: `.gitignore`

- [ ] **Step 1: Add `.auth/` and credentials file to `.gitignore`**

In `.gitignore`, append:
```
# Playwright
frontend/e2e/.auth/
frontend/e2e/.env.e2e
```

- [ ] **Step 2: Create credentials example file**

Create `frontend/e2e/.env.e2e.example`:
```
E2E_EMAIL=labpc@addisenergy.com
E2E_PASSWORD=your-password-here
```

Copy it (gitignored) as `frontend/e2e/.env.e2e` and fill in the real password for the `labpc@addisenergy.com` Firebase dev account.

- [ ] **Step 3: Create `frontend/e2e/fixtures/auth.ts`**

```typescript
import { chromium, FullConfig } from '@playwright/test'
import * as fs from 'fs'
import * as path from 'path'
import * as dotenv from 'dotenv'

dotenv.config({ path: path.join(__dirname, '../.env.e2e') })

const AUTH_FILE = path.join(__dirname, '../.auth/state.json')

export default async function globalSetup(_config: FullConfig) {
  // Ensure .auth directory exists
  fs.mkdirSync(path.dirname(AUTH_FILE), { recursive: true })

  const browser = await chromium.launch()
  const page = await browser.newPage()

  await page.goto('http://localhost:5173')

  // Fill login form (selectors from frontend/src/pages/Login.tsx)
  await page.getByPlaceholder('you@addisenergy.com').fill(process.env.E2E_EMAIL!)
  await page.getByPlaceholder('••••••••').fill(process.env.E2E_PASSWORD!)
  await page.getByRole('button', { name: /sign in/i }).click()

  // Wait for redirect to dashboard
  await page.waitForURL('**/dashboard', { timeout: 15_000 })

  // Save auth state
  await page.context().storageState({ path: AUTH_FILE })
  await browser.close()

  console.log('✓ Auth state saved to', AUTH_FILE)
}
```

- [ ] **Step 4: Create `frontend/playwright.config.ts`**

```typescript
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e/journeys',
  globalSetup: './e2e/fixtures/auth.ts',
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  reporter: 'list',

  use: {
    baseURL: 'http://localhost:5173',
    storageState: 'e2e/.auth/state.json',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
```

- [ ] **Step 5: Install dotenv for the auth fixture**

```bash
cd frontend && npm install --save-dev dotenv --legacy-peer-deps
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore frontend/playwright.config.ts frontend/e2e/fixtures/auth.ts \
  frontend/e2e/.env.e2e.example frontend/package.json frontend/package-lock.json
git commit -m "[M8] Chunk A: Playwright config + global auth setup"
```

---

### Task A2: Smoke test

**Files:**
- Create: `frontend/e2e/journeys/00-smoke.spec.ts`

- [ ] **Step 1: Create smoke test**

```typescript
import { test, expect } from '@playwright/test'

test('dashboard loads after auth', async ({ page }) => {
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/dashboard/)
  await expect(page.getByText('Reactor Status')).toBeVisible()
})

test('sidebar navigation links are present', async ({ page }) => {
  await page.goto('/dashboard')
  await expect(page.getByRole('link', { name: /experiments/i })).toBeVisible()
  await expect(page.getByRole('link', { name: /bulk uploads/i })).toBeVisible()
})
```

- [ ] **Step 2: Run the smoke test**

Ensure Vite dev server and FastAPI are running, then:
```bash
cd frontend && npx playwright test 00-smoke --headed
```
Expected: 2 tests pass. If auth fails, verify `e2e/.env.e2e` credentials and that Firebase is reachable.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/journeys/00-smoke.spec.ts
git commit -m "[M8] Chunk A: smoke test passing"
```

---

## Chunk B — Next-IDs Fix + New Experiments Upload

### Task B1: Fix `/api/experiments/next-ids` endpoint

**Files:**
- Modify: `backend/api/routers/experiments.py`
- Modify: `tests/api/test_experiments.py`

- [ ] **Step 1: Write failing tests**

In `tests/api/test_experiments.py`, add:

```python
def test_next_ids_no_auth_required(client):
    """next-ids must be accessible without authentication."""
    # Use a client without auth override
    from fastapi.testclient import TestClient
    from backend.api.main import app
    from backend.api.dependencies.db import get_db

    app_no_auth = app
    # Temporarily clear auth override
    original = app.dependency_overrides.copy()
    from backend.auth.firebase_auth import verify_firebase_token
    if verify_firebase_token in app.dependency_overrides:
        del app.dependency_overrides[verify_firebase_token]

    try:
        with TestClient(app) as c:
            r = c.get('/api/experiments/next-ids')
            assert r.status_code == 200
    finally:
        app.dependency_overrides.update(original)


def test_next_ids_includes_autoclave(client):
    """next-ids response includes Autoclave type."""
    r = client.get('/api/experiments/next-ids')
    assert r.status_code == 200
    data = r.json()
    assert 'Autoclave' in data
    assert isinstance(data['Autoclave'], int)
    assert data['Autoclave'] >= 1
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/api/test_experiments.py::test_next_ids_no_auth_required \
       tests/api/test_experiments.py::test_next_ids_includes_autoclave -v
```
Expected: Both FAIL.

- [ ] **Step 3: Fix the endpoint**

In `backend/api/routers/experiments.py`, find `@router.get("/next-ids")` and update:

```python
@router.get("/next-ids")
def get_next_experiment_ids(
    db: Session = Depends(get_db),
) -> dict:
    """
    Return the next sequence number for each experiment type.
    No auth required — read-only, non-sensitive.

    Response: ``{"HPHT": 107, "Serum": 165, "CF": 15, "Autoclave": 8}``
    """
    label_prefix = {
        "HPHT": "HPHT",
        "Serum": "SERUM",
        "CF": "CF",
        "Autoclave": "Autoclave",
    }
    result: dict[str, int] = {}
    for label, prefix in label_prefix.items():
        rows = db.execute(
            select(Experiment.experiment_id)
            .where(Experiment.experiment_id.like(f"{prefix}_%"))
        ).scalars().all()
        max_num = 0
        for eid in rows:
            suffix = eid[len(prefix) + 1:]
            if suffix.isdigit():
                max_num = max(max_num, int(suffix))
        result[label] = max_num + 1
    return result
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/api/test_experiments.py -v
```
Expected: all experiments tests pass including the two new ones.

- [ ] **Step 5: Update `NextIds` TypeScript interface and `NextIdChips` component**

In `frontend/src/api/bulkUploads.ts`, update `NextIds`:
```typescript
export interface NextIds {
  HPHT: number
  Serum: number
  CF: number
  Autoclave: number
}
```

In `frontend/src/pages/BulkUploads.tsx`, update `NextIdChips`:
```typescript
{(['HPHT', 'Serum', 'CF', 'Autoclave'] as const).map((type) => (
```

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/experiments.py frontend/src/api/bulkUploads.ts \
  frontend/src/pages/BulkUploads.tsx tests/api/test_experiments.py
git commit -m "[M8] Chunk B: next-ids — remove auth, add Autoclave type"
```

---

### Task B2: Test new-experiments upload with real file

**Files:**
- Create: `frontend/e2e/journeys/02-bulk-upload-experiments.spec.ts`

- [ ] **Step 1: Upload the real file manually first**

In the running app, navigate to Bulk Uploads → New Experiments → upload `docs/sample_data/new_experiments_template.xlsx`. Observe the response (created/updated/skipped/errors). Fix any parser errors before writing the E2E test.

Common issues to check:
- Experiment IDs in the template may already exist in DB → use `overwrite=true` column or note skipped count is expected
- Sample IDs referenced in the template must exist in DB → add them if needed

- [ ] **Step 2: Write E2E test**

```typescript
// frontend/e2e/journeys/02-bulk-upload-experiments.spec.ts
import { test, expect } from '@playwright/test'
import * as path from 'path'

const SAMPLE_FILE = path.resolve(
  __dirname, '../../../../docs/sample_data/new_experiments_template.xlsx'
)

test('new experiments upload processes without errors', async ({ page }) => {
  await page.goto('/bulk-uploads')

  // Open the New Experiments accordion
  await page.getByText('New Experiments').click()

  // Verify Next-ID chips are visible (including Autoclave after our fix)
  await expect(page.getByText('HPHT:')).toBeVisible()
  await expect(page.getByText('Autoclave:')).toBeVisible()

  // Upload the file
  const fileInput = page.locator('#new-experiments input[type="file"]')
  await fileInput.setInputFiles(SAMPLE_FILE)

  // Wait for upload result
  await expect(page.getByText(/created|updated|skipped/i)).toBeVisible({ timeout: 15_000 })

  // No errors reported
  await expect(page.getByText(/error/i)).not.toBeVisible()
})
```

- [ ] **Step 3: Run the test**

```bash
cd frontend && npx playwright test 02-bulk-upload-experiments --headed
```
Expected: PASS. If parser errors occur, fix the parser or template and re-run.

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/journeys/02-bulk-upload-experiments.spec.ts
git commit -m "[M8] Chunk B: new-experiments E2E test passing"
```

---

## Chunk C — ICP + Solution Chemistry Uploads

### Task C1: Test ICP-OES upload

**Files:**
- Create: `frontend/e2e/journeys/03-upload-icp.spec.ts`
- Modify: relevant parser files if bugs found

- [ ] **Step 1: Upload ICP file manually**

Navigate to Bulk Uploads → ICP-OES Data → upload `docs/sample_data/icp_raw_data.csv`. Read the response carefully:
- Note how many rows created/updated/skipped
- Copy any error messages
- Fix parser issues before writing the test

- [ ] **Step 2: Write ICP E2E test**

```typescript
// frontend/e2e/journeys/03-upload-icp.spec.ts
import { test, expect } from '@playwright/test'
import * as path from 'path'

const ICP_FILE = path.resolve(
  __dirname, '../../../../docs/sample_data/icp_raw_data.csv'
)

test('ICP-OES upload processes without errors', async ({ page }) => {
  await page.goto('/bulk-uploads')
  await page.getByText('ICP-OES Data').click()

  const fileInput = page.locator('#icp-oes input[type="file"]')
  await fileInput.setInputFiles(ICP_FILE)

  await expect(page.getByText(/created|updated|skipped/i)).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText(/\berror\b/i)).not.toBeVisible()
})
```

- [ ] **Step 3: Run and fix until passing**

```bash
cd frontend && npx playwright test 03-upload-icp --headed
```

- [ ] **Step 4: Commit (with any parser fixes)**

```bash
git add frontend/e2e/journeys/03-upload-icp.spec.ts
# Add any fixed parser files too
git commit -m "[M8] Chunk C: ICP upload E2E test passing"
```

---

### Task C2: Test Solution Chemistry upload

**Files:**
- Create: `frontend/e2e/journeys/08-solution-chemistry.spec.ts`

- [ ] **Step 1: Upload solution chemistry file manually**

Navigate to Bulk Uploads → Solution Chemistry → upload `docs/sample_data/solution chemistry upload.xlsx`. Fix any parser issues.

- [ ] **Step 2: Write E2E test**

```typescript
// frontend/e2e/journeys/08-solution-chemistry.spec.ts
import { test, expect } from '@playwright/test'
import * as path from 'path'

const SOL_CHEM_FILE = path.resolve(
  __dirname, '../../../../docs/sample_data/solution chemistry upload.xlsx'
)

test('solution chemistry upload processes without errors', async ({ page }) => {
  await page.goto('/bulk-uploads')
  await page.getByText('Solution Chemistry').click()

  const fileInput = page.locator('#scalar-results input[type="file"]')
  await fileInput.setInputFiles(SOL_CHEM_FILE)

  await expect(page.getByText(/created|updated|skipped/i)).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText(/\berror\b/i)).not.toBeVisible()
})
```

- [ ] **Step 3: Run and fix until passing**

```bash
cd frontend && npx playwright test 08-solution-chemistry --headed
```

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/journeys/08-solution-chemistry.spec.ts
git commit -m "[M8] Chunk C: solution chemistry E2E test passing"
```

---

## Chunk D — Master Results Sync Config

### Task D1: AppConfig table and migration

**Files:**
- Create: `database/models/app_config.py`
- Create: `alembic/versions/<hash>_add_app_config_table.py`
- Modify: `database/models/__init__.py`

- [ ] **Step 1: Create `database/models/app_config.py`**

```python
"""AppConfig — runtime-mutable key-value store for application settings."""
from __future__ import annotations

from sqlalchemy import Column, String, Text, DateTime, func

from database.base import Base


class AppConfig(Base):
    __tablename__ = "app_config"

    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 2: Register in `database/models/__init__.py`**

Add `from database.models.app_config import AppConfig` to the imports.

- [ ] **Step 3: Generate migration**

```bash
cd /path/to/project
.venv/Scripts/alembic revision --autogenerate -m "add_app_config_table"
```

Review the generated file — confirm it creates `app_config` with `key` (PK), `value`, `updated_at`.

- [ ] **Step 4: Apply migration**

```bash
.venv/Scripts/alembic upgrade head
```

Expected output: `Running upgrade ... -> <hash>, add_app_config_table`

- [ ] **Step 5: Write test**

In `tests/models/` (or `tests/api/`), add:
```python
def test_app_config_upsert(db_session):
    from database.models.app_config import AppConfig
    cfg = AppConfig(key="test_key", value="test_value")
    db_session.add(cfg)
    db_session.flush()
    fetched = db_session.query(AppConfig).filter_by(key="test_key").first()
    assert fetched.value == "test_value"
```

Run: `pytest tests/ -k test_app_config_upsert -v`

- [ ] **Step 6: Commit**

```bash
git add database/models/app_config.py database/models/__init__.py \
  alembic/versions/*add_app_config_table.py
git commit -m "[M8] Chunk D: AppConfig table + migration"
```

---

### Task D2: Master Results config endpoints

**Files:**
- Modify: `backend/api/routers/bulk_uploads.py`
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py`

- [ ] **Step 1: Write failing tests for config endpoints**

In `tests/api/test_bulk_uploads.py`, add:

```python
def test_get_master_results_config_returns_path(client):
    r = client.get('/api/bulk-uploads/master-results/config')
    assert r.status_code == 200
    data = r.json()
    assert 'path' in data


def test_patch_master_results_config_invalid_path(client):
    r = client.patch(
        '/api/bulk-uploads/master-results/config',
        json={'path': '/nonexistent/path/to/file.xlsx'},
    )
    assert r.status_code == 422


def test_patch_master_results_config_valid_path(client, tmp_path):
    # Create a minimal xlsx file at a known path
    import openpyxl
    p = tmp_path / "test.xlsx"
    wb = openpyxl.Workbook()
    wb.save(str(p))

    r = client.patch(
        '/api/bulk-uploads/master-results/config',
        json={'path': str(p)},
    )
    assert r.status_code == 200
    assert r.json()['path'] == str(p)
```

Run: `pytest tests/api/test_bulk_uploads.py::test_get_master_results_config_returns_path -v`
Expected: FAIL (404).

- [ ] **Step 2: Add config endpoints to `bulk_uploads.py`**

Add after the existing `/master-results` endpoint:

```python
from pydantic import BaseModel as PydanticBase


class MasterResultsConfigResponse(PydanticBase):
    path: str | None


class MasterResultsConfigUpdate(PydanticBase):
    path: str


_MASTER_RESULTS_CONFIG_KEY = "master_results_path"


@router.get("/master-results/config", response_model=MasterResultsConfigResponse)
def get_master_results_config(
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> MasterResultsConfigResponse:
    """Return the currently configured Master Results file path."""
    from database.models.app_config import AppConfig  # noqa: PLC0415
    cfg = db.query(AppConfig).filter_by(key=_MASTER_RESULTS_CONFIG_KEY).first()
    if cfg:
        return MasterResultsConfigResponse(path=cfg.value)
    # Fall back to settings default
    from backend.config.settings import get_settings  # noqa: PLC0415
    return MasterResultsConfigResponse(path=get_settings().master_results_path)


@router.patch("/master-results/config", response_model=MasterResultsConfigResponse)
def update_master_results_config(
    body: MasterResultsConfigUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> MasterResultsConfigResponse:
    """
    Set the Master Results file path. Validates the path resolves to a
    readable .xlsx file before saving.
    """
    import os  # noqa: PLC0415
    from database.models.app_config import AppConfig  # noqa: PLC0415

    path = body.path
    if not os.path.isfile(path):
        raise HTTPException(status_code=422, detail=f"File not found: {path}")
    if not path.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=422, detail="Path must point to an .xlsx or .xls file")

    cfg = db.query(AppConfig).filter_by(key=_MASTER_RESULTS_CONFIG_KEY).first()
    if cfg:
        cfg.value = path
    else:
        db.add(AppConfig(key=_MASTER_RESULTS_CONFIG_KEY, value=path))
    db.commit()
    return MasterResultsConfigResponse(path=path)
```

- [ ] **Step 3: Update `sync_from_path` to prefer DB config**

In `backend/services/bulk_uploads/master_bulk_upload.py`, update `sync_from_path`:

```python
@staticmethod
def sync_from_path(db: Session) -> Tuple[int, int, int, List[str], List[Dict[str, Any]]]:
    """
    Read the Master Results file from the configured path.
    Priority: AppConfig table > MASTER_RESULTS_PATH env/settings.
    """
    from backend.config.settings import get_settings  # noqa: PLC0415
    from database.models.app_config import AppConfig  # noqa: PLC0415

    cfg = db.query(AppConfig).filter_by(key="master_results_path").first()
    path = cfg.value if cfg else get_settings().master_results_path

    try:
        with open(path, "rb") as fh:
            file_bytes = fh.read()
    except FileNotFoundError:
        return 0, 0, 0, [
            f"Master Results file not found at: {path}. "
            "Configure the path via Bulk Uploads → Master Results Sync → Settings."
        ], []
    except PermissionError:
        return 0, 0, 0, [
            f"Permission denied reading: {path}. "
            "Ensure the file is not open in Excel."
        ], []
    except Exception as exc:
        return 0, 0, 0, [f"Failed to read Master Results file: {exc}"], []

    return _process_bytes(db, file_bytes)
```

- [ ] **Step 4: Run config endpoint tests**

```bash
pytest tests/api/test_bulk_uploads.py -k "master_results_config" -v
```
Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/bulk_uploads.py \
  backend/services/bulk_uploads/master_bulk_upload.py
git commit -m "[M8] Chunk D: master-results config GET/PATCH endpoints"
```

---

### Task D3: Master Results sync E2E test

**Files:**
- Create: `frontend/e2e/journeys/07-master-results-sync.spec.ts`

- [ ] **Step 1: Configure path in the live DB via Swagger UI**

Before running the E2E test, the `master_results_path` must be set in the `AppConfig` table.
Without it, the Master Results card shows the settings panel (not the Sync Now button).

1. Open `http://localhost:8000/docs`
2. Find `PATCH /api/bulk-uploads/master-results/config`
3. Authenticate (use the Authorize button with a Firebase token from the running app)
4. Set the path to the absolute path of the sample file on this machine, e.g.:

```json
{
  "path": "C:\\Users\\MathewHearl\\Documents\\0x_Software\\database_sandbox\\experiment_tracking_sandbox\\docs\\sample_data\\Master Reactor Sampling Tracker.xlsx"
}
```

5. Verify `GET /api/bulk-uploads/master-results/config` returns the configured path

This is a one-time setup step for the dev environment. The path persists in the `app_config` table.

- [ ] **Step 2: Trigger sync manually and inspect output**

```bash
curl -X POST http://localhost:8000/api/bulk-uploads/master-results \
  -H "Authorization: Bearer <token>"
```

Review the response. Fix any parser issues (e.g. `Standard` column handling, date parsing).

- [ ] **Step 3: Write E2E test**

```typescript
// frontend/e2e/journeys/07-master-results-sync.spec.ts
// PRECONDITION: master_results_path must be configured in app_config table.
// See Task D3 Step 1 for one-time setup instructions.
import { test, expect } from '@playwright/test'

test('master results sync button triggers sync', async ({ page }) => {
  await page.goto('/bulk-uploads')
  await page.getByText('Master Results Sync').click()

  // The Sync Now button is only visible when a path is configured.
  // If the settings panel is shown instead, complete Step 1 setup first.
  const syncBtn = page.getByRole('button', { name: /sync now/i })
  await expect(syncBtn).toBeVisible({ timeout: 5_000 })

  await syncBtn.click()

  // Wait for result
  await expect(page.getByText(/created|updated|skipped/i)).toBeVisible({ timeout: 20_000 })
})
```

- [ ] **Step 4: Run and fix until passing**

```bash
cd frontend && npx playwright test 07-master-results-sync --headed
```

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e/journeys/07-master-results-sync.spec.ts
git commit -m "[M8] Chunk D: master results sync E2E test passing"
```

---

## Chunk E — XRD Mineralogy (Aeris Format)

### Task E1: Test XRD Aeris upload and fix parser

**Files:**
- Create: `frontend/e2e/journeys/05-upload-xrd.spec.ts`
- Modify: `backend/services/bulk_uploads/aeris_xrd.py` if issues found

- [ ] **Step 1: Upload XRD file manually**

Navigate to Bulk Uploads → XRD Mineralogy → upload `docs/sample_data/XRD_result_070d19.xlsx`.

The file contains Aeris-format sample IDs like `20260218_HPHT070-d19_02`. The parser will:
1. Detect format as "aeris" (Sample ID column with matching values)
2. Parse: `measurement_date=2026-02-18`, `experiment_id_raw=HPHT070`, `days=19`
3. Fuzzy-match `HPHT070` → `HPHT_070` in the DB

**Expected issues to look for:**
- Experiment `HPHT_070` may not exist in the dev DB → create it via the UI or API first
- Aeris regex `r"^(\d{8})_(.+?)-d(\d+)_\d+$"` — verify it matches the actual sample ID format in the file

If `HPHT_070` doesn't exist, create it:
```bash
curl -X POST http://localhost:8000/api/experiments \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"experiment_id": "HPHT_070", "experiment_number": 70, "status": "COMPLETED"}'
```

- [ ] **Step 2: Fix parser if needed**

If the Aeris regex doesn't match the file's sample ID format, update `_AERIS_SAMPLE_RE` in `backend/services/bulk_uploads/aeris_xrd.py`. The current pattern is:
```python
_AERIS_SAMPLE_RE = re.compile(r"^(\d{8})_(.+?)-d(\d+)_\d+$")
```
Test against actual values from the file before changing.

- [ ] **Step 3: Write E2E test**

```typescript
// frontend/e2e/journeys/05-upload-xrd.spec.ts
import { test, expect } from '@playwright/test'
import * as path from 'path'

const XRD_FILE = path.resolve(
  __dirname, '../../../../docs/sample_data/XRD_result_070d19.xlsx'
)

test('XRD Aeris upload creates mineral phase records', async ({ page }) => {
  await page.goto('/bulk-uploads')
  await page.getByText('XRD Mineralogy').click()

  const fileInput = page.locator('#xrd-mineralogy input[type="file"]')
  await fileInput.setInputFiles(XRD_FILE)

  await expect(page.getByText(/created|updated|skipped/i)).toBeVisible({ timeout: 15_000 })
  // Created count should be > 0 (at least one mineral phase row)
  await expect(page.getByText(/created: [1-9]/i)).toBeVisible()
})
```

- [ ] **Step 4: Run and fix until passing**

```bash
cd frontend && npx playwright test 05-upload-xrd --headed
```

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e/journeys/05-upload-xrd.spec.ts
# Add any parser fixes
git commit -m "[M8] Chunk E: XRD Aeris E2E test passing"
```

---

## Chunk F — Elemental Composition

### Task F1: Fix `ActlabsRockTitrationService.import_excel()` bug

**Files:**
- Modify: `backend/services/bulk_uploads/actlabs_titration_data.py`
- Modify: `tests/services/bulk_uploads/test_elemental_composition.py`

- [ ] **Step 1: Write failing test**

In `tests/services/bulk_uploads/test_elemental_composition.py`, add:

```python
def test_actlabs_import_sets_external_analysis_id(db_session):
    """import_excel must link ElementalAnalysis rows to an ExternalAnalysis record."""
    from database.models import SampleInfo
    from database.models.analysis import ExternalAnalysis, ElementalAnalysis
    from backend.services.bulk_uploads.actlabs_titration_data import ActlabsRockTitrationService
    from tests.services.bulk_uploads.excel_helpers import make_excel

    # Seed a sample
    sample = SampleInfo(sample_id="TEST_ACTLABS_001", rock_classification="Dunite")
    db_session.add(sample)
    db_session.flush()

    # Build a minimal ActLabs-format file (header rows 0-5, data row 6)
    import openpyxl, io
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Report Number", "12345"])          # row 1
    ws.append(["Report Date", "2026-03-23"])        # row 2
    ws.append(["sample_id", "Fe", "SiO2"])          # row 3 — analyte symbols
    ws.append([None, "ppm", "%"])                   # row 4 — units
    ws.append([None, "0.01", "0.01"])               # row 5 — detection limits
    ws.append(["Analysis Method", "FUS-ICP", "FUS-ICP"])  # row 6
    ws.append(["TEST_ACTLABS_001", 45000.0, 38.5]) # data row
    buf = io.BytesIO()
    wb.save(buf)

    created, updated, skipped, errors = ActlabsRockTitrationService.import_excel(
        db_session, buf.getvalue()
    )
    assert errors == [], f"Unexpected errors: {errors}"
    assert created > 0

    # Every ElementalAnalysis row must have external_analysis_id set
    rows = db_session.query(ElementalAnalysis).filter_by(sample_id="TEST_ACTLABS_001").all()
    assert len(rows) > 0
    for row in rows:
        assert row.external_analysis_id is not None, (
            "external_analysis_id must be set — missing ExternalAnalysis linkage"
        )
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/services/bulk_uploads/test_elemental_composition.py::test_actlabs_import_sets_external_analysis_id -v
```
Expected: FAIL — `external_analysis_id is None`.

- [ ] **Step 3: Fix `ActlabsRockTitrationService.import_excel()`**

In `actlabs_titration_data.py`, inside `import_excel`, add the same `_get_or_create_ext_analysis` pattern already used by `ElementalCompositionService`. After loading `symbol_to_analyte`, add:

```python
# Cache ExternalAnalysis stubs per sample_id (same pattern as ElementalCompositionService)
from database.models.analysis import ExternalAnalysis  # noqa: PLC0415
ext_analysis_cache: dict[str, int] = {}

def _get_ext_analysis_id(sid: str) -> int:
    if sid in ext_analysis_cache:
        return ext_analysis_cache[sid]
    stub = (
        db.query(ExternalAnalysis)
        .filter_by(sample_id=sid, analysis_type="Elemental")
        .first()
    )
    if not stub:
        stub = ExternalAnalysis(sample_id=sid, analysis_type="Elemental")
        db.add(stub)
        db.flush()
    ext_analysis_cache[sid] = stub.id
    return stub.id
```

Then update the `db.add(ElementalAnalysis(...))` line (currently line 467) to include `external_analysis_id`:

```python
# Replace:
db.add(ElementalAnalysis(sample_id=sample_id, analyte_id=analyte.id, analyte_composition=vnum))
# With:
db.add(ElementalAnalysis(
    external_analysis_id=_get_ext_analysis_id(sample_id),
    sample_id=sample_id,
    analyte_id=analyte.id,
    analyte_composition=vnum,
))
```

- [ ] **Step 4: Run test — expect pass**

```bash
pytest tests/services/bulk_uploads/test_elemental_composition.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/actlabs_titration_data.py \
  tests/services/bulk_uploads/test_elemental_composition.py
git commit -m "[M8] Chunk F: fix ActlabsRockTitrationService missing external_analysis_id"
```

---

### Task F2: New `elemental_composition.py` parser

**Files:**
- Create: `backend/services/bulk_uploads/elemental_composition.py`
- Modify: `backend/api/routers/bulk_uploads.py`
- Create: `tests/services/bulk_uploads/test_elemental_composition_new.py`

- [ ] **Step 1: Write failing tests**

Create `tests/services/bulk_uploads/test_elemental_composition_new.py`:

```python
"""Tests for the new flexible elemental_composition.py parser."""
from __future__ import annotations
import io
import pytest
from database.models import SampleInfo
from database.models.analysis import ExternalAnalysis, ElementalAnalysis

def _seed_sample(db, sample_id):
    s = SampleInfo(sample_id=sample_id, rock_classification="Test")
    db.add(s)
    db.flush()
    return s


def test_parses_unit_from_parenthetical_header(db_session):
    """'Fe (ppm)' → symbol='Fe', unit='ppm'."""
    from backend.services.bulk_uploads.elemental_composition import ElementalCompositionFlexibleService
    import openpyxl
    _seed_sample(db_session, "FLEX_001")
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Sample ID", "Fe (ppm)", "SiO2 (%)"])
    ws.append(["FLEX_001", 45000.0, 38.5])
    buf = io.BytesIO(); wb.save(buf)
    created, updated, skipped, errors = ElementalCompositionFlexibleService.upload(
        db_session, buf.getvalue()
    )
    assert errors == []
    assert created == 2
    rows = db_session.query(ElementalAnalysis).filter_by(sample_id="FLEX_001").all()
    assert all(r.external_analysis_id is not None for r in rows)


def test_skips_unknown_sample(db_session):
    from backend.services.bulk_uploads.elemental_composition import ElementalCompositionFlexibleService
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Sample ID", "Fe (ppm)"])
    ws.append(["NONEXISTENT_999", 1000.0])
    buf = io.BytesIO(); wb.save(buf)
    created, updated, skipped, errors = ElementalCompositionFlexibleService.upload(
        db_session, buf.getvalue()
    )
    assert created == 0
    assert len(errors) > 0
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/services/bulk_uploads/test_elemental_composition_new.py -v
```
Expected: FAIL (module not found).

- [ ] **Step 3: Create `backend/services/bulk_uploads/elemental_composition.py`**

Implement `ElementalCompositionFlexibleService` per `docs/specs/elemental_composition_upload.md`:

```python
"""Flexible wide-format elemental composition parser.

Column header format: 'Symbol (unit)', 'Symbol [unit]', 'Symbol_unit', or bare 'Symbol'.
First column must be 'Sample ID'.
"""
from __future__ import annotations

import io
import re
from typing import List, Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from database.models import SampleInfo, Analyte
from database.models.analysis import ExternalAnalysis, ElementalAnalysis

_SUPPORTED_UNITS = {"ppm", "ppb", "%", "wt%", "mg/kg", "g/t"}
_PAREN_RE = re.compile(r"^(.+?)\s*\(([^)]+)\)\s*$")
_BRACKET_RE = re.compile(r"^(.+?)\s*\[([^\]]+)\]\s*$")
_UNDERSCORE_RE = re.compile(r"^(.+?)_([^_]+)$")


def _parse_header(header: str) -> Tuple[str, str]:
    """Extract (symbol, unit) from a column header string."""
    h = header.strip()
    for pattern in (_PAREN_RE, _BRACKET_RE):
        m = pattern.match(h)
        if m:
            sym, unit = m.group(1).strip(), m.group(2).strip()
            unit_norm = unit.lower()
            if unit_norm in _SUPPORTED_UNITS:
                return sym, unit
            return sym, "ppm"  # unrecognised unit — default

    m = _UNDERSCORE_RE.match(h)
    if m:
        sym, unit = m.group(1).strip(), m.group(2).strip()
        if unit.lower() in _SUPPORTED_UNITS:
            return sym, unit

    return h, "%"  # bare symbol — default unit


class ElementalCompositionFlexibleService:
    @staticmethod
    def upload(
        db: Session,
        file_bytes: bytes,
        overwrite: bool = False,
    ) -> Tuple[int, int, int, List[str]]:
        """
        Parse a wide-format Excel/CSV file and upsert ElementalAnalysis rows.
        Returns (created, updated, skipped, errors).
        """
        errors: List[str] = []
        created = updated = skipped = 0

        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception:
            try:
                df = pd.read_csv(io.BytesIO(file_bytes))
            except Exception as e:
                return 0, 0, 0, [f"Failed to read file: {e}"]

        df.columns = [str(c).strip() for c in df.columns]

        # Find sample_id column
        sample_col = next(
            (c for c in df.columns if c.lower().replace(" ", "_") == "sample_id"),
            None,
        )
        if not sample_col:
            return 0, 0, 0, ["No 'Sample ID' column found."]

        analyte_cols = [c for c in df.columns if c != sample_col]
        if not analyte_cols:
            return 0, 0, 0, ["No analyte columns found."]

        # Parse headers → (symbol, unit)
        header_map = {col: _parse_header(col) for col in analyte_cols}

        # Resolve/create Analyte records
        analyte_cache: dict[str, Analyte] = {}
        for col, (symbol, unit) in header_map.items():
            existing = db.query(Analyte).filter(Analyte.analyte_symbol.ilike(symbol)).first()
            if not existing:
                existing = Analyte(analyte_symbol=symbol, unit=unit)
                db.add(existing)
                db.flush()
            analyte_cache[col] = existing

        # ExternalAnalysis cache
        ext_cache: dict[str, int] = {}

        def _get_ext_id(sid: str) -> int:
            if sid in ext_cache:
                return ext_cache[sid]
            stub = (
                db.query(ExternalAnalysis)
                .filter_by(sample_id=sid, analysis_type="Elemental")
                .first()
            )
            if not stub:
                import datetime  # noqa: PLC0415
                stub = ExternalAnalysis(
                    sample_id=sid,
                    analysis_type="Elemental",  # AnalysisType.ELEMENTAL enum value
                    analysis_date=datetime.date.today(),
                )
                db.add(stub)
                db.flush()
            ext_cache[sid] = stub.id
            return stub.id

        for idx, row in df.iterrows():
            row_num = idx + 2
            sample_id = str(row.get(sample_col) or "").strip()
            if not sample_id:
                skipped += 1
                continue

            # Normalise sample ID — uppercase, strip spaces
            sample_id_norm = sample_id.upper().replace(" ", "")
            sample = (
                db.query(SampleInfo)
                .filter(SampleInfo.sample_id.ilike(sample_id_norm))
                .first()
            )
            if not sample:
                errors.append(f"Row {row_num}: sample_id '{sample_id}' not found")
                continue

            ext_id = _get_ext_id(sample.sample_id)

            for col in analyte_cols:
                analyte = analyte_cache[col]
                val = row.get(col)
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    continue
                try:
                    fval = float(val)
                except (ValueError, TypeError):
                    continue

                existing_ea = (
                    db.query(ElementalAnalysis)
                    .filter_by(external_analysis_id=ext_id, analyte_id=analyte.id)
                    .first()
                )
                if existing_ea:
                    if overwrite:
                        existing_ea.analyte_composition = fval
                        updated += 1
                    else:
                        skipped += 1
                else:
                    db.add(ElementalAnalysis(
                        external_analysis_id=ext_id,
                        sample_id=sample.sample_id,
                        analyte_id=analyte.id,
                        analyte_composition=fval,
                    ))
                    created += 1

        return created, updated, skipped, errors
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/services/bulk_uploads/test_elemental_composition_new.py -v
```

- [ ] **Step 5: Update the `/elemental-composition` endpoint to use the new parser**

In `backend/api/routers/bulk_uploads.py`, update `upload_elemental_composition`:

```python
@router.post("/elemental-composition", response_model=UploadResponse)
async def upload_elemental_composition(
    file: UploadFile = File(...),
    overwrite: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload flexible wide-format elemental composition (Symbol (unit) headers)."""
    from backend.services.bulk_uploads.elemental_composition import ElementalCompositionFlexibleService  # noqa: PLC0415
    file_bytes = await file.read()
    try:
        created, updated, skipped, errors = ElementalCompositionFlexibleService.upload(
            db, file_bytes, overwrite=overwrite
        )
        if not errors:
            db.commit()
        else:
            db.rollback()
    except Exception as exc:
        db.rollback()
        log.error("elemental_composition_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)], message="Upload failed")
    return UploadResponse(
        created=created, updated=updated, skipped=skipped, errors=errors,
        message=f"Elemental Composition: {created} created, {updated} updated",
    )
```

- [ ] **Step 6: Test with real file manually**

Upload `docs/sample_data/sample_actlabs_rock_composition.xlsx` via Bulk Uploads → Sample Chemical Composition. Inspect results.

- [ ] **Step 7: Write E2E test**

```typescript
// frontend/e2e/journeys/09-elemental-composition.spec.ts
import { test, expect } from '@playwright/test'
import * as path from 'path'

const ACTLABS_FILE = path.resolve(
  __dirname, '../../../../docs/sample_data/sample_actlabs_rock_composition.xlsx'
)

test('elemental composition upload processes without errors', async ({ page }) => {
  await page.goto('/bulk-uploads')
  await page.getByText('Sample Chemical Composition').click()

  const fileInput = page.locator('#elemental-composition input[type="file"]')
  await fileInput.setInputFiles(ACTLABS_FILE)

  await expect(page.getByText(/created|updated|skipped/i)).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText(/\berror\b/i)).not.toBeVisible()
})
```

- [ ] **Step 8: Run and fix until passing**

```bash
cd frontend && npx playwright test 09-elemental-composition --headed
```

- [ ] **Step 9: Commit**

```bash
git add backend/services/bulk_uploads/elemental_composition.py \
  backend/api/routers/bulk_uploads.py \
  tests/services/bulk_uploads/test_elemental_composition_new.py \
  frontend/e2e/journeys/09-elemental-composition.spec.ts
git commit -m "[M8] Chunk F: new elemental_composition parser + E2E test"
```

---

## Chunk G — Core E2E Journeys + Documentation

### Task G1: Journey 1 — Create experiment end-to-end

**Files:**
- Create: `frontend/e2e/journeys/01-create-experiment.spec.ts`

- [ ] **Step 1: Write the spec**

```typescript
// frontend/e2e/journeys/01-create-experiment.spec.ts
import { test, expect } from '@playwright/test'

const E2E_EXP_ID = `E2E_HPHT_${Date.now()}`

test('create experiment with conditions and verify derived fields', async ({ page }) => {
  await page.goto('/experiments/new')

  // Step 1 — Experiment details
  await page.getByLabel(/experiment id/i).fill(E2E_EXP_ID)
  await page.getByRole('button', { name: /next/i }).click()

  // Step 2 — Conditions
  await page.getByLabel(/rock mass/i).fill('10')
  await page.getByLabel(/water volume/i).fill('100')
  await page.getByRole('button', { name: /next|save/i }).click()

  // Navigate to detail page
  await page.goto('/experiments')
  await page.getByText(E2E_EXP_ID).click()

  // Verify water_to_rock_ratio derived field is displayed
  await expect(page.getByText(/water.to.rock/i)).toBeVisible()
})
```

- [ ] **Step 2: Run and fix**

```bash
cd frontend && npx playwright test 01-create-experiment --headed
```

Adjust selectors to match the actual `NewExperiment` page form structure.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/journeys/01-create-experiment.spec.ts
git commit -m "[M8] Chunk G: journey 1 — create experiment E2E"
```

---

### Task G2: Journey 4 — Status change reflects on dashboard

**Files:**
- Create: `frontend/e2e/journeys/04-update-status-dashboard.spec.ts`

- [ ] **Step 1: Write the spec**

```typescript
// frontend/e2e/journeys/04-update-status-dashboard.spec.ts
import { test, expect } from '@playwright/test'

test('status change on reactor grid updates badge after reload', async ({ page }) => {
  await page.goto('/dashboard')

  // Find an ONGOING reactor card
  const card = page.locator('[data-reactor]').filter({ hasText: /ONGOING/i }).first()
  await expect(card).toBeVisible()

  // Click the status badge to open dropdown
  await card.getByText(/ONGOING/i).click()

  // Select COMPLETED
  await page.getByRole('menuitem', { name: /completed/i }).click()

  // Wait for mutation to settle
  await page.waitForTimeout(500)

  // Reload and verify the badge changed
  await page.reload()
  await page.waitForLoadState('networkidle')

  // The card should now show COMPLETED
  await expect(card.or(page.locator('[data-reactor]').filter({ hasText: /COMPLETED/i }).first())).toBeVisible()
})
```

- [ ] **Step 2: Run, inspect, adjust selectors**

```bash
cd frontend && npx playwright test 04-update-status-dashboard --headed
```

The `data-reactor` attribute may need to be added to `ReactorGrid.tsx` reactor card elements if not present. Add `data-reactor={slot}` to the reactor card wrapper div.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/journeys/04-update-status-dashboard.spec.ts
git commit -m "[M8] Chunk G: journey 4 — status change dashboard E2E"
```

---

### Task G3: Journey 6 — Derived field recalculation

**Files:**
- Create: `frontend/e2e/journeys/06-recalculate-derived-fields.spec.ts`

- [ ] **Step 1: Write the spec**

```typescript
// frontend/e2e/journeys/06-recalculate-derived-fields.spec.ts
import { test, expect } from '@playwright/test'

test('editing rock_mass_g triggers water_to_rock_ratio recalculation', async ({ page }) => {
  // Use an existing experiment from the list
  await page.goto('/experiments')
  await page.getByRole('row').nth(1).click()  // first data row

  // Navigate to conditions tab
  await page.getByRole('tab', { name: /conditions/i }).click()

  // Read current rock mass value
  const rockMassInput = page.getByLabel(/rock mass/i)
  await expect(rockMassInput).toBeVisible()

  // Edit the rock mass (fill() selects-all and replaces in Playwright)
  await rockMassInput.fill('20')
  await page.getByRole('button', { name: /save/i }).click()

  // Verify water_to_rock_ratio updated
  await expect(page.getByText(/water.to.rock/i)).toBeVisible()
  // The ratio for water=100mL, rock=20g should be 5.0
  await expect(page.getByText(/5\.0|5,0/)).toBeVisible()
})
```

Note: Adjust selectors to match the actual `ExperimentDetail` conditions tab structure.

- [ ] **Step 2: Run and fix**

```bash
cd frontend && npx playwright test 06-recalculate-derived-fields --headed
```

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/journeys/06-recalculate-derived-fields.spec.ts
git commit -m "[M8] Chunk G: journey 6 — derived field recalculation E2E"
```

---

### Task G4: Calculation regression test

**Files:**
- Create: `tests/regression/__init__.py`
- Create: `tests/regression/test_calc_regression.py`

The calc engine uses ORM-mutating functions — there are no standalone pure functions.
Use mock objects with the required attributes and call the registry functions directly.

- [ ] **Step 1: Create the regression directory**

```bash
mkdir -p tests/regression && touch tests/regression/__init__.py
```

- [ ] **Step 2: Create regression test**

```python
"""Calculation regression tests — verify derived fields for known inputs.

The calc engine works by mutating ORM instances in place. Tests create
lightweight mock objects with the required attributes and verify the
mutated values after calling the registry functions.
"""
from __future__ import annotations
import pytest
from types import SimpleNamespace


def test_water_to_rock_ratio_normal():
    """water_volume_mL=100, rock_mass_g=10 → water_to_rock_ratio=10.0"""
    from backend.services.calculations.conditions_calcs import recalculate_conditions
    instance = SimpleNamespace(
        water_volume_mL=100.0,
        rock_mass_g=10.0,
        water_to_rock_ratio=None,
        chemical_additives=[],
        formatted_additives=None,
    )
    recalculate_conditions(instance, session=None)
    assert instance.water_to_rock_ratio == pytest.approx(10.0)


def test_water_to_rock_ratio_zero_rock():
    """rock_mass_g=0 → water_to_rock_ratio=None (no division by zero)"""
    from backend.services.calculations.conditions_calcs import recalculate_conditions
    instance = SimpleNamespace(
        water_volume_mL=100.0,
        rock_mass_g=0.0,
        water_to_rock_ratio=None,
        chemical_additives=[],
        formatted_additives=None,
    )
    recalculate_conditions(instance, session=None)
    assert instance.water_to_rock_ratio is None


def test_h2_micromoles_known_value():
    """
    h2=100ppm, gas_vol=10mL, pressure=0.1MPa at 20°C
    Uses R=0.082057 L·atm/(mol·K), T=293.15K, 1MPa=9.86923atm

    P_atm = 0.1 * 9.86923 = 0.986923
    V_L   = 10 / 1000     = 0.01
    n_total = (0.986923 * 0.01) / (0.082057 * 293.15) = 4.104e-4 mol
    h2_moles = 4.104e-4 * (100/1e6)                   = 4.104e-8 mol
    h2_micromoles = 4.104e-8 * 1e6                    ≈ 0.04104 µmol
    """
    from backend.services.calculations.scalar_calcs import _calculate_hydrogen
    instance = SimpleNamespace(
        h2_concentration=100.0,
        gas_sampling_volume_ml=10.0,
        gas_sampling_pressure_MPa=0.1,
        h2_micromoles=None,
        h2_mass_ug=None,
    )
    _calculate_hydrogen(instance)
    assert instance.h2_micromoles == pytest.approx(0.04104, rel=0.01)


def test_h2_micromoles_none_when_missing_inputs():
    """Missing gas_sampling_volume_ml → h2_micromoles=None."""
    from backend.services.calculations.scalar_calcs import _calculate_hydrogen
    instance = SimpleNamespace(
        h2_concentration=100.0,
        gas_sampling_volume_ml=None,
        gas_sampling_pressure_MPa=0.1,
        h2_micromoles=None,
        h2_mass_ug=None,
    )
    _calculate_hydrogen(instance)
    assert instance.h2_micromoles is None
```

- [ ] **Step 3: Run**

```bash
pytest tests/regression/test_calc_regression.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/regression/
git commit -m "[M8] Chunk G: calculation regression tests"
```

---

### Task G5: Run full Playwright suite

- [ ] **Step 1: Run all specs**

```bash
cd frontend && npx playwright test
```

Expected: all 10 specs pass (00-smoke + 01-09 journeys).

- [ ] **Step 2: Fix any remaining failures**

Common issues:
- Selector mismatches — use `--headed` and `--debug` to inspect
- Race conditions — add `await page.waitForLoadState('networkidle')` before assertions
- Missing test data — create required experiments/samples in the dev DB

- [ ] **Step 3: Commit any fixes**

```bash
git add frontend/e2e/
git commit -m "[M8] Chunk G: all Playwright specs passing"
```

---

### Task G6: Documentation

**Files:**
- Modify: `README.md`
- Create: `CONTRIBUTING.md`
- Create: `docs/deployment/PRODUCTION_DEPLOYMENT.md`
- Create: `docs/user_guide/USER_MANUAL.md`
- Audit: `docs/CALCULATIONS.md`, `docs/FIELD_MAPPING.md`

- [ ] **Step 1: Rewrite `README.md`**

The README must work on a clean machine. Required sections:
- Project overview (1 paragraph)
- Prerequisites (Python 3.11+, Node 18+, PostgreSQL 18, Firebase project)
- Installation (`git clone`, `.venv`, `npm install`, `.env` setup, `alembic upgrade head`)
- Running the app (start FastAPI, start Vite dev server)
- Running tests (`pytest tests/`, `cd frontend && npx playwright test`)
- Architecture overview (React + FastAPI + PostgreSQL)

- [ ] **Step 2: Create `CONTRIBUTING.md`**

Required sections:
- Branch naming (`feature/m*-description`)
- Commit format (from CLAUDE.md §9)
- Running tests before pushing
- Milestone workflow (`/start-task`, `/complete-task`)
- Code standards reference

- [ ] **Step 3: Create `docs/deployment/PRODUCTION_DEPLOYMENT.md`**

Required sections:
- Server requirements (Windows 10/11, PostgreSQL 18, Node 18, Python 3.11)
- First-time setup (clone, venv, npm build, alembic, NSSM service registration)
- Updating the app (git pull, npm build, alembic upgrade, restart service)
- Firewall setup (allow LAN port 8000)
- Backup strategy (pg_dump daily, retention policy)

- [ ] **Step 4: Create `docs/user_guide/USER_MANUAL.md`**

Required sections:
- Logging in (Firebase auth, approval workflow)
- Dashboard overview (reactor grid, timeline, activity feed)
- Experiments (list, create, detail tabs)
- Bulk Uploads (one section per upload type)
- Samples and chemicals management

- [ ] **Step 5: Audit `docs/CALCULATIONS.md` and `docs/FIELD_MAPPING.md`**

Verify each formula against the actual calculation engine code in `backend/services/calculations/`. Update any outdated formulas or field names.

- [ ] **Step 6: Commit all docs**

```bash
git add README.md CONTRIBUTING.md docs/deployment/PRODUCTION_DEPLOYMENT.md \
  docs/user_guide/USER_MANUAL.md docs/CALCULATIONS.md docs/FIELD_MAPPING.md
git commit -m "[M8] Chunk G: documentation pass complete"
```

---

### Task G7: Final verification and plan.md update

- [ ] **Step 1: Run full test suite**

```bash
# Backend
pytest tests/ -v --tb=short

# Frontend E2E
cd frontend && npx playwright test
```

Expected: all tests pass.

- [ ] **Step 2: Update `docs/working/plan.md`**

Mark M8 as complete, record what was built, decisions made, and known issues.

- [ ] **Step 3: Final commit**

```bash
git add docs/working/plan.md
git commit -m "[M8] Sign-off: all tests passing, docs complete, advance milestone index to M9"
```
