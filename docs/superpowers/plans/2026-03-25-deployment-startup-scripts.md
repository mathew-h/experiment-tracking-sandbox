# Deployment Startup Scripts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace broken legacy `.bat` files with `setup.ps1` (one-time post-clone setup) and `update.ps1` (manual/scheduled updates), and update deployment documentation.

**Architecture:** Two self-elevating PowerShell scripts at the repo root. `setup.ps1` installs everything and registers the NSSM Windows service + Task Scheduler job. `update.ps1` is called manually or nightly by Task Scheduler — it diffs HEAD before/after pull and only rebuilds what changed. Documentation is updated in `docs/deployment/`.

**Tech Stack:** PowerShell 5.1+, NSSM (Windows service manager), Windows Task Scheduler, git, Python venv, npm/vite

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Delete | `start_app.bat` | Legacy Streamlit launcher — gone |
| Delete | `auto_update.bat` | Calls non-existent module — gone |
| Create | `setup.ps1` | One-time setup: preflight → env files → venv → migrations → frontend build → NSSM → firewall → Task Scheduler → start service |
| Create | `update.ps1` | Recurring update: git pull → diff → selective rebuild → conditional restart → log |
| Create | `docs/deployment/STARTUP_GUIDE.md` | Full post-clone walkthrough for lab tech |
| Modify | `docs/deployment/PRODUCTION_DEPLOYMENT.md` | Replace manual NSSM steps with reference to `setup.ps1` |

---

## Task 1: Delete legacy files and stub new scripts

**Files:**
- Delete: `start_app.bat`
- Delete: `auto_update.bat`
- Create: `setup.ps1`
- Create: `update.ps1`

- [ ] **Step 1: Delete the legacy files**

```bash
git checkout chore/deployment-startup-scripts
git rm start_app.bat auto_update.bat
```

Expected: both files removed from working tree and staged.

- [ ] **Step 2: Create `setup.ps1` stub**

Create `setup.ps1` at repo root with this content:

```powershell
#Requires -Version 5.1
<#
.SYNOPSIS
    One-time setup for the Experiment Tracker lab application.
    Run once after cloning. Right-click -> Run with PowerShell.
#>
# Full implementation in subsequent tasks.
Write-Host "Setup script stub — implementation in progress."
Read-Host "Press Enter to exit"
```

- [ ] **Step 3: Create `update.ps1` stub**

Create `update.ps1` at repo root:

```powershell
#Requires -Version 5.1
<#
.SYNOPSIS
    Update the Experiment Tracker to the latest version.
    Run manually or called nightly by Task Scheduler.
#>
# Full implementation in subsequent tasks.
Write-Host "Update script stub — implementation in progress."
```

- [ ] **Step 4: Commit**

```bash
git add setup.ps1 update.ps1
git commit -m "[chore] Delete legacy bat files, stub setup.ps1 and update.ps1

- Tests added: no
- Docs updated: no"
```

---

## Task 2: `setup.ps1` — skeleton, elevation, helpers, preflight, and env checks

**Files:**
- Modify: `setup.ps1`

- [ ] **Step 1: Replace `setup.ps1` with full skeleton**

Replace the contents of `setup.ps1` with:

```powershell
#Requires -Version 5.1
<#
.SYNOPSIS
    One-time setup for the Experiment Tracker lab application.
    Run once after cloning. Right-click -> Run with PowerShell.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Configuration ────────────────────────────────────────────────────────────
$UpdateTime  = "02:00"          # Time for nightly Task Scheduler trigger (24-hour)
$ServiceName = "ExperimentTracker"
$AppPort     = 8000
$LogDir      = "C:\Logs\experiment-tracker"
$TaskName    = "ExperimentTrackerUpdate"

# ── Self-elevation ────────────────────────────────────────────────────────────
if (-not ([Security.Principal.WindowsPrincipal]
          [Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Requesting administrator privileges..."
    Start-Process powershell.exe "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# ── Paths ─────────────────────────────────────────────────────────────────────
$RepoRoot           = Split-Path -Parent $PSCommandPath
$VenvPip            = Join-Path $RepoRoot ".venv\Scripts\pip.exe"
$VenvAlembic        = Join-Path $RepoRoot ".venv\Scripts\alembic.exe"
$VenvUvicorn        = Join-Path $RepoRoot ".venv\Scripts\uvicorn.exe"
$FrontendDir        = Join-Path $RepoRoot "frontend"
$EnvFile            = Join-Path $RepoRoot ".env"
$EnvExample         = Join-Path $RepoRoot ".env.example"
$FrontendEnv        = Join-Path $FrontendDir ".env.local"
$FrontendEnvExample = Join-Path $FrontendDir ".env.example"

# ── Helpers ───────────────────────────────────────────────────────────────────
function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-OK   { param($msg) Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Skip { param($msg) Write-Host "    SKIP: $msg" -ForegroundColor Yellow }
function Fail       {
    param($msg)
    Write-Host "`nERROR: $msg" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# ── Step 1: Preflight checks ──────────────────────────────────────────────────
Write-Step "Step 1: Preflight checks"

$hints = @{
    python = "Download Python 3.11+ from https://python.org"
    node   = "Download Node 18+ from https://nodejs.org"
    npm    = "Included with Node.js — reinstall Node"
    nssm   = "Download NSSM from https://nssm.cc and add the folder to PATH"
    git    = "Download git from https://git-scm.com"
}
foreach ($cmd in @('python', 'node', 'npm', 'nssm', 'git')) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Fail "$cmd not found on PATH. $($hints[$cmd])"
    }
}

$pyVer = python --version 2>&1
if ($pyVer -match 'Python (\d+)\.(\d+)') {
    if ([int]$Matches[1] -lt 3 -or ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -lt 11)) {
        Fail "Python 3.11+ required, found: $pyVer. Download from https://python.org"
    }
}

$nodeVer = node --version 2>&1
if ($nodeVer -match 'v(\d+)') {
    if ([int]$Matches[1] -lt 18) {
        Fail "Node 18+ required, found: $nodeVer. Download from https://nodejs.org"
    }
}
Write-OK "All prerequisites found"

# ── Step 2: Root .env check ───────────────────────────────────────────────────
Write-Step "Step 2: Root .env check"

if (-not (Test-Path $EnvFile)) {
    Copy-Item $EnvExample $EnvFile
    Write-Host ""
    Write-Host "  Created: $EnvFile" -ForegroundColor Yellow
    Write-Host "  Required fields to fill in:" -ForegroundColor Yellow
    Write-Host "    DATABASE_URL          (e.g. postgresql://user:pass@localhost:5432/experiments)" -ForegroundColor White
    Write-Host "    FIREBASE_PROJECT_ID   (from Firebase Console -> Project Settings)" -ForegroundColor White
    Write-Host "    FIREBASE_PRIVATE_KEY  (the full -----BEGIN PRIVATE KEY----- block)" -ForegroundColor White
    Write-Host "    FIREBASE_CLIENT_EMAIL (service account email)" -ForegroundColor White
    Write-Host "  (All other fields have working defaults)" -ForegroundColor Gray
    Read-Host "`n  Open $EnvFile, fill in the required values, then press Enter to continue"
} else {
    Write-Skip ".env already exists"
}

# ── Step 2b: Frontend .env.local check ────────────────────────────────────────
Write-Step "Step 2b: Frontend .env.local check"

if (-not (Test-Path $FrontendEnv)) {
    Copy-Item $FrontendEnvExample $FrontendEnv
    Write-Host ""
    Write-Host "  Created: $FrontendEnv" -ForegroundColor Yellow
    Write-Host "  Get values from: Firebase Console -> Project Settings -> Your Apps -> Web App" -ForegroundColor Gray
    Write-Host "  Required fields:" -ForegroundColor Yellow
    Write-Host "    VITE_FIREBASE_API_KEY" -ForegroundColor White
    Write-Host "    VITE_FIREBASE_AUTH_DOMAIN" -ForegroundColor White
    Write-Host "    VITE_FIREBASE_PROJECT_ID" -ForegroundColor White
    Write-Host "    VITE_FIREBASE_STORAGE_BUCKET" -ForegroundColor White
    Write-Host "    VITE_FIREBASE_MESSAGING_SENDER_ID" -ForegroundColor White
    Write-Host "    VITE_FIREBASE_APP_ID" -ForegroundColor White
    Write-Host ""
    Write-Host "  WARNING: Without these values users cannot log in." -ForegroundColor Red
    Read-Host "`n  Open $FrontendEnv, fill in all values, then press Enter to continue"
} else {
    Write-Skip "frontend/.env.local already exists"
}

Write-Host "`n[Remaining steps not yet implemented]"
Read-Host "Press Enter to exit"
```

- [ ] **Step 2: Verify syntax (no side effects)**

Run in an elevated PowerShell window:

```powershell
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path .\setup.ps1), [ref]$null, [ref]$errors)
if ($errors) { $errors } else { "No syntax errors" }
```

Expected: `No syntax errors`

- [ ] **Step 3: Commit**

```bash
git add setup.ps1
git commit -m "[chore] setup.ps1: skeleton, elevation, preflight, env checks

- Tests added: no
- Docs updated: no"
```

---

## Task 3: `setup.ps1` — venv, migrations, frontend build, log directories

**Files:**
- Modify: `setup.ps1`

- [ ] **Step 1: Replace the placeholder at the bottom of `setup.ps1`**

Remove the last two lines:
```powershell
Write-Host "`n[Remaining steps not yet implemented]"
Read-Host "Press Enter to exit"
```

Replace with:

```powershell
# ── Step 3: Create venv + install Python dependencies ─────────────────────────
Write-Step "Step 3: Create venv and install Python dependencies"

$VenvDir = Join-Path $RepoRoot ".venv"
if (-not (Test-Path $VenvDir)) {
    & python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Fail "Failed to create virtual environment" }
    Write-OK "venv created"
} else {
    Write-Skip "venv already exists — running pip install anyway to ensure deps are current"
}

& $VenvPip install -r (Join-Path $RepoRoot "requirements.txt") -q
if ($LASTEXITCODE -ne 0) { Fail "pip install failed. Check requirements.txt and your internet connection." }
Write-OK "Python dependencies installed"

# ── Step 4: Run database migrations ───────────────────────────────────────────
Write-Step "Step 4: Run database migrations"

Push-Location $RepoRoot
try {
    & $VenvAlembic upgrade head
    if ($LASTEXITCODE -ne 0) { Fail "Alembic migration failed. Ensure DATABASE_URL in .env is correct and PostgreSQL is running." }
    Write-OK "Database migrations applied"
} finally {
    Pop-Location
}

# ── Step 5: Build frontend ─────────────────────────────────────────────────────
Write-Step "Step 5: Build frontend (this may take a minute)"

Push-Location $FrontendDir
try {
    & npm install --silent
    if ($LASTEXITCODE -ne 0) { Fail "npm install failed. Check your internet connection." }
    & npm run build
    if ($LASTEXITCODE -ne 0) { Fail "npm run build failed. Check frontend/.env.local has all required values." }
    Write-OK "Frontend built to frontend/dist/"
} finally {
    Pop-Location
}

# ── Step 6: Create log directories ────────────────────────────────────────────
Write-Step "Step 6: Create log directories"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Write-OK "Log directory ready: $LogDir"

Write-Host "`n[Steps 7-11 not yet implemented]"
Read-Host "Press Enter to exit"
```

- [ ] **Step 2: Commit**

```bash
git add setup.ps1
git commit -m "[chore] setup.ps1: venv, migrations, frontend build, log dirs

- Tests added: no
- Docs updated: no"
```

---

## Task 4: `setup.ps1` — NSSM service, firewall, Task Scheduler, start, success

**Files:**
- Modify: `setup.ps1`

- [ ] **Step 1: Replace placeholder at bottom of `setup.ps1`**

Remove:
```powershell
Write-Host "`n[Steps 7-11 not yet implemented]"
Read-Host "Press Enter to exit"
```

Replace with:

```powershell
# ── Step 7: Register NSSM service (idempotent) ────────────────────────────────
Write-Step "Step 7: Register NSSM Windows service"

$svcStatus = nssm status $ServiceName 2>&1
if ($svcStatus -notmatch "Can't open service") {
    Write-Skip "Service '$ServiceName' already registered — skipping"
} else {
    & nssm install $ServiceName $VenvUvicorn
    & nssm set $ServiceName AppParameters "backend.api.main:app --host 0.0.0.0 --port $AppPort"
    & nssm set $ServiceName AppDirectory $RepoRoot
    & nssm set $ServiceName AppEnvironmentExtra "DOTENV_PATH=$EnvFile"
    & nssm set $ServiceName AppStdout (Join-Path $LogDir "stdout.log")
    & nssm set $ServiceName AppStderr (Join-Path $LogDir "stderr.log")
    & nssm set $ServiceName Start SERVICE_AUTO_START
    Write-OK "Service '$ServiceName' registered (auto-start on boot)"
}

# ── Step 8: Open firewall (idempotent) ────────────────────────────────────────
Write-Step "Step 8: Open firewall (port $AppPort)"

$existingRule = Get-NetFirewallRule -DisplayName "Experiment Tracker" -ErrorAction SilentlyContinue
if ($existingRule) {
    Write-Skip "Firewall rule 'Experiment Tracker' already exists"
} else {
    New-NetFirewallRule `
        -DisplayName "Experiment Tracker" `
        -Direction   Inbound `
        -Protocol    TCP `
        -LocalPort   $AppPort `
        -Action      Allow `
        -Profile     Private, Domain | Out-Null  # Domain included: domain-joined lab PCs classify the NIC as Domain, not Private
    Write-OK "Firewall rule created (Private + Domain profiles, inbound TCP port $AppPort)"
}

# ── Step 9: Register nightly update task ──────────────────────────────────────
Write-Step "Step 9: Register nightly update task ($UpdateTime daily)"

$UpdateScript = Join-Path $RepoRoot "update.ps1"
$Action   = New-ScheduledTaskAction `
                -Execute  "powershell.exe" `
                -Argument "-ExecutionPolicy Bypass -File `"$UpdateScript`""
$Trigger  = New-ScheduledTaskTrigger -Daily -At $UpdateTime
$Settings = New-ScheduledTaskSettingsSet `
                -RestartCount    1 `
                -RestartInterval (New-TimeSpan -Minutes 5)

Write-Host ""
Write-Host "  Windows requires your account password to run this task when you are not logged in." -ForegroundColor Yellow
Write-Host "  You will be prompted for your Windows credentials now." -ForegroundColor Yellow
$Cred = Get-Credential -Message "Enter your Windows account credentials for the scheduled task" -UserName $env:USERNAME

Register-ScheduledTask `
    -TaskName  $TaskName `
    -Action    $Action `
    -Trigger   $Trigger `
    -Settings  $Settings `
    -User      $Cred.UserName `
    -Password  $Cred.GetNetworkCredential().Password `
    -RunLevel  Highest `
    -Force | Out-Null

Write-OK "Task '$TaskName' registered (daily at $UpdateTime)"
Write-Host "  NOTE: If you change your Windows password, update this task's credentials:" -ForegroundColor Gray
Write-Host "        Task Scheduler -> Task Scheduler Library -> $TaskName -> Properties -> enter new password" -ForegroundColor Gray

# ── Step 10: Start service ─────────────────────────────────────────────────────
Write-Step "Step 10: Start service"

& nssm start $ServiceName
if ($LASTEXITCODE -ne 0) {
    Write-Host "  The service failed to start. Check the error log:" -ForegroundColor Red
    Write-Host "  type `"$(Join-Path $LogDir 'stderr.log')`"" -ForegroundColor Red
    Fail "Service start failed"
}
Write-OK "Service '$ServiceName' started"

# ── Step 11: Success ───────────────────────────────────────────────────────────
$hostname = $env:COMPUTERNAME
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host "  App running at:          http://${hostname}:${AppPort}" -ForegroundColor Green
Write-Host "  Nightly updates at:      $UpdateTime" -ForegroundColor Green
Write-Host "  Logs:                    $LogDir" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Read-Host "Press Enter to exit"
```

- [ ] **Step 2: Verify `setup.ps1` is complete — check line count**

```bash
wc -l setup.ps1
```

Expected: ~230 lines. If significantly less, a step was missed.

- [ ] **Step 3: Commit**

```bash
git add setup.ps1
git commit -m "[chore] setup.ps1: NSSM, firewall, Task Scheduler, start, success

- Tests added: no
- Docs updated: no"
```

---

## Task 5: `update.ps1` — complete implementation

**Files:**
- Modify: `update.ps1`

- [ ] **Step 1: Replace `update.ps1` with full implementation**

```powershell
#Requires -Version 5.1
<#
.SYNOPSIS
    Update the Experiment Tracker to the latest version.
    Run manually (right-click -> Run with PowerShell) or called nightly by Task Scheduler.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Configuration ─────────────────────────────────────────────────────────────
$ServiceName = "ExperimentTracker"
$LogDir      = "C:\Logs\experiment-tracker"
$UpdateLog   = Join-Path $LogDir "updates.log"

# ── Self-elevation ────────────────────────────────────────────────────────────
if (-not ([Security.Principal.WindowsPrincipal]
          [Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell.exe "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# ── Paths ─────────────────────────────────────────────────────────────────────
$RepoRoot    = Split-Path -Parent $PSCommandPath
$VenvPip     = Join-Path $RepoRoot ".venv\Scripts\pip.exe"
$VenvAlembic = Join-Path $RepoRoot ".venv\Scripts\alembic.exe"
$FrontendDir = Join-Path $RepoRoot "frontend"

# ── Helpers ───────────────────────────────────────────────────────────────────
function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }

function Log {
    param($msg)
    $ts    = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "[$ts] $msg"
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
    Add-Content -Path $UpdateLog -Value $entry -Encoding UTF8
    Write-Host $entry
}

function Abort {
    param($step, $detail)
    Log "FAILED -- step: $step -- error: $detail"
    exit 1
}

# ── Step 1: Capture HEAD before pull ──────────────────────────────────────────
Write-Step "Step 1: git pull"

$headBefore = git -C $RepoRoot rev-parse HEAD 2>&1
if ($LASTEXITCODE -ne 0) { Abort "git rev-parse" $headBefore }

git -C $RepoRoot pull 2>&1 | ForEach-Object { Write-Host "  $_" }
if ($LASTEXITCODE -ne 0) { Abort "git pull" "exit code $LASTEXITCODE — check for merge conflicts or network issues" }

# ── Step 2: Detect changes ────────────────────────────────────────────────────
Write-Step "Step 2: Detecting changes"

$headAfter = git -C $RepoRoot rev-parse HEAD 2>&1

if ($headBefore -eq $headAfter) {
    Log "SKIPPED -- already up to date"
    exit 0
}

# Force array: @() ensures -match tests elements individually, avoiding multiline-string regex edge cases
$changedFiles    = @(git -C $RepoRoot diff $headBefore $headAfter --name-only 2>&1)
$reinstallDeps   = [bool]($changedFiles -match '^requirements\.txt$')
$runMigrations   = [bool]($changedFiles -match '^alembic/')
$rebuildFrontend = [bool]($changedFiles -match '^frontend/(src/|package\.json)')

$depsStr  = if ($reinstallDeps)   { "yes" } else { "no" }
$migrStr  = if ($runMigrations)   { "yes" } else { "no" }
$frontStr = if ($rebuildFrontend) { "yes" } else { "no" }
Write-Host "  deps:$depsStr  migrations:$migrStr  frontend:$frontStr"

# ── Step 3: Reinstall Python dependencies (conditional) ───────────────────────
if ($reinstallDeps) {
    Write-Step "Step 3: Reinstalling Python dependencies"
    & $VenvPip install -r (Join-Path $RepoRoot "requirements.txt") -q
    if ($LASTEXITCODE -ne 0) { Abort "pip install" "exit code $LASTEXITCODE" }
}

# ── Step 4: Run migrations (conditional) ──────────────────────────────────────
if ($runMigrations) {
    Write-Step "Step 4: Running database migrations"
    Push-Location $RepoRoot
    try {
        & $VenvAlembic upgrade head
        if ($LASTEXITCODE -ne 0) { Abort "alembic upgrade head" "exit code $LASTEXITCODE" }
    } finally { Pop-Location }
}

# ── Step 5: Rebuild frontend (conditional) ────────────────────────────────────
if ($rebuildFrontend) {
    Write-Step "Step 5: Rebuilding frontend"
    Push-Location $FrontendDir
    try {
        & npm install --silent
        if ($LASTEXITCODE -ne 0) { Abort "npm install" "exit code $LASTEXITCODE" }
        & npm run build
        if ($LASTEXITCODE -ne 0) { Abort "npm run build" "exit code $LASTEXITCODE" }
    } finally { Pop-Location }
}

# ── Step 6: Restart service ────────────────────────────────────────────────────
Write-Step "Step 6: Restarting service"

& nssm restart $ServiceName 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Abort "nssm restart" "exit code $LASTEXITCODE -- check $LogDir\stderr.log" }

# ── Step 7: Log success ────────────────────────────────────────────────────────
Log "SUCCESS -- deps:$depsStr migrations:$migrStr frontend:$frontStr"
exit 0
```

- [ ] **Step 2: Verify line count**

```bash
wc -l update.ps1
```

Expected: ~100 lines.

- [ ] **Step 3: Commit**

```bash
git add update.ps1
git commit -m "[chore] Add update.ps1: git pull, selective rebuild, NSSM restart

- Tests added: no
- Docs updated: no"
```

---

## Task 6: `docs/deployment/STARTUP_GUIDE.md` — new document

**Files:**
- Create: `docs/deployment/STARTUP_GUIDE.md`

- [ ] **Step 1: Create `docs/deployment/STARTUP_GUIDE.md`**

```markdown
# Startup Guide — Experiment Tracker Lab PC Setup

This guide covers everything needed to get the Experiment Tracker running on the lab PC from a fresh clone. Follow each step in order.

---

## Prerequisites

Install all of the following before running setup. Restart your terminal after each installation.

| Software | Version | Download |
|---|---|---|
| Python | 3.11 or higher | https://python.org/downloads |
| Node.js | 18 or higher | https://nodejs.org |
| NSSM | Latest | https://nssm.cc/download — extract and add the `win64/` folder to your PATH |
| Git | Latest | https://git-scm.com/downloads |
| PostgreSQL | 16+ | Already installed on the lab PC — skip if present |

**Verify everything is installed:** open PowerShell and run:

```powershell
python --version; node --version; nssm version; git --version
```

All four commands should print version numbers. If any fail, install the missing tool first.

---

## First-Time Setup

### 1. Clone the repository

Open PowerShell and run:

```powershell
git clone https://github.com/mathew-h/experiment-tracking-sandbox.git C:\Apps\experiment-tracking
cd C:\Apps\experiment-tracking
```

### 2. Run setup.ps1

Right-click `setup.ps1` in File Explorer and choose **Run with PowerShell**.

The script will:
- Check all prerequisites are installed
- Create `.env` and pause for you to fill in credentials (see below)
- Create `frontend/.env.local` and pause for you to fill in Firebase values (see below)
- Install Python and Node dependencies
- Apply database migrations
- Build the React frontend
- Register the app as a Windows service (auto-starts on boot)
- Open the firewall on port 8000
- Register the nightly update task
- Start the service

The script prompts for your **Windows account password** near the end — this is needed so the nightly update task can run when you are not logged in.

### 3. Fill in `.env`

When the script pauses at the `.env` step, open `C:\Apps\experiment-tracking\.env` in Notepad and fill in:

| Field | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string, e.g. `postgresql://user:password@localhost:5432/experiments` |
| `FIREBASE_PROJECT_ID` | From Firebase Console → Project Settings → General |
| `FIREBASE_PRIVATE_KEY` | The full `-----BEGIN PRIVATE KEY-----` block from the service account JSON |
| `FIREBASE_CLIENT_EMAIL` | Service account email from Firebase Console |

All other fields (`APP_ENV`, `API_PORT`, etc.) have working defaults and do not need to be changed.

### 4. Fill in `frontend/.env.local`

When the script pauses at the frontend `.env.local` step, open `C:\Apps\experiment-tracking\frontend\.env.local` in Notepad.

Get the values from **Firebase Console → Project Settings → Your Apps → Web App** (the config snippet):

| Field | Where to find it |
|---|---|
| `VITE_FIREBASE_API_KEY` | `apiKey` in the Firebase web config |
| `VITE_FIREBASE_AUTH_DOMAIN` | `authDomain` |
| `VITE_FIREBASE_PROJECT_ID` | `projectId` |
| `VITE_FIREBASE_STORAGE_BUCKET` | `storageBucket` |
| `VITE_FIREBASE_MESSAGING_SENDER_ID` | `messagingSenderId` |
| `VITE_FIREBASE_APP_ID` | `appId` |

**Important:** Without these values the app will start but users will not be able to log in.

### 5. Verify

After setup completes, open a browser on any LAN machine and navigate to:

```
http://<lab-pc-hostname>:8000
```

The login page should appear. If it does not, see [Troubleshooting](#troubleshooting) below.

---

## Manual Updates

To update the app at any time, right-click `update.ps1` in File Explorer and choose **Run with PowerShell**.

The script pulls the latest code, runs any new migrations, rebuilds the frontend if needed, and restarts the service. It logs the result to `C:\Logs\experiment-tracker\updates.log`.

---

## Scheduled Updates

`setup.ps1` registers a Windows Task Scheduler job called `ExperimentTrackerUpdate` that runs `update.ps1` every night at 02:00.

### Verify the task is registered

```powershell
Get-ScheduledTask -TaskName "ExperimentTrackerUpdate" | Select-Object TaskName, State
```

Expected output:
```
TaskName                  State
--------                  -----
ExperimentTrackerUpdate   Ready
```

Or open **Task Scheduler** from the Start menu → **Task Scheduler Library** → find `ExperimentTrackerUpdate`.

### Check the last update log

```powershell
Get-Content "C:\Logs\experiment-tracker\updates.log" -Tail 10
```

### If you change your Windows password

The scheduled task stores your credentials. If you change your Windows account password, the task will silently stop working. To fix it:

1. Open **Task Scheduler** (Start → search "Task Scheduler")
2. Click **Task Scheduler Library** in the left panel
3. Double-click **ExperimentTrackerUpdate**
4. Click the **General** tab → **Change User or Group** (or just re-enter password via **Properties** → **OK** → enter password when prompted)
5. Click **OK**

### Changing the update time

1. Open `setup.ps1` in Notepad
2. Change the `$UpdateTime = "02:00"` line at the top to your preferred time (24-hour format)
3. Right-click `setup.ps1` → **Run with PowerShell** — it will re-register the task with the new time

---

## Troubleshooting

**Service won't start:**
```powershell
type "C:\Logs\experiment-tracker\stderr.log"
```
Check for database connection errors (wrong `DATABASE_URL`) or missing `.env` values.

**Port 8000 blocked — can't reach from other PCs:**
```powershell
Get-NetFirewallRule -DisplayName "Experiment Tracker" | Select-Object DisplayName, Enabled, Profile
```
If the rule is missing or shows the wrong profile (must include `Domain` for domain-joined PCs), re-run `setup.ps1`.

**Blank page or "Cannot GET /" at the app URL:**
The React build may be missing. Run:
```powershell
ls C:\Apps\experiment-tracking\frontend\dist\
```
If the directory is empty or missing, rebuild manually:
```powershell
cd C:\Apps\experiment-tracking\frontend
npm run build
nssm restart ExperimentTracker
```

**Update failed — scheduled task error:**
```powershell
Get-Content "C:\Logs\experiment-tracker\updates.log" -Tail 20
```
Look for `FAILED -- step: <step name>` to identify where it broke. Common causes: network outage during `git pull`, migration error (check `DATABASE_URL`), or expired Windows credentials (see [Changing your Windows password](#if-you-change-your-windows-password) above).

**Check service status:**
```powershell
nssm status ExperimentTracker
```

**Restart the service manually:**
```powershell
nssm restart ExperimentTracker
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/deployment/STARTUP_GUIDE.md
git commit -m "[chore] Add STARTUP_GUIDE.md for lab PC setup

- Tests added: no
- Docs updated: yes"
```

---

## Task 7: Update `docs/deployment/PRODUCTION_DEPLOYMENT.md`

**Files:**
- Modify: `docs/deployment/PRODUCTION_DEPLOYMENT.md`

The goal is minimal surgical changes — replace the manual NSSM steps and manual update steps with references to the new scripts. All other sections stay untouched.

- [ ] **Step 1: Replace the one-time setup steps 6 and 7**

Find this section (steps 6–7 in the existing doc):

```markdown
### 6. Register uvicorn as a Windows service using NSSM
...
nssm start ExperimentTracker
...
### 7. Open the firewall for LAN access (port 8000)
...
```

Replace with:

```markdown
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
```

**Note:** The original steps 6, 7, and 8 are replaced by new steps 6 and 7 above. Ensure no "### 8." heading remains in this section after the edit.

- [ ] **Step 2: Replace the "Updating the App" section**

Find:

```markdown
## Updating the App

After merging changes into the main branch:

```powershell
cd C:\Apps\experiment-tracking
...
nssm restart ExperimentTracker
```
```

Replace with:

```markdown
## Updating the App

Right-click `update.ps1` at the repo root and choose **Run with PowerShell**, or wait for the nightly scheduled update (runs at 02:00 by default).

The script automatically detects what changed (Python dependencies, database migrations, frontend files) and only rebuilds what is needed, then restarts the service.

To check the update log:
```powershell
Get-Content "C:\Logs\experiment-tracker\updates.log" -Tail 20
```

---
```

**Important:** Preserve the trailing `---` — it is the section separator before "Database Backups" and must not be dropped.

- [ ] **Step 3: Commit**

```bash
git add docs/deployment/PRODUCTION_DEPLOYMENT.md
git commit -m "[chore] Update PRODUCTION_DEPLOYMENT.md: reference setup.ps1 + update.ps1

- Tests added: no
- Docs updated: yes"
```

---

## Task 8: Final verification checklist

Run through this checklist before declaring the work done.

- [ ] **Acceptance: legacy files gone**

```bash
ls start_app.bat auto_update.bat 2>/dev/null && echo "FAIL — files still exist" || echo "PASS — files deleted"
```

- [ ] **Acceptance: new scripts exist**

```bash
ls setup.ps1 update.ps1 docs/deployment/STARTUP_GUIDE.md
```

All three should be listed.

- [ ] **Acceptance: setup.ps1 syntax check**

```powershell
powershell.exe -Command "& { [System.Management.Automation.Language.Parser]::ParseFile('setup.ps1', [ref]$null, [ref]$errors); $errors }"
```

Expected: no output (no syntax errors).

- [ ] **Acceptance: update.ps1 syntax check**

```powershell
powershell.exe -Command "& { [System.Management.Automation.Language.Parser]::ParseFile('update.ps1', [ref]$null, [ref]$errors); $errors }"
```

Expected: no output.

- [ ] **Acceptance: STARTUP_GUIDE has all required sections**

```bash
grep -c "^##" docs/deployment/STARTUP_GUIDE.md
```

Expected: 6 or more sections (Prerequisites, First-Time Setup, Manual Updates, Scheduled Updates, Troubleshooting + subsections).

- [ ] **Acceptance: PRODUCTION_DEPLOYMENT.md still has non-modified sections**

```bash
grep -c "Database Backups\|Adding Users\|Configuring the Master Results" docs/deployment/PRODUCTION_DEPLOYMENT.md
```

Expected: 3 — confirms the sections that should not have changed are still present.

- [ ] **Final commit (if any loose changes)**

```bash
git status
# If clean, nothing to do. If any docs were tweaked during verification:
git add -p
git commit -m "[chore] Final verification fixes

- Tests added: no
- Docs updated: yes"
```
