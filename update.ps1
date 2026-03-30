#Requires -Version 5.1
<#
.SYNOPSIS
    Update the Experiment Tracker to the latest version.
    Run manually (right-click -> Run with PowerShell) or called nightly by Task Scheduler.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# -- Configuration ------------------------------------------------------------
$ServiceName = "ExperimentTracker"
$LogDir      = "C:\Logs\experiment-tracker"
$UpdateLog   = Join-Path $LogDir "updates.log"

# -- Self-elevation ------------------------------------------------------------
$currentPrincipal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell.exe "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# -- Paths --------------------------------------------------------------------
$RepoRoot    = Split-Path -Parent $PSCommandPath
$VenvPip     = Join-Path $RepoRoot ".venv\Scripts\pip.exe"
$VenvAlembic = Join-Path $RepoRoot ".venv\Scripts\alembic.exe"
$FrontendDir = Join-Path $RepoRoot "frontend"

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

function Abort {
    param($step, $detail)
    Log "FAILED -- step: $step -- error: $detail"
    Pause-IfInteractive
    exit 1
}

# -- Step 1: Capture HEAD before pull -----------------------------------------
Write-Step "Step 1: git pull"

git -C $RepoRoot checkout main 2>&1 | ForEach-Object { Write-Host "  $_" }
if ($LASTEXITCODE -ne 0) { Abort "git checkout main" "exit code $LASTEXITCODE" }

$headBefore = git -C $RepoRoot rev-parse HEAD 2>&1
if ($LASTEXITCODE -ne 0) { Abort "git rev-parse" $headBefore }

git -C $RepoRoot pull origin main 2>&1 | ForEach-Object { Write-Host "  $_" }
if ($LASTEXITCODE -ne 0) { Abort "git pull origin main" "exit code $LASTEXITCODE - check for merge conflicts or network issues" }

# -- Step 2: Detect changes ---------------------------------------------------
Write-Step "Step 2: Detecting changes"

$headAfter = git -C $RepoRoot rev-parse HEAD 2>&1

if ($headBefore -eq $headAfter) {
    Log "SKIPPED -- already up to date"
    Pause-IfInteractive
    exit 0
}

# @() forces an array so -match tests elements individually
$changedFiles    = @(git -C $RepoRoot diff $headBefore $headAfter --name-only 2>&1)
$reinstallDeps   = [bool]($changedFiles -match '^requirements\.txt$')
$runMigrations   = [bool]($changedFiles -match '^alembic/')
$rebuildFrontend = [bool]($changedFiles -match '^frontend/(src/|package\.json)')

$depsStr  = if ($reinstallDeps)   { "yes" } else { "no" }
$migrStr  = if ($runMigrations)   { "yes" } else { "no" }
$frontStr = if ($rebuildFrontend) { "yes" } else { "no" }
Write-Host "  deps:$depsStr  migrations:$migrStr  frontend:$frontStr"

# -- Step 3: Reinstall Python dependencies (conditional) ----------------------
if ($reinstallDeps) {
    Write-Step "Step 3: Reinstalling Python dependencies"
    & $VenvPip install -r (Join-Path $RepoRoot "requirements.txt") -q
    if ($LASTEXITCODE -ne 0) { Abort "pip install" "exit code $LASTEXITCODE" }
}

# -- Step 4: Run migrations (conditional) -------------------------------------
if ($runMigrations) {
    Write-Step "Step 4: Running database migrations"
    Push-Location $RepoRoot
    try {
        & $VenvAlembic upgrade head
        if ($LASTEXITCODE -ne 0) { Abort "alembic upgrade head" "exit code $LASTEXITCODE" }
    } finally { Pop-Location }
}

# -- Step 5: Rebuild frontend (conditional) -----------------------------------
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

# -- Step 6: Restart service --------------------------------------------------
Write-Step "Step 6: Restarting service"

& nssm restart $ServiceName 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Abort "nssm restart" "exit code $LASTEXITCODE -- check $LogDir\stderr.log" }

# -- Step 7: Log success ------------------------------------------------------
Log "SUCCESS -- deps:$depsStr migrations:$migrStr frontend:$frontStr"
Pause-IfInteractive
exit 0
