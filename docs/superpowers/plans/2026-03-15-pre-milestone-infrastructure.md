# Pre-Milestone Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the infrastructure layer — Docker dev environment, SQLAlchemy connection module, FastAPI skeleton update, Windows production scripts, and deployment documentation — that the rest of the milestones build on.

**Architecture:** Docker Compose runs PostgreSQL + pgAdmin for development; a SQLAlchemy sync engine in `database/connection.py` provides the `get_db` FastAPI dependency; Windows `.bat` scripts handle production deployment, backups, and NSSM service setup on the lab PC.

**Tech Stack:** Docker Compose, PostgreSQL 16, pgAdmin 4, FastAPI, SQLAlchemy 2.0 (sync), python-dotenv, structlog, NSSM, Windows Batch scripting.

**Spec:** `docs/superpowers/specs/2026-03-15-pre-milestone-infrastructure-design.md`

**Note for implementer:** Use `%~dp0..\.env` (not bare `.env`) when reading the `.env` file in all `.bat` scripts — Task Scheduler may run with a different working directory than the repo root.

---

## Chunk 1: Branch + Dependency Files

### Task 1: Create feature branch

**Files:** none (git operation)

- [ ] **Step 1: Create and switch to feature branch**

```bash
git checkout develop
git checkout -b infra/lab-pc-server-setup
```

Expected: `Switched to a new branch 'infra/lab-pc-server-setup'`

---

### Task 2: Fix `requirements.txt`

**Files:**
- Modify: `requirements.txt`

**Model:** haiku (file edit, no logic)

- [ ] **Step 1: Remove the stale `dotenv==0.9.9` package**

Open `requirements.txt`. Find and delete the line:
```
dotenv==0.9.9
```
This is an incorrect PyPI stub (not `python-dotenv`). `python-dotenv==1.0.1` is already present on a later line — that is the correct package.

- [ ] **Step 2: Add `structlog==24.4.0`**

After the existing `SQLAlchemy==2.0.39` line, add:
```
structlog==24.4.0
```

- [ ] **Step 3: Verify no duplicate `python-dotenv` entries remain**

Run:
```bash
grep -n "dotenv" requirements.txt
```
Expected output (exactly two lines, no `dotenv==0.9.9`):
```
58:python-dotenv==1.0.1
```
(Line number may vary. The point is: one `python-dotenv==1.0.1` entry, zero `dotenv==0.9.9` entries.)

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "[Pre-M] Fix requirements: remove dotenv stub, add structlog==24.4.0

- Remove dotenv==0.9.9 (incorrect PyPI stub, not python-dotenv)
- Add structlog==24.4.0 for CLAUDE.md-mandated structured logging
- Tests added: no
- Docs updated: no"
```

---

### Task 3: Update `.env.example`

**Files:**
- Modify: `.env.example`

**Model:** haiku (template generation)

- [ ] **Step 1: Replace `.env.example` contents entirely**

The current file has a password in `DATABASE_URL` and is missing several vars. Replace the entire file with:

```
# ============================================================
# Experiment Tracking System — Environment Variables
# Copy to .env and fill in values before running.
# NEVER commit .env to version control.
# ============================================================

# ── Database (all environments) ──────────────────────────────
DATABASE_URL=
DB_USER=experiments_user
DB_NAME=experiments
DB_PASSWORD=

# ── Firebase Authentication ──────────────────────────────────
FIREBASE_PROJECT_ID=
FIREBASE_PRIVATE_KEY=
FIREBASE_CLIENT_EMAIL=

# ── Application ──────────────────────────────────────────────
APP_ENV=development
API_PORT=8000
CORS_ORIGINS=

# ── Logging ──────────────────────────────────────────────────
LOG_LEVEL=INFO

# ── Backups (production Windows lab PC only) ─────────────────
BACKUP_DIR=
PUBLIC_COPY_DIR=

# ── PostgreSQL binary path (production Windows only) ─────────
# Default works for a standard PostgreSQL 16 install.
# Update if you installed a different version or non-default path.
PG_BIN_PATH=C:\Program Files\PostgreSQL\16\bin

# ── Network (production Windows only) ────────────────────────
# Firewall rule allows inbound port 8000 from this subnet only.
# Change if your lab network is 10.x.x.x or 172.16.x.x.
LAN_SUBNET=192.168.0.0/16
```

- [ ] **Step 2: Verify no passwords remain**

```bash
grep -i "password\|secret\|private_key" .env.example
```
Expected: lines with blank values only (e.g. `DB_PASSWORD=`, `FIREBASE_PRIVATE_KEY=`). No non-blank secrets.

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "[Pre-M] Update .env.example: blank secrets, add backup/network vars

- Blank DATABASE_URL password (was leaking dev password)
- Add DB_USER, DB_NAME, DB_PASSWORD for Windows backup script
- Add PG_BIN_PATH, LAN_SUBNET for production Windows scripts
- Tests added: no
- Docs updated: no"
```

---

## Chunk 2: Docker Compose — pgAdmin Service

### Task 4: Add pgAdmin to `docker-compose.yml`

**Files:**
- Modify: `docker-compose.yml`

**Model:** haiku (config template)

- [ ] **Step 1: Add pgAdmin service block**

Open `docker-compose.yml`. After the closing `networks:` block of the `app:` service (before the top-level `volumes:` key), add the following service. Also add `pgadmin_data` to the top-level `volumes:` section.

Add this service:
```yaml
  # pgAdmin — database management UI (dev only)
  pgadmin:
    image: dpage/pgadmin4:latest
    container_name: experiment_tracking_pgadmin
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@lab.local
      PGADMIN_DEFAULT_PASSWORD: pgadmin_dev
    ports:
      - "5050:80"
    volumes:
      - pgadmin_data:/var/lib/pgadmin
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - app_network
```

Add to the top-level `volumes:` section:
```yaml
  pgadmin_data:
```

- [ ] **Step 2: Validate compose file syntax**

```bash
docker compose config --quiet
```
Expected: exits with code 0, no output. If there are YAML errors, fix indentation.

- [ ] **Step 3: Start containers and verify pgAdmin**

```bash
docker compose up -d
docker compose ps
```
Expected: three services shown — `experiment_tracking_postgres`, `experiment_tracking_app`, `experiment_tracking_pgadmin` — all with status `running` or `Up`.

- [ ] **Step 4: Verify pgAdmin is reachable**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:5050
```
Expected: `200` or `302` (pgAdmin login redirect).

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml
git commit -m "[Pre-M] Add pgAdmin service to docker-compose.yml

- pgAdmin 4 on port 5050 with dev-only hardcoded credentials
- Depends on postgres health check
- pgadmin_data named volume for persistence
- Tests added: no
- Docs updated: no"
```

---

## Chunk 3: Python Code — connection.py and main.py

### Task 5: Write tests for `database/connection.py`

**Files:**
- Create: `tests/test_connection.py`

**Model:** sonnet (test logic)

- [ ] **Step 1: Create test file**

```python
# tests/test_connection.py
"""
Tests for database/connection.py.
Verifies that get_db yields a SQLAlchemy Session and closes it on exit.
Uses an in-memory SQLite DB to avoid requiring a live PostgreSQL connection.

IMPORTANT: We patch both os.environ and load_dotenv.
load_dotenv() is called at module level in connection.py — if not patched,
it will read the real .env file in the container and override our patched
DATABASE_URL before we can use it. Patching load_dotenv to a no-op ensures
the test env var is the one that connection.py sees.
"""
import importlib
import os
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session


def _reload_connection(sqlite_url: str):
    """Reload database.connection with a patched DATABASE_URL and no-op load_dotenv."""
    with patch.dict(os.environ, {"DATABASE_URL": sqlite_url}, clear=False):
        with patch("database.connection.load_dotenv", return_value=None):
            import database.connection as conn_module
            importlib.reload(conn_module)
            return conn_module


def test_get_db_yields_session(tmp_path):
    """get_db must yield a SQLAlchemy Session instance."""
    sqlite_url = f"sqlite:///{tmp_path}/test.db"
    conn = _reload_connection(sqlite_url)

    gen = conn.get_db()
    db = next(gen)
    assert isinstance(db, Session), f"Expected Session, got {type(db)}"

    # Exhaust generator to trigger the finally block (closes session)
    try:
        next(gen)
    except StopIteration:
        pass


def test_get_db_closes_on_exit(tmp_path):
    """get_db must call db.close() in its finally block."""
    sqlite_url = f"sqlite:///{tmp_path}/test.db"
    conn = _reload_connection(sqlite_url)

    gen = conn.get_db()
    db = next(gen)

    # Wrap db.close so we can assert it was called
    original_close = db.close
    close_calls = []
    db.close = lambda: close_calls.append(True) or original_close()

    # Simulate FastAPI tearing down the dependency after the request
    try:
        next(gen)
    except StopIteration:
        pass

    assert len(close_calls) == 1, "db.close() must be called exactly once in the finally block"


def test_get_db_fails_fast_without_database_url():
    """
    database/connection.py must raise KeyError at reload time
    if DATABASE_URL is not set in the environment.

    The module import happens BEFORE patching the environment so that
    database.connection is guaranteed to be in sys.modules. The reload
    (which re-executes module-level code) is what must raise KeyError.
    This makes the test order-independent.
    """
    import database.connection as conn_module  # ensure in sys.modules before patching

    # Remove only DATABASE_URL; leave the rest of the environment intact
    # so unrelated imports don't fail for irrelevant reasons.
    env_without_url = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}

    with patch.dict(os.environ, env_without_url, clear=True):
        with patch("database.connection.load_dotenv", return_value=None):
            with pytest.raises(KeyError):
                importlib.reload(conn_module)
```

- [ ] **Step 2: Run test to confirm failure (connection.py doesn't exist yet)**

```bash
docker compose exec app pytest tests/test_connection.py -v 2>&1 | head -30
```
Expected: `ModuleNotFoundError` or `ImportError` — confirms tests are written against a missing implementation.

---

### Task 6: Implement `database/connection.py`

**Files:**
- Create: `database/connection.py`

**Model:** sonnet (module implementation)

- [ ] **Step 1: Create `database/connection.py`**

```python
"""
SQLAlchemy engine, session factory, and FastAPI get_db dependency.

This module uses python-dotenv as a temporary measure for the Pre-Milestone.
TODO M2: replace DATABASE_URL loading with backend.core.config.Settings
         (pydantic-settings) once backend/core/config.py is implemented.
"""
import os
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Load .env file if present. In production (NSSM service), .env is in the
# repo root; python-dotenv searches from the CWD upwards.
load_dotenv()

# TODO M2: replace with backend.core.config.Settings.database_url
DATABASE_URL: str = os.environ["DATABASE_URL"]

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Recycle stale connections on reconnect
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a SQLAlchemy Session.

    Usage in a route:
        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 2: Run the tests**

```bash
docker compose exec app pytest tests/test_connection.py -v
```
Expected:
```
tests/test_connection.py::test_get_db_yields_session PASSED
tests/test_connection.py::test_get_db_closes_on_exit PASSED
tests/test_connection.py::test_get_db_fails_fast_without_database_url PASSED
```

- [ ] **Step 3: Commit**

```bash
git add database/connection.py tests/test_connection.py
git commit -m "[Pre-M] Add database/connection.py with get_db FastAPI dependency

- SQLAlchemy 2.0 sync engine + sessionmaker + get_db generator
- Reads DATABASE_URL from env (python-dotenv, TODO M2: pydantic-settings)
- pool_pre_ping=True for stale connection recovery
- Tests added: yes (tests/test_connection.py — 3 tests)
- Docs updated: no"
```

---

### Task 7: Write tests for `backend/api/main.py` changes

**Files:**
- Create: `tests/api/test_main.py`

**Model:** sonnet (test logic)

- [ ] **Step 1: Create test file**

```python
# tests/api/test_main.py
"""
Tests for backend/api/main.py.

Verifies:
- GET /health returns 200 with correct body
- GET / returns 404 when frontend/dist does not exist (static mount not registered)
- GET /api/docs redirects to /docs (existing behaviour preserved)
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """TestClient wrapping the FastAPI app."""
    from backend.api.main import app
    return TestClient(app, raise_server_exceptions=True)


def test_health_check_returns_200(client):
    """GET /health must return 200 with status=ok."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "experiment_tracking_api"


def test_root_returns_404_when_no_frontend_dist():
    """
    When frontend/dist does not exist, GET / must return 404.
    The old GET / JSON handler must be removed; StaticFiles mount
    is not registered when the dist directory is absent.

    StaticFiles mounts are registered at module import time, so we cannot
    retroactively un-mount them from the live `app` instance. Instead we
    construct a minimal fresh FastAPI app that mirrors main.py's no-dist
    state (no root handler, no StaticFiles). This verifies the invariant:
    the route table has no handler for GET / when the frontend is absent.
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.testclient import TestClient

    fresh_app = FastAPI()
    fresh_app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @fresh_app.get("/health")
    async def health():
        return {"status": "ok", "service": "experiment_tracking_api"}

    # No StaticFiles mount — mirrors main.py when frontend/dist does not exist
    test_client = TestClient(fresh_app, raise_server_exceptions=True)

    response = test_client.get("/")
    # 404 = no static mount registered, no JSON handler at /.
    # 200 with JSON body would mean the old GET / handler was not removed.
    assert response.status_code == 404


def test_health_check_is_not_shadowed_by_static_mount(client):
    """
    GET /health must return JSON even if a StaticFiles mount exists.
    API routes must be registered before the static mount.
    """
    response = client.get("/health")
    assert response.headers["content-type"].startswith("application/json")
```

- [ ] **Step 2: Run to confirm current state**

```bash
docker compose exec app pytest tests/api/test_main.py -v 2>&1 | head -40
```
Expected: `test_root_returns_404_when_no_frontend_dist` **FAILS** (current `GET /` returns 200 JSON). Other tests pass. This confirms the test is correctly identifying the problem.

---

### Task 8: Update `backend/api/main.py`

**Files:**
- Modify: `backend/api/main.py`

**Model:** sonnet (code modification)

- [ ] **Step 1: Remove the `GET /` JSON handler and add static file mount**

Replace the entire file with:

```python
"""
FastAPI application entry point.

Route registration order matters:
  1. CORS middleware
  2. API routes (health, docs, future routers)
  3. StaticFiles mount at "/" — MUST be last; it catches all unmatched paths.

The StaticFiles mount is only registered if frontend/dist exists, so the
app starts cleanly before the React app is built.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Load environment variables
load_dotenv()

# ── App instance ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Experiment Tracking System API",
    description="Backend API for laboratory experiment tracking",
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:8000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Liveness check. Returns 200 when the application is running."""
    return {"status": "ok", "service": "experiment_tracking_api"}


@app.get("/api/docs", include_in_schema=False)
async def redirect_docs():
    """Redirect bare /api/docs to Swagger UI."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")


# TODO M3: register routers here, e.g.:
#   from backend.api.routers import experiments, results, samples
#   app.include_router(experiments.router, prefix="/api")

# ── Static file mount (React SPA) ────────────────────────────────────────────
# IMPORTANT: This must be the LAST mount — it catches all unmatched routes
# and returns index.html for React Router client-side navigation.
# html=True enables fallback to index.html for unknown paths (SPA support).
FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_DIST), html=True),
        name="static",
    )

# ── Dev entrypoint ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.api.main:app",
        host="0.0.0.0",
        port=int(os.getenv("API_PORT", "8000")),
        reload=True,
    )
```

- [ ] **Step 2: Run the tests**

```bash
docker compose exec app pytest tests/api/test_main.py -v
```
Expected: all three tests PASS.

- [ ] **Step 3: Verify live endpoint**

```bash
curl -s http://localhost:8000/health
```
Expected: `{"status":"ok","service":"experiment_tracking_api"}`

- [ ] **Step 4: Commit**

```bash
git add backend/api/main.py tests/api/test_main.py
git commit -m "[Pre-M] Update main.py: remove GET / handler, add static file mount

- Remove GET / JSON handler (conflicted with StaticFiles SPA mount)
- Add StaticFiles mount at / with html=True for React Router support
- Mount uses absolute Path(__file__)-relative path (NSSM-safe)
- Mount only registered when frontend/dist exists (safe pre-build)
- Tests added: yes (tests/api/test_main.py — 3 tests)
- Docs updated: no"
```

---

## Chunk 4: Windows Batch Scripts

> **Model for all tasks in this chunk:** sonnet (scripting logic with error handling)

### Task 9: Create `scripts/deploy.bat`

**Files:**
- Create: `scripts/deploy.bat`

**Model:** sonnet

- [ ] **Step 1: Create `scripts/deploy.bat`**

```bat
@echo off
REM ============================================================
REM deploy.bat — Production deployment for Experiment Tracking
REM
REM Replaces auto_update.bat. Runs on the lab PC.
REM Usage: deploy.bat
REM
REM What it does:
REM   1. Captures current HEAD for safe rollback
REM   2. git pull origin main
REM   3. pip install -r requirements.txt
REM   4. alembic upgrade head
REM   5. Restarts the ExperimentTrackingAPI Windows service
REM
REM On any failure: resets to saved HEAD, restarts service on
REM previous code, and exits with code 1.
REM
REM IMPORTANT: If alembic upgrade ran before failure, the database
REM schema may be ahead of the code. Manual intervention may be
REM required — do NOT auto-downgrade (destructive).
REM ============================================================

setlocal enabledelayedexpansion

set NSSM=C:\nssm\nssm.exe
set SERVICE=ExperimentTrackingAPI
set STEP=unknown
REM NOTE: deploy.bat intentionally does not read .env.
REM       NSSM injects environment variables directly into the service process.
REM       Python/alembic/git are assumed to be in PATH (set during install).

REM ── Step 0: Capture current HEAD ─────────────────────────────
for /f %%i in ('git rev-parse HEAD') do set PREV_HASH=%%i
if errorlevel 1 (
    echo ERROR: Could not determine current git HEAD. Aborting.
    exit /b 1
)
echo [deploy] Starting deploy from commit %PREV_HASH%

REM ── Step 1: git pull ─────────────────────────────────────────
set STEP=git pull
echo [deploy] Running: git pull origin main
git pull origin main
if errorlevel 1 goto :ROLLBACK

REM ── Step 2: pip install ──────────────────────────────────────
set STEP=pip install
echo [deploy] Running: pip install -r requirements.txt
pip install -r requirements.txt
if errorlevel 1 goto :ROLLBACK

REM ── Step 3: alembic upgrade ──────────────────────────────────
set STEP=alembic upgrade
echo [deploy] Running: alembic upgrade head
alembic upgrade head
if errorlevel 1 goto :ROLLBACK

REM ── Step 4: restart service ───────────────────────────────────
set STEP=nssm restart
echo [deploy] Restarting service: %SERVICE%
"%NSSM%" restart %SERVICE%
if errorlevel 1 goto :ROLLBACK

echo [deploy] SUCCESS. Service restarted on latest code.
exit /b 0

:ROLLBACK
echo.
echo ============================================================
echo DEPLOY FAILED at step: %STEP%
echo Rolling back to commit: %PREV_HASH%
echo ============================================================
git reset --hard %PREV_HASH%
echo [deploy] Restarting service on previous code...
"%NSSM%" restart %SERVICE%
echo.
echo [deploy] Service restarted on %PREV_HASH%.
if "%STEP%"=="alembic upgrade" (
    echo.
    echo WARNING: alembic upgrade ran before failure.
    echo          The database schema may be ahead of the restored code.
    echo          Manual review required: run 'alembic current' and 'alembic history'.
    echo          Do NOT run alembic downgrade without reviewing the migration first.
)
exit /b 1
```

- [ ] **Step 2: Validate BAT syntax by running a dry parse on Windows**

```bash
cmd /c "scripts\deploy.bat /?" 2>&1 || true
```
If the script outputs anything other than a "not a recognized command" error for `/?`, the syntax is valid. Alternatively:
```bash
cmd /c "echo off && call scripts\deploy.bat" 2>&1 | head -5 || true
```
The script will fail fast at `git rev-parse HEAD` — that is fine. Look for no syntax errors like `unexpected token` or `missing closing parenthesis`.

- [ ] **Step 3: Commit**

```bash
git add scripts/deploy.bat
git commit -m "[Pre-M] Add scripts/deploy.bat production deployment script

- Replaces auto_update.bat
- Captures HEAD before pull for deterministic rollback
- Explicit ERRORLEVEL check after each step
- Warns if alembic migration ran before failure (schema/code divergence)
- NSSM at C:\nssm\nssm.exe (documented prerequisite)
- Tests added: no (Windows-only script)
- Docs updated: no"
```

---

### Task 10: Create `scripts/backup.bat`

**Files:**
- Create: `scripts/backup.bat`

**Model:** sonnet

- [ ] **Step 1: Create `scripts/backup.bat`**

```bat
@echo off
REM ============================================================
REM backup.bat — Nightly PostgreSQL backup for Experiment Tracking
REM
REM Usage: backup.bat
REM Schedule: Windows Task Scheduler, nightly at 02:00.
REM
REM What it does:
REM   1. Reads config from .env (path relative to this script)
REM   2. pg_dump -Fc to BACKUP_DIR\experiments_YYYYMMDD_HHMMSS.dump
REM   3. Deletes .dump files older than 30 days from BACKUP_DIR
REM
REM Required .env variables:
REM   DB_USER, DB_NAME, DB_PASSWORD, BACKUP_DIR
REM   PG_BIN_PATH  (optional, defaults to PostgreSQL 16 standard path)
REM ============================================================

setlocal enabledelayedexpansion

REM ── Locate .env relative to this script (safe for Task Scheduler) ──
set ENV_FILE=%~dp0..\.env

if not exist "%ENV_FILE%" (
    echo ERROR: .env file not found at %ENV_FILE%
    echo        Copy .env.example to .env in the repo root and fill in values.
    exit /b 1
)

REM ── Parse .env using tokens=1,* to handle values with spaces ──
REM Skips blank lines and comment lines (starting with #).
set DB_USER=
set DB_NAME=
set DB_PASSWORD=
set BACKUP_DIR=
set PG_BIN_PATH=C:\Program Files\PostgreSQL\16\bin

for /f "usebackq tokens=1,* delims==" %%a in ("%ENV_FILE%") do (
    set LINE=%%a
    REM Skip blank lines and comments
    if not "!LINE!"=="" if not "!LINE:~0,1!"=="#" (
        if "%%a"=="DB_USER"      set DB_USER=%%b
        if "%%a"=="DB_NAME"      set DB_NAME=%%b
        if "%%a"=="DB_PASSWORD"  set DB_PASSWORD=%%b
        if "%%a"=="BACKUP_DIR"   set BACKUP_DIR=%%b
        if "%%a"=="PG_BIN_PATH"  set PG_BIN_PATH=%%b
    )
)

REM ── Validate required vars ────────────────────────────────────
if "%DB_USER%"=="" (echo ERROR: DB_USER not set in .env & exit /b 1)
if "%DB_NAME%"=="" (echo ERROR: DB_NAME not set in .env & exit /b 1)
if "%DB_PASSWORD%"=="" (echo ERROR: DB_PASSWORD not set in .env & exit /b 1)
if "%BACKUP_DIR%"=="" (echo ERROR: BACKUP_DIR not set in .env & exit /b 1)

REM ── Create BACKUP_DIR if it doesn't exist ─────────────────────
if not exist "%BACKUP_DIR%" (
    mkdir "%BACKUP_DIR%"
    if errorlevel 1 (
        echo ERROR: Could not create BACKUP_DIR: %BACKUP_DIR%
        exit /b 1
    )
)

REM ── Generate timestamped filename ────────────────────────────
for /f "tokens=2 delims==" %%i in ('wmic os get localdatetime /value') do set DT=%%i
set TIMESTAMP=%DT:~0,8%_%DT:~8,6%
set FILENAME=experiments_%TIMESTAMP%.dump
set DUMP_PATH=%BACKUP_DIR%\%FILENAME%

echo [backup] Starting backup: %DUMP_PATH%

REM ── Run pg_dump ───────────────────────────────────────────────
set PGPASSWORD=%DB_PASSWORD%
"%PG_BIN_PATH%\pg_dump" -Fc -h localhost -U %DB_USER% %DB_NAME% -f "%DUMP_PATH%"
set PG_EXIT=%ERRORLEVEL%
set PGPASSWORD=

if %PG_EXIT% neq 0 (
    echo ERROR: pg_dump failed with exit code %PG_EXIT%. Backup was NOT created.
    exit /b 1
)

echo [backup] Backup complete: %DUMP_PATH%

REM ── Prune files older than 30 days ────────────────────────────
echo [backup] Pruning backups older than 30 days from %BACKUP_DIR%
forfiles /p "%BACKUP_DIR%" /s /m *.dump /d -30 /c "cmd /c del @path" 2>nul
REM forfiles exits 1 if no files match the age filter — that is not an error.

echo [backup] Done.
exit /b 0
```

- [ ] **Step 2: Verify syntax by listing the script**

```bash
cmd /c "scripts\backup.bat /?" 2>&1 | head -5 || true
```
Look for the help output or fast-fail at `.env` not found — no syntax errors.

- [ ] **Step 3: Commit**

```bash
git add scripts/backup.bat
git commit -m "[Pre-M] Add scripts/backup.bat nightly pg_dump with 30-day retention

- Reads config from .env using script-relative path (Task Scheduler safe)
- Uses tokens=1,* delims== for .env parsing (handles paths with spaces)
- Checks ERRORLEVEL after pg_dump; fails loudly on error
- Clears PGPASSWORD immediately after pg_dump call
- forfiles prunes .dump files older than 30 days
- Tests added: no (Windows-only script)
- Docs updated: no"
```

---

### Task 11: Create `scripts/install_services.bat`

**Files:**
- Create: `scripts/install_services.bat`

**Model:** sonnet

- [ ] **Step 1: Create `scripts/install_services.bat`**

```bat
@echo off
REM ============================================================
REM install_services.bat — Idempotent NSSM service setup
REM
REM Usage (run as Administrator):
REM   install_services.bat C:\path\to\repo
REM
REM What it does:
REM   1. Creates the ExperimentTrackingAPI Windows service via NSSM
REM      (skips creation if service already exists)
REM   2. Sets AppParameters, AppDirectory, auto-start, log files
REM   3. Adds Windows Firewall inbound rule for port 8000
REM      (skips if rule already exists)
REM   4. Starts the service
REM
REM Prerequisites:
REM   - NSSM at C:\nssm\nssm.exe
REM   - Python in PATH
REM   - Repo cloned and .env configured at REPO_PATH\.env
REM   - Run as Administrator (required for service and firewall changes)
REM ============================================================

setlocal enabledelayedexpansion

REM ── Validate argument ─────────────────────────────────────────
if "%~1"=="" (
    echo ERROR: Repo path argument is required.
    echo Usage: install_services.bat C:\path\to\repo
    exit /b 1
)
set REPO_PATH=%~1
set NSSM=C:\nssm\nssm.exe
set SERVICE=ExperimentTrackingAPI

REM Validate NSSM exists
if not exist "%NSSM%" (
    echo ERROR: NSSM not found at %NSSM%
    echo Download from https://nssm.cc and place nssm.exe at C:\nssm\nssm.exe
    exit /b 1
)

REM Validate repo path exists
if not exist "%REPO_PATH%" (
    echo ERROR: Repo path does not exist: %REPO_PATH%
    exit /b 1
)

REM ── Read LAN_SUBNET from .env (default 192.168.0.0/16) ────────
set ENV_FILE=%REPO_PATH%\.env
set LAN_SUBNET=192.168.0.0/16

if exist "%ENV_FILE%" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%ENV_FILE%") do (
        set LINE=%%a
        if not "!LINE!"=="" if not "!LINE:~0,1!"=="#" (
            if "%%a"=="LAN_SUBNET" set LAN_SUBNET=%%b
        )
    )
)
echo [install] Using LAN_SUBNET: %LAN_SUBNET%
echo [install] NOTE: If your lab network is 10.x.x.x or 172.16.x.x,
echo [install]       set LAN_SUBNET in .env and re-run this script.

REM Create logs directory
if not exist "%REPO_PATH%\logs" mkdir "%REPO_PATH%\logs"

REM ── Service installation ──────────────────────────────────────
sc query %SERVICE% >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [install] Service %SERVICE% already exists. Updating configuration...
) else (
    echo [install] Installing service: %SERVICE%
    "%NSSM%" install %SERVICE% python
    if errorlevel 1 (
        echo ERROR: Failed to install service %SERVICE%
        exit /b 1
    )
)

REM ── Configure service (idempotent — safe to re-run) ───────────
echo [install] Configuring service parameters...

"%NSSM%" set %SERVICE% AppParameters "-m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000"
"%NSSM%" set %SERVICE% AppDirectory "%REPO_PATH%"
"%NSSM%" set %SERVICE% Start SERVICE_AUTO_START
"%NSSM%" set %SERVICE% AppStdout "%REPO_PATH%\logs\uvicorn.log"
"%NSSM%" set %SERVICE% AppStderr "%REPO_PATH%\logs\uvicorn_stderr.log"
"%NSSM%" set %SERVICE% AppStdoutCreationDisposition 4
"%NSSM%" set %SERVICE% AppStderrCreationDisposition 4

echo [install] Service configured.

REM ── Firewall rule ─────────────────────────────────────────────
netsh advfirewall firewall show rule name="ExperimentTracking-8000" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [install] Firewall rule already exists. Skipping.
) else (
    echo [install] Adding firewall rule for port 8000 (subnet: %LAN_SUBNET%)
    netsh advfirewall firewall add rule ^
        name="ExperimentTracking-8000" ^
        protocol=TCP ^
        dir=in ^
        localport=8000 ^
        action=allow ^
        remoteip=%LAN_SUBNET%
    if errorlevel 1 (
        echo WARNING: Failed to add firewall rule. You may need to add it manually.
        echo          Run this script as Administrator to create firewall rules.
    )
)

REM ── Start service ─────────────────────────────────────────────
echo [install] Starting service: %SERVICE%
"%NSSM%" start %SERVICE% 2>nul
REM start returns non-zero if service is already running — that is fine
sc query %SERVICE% | findstr /i "RUNNING" >nul
if errorlevel 1 (
    echo WARNING: Service may not have started. Check logs at %REPO_PATH%\logs\uvicorn.log
    echo          Run: sc query %SERVICE%  to check status.
) else (
    echo [install] Service is RUNNING.
)

echo.
echo ============================================================
echo Install complete.
echo   Service:  %SERVICE%
echo   App dir:  %REPO_PATH%
echo   Logs:     %REPO_PATH%\logs\
echo   Port:     8000 (LAN subnet: %LAN_SUBNET%)
echo   Browse:   http://localhost:8000/health
echo ============================================================
exit /b 0
```

- [ ] **Step 2: Validate syntax**

```bash
cmd /c "scripts\install_services.bat /?" 2>&1 | head -5 || true
```
Expected: prints the "ERROR: Repo path argument is required" usage message (because no argument passed) and exits — no syntax errors.

- [ ] **Step 3: Commit**

```bash
git add scripts/install_services.bat
git commit -m "[Pre-M] Add scripts/install_services.bat NSSM service setup

- Idempotent: sc query checks before creating service
- NSSM install + separate AppParameters set (required by NSSM CLI)
- Reads LAN_SUBNET from .env (defaults to 192.168.0.0/16)
- Idempotent firewall rule (netsh show before add)
- Logs stdout/stderr to logs/uvicorn.log and logs/uvicorn_stderr.log
- Tests added: no (Windows-only script)
- Docs updated: no"
```

---

## Chunk 5: Documentation + Final Verification

### Task 12: Create `docs/deployment/LAB_PC_SETUP.md`

**Files:**
- Create: `docs/deployment/LAB_PC_SETUP.md`

**Model:** haiku (documentation)

- [ ] **Step 1: Create `docs/deployment/LAB_PC_SETUP.md`**

```markdown
# Lab PC Setup Guide

Step-by-step instructions for setting up the Experiment Tracking System
on the lab PC as a permanent Windows service.

**Target:** Windows 10/11 Pro, always-on lab PC on local network.
**Users:** Researchers access the app at `http://<lab-pc-hostname>:8000`.

---

## Prerequisites

Install these before running any setup scripts:

| Tool | Version | Notes |
|---|---|---|
| Windows 10/11 Pro | Any | Pro required for Windows Services |
| Python | 3.11+ | Check "Add to PATH" during install |
| Git for Windows | Latest | [git-scm.com](https://git-scm.com) |
| NSSM | Latest | Download from [nssm.cc](https://nssm.cc); extract `nssm.exe` to `C:\nssm\nssm.exe` |
| PostgreSQL | 16 | See Section 2 |

---

## 1. Install PostgreSQL as a Windows Service

1. Download the PostgreSQL 16 Windows installer from [postgresql.org](https://www.postgresql.org/download/windows/)
2. Run the installer:
   - Install as a Windows service (default — leave checked)
   - Note the bin directory (default: `C:\Program Files\PostgreSQL\16\bin`)
   - Set a strong `postgres` superuser password — save it securely
3. Verify the service auto-starts:
   ```
   sc query postgresql-x64-16
   ```
   Expected: `STATE: 4  RUNNING`
4. Add the PostgreSQL bin directory to your system PATH (optional but convenient):
   - System Properties → Environment Variables → System Variables → Path → Edit → New
   - Add: `C:\Program Files\PostgreSQL\16\bin`

---

## 2. Create the Application Database and User

Open a Command Prompt and connect to PostgreSQL as the superuser:

```
psql -U postgres
```

Run these SQL commands:

```sql
-- Create the application database
CREATE DATABASE experiments ENCODING 'UTF8';

-- Create the application user (least privilege)
CREATE USER experiments_user WITH PASSWORD 'choose-a-strong-password';
GRANT CONNECT ON DATABASE experiments TO experiments_user;
\c experiments
GRANT USAGE ON SCHEMA public TO experiments_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO experiments_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO experiments_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO experiments_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO experiments_user;
```

---

## 3. Create the Power BI Reader Role

Power BI Desktop connects directly to PostgreSQL using a read-only role.
No dump file or ETL step is required.

Connect to PostgreSQL and run:

```sql
\c experiments
CREATE ROLE powerbi_reader WITH LOGIN PASSWORD 'choose-a-strong-password';
GRANT CONNECT ON DATABASE experiments TO powerbi_reader;
GRANT USAGE ON SCHEMA public TO powerbi_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO powerbi_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO powerbi_reader;
```

> **Note:** `ALTER DEFAULT PRIVILEGES` ensures the `powerbi_reader` role
> automatically gains SELECT on any tables created in the future (e.g., after
> a migration), without needing to re-run grants.

---

## 4. Connect Power BI Desktop

Use the **native PostgreSQL connector** (not ODBC):

1. Open Power BI Desktop
2. **Home → Get Data → More → Database → PostgreSQL Database**
3. Fill in:
   - **Server:** `<lab-pc-hostname>:5432` (use the lab PC's network name, not `localhost`)
   - **Database:** `experiments`
   - **Data Connectivity mode:** DirectQuery *(recommended — data updates without refresh)*
4. Click **OK**
5. When prompted for credentials:
   - Authentication method: **Database**
   - User name: `powerbi_reader`
   - Password: (the password you set above)
6. Click **Connect**

> **Tip:** To find the lab PC hostname, run `hostname` in a Command Prompt on the lab PC.

> **If connection fails:** Ensure PostgreSQL `postgresql.conf` has
> `listen_addresses = '*'` and `pg_hba.conf` has a host entry for the
> LAN subnet. See the Troubleshooting section.

---

## 5. Clone the Repository and Configure Environment

```bat
git clone <repo-url> C:\ExperimentTracking
cd C:\ExperimentTracking
copy .env.example .env
```

Edit `C:\ExperimentTracking\.env` and fill in all values:

```
DATABASE_URL=postgresql://experiments_user:<password>@localhost:5432/experiments
DB_USER=experiments_user
DB_NAME=experiments
DB_PASSWORD=<same password as above>
PG_BIN_PATH=C:\Program Files\PostgreSQL\16\bin
BACKUP_DIR=C:\ExperimentTracking\backups
FIREBASE_PROJECT_ID=<your Firebase project ID>
FIREBASE_PRIVATE_KEY=<your Firebase private key>
FIREBASE_CLIENT_EMAIL=<your Firebase client email>
APP_ENV=production
API_PORT=8000
CORS_ORIGINS=http://localhost:8000,http://<lab-pc-hostname>:8000
LOG_LEVEL=INFO
LAN_SUBNET=192.168.0.0/16
```

> **Note on `LAN_SUBNET`:** If your lab network uses `10.x.x.x` or `172.16.x.x`
> addresses, update `LAN_SUBNET` accordingly before running `install_services.bat`.

---

## 6. Install Python Dependencies

```bat
cd C:\ExperimentTracking
pip install -r requirements.txt
```

---

## 7. Run the Service Installer

Open a **Command Prompt as Administrator** and run:

```bat
cd C:\ExperimentTracking
scripts\install_services.bat C:\ExperimentTracking
```

This will:
- Install the `ExperimentTrackingAPI` Windows service via NSSM
- Configure auto-start, working directory, and log paths
- Add the Windows Firewall inbound rule for port 8000
- Start the service

---

## 8. Run the First Migration

```bat
cd C:\ExperimentTracking
alembic upgrade head
```

Verify:
```bat
alembic current
```
Expected output ends with `(head)`.

---

## 9. Verify the Service

```bat
sc query ExperimentTrackingAPI
```
Expected: `STATE: 4  RUNNING`

From the lab PC browser:
```
http://localhost:8000/health
```
Expected response: `{"status":"ok","service":"experiment_tracking_api"}`

From another machine on the LAN:
```
http://<lab-pc-hostname>:8000/health
```

---

## 10. Configure the Nightly Backup

1. Open **Task Scheduler** (search "Task Scheduler" in Start)
2. Click **Create Basic Task…**
3. Fill in:
   - **Name:** `ExperimentTracking-NightlyBackup`
   - **Trigger:** Daily at **02:00**
   - **Action:** Start a program
   - **Program/script:** `C:\ExperimentTracking\scripts\backup.bat`
   - **Start in:** `C:\ExperimentTracking`
4. Click **Finish**
5. Right-click the task → **Properties**:
   - Check **Run whether user is logged on or not**
   - Check **Run with highest privileges**
   - Click **OK** and enter your Windows credentials when prompted

To test the backup immediately:
```bat
C:\ExperimentTracking\scripts\backup.bat
```
Expected: a `.dump` file appears in your `BACKUP_DIR`.

---

## 11. Deploying Updates

When a new version is available, run from the repo root:

```bat
cd C:\ExperimentTracking
scripts\deploy.bat
```

This pulls from `main`, updates dependencies, runs migrations, and restarts the service. If any step fails, it rolls back to the previous commit and restarts.

---

## 12. Firewall Verification

```bat
netsh advfirewall firewall show rule name="ExperimentTracking-8000"
```

Expected output includes:
```
Action:                           Allow
Direction:                        In
LocalPort:                        8000
RemoteIP:                         192.168.0.0/16
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Service won't start | Bad `DATABASE_URL` or missing `.env` | Check `C:\ExperimentTracking\logs\uvicorn_stderr.log` |
| `alembic upgrade head` fails | PostgreSQL not running or wrong `DATABASE_URL` | `sc query postgresql-x64-16`; verify `.env` |
| Port 8000 unreachable from LAN | Firewall subnet mismatch | Check `LAN_SUBNET` in `.env`; re-run `install_services.bat` if needed |
| Power BI can't connect | PostgreSQL not listening on network | Set `listen_addresses = '*'` in `postgresql.conf`; add host entry for LAN in `pg_hba.conf`; restart PostgreSQL |
| Backup fails silently | Wrong `PG_BIN_PATH` | Run `backup.bat` from cmd to see error output; update `PG_BIN_PATH` in `.env` |
| `pg_hba.conf` auth error | Auth method not configured | Add `host all all 192.168.0.0/16 scram-sha-256` to `pg_hba.conf`; reload PostgreSQL |
```

- [ ] **Step 2: Commit**

```bash
git add docs/deployment/LAB_PC_SETUP.md
git commit -m "[Pre-M] Add docs/deployment/LAB_PC_SETUP.md

- Step-by-step Windows lab PC setup guide
- Covers PostgreSQL install, DB/user creation, Power BI reader role
- Power BI DirectQuery via native PostgreSQL connector (not ODBC)
- NSSM service install, backup schedule, deploy workflow
- Troubleshooting table for common issues
- Tests added: no
- Docs updated: yes (LAB_PC_SETUP.md created)"
```

---

### Task 13: Run full acceptance criteria verification

**Model:** sonnet

- [ ] **Step 1: Run all tests**

```bash
docker compose exec app pytest tests/test_connection.py tests/api/test_main.py -v
```
Expected: 6 tests PASS, 0 FAIL.

- [ ] **Step 2: Verify docker compose**

```bash
docker compose ps
```
Expected: `experiment_tracking_postgres`, `experiment_tracking_app`, `experiment_tracking_pgadmin` all running.

- [ ] **Step 3: Verify health endpoint**

```bash
curl -s http://localhost:8000/health
```
Expected: `{"status":"ok","service":"experiment_tracking_api"}`

- [ ] **Step 4: Verify alembic runs clean against Docker PostgreSQL**

```bash
docker compose exec app alembic upgrade head
docker compose exec app alembic current
```
Expected: exits 0; current shows `(head)`.

- [ ] **Step 5: Verify no secrets in committed files**

```bash
grep -rn "experiments_dev_password\|private_key.*=.*[A-Za-z0-9]" .env.example || echo "CLEAN"
```
Expected: `CLEAN`

- [ ] **Step 6: Verify .env is gitignored**

```bash
git check-ignore -v .env
```
Expected: `.gitignore:.env  .env`

- [ ] **Step 7: Verify structlog is in requirements.txt and importable in the container**

```bash
grep structlog requirements.txt
```
Expected: `structlog==24.4.0`

```bash
docker compose exec app python -c "import structlog; print(structlog.__version__)"
```
Expected: prints `24.4.0`. If `ModuleNotFoundError`, run `docker compose exec app pip install -r requirements.txt` then retry.

- [ ] **Step 7b: Verify GET / returns 404 (no frontend/dist yet)**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/
```
Expected: `404`. If `200` with JSON body, the old `GET /` handler was not removed — go back to Task 8.

- [ ] **Step 8: Verify stale dotenv package removed**

```bash
grep "^dotenv==" requirements.txt && echo "STILL PRESENT - FIX THIS" || echo "CLEAN"
```
Expected: `CLEAN`

- [ ] **Step 9: Create PR to develop**

```bash
git push origin infra/lab-pc-server-setup
```
Then open a PR from `infra/lab-pc-server-setup` → `develop`.

---

## Summary

| Task | Files | Model |
|---|---|---|
| 1. Branch | — | — |
| 2. Fix requirements.txt | `requirements.txt` | haiku |
| 3. Update .env.example | `.env.example` | haiku |
| 4. Add pgAdmin to docker-compose.yml | `docker-compose.yml` | haiku |
| 5. Tests for connection.py | `tests/test_connection.py` | sonnet |
| 6. Create database/connection.py | `database/connection.py` | sonnet |
| 7. Tests for main.py changes | `tests/api/test_main.py` | sonnet |
| 8. Update backend/api/main.py | `backend/api/main.py` | sonnet |
| 9. Create scripts/deploy.bat | `scripts/deploy.bat` | sonnet |
| 10. Create scripts/backup.bat | `scripts/backup.bat` | sonnet |
| 11. Create scripts/install_services.bat | `scripts/install_services.bat` | sonnet |
| 12. Create LAB_PC_SETUP.md | `docs/deployment/LAB_PC_SETUP.md` | haiku |
| 13. Acceptance verification | — | sonnet |
