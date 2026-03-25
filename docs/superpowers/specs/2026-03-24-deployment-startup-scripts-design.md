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
   - Print the list of required fields (DATABASE_URL, FIREBASE_PROJECT_ID, FIREBASE_PRIVATE_KEY, FIREBASE_CLIENT_EMAIL, FIREBASE_API_KEY, FIREBASE_AUTH_DOMAIN)
   - Pause: "Fill in all required values in `.env`, then press any key to continue"
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

7. **Register NSSM service (idempotent)**
   - Service name: `ExperimentTracker`
   - Check if service already exists via `nssm status ExperimentTracker`; if it does, skip registration entirely (print "Service already registered — skipping")
   - Executable: `.venv\Scripts\uvicorn.exe` — implementer must verify this path resolves correctly for the repo structure; the uvicorn entry point is `backend.api.main:app`
   - Parameters: `backend.api.main:app --host 0.0.0.0 --port 8000`
   - Working directory: repo root (absolute path, derived from script location)
   - Env extra: `DOTENV_PATH=<repo-root>\.env`
   - Stdout log: `C:\Logs\experiment-tracker\stdout.log`
   - Stderr log: `C:\Logs\experiment-tracker\stderr.log`
   - Start type: `SERVICE_AUTO_START`

8. **Open firewall (idempotent)**
   - `New-NetFirewallRule` for port 8000, inbound, TCP, Private **and Domain** profiles
   - Skip if rule named "Experiment Tracker" already exists
   - **Note:** Both Private and Domain profiles are included because Windows may classify a domain-joined lab network as Domain rather than Private; using only Private would silently block LAN access in that environment

9. **Register nightly update task**
   - Task name: `ExperimentTrackerUpdate`
   - Trigger: daily at 02:00 (configurable via `$UpdateTime` variable at top of `setup.ps1`)
   - Action: `powershell.exe -ExecutionPolicy Bypass -File "<repo-root>\update.ps1"`
   - Principal: the **current user** (the admin running `setup.ps1`), with password stored in the Task Scheduler credential vault
   - `setup.ps1` will prompt for the current user's Windows password to store credentials — this is a Windows requirement for tasks that run when the user is not logged in
   - **Important for lab tech:** if the Windows account password is changed later, the scheduled task will stop working silently. To re-enter credentials: open Task Scheduler → Task Scheduler Library → `ExperimentTrackerUpdate` → Properties → enter current password
   - On failure: retry once after 5 minutes
   - This note must appear in `STARTUP_GUIDE.md` under the scheduled update section

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
   - Use `ORIG_HEAD` for diffing: git writes `ORIG_HEAD` during any pull that advances HEAD (`git diff ORIG_HEAD --name-only`)
   - If `ORIG_HEAD` does not exist (first-ever pull, or no-op pull that didn't move HEAD): default all flags to `$true` as a safe fallback — run all steps
   - If `ORIG_HEAD` equals `HEAD` (no-op pull, nothing changed): set `$nothingChanged = $true`, skip all conditional steps and skip service restart
   - Set flags:
     - `$reinstallDeps` — true if `requirements.txt` appears in the diff
     - `$runMigrations` — true if any file under `alembic/versions/` appears in the diff
     - `$rebuildFrontend` — true if any file under `frontend/src/` or `frontend/package.json` appears in the diff

3. **Conditionally: reinstall Python dependencies**
   - If `$reinstallDeps`: `.venv\Scripts\pip install -r requirements.txt`

4. **Conditionally: run migrations**
   - If `$runMigrations`: `.venv\Scripts\alembic upgrade head`

5. **Conditionally: rebuild frontend**
   - If `$rebuildFrontend`: `npm run build` in `frontend/`
   - If the build fails: log the error, exit 1, **do not restart the service** — serve the last working build rather than restart into a broken state

6. **Restart service (conditional)**
   - If `$nothingChanged`: skip restart, log `[timestamp] SKIPPED — no changes pulled`
   - Otherwise: `nssm restart ExperimentTracker`
   - **Design note:** the restart is skipped on no-op pulls to avoid brief unavailability at 02:00 on nights with no updates

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
1. **Prerequisites** — Python 3.11+, Node 18+, NSSM, git — with download links for each
2. **First-time setup** — clone → fill `.env` (with field-by-field description of every required value) → run `setup.ps1` → enter Windows password when prompted → verify at `http://<hostname>:8000`
3. **Manual updates** — right-click `update.ps1` → Run with PowerShell
4. **Scheduled updates** — how to verify the Task Scheduler entry is registered (UI path + PowerShell one-liner); what to do if Windows password changes (re-enter credentials via Task Scheduler UI — step-by-step with screenshots if possible)
5. **Changing the update schedule** — edit `$UpdateTime` at the top of `setup.ps1` and re-run the Task Scheduler registration step
6. **Troubleshooting** — service won't start, port blocked (including domain network caveat), blank frontend, update failed — each with a diagnostic one-liner

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
