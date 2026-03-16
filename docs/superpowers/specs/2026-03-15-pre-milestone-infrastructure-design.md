# Pre-Milestone Infrastructure Setup — Design Spec
**Date:** 2026-03-15
**Branch:** `infra/lab-pc-server-setup`
**Conductor:** Claude Code
**Status:** Approved (v3 — post spec-review round 2)

---

## Scope

Deliver the infrastructure layer that transforms the lab PC from a Streamlit host into a proper application server. This milestone produces no user-facing features — it produces the platform everything else runs on.

Two distinct environments are in scope:

| Environment | PostgreSQL | Python app | Notes |
|---|---|---|---|
| **Development** | Docker container | Docker container | Already running via `docker compose up` |
| **Production (lab PC)** | Native Windows service | uvicorn Windows service via NSSM | Scripts target this environment |

Docker Compose is **dev-only**. The Windows scripts (`deploy.bat`, `backup.bat`, `install_services.bat`) target the production lab PC exclusively.

**CLAUDE.md note:** CLAUDE.md Section 2 (Target State) and Section 6 (Pre-Milestone task 7) describe a "read-only dump for Power BI on 12-hour schedule." This spec supersedes that description: Power BI connects directly to PostgreSQL via a `powerbi_reader` role (SELECT-only). No dump-based delivery. CLAUDE.md should be updated at session end via `/revise-claude-md`.

---

## Deliverables

### 1. `docker-compose.yml` — add pgAdmin service

**Change:** Append a `pgadmin` service and `pgadmin_data` named volume. All existing services (`postgres`, `app`) are unchanged.

- Image: `dpage/pgadmin4:latest`
- Port: `5050:80`
- Credentials hardcoded in `docker-compose.yml` (dev-only tool, not in `.env.example`). This is an accepted exception to the "no hardcoded secrets" rule, scoped to this dev-only service. Use `PGADMIN_DEFAULT_EMAIL: admin@lab.local` and `PGADMIN_DEFAULT_PASSWORD: pgadmin_dev`.
- Depends on `postgres` being healthy
- Data volume: `pgadmin_data` named volume
- Network: `app_network`

### 2. `database/connection.py` — new file

SQLAlchemy 2.0 sync engine for the FastAPI app layer.

```python
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]  # hard fail if missing

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- Uses `python-dotenv` (`load_dotenv()`) as a **temporary measure** for Pre-Milestone. This will be refactored to use `backend/core/config.py` (pydantic-settings) in Milestone 2.
- Add a `# TODO M2: replace with backend.core.config.Settings` comment on the DATABASE_URL line.
- Sync `Session` — matches existing codebase; lab has 2-5 users; async not needed.
- `pool_pre_ping=True` — recycles stale connections.
- Alembic continues to use its own engine in `alembic/env.py` — no change there.

### 3. `backend/api/main.py` — add static file mount + fix root handler

**Two changes:**

**a) Remove the existing `GET /` JSON handler.** It conflicts with the `StaticFiles` mount — the JSON handler would shadow `index.html` and break SPA navigation. Replace with `GET /api/` (or simply remove it; `/health` is sufficient for liveness checks).

**b) Add `StaticFiles` mount at the end of the file**, after all API routes:

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static")
```

Using `Path(__file__).parent.parent.parent` (absolute path relative to `main.py`) ensures correct resolution regardless of NSSM `AppDirectory` or current working directory. The `if` guard lets the app start cleanly before the frontend is built.

### 4. `scripts/deploy.bat` — production lab PC

**Purpose:** Replaces `auto_update.bat`. Pulls latest code and restarts the service.

**Implementation notes:**

Capture `HEAD` before pull to make rollback safe under all failure modes:

```bat
for /f %%i in ('git rev-parse HEAD') do set PREV_HASH=%%i
```

Use `%PREV_HASH%` (not `HEAD@{1}`) in the rollback handler.

**Sequence:**
1. Capture current commit hash → `%PREV_HASH%`
2. `git pull origin main` — on failure → rollback
3. `pip install -r requirements.txt` — on failure → rollback
4. `alembic upgrade head` — on failure → rollback + print migration warning (see below)
5. `C:\nssm\nssm.exe restart ExperimentTrackingAPI` — on failure → rollback

**Rollback handler:**
1. `git reset --hard %PREV_HASH%`
2. `C:\nssm\nssm.exe restart ExperimentTrackingAPI`
3. Print: `DEPLOY FAILED at step [N]. Service restarted on previous code.`
4. Print: `WARNING: If alembic upgrade ran before failure, schema may be ahead of code. Manual intervention may be required.`
5. `exit /b 1`

**Migration rollback caveat:** The script explicitly warns when the failure occurs after `alembic upgrade head`. It does NOT auto-run `alembic downgrade` — that is a manual operator decision because downgrades can be destructive. The warning in step 4 above surfaces this condition.

**Assumptions:**
- NSSM at `C:\nssm\nssm.exe`
- Python and `alembic` in PATH
- Service name: `ExperimentTrackingAPI`

### 5. `scripts/backup.bat` — production lab PC

**Purpose:** One job — nightly full `pg_dump` with 30-day retention.

**Sequence:**
1. Read vars from `.env` using `for /f "tokens=1,* delims==" %%a in (.env) do` pattern — the `tokens=1,*` idiom captures the full value after the first `=`, correctly handling values that contain spaces (e.g. `C:\Program Files\PostgreSQL\16\bin`). Skip comment lines (starting with `#`) and blank lines.
2. Set `PGPASSWORD=%DB_PASSWORD%` — standard mechanism for non-interactive pg_dump authentication; password visible in process environment but not in logs or script text
3. Generate filename: `experiments_YYYYMMDD_HHMMSS.dump`
4. `"%PG_BIN%\pg_dump" -Fc -h localhost -U %DB_USER% %DB_NAME% -f "%BACKUP_DIR%\%FILENAME%"`
5. Check `%ERRORLEVEL%` — if non-zero, print `ERROR: pg_dump failed (exit code %ERRORLEVEL%). Backup was NOT created.` and exit with error code 1
6. Clear `PGPASSWORD` immediately: `set PGPASSWORD=`
7. `forfiles /p "%BACKUP_DIR%" /s /m *.dump /d -30 /c "cmd /c del @path"` — delete files older than 30 days

**`PG_BIN` variable:** Read from `.env` as well (key: `PG_BIN_PATH`), defaulting to `C:\Program Files\PostgreSQL\16\bin` if not set. This makes the PostgreSQL version/path configurable without editing the script.

**`.env.example` additions:** `PG_BIN_PATH=C:\Program Files\PostgreSQL\16\bin`, `DB_USER=experiments_user`, `DB_NAME=experiments`, `DB_PASSWORD=`

**Power BI access:** Direct PostgreSQL connection using `powerbi_reader` role. No dump file involved. See LAB_PC_SETUP.md.

**Scheduling:** Windows Task Scheduler, nightly at 02:00. Documented in LAB_PC_SETUP.md — not automated by this script.

### 6. `scripts/install_services.bat` — idempotent NSSM setup

**Purpose:** One-time setup of the uvicorn Windows service on the lab PC.

**Usage:** `install_services.bat C:\path\to\repo`

**Steps:**
1. Check if service exists: `sc query ExperimentTrackingAPI >nul 2>&1` — if found, skip install step (still apply `set` commands for idempotency)
2. Install: `C:\nssm\nssm.exe install ExperimentTrackingAPI python`
3. Set arguments separately (NSSM requires this): `C:\nssm\nssm.exe set ExperimentTrackingAPI AppParameters "-m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000"`
4. Set working directory: `C:\nssm\nssm.exe set ExperimentTrackingAPI AppDirectory "%REPO_PATH%"`
5. Set auto-start: `C:\nssm\nssm.exe set ExperimentTrackingAPI Start SERVICE_AUTO_START`
6. Set stdout/stderr log: `C:\nssm\nssm.exe set ExperimentTrackingAPI AppStdout "%REPO_PATH%\logs\uvicorn.log"` and `AppStderr`
7. Read `LAN_SUBNET` from `.env` (same `for /f` parsing as backup.bat); default to `192.168.0.0/16` if not set. Add a note: if the lab network is `10.x.x.x` or `172.16.x.x`, set `LAN_SUBNET` in `.env` before running.
8. Check if firewall rule exists: `netsh advfirewall firewall show rule name="ExperimentTracking-8000" >nul 2>&1`
9. If not found: `netsh advfirewall firewall add rule name="ExperimentTracking-8000" protocol=TCP dir=in localport=8000 action=allow remoteip=%LAN_SUBNET%`
10. Start service: `C:\nssm\nssm.exe start ExperimentTrackingAPI`

**Assumptions:**
- NSSM at `C:\nssm\nssm.exe`
- Python in PATH
- First argument (`%1`) is the repo root path
- `LAN_SUBNET` in `.env` (optional; defaults to `192.168.0.0/16` if absent)

### 7. `requirements.txt` — add `structlog`, remove stale `dotenv`

Two changes:

1. **Add** `structlog==24.4.0` — absent from `requirements.txt` but required by CLAUDE.md Section 8 for all logging. Pin to `24.4.0` to match the fully-pinned convention of the rest of the file.

2. **Remove** `dotenv==0.9.9` (line 13) — this is a stale, incorrect PyPI package (an unrelated stub). The correct package `python-dotenv==1.0.1` is already present. Leaving both installed causes a spurious import resolution. Delete the `dotenv==0.9.9` line entirely.

### 8. `.env.example` — update

Ensure all vars from CLAUDE.md Section 5 are present. The existing `DATABASE_URL` line contains `experiments_dev_password` — this must be **blanked** (`DATABASE_URL=`) to comply with "no secrets in committed files."

Final complete `.env.example`:

```
# Database
DATABASE_URL=
DB_USER=experiments_user
DB_NAME=experiments
DB_PASSWORD=

# PostgreSQL binary path (production Windows only)
PG_BIN_PATH=C:\Program Files\PostgreSQL\16\bin

# Firebase Authentication
FIREBASE_PROJECT_ID=
FIREBASE_PRIVATE_KEY=
FIREBASE_CLIENT_EMAIL=

# Application
APP_ENV=development
API_PORT=8000
CORS_ORIGINS=

# Logging
LOG_LEVEL=INFO

# Backups (production Windows only)
BACKUP_DIR=
PUBLIC_COPY_DIR=

# Network (production Windows only — set if lab is NOT on 192.168.x.x)
LAN_SUBNET=192.168.0.0/16
```

### 9. `docs/deployment/LAB_PC_SETUP.md`

Step-by-step Windows setup guide. Sections:

**1. Prerequisites**
- Windows 10/11 Pro (required for Windows Services)
- Python 3.11+ (add to PATH during install)
- Git for Windows
- NSSM: download from nssm.cc, extract `nssm.exe` to `C:\nssm\nssm.exe`

**2. PostgreSQL for Windows**
- Download PostgreSQL 16 Windows installer from postgresql.org
- Install as a Windows service (default option in installer)
- Verify auto-start: `sc query postgresql-x64-16`
- Note the PostgreSQL bin path (default: `C:\Program Files\PostgreSQL\16\bin`)

**3. Database and application user**
```sql
CREATE DATABASE experiments ENCODING 'UTF8';
CREATE USER experiments_user WITH PASSWORD 'choose-a-strong-password';
GRANT CONNECT ON DATABASE experiments TO experiments_user;
\c experiments
GRANT USAGE ON SCHEMA public TO experiments_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO experiments_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO experiments_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO experiments_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO experiments_user;
```

**4. Power BI reader role**
```sql
\c experiments
CREATE ROLE powerbi_reader WITH LOGIN PASSWORD 'choose-a-strong-password';
GRANT CONNECT ON DATABASE experiments TO powerbi_reader;
GRANT USAGE ON SCHEMA public TO powerbi_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO powerbi_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO powerbi_reader;
```

**5. Power BI Desktop connection**
- Open Power BI Desktop → Get Data → Database → PostgreSQL
- Server: `<lab-pc-hostname>:5432` (use the lab PC's network hostname, not `localhost`)
- Database: `experiments`
- Data Connectivity mode: Import or DirectQuery (DirectQuery recommended for live data)
- Credentials: Database authentication → Username: `powerbi_reader` / Password: (set above)
- Do NOT use ODBC connector — use the native PostgreSQL connector

**6. Clone repo and configure .env**
- `git clone <repo-url> C:\ExperimentTracking`
- `cd C:\ExperimentTracking`
- `copy .env.example .env`
- Edit `.env`: fill in `DATABASE_URL`, `DB_USER`, `DB_NAME`, `DB_PASSWORD`, `PG_BIN_PATH`, `BACKUP_DIR`, Firebase vars

**7. Install Python dependencies**
- `pip install -r requirements.txt`

**8. Run install_services.bat**
- Open Command Prompt as Administrator
- `scripts\install_services.bat C:\ExperimentTracking`

**9. First migration**
- `alembic upgrade head`
- Verify: `alembic current` should show `head`

**10. Verify service**
- `sc query ExperimentTrackingAPI` → should show `RUNNING`
- Browse to `http://localhost:8000/health` → should return `{"status": "ok"}`
- Browse from another LAN machine: `http://<lab-pc-hostname>:8000/health`

**11. Configure backup schedule**
- Open Task Scheduler → Create Basic Task
- Name: `ExperimentTracking-NightlyBackup`
- Trigger: Daily at 02:00
- Action: Start a program → `C:\ExperimentTracking\scripts\backup.bat`
- Run whether user is logged in or not; Run with highest privileges

**12. Firewall verification**
```bat
netsh advfirewall firewall show rule name="ExperimentTracking-8000"
```
Expected: `Action: Allow`, `RemoteIP: 192.168.0.0/16`, `LocalPort: 8000`

**13. Troubleshooting**
- Service won't start: Check `logs\uvicorn.log` and `logs\uvicorn_stderr.log`; verify `DATABASE_URL` in `.env`
- PostgreSQL auth error: Verify `pg_hba.conf` allows `md5` or `scram-sha-256` for local connections
- Port 8000 unreachable from LAN: Verify firewall rule subnet matches actual LAN (check `LAN_SUBNET` in `.env`; if lab is on `10.x.x.x` or `172.16.x.x`, update accordingly and re-run `install_services.bat`). Also verify Windows Defender Firewall is not blocking.
- Power BI can't connect: Ensure PostgreSQL `listen_addresses = '*'` in `postgresql.conf` and `pg_hba.conf` has a host entry for the LAN subnet

---

## Acceptance Criteria

- [ ] `docker compose up -d` starts PostgreSQL, app, and pgAdmin cleanly
- [ ] `alembic upgrade head` runs against Dockerized PostgreSQL without errors
- [ ] `GET /health` returns `{"status": "ok", "service": "experiment_tracking_api"}`
- [ ] `GET /` returns React SPA (if `frontend/dist` exists) or 404 (if not built yet — acceptable)
- [ ] All `.bat` scripts are syntactically valid
- [ ] No secrets in any committed file (`.env.example` has all values blanked)
- [ ] `.env` is in `.gitignore` (already confirmed)
- [ ] `database/connection.py` imports cleanly and `get_db` yields a `Session`
- [ ] `structlog` present in `requirements.txt`

---

## Files Changed / Created

| File | Action |
|---|---|
| `docker-compose.yml` | Edit — add pgAdmin service + `pgadmin_data` volume |
| `database/connection.py` | Create |
| `backend/api/main.py` | Edit — remove `GET /` JSON handler, add static file mount |
| `scripts/deploy.bat` | Create |
| `scripts/backup.bat` | Create |
| `scripts/install_services.bat` | Create |
| `requirements.txt` | Edit — add `structlog==24.4.0`, remove stale `dotenv==0.9.9` |
| `.env.example` | Edit — blank existing password value, add backup/DB vars |
| `docs/deployment/LAB_PC_SETUP.md` | Create |

---

## Out of Scope

- FastAPI routers beyond the skeleton (Milestone 3)
- React frontend (Milestone 4+)
- Calculation engine (Milestone 2)
- `backend/core/config.py` pydantic-settings module (Milestone 2) — `connection.py` uses python-dotenv as a temporary measure with a TODO comment
- Any modification to the legacy Streamlit app
- Any modification to existing bulk upload parsers
- Modifying any locked SQLAlchemy model
- Alembic downgrade automation in `deploy.bat` — migration rollback is a manual operator decision
