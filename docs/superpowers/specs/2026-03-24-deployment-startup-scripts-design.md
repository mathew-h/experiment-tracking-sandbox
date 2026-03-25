# Design Spec: Deployment Startup Scripts
**Date:** 2026-03-24
**Branch:** `chore/deployment-startup-scripts`
**Status:** Approved

---

## Problem

The root directory contains two broken scripts tied to the old Streamlit architecture:

- `start_app.bat` — launches `python -m streamlit run app.py`; irrelevant to the new FastAPI + React stack
- `auto_update.bat` — calls `python -m utils.auto_updater`; the module does not exist

The new production architecture (FastAPI + React static build served via uvicorn, managed as a Windows service via NSSM) has no equivalent "start the app" script, and no functional update mechanism. A lab PC tech (comfortable following instructions but not a developer) has no clear path from `git clone` to a running application.

---

## Goals

1. Delete the broken legacy scripts
2. Provide a seamless post-clone experience: one script, run once, app starts forever
3. Provide an update mechanism: one script, run manually or nightly via Task Scheduler
4. Update deployment documentation to reflect the new scripts

---

## Non-Goals

- Docker or containerisation
- Remote deployment or CI/CD
- A service management UI (start/stop/restart are handled via `nssm` commands documented in the troubleshooting guide)
- Per-user credential management beyond `.env`

---

## Audience

A lab technician who can follow step-by-step written instructions but should not need to understand what the scripts do internally. Scripts must fail fast with clear, actionable error messages.

---

## Architecture

### Files Deleted
| File | Reason |
|---|---|
| `start_app.bat` | Launches old Streamlit app; NSSM replaces its purpose |
| `auto_update.bat` | Calls non-existent `utils.auto_updater` module |

### Files Created
| File | Purpose | When run | Admin required |
|---|---|---|---|
| `setup.ps1` | One-time post-clone setup | Once, after cloning | Yes (self-elevates) |
| `update.ps1` | Pull latest, migrate, rebuild, restart | Manually or nightly | Yes (self-elevates for service restart) |

### Docs Updated
| File | Change |
|---|---|
| `docs/deployment/PRODUCTION_DEPLOYMENT.md` | Replace manual NSSM steps with reference to `setup.ps1`; add `update.ps1` to update section |
| `docs/deployment/STARTUP_GUIDE.md` | New file — full post-clone walkthrough, Task Scheduler verification, troubleshooting |

---

## `setup.ps1` — Detailed Flow

**Trigger:** Run once after cloning the repository.
**Elevation:** Self-elevates to admin at the top of the script using a UAC re-launch pattern.

### Steps (in order)

1. **Preflight checks**
   - Verify Python 3.11+ is on PATH
   - Verify Node 18+ is on PATH
   - Verify NSSM is on PATH
   - Verify git is on PATH
   - On any failure: print actionable message and exit 1 (e.g., "NSSM not found — download from nssm.cc and add to PATH, then re-run setup.ps1")

2. **`.env` check**
   - If `.env` does not exist: copy `.env.example` → `.env`
   - Print the full path to `.env`
   - Pause: "Fill in your credentials in `.env`, then press any key to continue"
   - If `.env` already exists: skip silently

3. **Create venv + install Python dependencies**
   - `python -m venv .venv`
   - `.venv\Scripts\pip install -r requirements.txt`

4. **Run database migrations**
   - `.venv\Scripts\alembic upgrade head`

5. **Build frontend**
   - `npm install` in `frontend/`
   - `npm run build` in `frontend/`
   - Output lands in `frontend/dist/` (served as static files by FastAPI)

6. **Create log directories**
   - `C:\Logs\experiment-tracker\` (stdout, stderr, updates)

7. **Register NSSM service**
   - Service name: `ExperimentTracker`
   - Executable: `.venv\Scripts\uvicorn.exe`
   - Parameters: `backend.api.main:app --host 0.0.0.0 --port 8000`
   - Working directory: repo root
   - Env extra: `DOTENV_PATH=<repo-root>\.env`
   - Stdout log: `C:\Logs\experiment-tracker\stdout.log`
   - Stderr log: `C:\Logs\experiment-tracker\stderr.log`
   - Start type: `SERVICE_AUTO_START`

8. **Open firewall**
   - `New-NetFirewallRule` for port 8000, inbound, TCP, private profile only
   - Skip if rule named "Experiment Tracker" already exists

9. **Register nightly update task**
   - Task name: `ExperimentTrackerUpdate`
   - Trigger: daily at 02:00
   - Action: `powershell.exe -ExecutionPolicy Bypass -File "<repo-root>\update.ps1"`
   - Run whether user is logged on or not
   - On failure: retry once after 5 minutes
   - Configurable via `$UpdateTime` variable at top of `setup.ps1` (default `"02:00"`)

10. **Start service**
    - `nssm start ExperimentTracker`

11. **Success message**
    - Print: `Setup complete. App running at http://<hostname>:8000`
    - Print: `Nightly updates scheduled at <UpdateTime>`

---

## `update.ps1` — Detailed Flow

**Trigger:** Run manually (right-click → Run with PowerShell) or by Task Scheduler nightly.
**Elevation:** Self-elevates when service restart requires admin.
**Log:** Appends timestamped result to `C:\Logs\experiment-tracker\updates.log`.

### Steps (in order)

1. **`git pull`**
   - Pull from tracked remote branch
   - On failure (merge conflict, detached HEAD, network error): log error, exit 1, do not proceed

2. **Detect changed files**
   - `git diff HEAD@{1} --name-only` against previous HEAD
   - Set flags:
     - `$reinstallDeps` — true if `requirements.txt` changed
     - `$runMigrations` — true if any file under `alembic/versions/` changed
     - `$rebuildFrontend` — true if any file under `frontend/src/` or `frontend/package.json` changed

3. **Conditionally: reinstall Python dependencies**
   - If `$reinstallDeps`: `.venv\Scripts\pip install -r requirements.txt`

4. **Conditionally: run migrations**
   - If `$runMigrations`: `.venv\Scripts\alembic upgrade head`

5. **Conditionally: rebuild frontend**
   - If `$rebuildFrontend`: `npm run build` in `frontend/`

6. **Restart service**
   - `nssm restart ExperimentTracker`
   - Always runs regardless of which steps above ran

7. **Log outcome**
   - Append to `C:\Logs\experiment-tracker\updates.log`:
     `[2026-03-24 02:01:15] SUCCESS — deps:no migrations:yes frontend:no`
   - On any failure: `[2026-03-24 02:01:15] FAILED — step: migrations — error: <message>`

8. **Exit code**
   - Exit 0 on success, exit 1 on any failure (allows Task Scheduler to detect failures)

---

## Task Scheduler — Auto-Start on Boot

NSSM's `SERVICE_AUTO_START` flag handles boot-time startup at the service level — the service starts before any user logs in, survives reboots and power outages. No Task Scheduler entry is needed for this.

The `ExperimentTrackerUpdate` Task Scheduler entry (registered by `setup.ps1`) is only for nightly updates.

---

## Documentation Changes

### `docs/deployment/STARTUP_GUIDE.md` (new)

Sections:
1. **Prerequisites** — Python 3.11+, Node 18+, NSSM, git — with download links
2. **First-time setup** — clone → fill `.env` → run `setup.ps1` → verify at `http://<hostname>:8000`
3. **Manual updates** — right-click `update.ps1` → Run with PowerShell
4. **Verify scheduled updates** — how to check the Task Scheduler entry (UI path + PowerShell one-liner)
5. **Troubleshooting** — service won't start, port blocked, blank frontend, update failed — each with a diagnostic one-liner

### `docs/deployment/PRODUCTION_DEPLOYMENT.md` (updated)

- **One-time setup section:** replace manual NSSM steps 6–7 with: "Run `setup.ps1` as administrator — this handles all service registration and firewall setup. See `STARTUP_GUIDE.md` for the full walkthrough."
- **Updating the app section:** replace manual steps with: "Run `update.ps1` — or wait for the nightly scheduled update."
- All other sections (PostgreSQL backup, user management, master results path, troubleshooting) remain unchanged.

---

## Error Handling Principles

- Both scripts fail fast: any step failure aborts the script and prints a clear message
- No silent failures — every step is wrapped in error checking
- Exit codes are meaningful: 0 = success, 1 = failure (required for Task Scheduler)
- Admin elevation is automatic: scripts re-launch themselves elevated via UAC if not already admin

---

## Acceptance Criteria

- [ ] `start_app.bat` and `auto_update.bat` are deleted
- [ ] `setup.ps1` runs end-to-end on a fresh clone and leaves the service running
- [ ] `setup.ps1` is idempotent: re-running after a successful setup does not break anything
- [ ] `update.ps1` correctly detects changed file paths and skips unnecessary steps
- [ ] `update.ps1` exits 1 on git pull failure and does not restart the service
- [ ] Task Scheduler entry `ExperimentTrackerUpdate` is registered and runs `update.ps1`
- [ ] `STARTUP_GUIDE.md` covers all steps a lab tech needs without assuming developer knowledge
- [ ] `PRODUCTION_DEPLOYMENT.md` is updated to reference the new scripts
