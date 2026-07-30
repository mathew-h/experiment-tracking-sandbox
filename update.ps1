#Requires -Version 5.1
<#
.SYNOPSIS
    Update the Experiment Tracker to the latest version.
    Run manually (right-click -> Run with PowerShell) or called nightly by Task Scheduler.

.NOTES
    Hardened 2026-07-30 after the lab PC sat 22 commits behind for ten days. The nightly
    job had been failing on `git pull` because the working tree was dirty, logging FAILED
    to a file nobody reads. Three properties are now enforced; see tests/deployment/
    test_update_script.py, which asserts each of them:

      1. The service is STOPPED before git rewrites any file. A running Python process
         holding open handles (or with its CWD inside the repo) can make git apply a pull
         only partially, which is the most likely origin of the dirty tree in the first
         place. Because stopping first means a later failure would leave the lab app
         OFFLINE rather than merely stale, every exit path routes through
         Start-TrackerService.
      2. A dirty tree is discarded before pulling, and WHAT was discarded is logged, so
         a recurrence is visible instead of silent. This machine is a deploy target and
         must never hold local work.
      3. The pull is verified to have actually landed on origin/main. A partial update
         must not be able to report SUCCESS.

    The reset target is deliberately HEAD, never origin/main. `reset --hard origin/main`
    moves HEAD itself, so the `git pull` below finds nothing to do, $headBefore equals
    $headAfter, the "no new commits" branch fires, and the frontend is never rebuilt --
    a deploy that logs SUCCESS while serving a stale frontend/dist.

    `git clean` is likewise deliberately -fd and never -fdx. The ignored files that -x
    would delete are .venv (which this script's own pip and alembic live in), .env,
    frontend/.env.local, node_modules and frontend/dist. None are recoverable from the repo.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# -- Configuration ------------------------------------------------------------
$ServiceName = "ExperimentTracker"
$LogDir      = "C:\Logs\experiment-tracker"
$UpdateLog   = Join-Path $LogDir "updates.log"

# -- Paths --------------------------------------------------------------------
$RepoRoot    = Split-Path -Parent $PSCommandPath
$VenvPip     = Join-Path $RepoRoot ".venv\Scripts\pip.exe"
$VenvAlembic = Join-Path $RepoRoot ".venv\Scripts\alembic.exe"
$FrontendDir = Join-Path $RepoRoot "frontend"

# Tracks whether WE took the service down, so that every exit path -- including a
# mid-script Abort -- brings it back up.
$script:ServiceStoppedByUs = $false

# -- Helpers ------------------------------------------------------------------
function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }

function Log {
    param($msg)
    $ts    = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "[$ts] $msg"
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
    Add-Content -Path $UpdateLog -Value $entry -Encoding UTF8
    Write-Host $entry
}

function Pause-IfInteractive {
    # Only prompt when run in a real console window (not Task Scheduler / headless).
    if ([Environment]::UserInteractive -and $Host.Name -ne 'Default Host') {
        Write-Host ""
        Read-Host "Press Enter to close"
    }
}

function Start-TrackerService {
    <#
        Bring the service back up if we stopped it. Safe to call repeatedly and safe to
        call when we never stopped it. Deliberately does NOT Abort on failure: it is
        called FROM Abort, and a failure to start must be reported without recursing.
    #>
    if (-not $script:ServiceStoppedByUs) { return }

    $ErrorActionPreference = 'Continue'
    & nssm start $ServiceName 2>&1 | Out-Null
    $code = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'

    if ($code -eq 0) {
        $script:ServiceStoppedByUs = $false
        Log "service $ServiceName started"
    } else {
        Log "CRITICAL -- could not start ${ServiceName} (exit $code) -- the app is DOWN; check $LogDir\stderr.log and run: nssm start $ServiceName"
    }
}

function Abort {
    param($step, $detail)
    Log "FAILED -- step: $step -- error: $detail"
    # Never leave the lab PC's app offline because a deploy step failed.
    Start-TrackerService
    Pause-IfInteractive
    exit 1
}

# -- Self-elevation (skip in non-interactive / Task Scheduler sessions) --------
$currentPrincipal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    if ([Environment]::UserInteractive) {
        Write-Host "Requesting administrator privileges..." -ForegroundColor Yellow
        Start-Process powershell.exe "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs -Wait
        Pause-IfInteractive
        exit
    } else {
        Log "WARNING -- running non-elevated in non-interactive session; some steps may fail"
    }
}

# -- Step 1: Stop the service before touching any file ------------------------
# Open handles held by the running service can make git apply a pull only partially.
Write-Step "Step 1: Stopping service"

$ErrorActionPreference = 'Continue'
& nssm stop $ServiceName 2>&1 | Out-Null
$stopCode = $LASTEXITCODE
$ErrorActionPreference = 'Stop'

# A non-zero code here usually means "already stopped", which is not a failure. Mark the
# service as ours to restart either way, so a genuinely stopped-by-us service is never
# left down and an already-stopped one is simply started at the end.
$script:ServiceStoppedByUs = $true
if ($stopCode -ne 0) {
    Log "note: nssm stop returned $stopCode (service likely already stopped)"
} else {
    Log "service $ServiceName stopped for update"
}

# -- Step 2: Update the working copy ------------------------------------------
Write-Step "Step 2: git pull"

$ErrorActionPreference = 'Continue'
git -C $RepoRoot checkout main 2>&1 | ForEach-Object { Write-Host "  $_" }
if ($LASTEXITCODE -ne 0) { $ErrorActionPreference = 'Stop'; Abort "git checkout main" "exit code $LASTEXITCODE" }

# This machine is a deploy target and must never hold local work. Any dirty state blocks
# `git pull` indefinitely, so discard it -- but log exactly what was discarded, so that a
# recurrence is visible in updates.log instead of silently repeating every night.
$dirty = @(git -C $RepoRoot status --porcelain 2>&1)
$ErrorActionPreference = 'Stop'

if ($dirty.Count -gt 0) {
    Log "WARNING -- working tree was dirty before pull; discarding $($dirty.Count) local entr$(if ($dirty.Count -eq 1) { 'y' } else { 'ies' })"
    $dirty | ForEach-Object { Log "  discarded: $_" }
    Log "WARNING -- if this recurs, something is writing to this checkout; see docs/deployment/PRODUCTION_DEPLOYMENT.md"

    $ErrorActionPreference = 'Continue'
    # HEAD, not origin/main -- see the .NOTES block above. Getting this wrong turns the
    # pull into a no-op and silently skips the frontend rebuild.
    git -C $RepoRoot reset --hard HEAD 2>&1 | ForEach-Object { Write-Host "  $_" }
    $resetCode = $LASTEXITCODE
    # -fd, never -fdx. Best-effort: this has failed with "Permission denied" on stray
    # EMPTY directories, which is harmless and must not block every deploy.
    git -C $RepoRoot clean -fd 2>&1 | ForEach-Object { Write-Host "  $_" }
    $cleanCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'

    if ($resetCode -ne 0) { Abort "git reset --hard HEAD" "exit code $resetCode" }
    if ($cleanCode -ne 0) {
        Log "note: git clean -fd returned $cleanCode (usually a locked or permission-denied empty directory); continuing"
    }
}

$ErrorActionPreference = 'Continue'
$headBefore = (git -C $RepoRoot rev-parse HEAD 2>&1) | Out-String
$headBefore = $headBefore.Trim()
if ($LASTEXITCODE -ne 0) { $ErrorActionPreference = 'Stop'; Abort "git rev-parse" $headBefore }

git -C $RepoRoot pull origin main 2>&1 | ForEach-Object { Write-Host "  $_" }
if ($LASTEXITCODE -ne 0) { $ErrorActionPreference = 'Stop'; Abort "git pull origin main" "exit code $LASTEXITCODE - check for merge conflicts or network issues" }

$headAfter = (git -C $RepoRoot rev-parse HEAD 2>&1) | Out-String
$headAfter = $headAfter.Trim()

# The pull must have actually landed on the remote tip. Without this, a partially applied
# update reports SUCCESS and the stale build is served until someone notices by eye.
$remoteHead = (git -C $RepoRoot rev-parse origin/main 2>&1) | Out-String
$remoteHead = $remoteHead.Trim()
$ErrorActionPreference = 'Stop'

if ($headAfter -ne $remoteHead) {
    Abort "verify pull" "HEAD is $headAfter but origin/main is $remoteHead -- the pull did not fully apply"
}

# -- Step 3: Detect changes ---------------------------------------------------
Write-Step "Step 3: Detecting changes"

if ($headBefore -eq $headAfter) {
    Log "No new commits -- skipping deps/migrations/frontend, restarting service"
    Start-TrackerService
    if ($script:ServiceStoppedByUs) { Abort "nssm start" "service did not start -- check $LogDir\stderr.log" }
    Log "SUCCESS -- restart only (no changes)"
    Pause-IfInteractive
    exit 0
}

# @() forces an array so -match tests elements individually
$ErrorActionPreference = 'Continue'
$changedFiles    = @(git -C $RepoRoot diff $headBefore $headAfter --name-only 2>&1)
$ErrorActionPreference = 'Stop'
$reinstallDeps        = [bool]($changedFiles -match '^requirements\.txt$')
$reinstallNodeModules = [bool]($changedFiles -match '^frontend/package(-lock)?\.json$')
$rebuildFrontend      = [bool]($changedFiles -match '^frontend/(src/|public/|index\.html|package\.json)')

$depsStr  = if ($reinstallDeps)   { "yes" } else { "no" }
$frontStr = if ($rebuildFrontend) { "yes" } else { "no" }
$nmStr    = if ($reinstallNodeModules) { "yes" } else { "no" }
Write-Host "  deps:$depsStr  migrations:always  frontend:$frontStr  node_modules:$nmStr"
Log "updating $headBefore -> $headAfter ($($changedFiles.Count) files) deps:$depsStr frontend:$frontStr node_modules:$nmStr"

# -- Step 4: Reinstall Python dependencies (conditional) ----------------------
if ($reinstallDeps) {
    Write-Step "Step 4: Reinstalling Python dependencies"
    & $VenvPip install -r (Join-Path $RepoRoot "requirements.txt") -q
    if ($LASTEXITCODE -ne 0) { Abort "pip install" "exit code $LASTEXITCODE" }
}

# -- Step 5: Run migrations (always -- idempotent, exits cleanly at head) -----
# Runs with the service down, so no request can hit a half-migrated schema.
Write-Step "Step 5: Running database migrations"
Push-Location $RepoRoot
try {
    & $VenvAlembic upgrade head
    if ($LASTEXITCODE -ne 0) { Abort "alembic upgrade head" "exit code $LASTEXITCODE" }
} finally { Pop-Location }

# -- Step 6: Rebuild frontend (conditional) -----------------------------------
if ($rebuildFrontend) {
    Write-Step "Step 6: Rebuilding frontend"
    Push-Location $FrontendDir
    try {
        if ($reinstallNodeModules) {
            Log "frontend: npm ci starting (package files changed)"
            $env:CI = '1'
            & npm ci --prefer-offline --loglevel=error
            if ($LASTEXITCODE -ne 0) { Abort "npm ci" "exit code $LASTEXITCODE -- package.json/package-lock.json out of sync, or install failed" }
            Log "frontend: npm ci done"
        }
        Log "frontend: vite build starting"
        $env:CI = '1'
        & npm run build
        if ($LASTEXITCODE -ne 0) { Abort "npm run build" "exit code $LASTEXITCODE" }
        Log "frontend: vite build done"
    } finally { Pop-Location }
}

# -- Step 7: Start service ----------------------------------------------------
Write-Step "Step 7: Starting service"

Start-TrackerService
if ($script:ServiceStoppedByUs) { Abort "nssm start" "service did not start -- check $LogDir\stderr.log" }

# -- Step 8: Log success ------------------------------------------------------
Log "SUCCESS -- deps:$depsStr migrations:always frontend:$frontStr"
Pause-IfInteractive
exit 0
