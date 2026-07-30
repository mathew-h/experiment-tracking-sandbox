# Production Deployment Guide

This guide covers deploying the Experiment Tracking System on the lab PC as a Windows service accessible to all users on the LAN.

## Prerequisites

Before starting, ensure the following are installed and running on the lab PC:

- **PostgreSQL 16+** — configured as a Windows service, database created
- **Node 18+** — only needed to build the frontend; can be uninstalled after
- **Python 3.11+** — used for the venv and application runtime
- **NSSM** (Non-Sucking Service Manager) — used to register uvicorn as a Windows service; download from [nssm.cc](https://nssm.cc)
- **Firebase project credentials** — `PROJECT_ID`, `PRIVATE_KEY`, `CLIENT_EMAIL`, `API_KEY`, `AUTH_DOMAIN`

---

## One-Time Setup

### 1. Clone the repository

```powershell
git clone https://github.com/mathew-h/experiment-tracking-sandbox.git C:\Apps\experiment-tracking
cd C:\Apps\experiment-tracking
```

### 2. Create `.env` with production values

```powershell
copy .env.example .env
notepad .env
```

Fill in all required values:

```
DATABASE_URL=postgresql://user:password@localhost:5432/experiments
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
FIREBASE_CLIENT_EMAIL=firebase-adminsdk-xxx@your-project.iam.gserviceaccount.com
FIREBASE_API_KEY=your-web-api-key
FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
APP_ENV=production
API_PORT=8000
CORS_ORIGINS=http://localhost:8000,http://<lab-pc-hostname>:8000
LOG_LEVEL=INFO
BACKUP_DIR=C:\Backups\experiments
PUBLIC_COPY_DIR=\\server\shared\experiment-exports
```

### 3. Create venv and install Python dependencies

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 4. Run database migrations

```powershell
.venv\Scripts\alembic upgrade head
```

### 5. Build the frontend

```powershell
cd frontend
npm install
npm run build
cd ..
```

The build output lands in `frontend/dist/`. FastAPI serves these static files at the root URL — no separate Node server is needed in production.

### 6. Run `setup.ps1`

Right-click `setup.ps1` at the repo root and choose **Run with PowerShell**. This handles all remaining setup automatically:
- Creates the Python virtual environment and installs dependencies
- Runs database migrations
- Builds the React frontend
- Registers the `ExperimentTracker` Windows service via NSSM (auto-starts on boot)
- Opens the firewall on port 8000 (Private + Domain profiles)
- Registers a nightly update task in Task Scheduler

See `docs/deployment/STARTUP_GUIDE.md` for the full step-by-step walkthrough, including credential requirements and troubleshooting.

### 7. Verify access

Users on the LAN can now open:
```
http://<lab-pc-hostname>:8000
```

---

## Updating the App

Right-click `update.ps1` at the repo root and choose **Run with PowerShell**, or wait for the nightly scheduled update (runs at 02:00 by default).

The script automatically detects what changed (Python dependencies, database migrations, frontend files) and only rebuilds what is needed, then restarts the service.

To check the update log:
```powershell
Get-Content "C:\Logs\experiment-tracker\updates.log" -Tail 20
```

### The lab PC must never hold local changes

**This checkout is a deploy target, not a workspace.** Do not edit files here, and do not
run a coding agent against it that can write to tracked files. Any local modification
blocks `git pull`, and because the nightly job only writes `FAILED` to the log, the machine
then silently stops updating. On 2026-07-30 it was found 22 commits behind, having failed
this way for ten days; the same thing had happened on 2026-07-20 and been worked around
with a `git stash` rather than fixed.

`update.ps1` now defends itself, but prevention is still better than recovery:

| Guard | Why |
|-------|-----|
| The service is **stopped before** `git pull` and started after | A running Python process holding open file handles can make a pull apply only *partially*, which is the likeliest origin of the dirty tree. Because a failure would now leave the app offline rather than merely stale, every exit path — including `Abort` — calls `Start-TrackerService`. |
| A dirty tree is **discarded** before pulling, and each discarded entry is logged | Turns a permanently-stuck deploy into a self-healing one, while leaving evidence in `updates.log` so a recurrence is visible instead of silent. |
| HEAD is **verified against `origin/main`** after the pull | A partially applied update can no longer report `SUCCESS`. |

Two details in that script are load-bearing and must not be "simplified":

- The reset is `git reset --hard HEAD`, **never** `origin/main`. Resetting to `origin/main`
  moves HEAD itself, so the script's own `git pull` finds nothing to do, `$headBefore`
  equals `$headAfter`, the "no new commits" branch fires, and **the frontend is never
  rebuilt** — a deploy that logs SUCCESS while serving a stale `frontend/dist`.
- The clean is `git clean -fd`, **never** `-fdx`. `-x` deletes ignored files, which here
  means `.venv` (containing the `pip.exe` and `alembic.exe` this script runs), `.env`,
  `frontend/.env.local`, `node_modules` and `frontend/dist`. None are recoverable from the
  repository.

`tests/deployment/test_update_script.py` asserts all of the above.

### If a deploy fails on `git pull`

The script now recovers on its own, but to do it by hand — from `C:\Apps\experiment-tracking`:

```powershell
git stash list                 # anything already stashed? archive it before touching anything
git fetch origin main
git status --porcelain

# Confirm nothing unique is at risk: every untracked file should be IDENTICAL to upstream.
git ls-files --others --exclude-standard | ForEach-Object {
  $local = git hash-object -- $_
  $main  = git rev-parse "origin/main:$_" 2>$null
  if ($LASTEXITCODE -ne 0) { "ONLY-LOCAL  $_" }
  elseif ($local -eq $main) { "IDENTICAL   $_" }
  else                      { "DIFFERS     $_" }
}
```

`ONLY-LOCAL` or `DIFFERS` means real work exists only on this machine — recover it before
continuing. Otherwise clear the tree (`git reset --hard HEAD`, `git clean -fd`) and re-run
`update.ps1`. Note that **`git diff origin/main` is not a useful check here**: it compares
against the index, so on a checkout that is behind it reports every missing commit's
content as a deletion, which looks alarming and means nothing.

Stashes are not touched by `reset --hard` or `clean -fd`, so old ones accumulate silently —
`git stash list` is worth checking periodically.

---

## Database Backups

A daily backup is recommended. Until an automated backup script is in place, run this manually or via Windows Task Scheduler:

```powershell
pg_dump -U postgres experiments > "C:\Backups\experiments\experiments_%DATE:~-4,4%%DATE:~-7,2%%DATE:~-10,2%.sql"
```

Store backups on a separate drive or network share. The `BACKUP_DIR` env var is reserved for a future automated backup service.

---

## Adding Users

New users must register at `http://<lab-pc-hostname>:8000` with an `@addisenergy.com` email address. Their account is not active until an admin approves it.

**Create a user directly (admin only):**
```powershell
cd C:\Apps\experiment-tracking
.venv\Scripts\python scripts\manage_users.py create user@addisenergy.com TempPassword123 "Display Name"
```

**List pending registration requests:**
```powershell
.venv\Scripts\python scripts\manage_users.py pending
```

**Approve a registration request:**
```powershell
.venv\Scripts\python scripts\manage_users.py approve <request_id>
```

## Troubleshooting

**View application logs:**
```powershell
nssm get ExperimentTracker AppStdout   # shows log file path
type C:\Logs\experiment-tracker\stdout.log | more
```

**Restart the service:**
```powershell
nssm restart ExperimentTracker
```

**Service won't start — check environment:**
```powershell
nssm get ExperimentTracker AppEnvironmentExtra
```

**Database connection errors:**
Verify PostgreSQL is running and `DATABASE_URL` in `.env` is correct:
```powershell
.venv\Scripts\python -c "from database.db import engine; print(engine.connect())"
```

**Frontend not loading (blank page or 404):**
Confirm the build completed and `frontend/dist/index.html` exists. Rebuild if necessary:
```powershell
cd frontend && npm run build
```
