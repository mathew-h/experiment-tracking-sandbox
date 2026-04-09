#Requires -Version 5.1
<#
.SYNOPSIS
    One-time setup for the Experiment Tracker lab application.
    Run once after cloning. Right-click -> Run with PowerShell.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# -- Configuration ------------------------------------------------------------
$UpdateTime  = "02:00"          # Time for nightly Task Scheduler trigger (24-hour)
$ServiceName = "ExperimentTracker"
$AppPort     = 8000
$LogDir      = "C:\Logs\experiment-tracker"
$TaskName    = "ExperimentTrackerUpdate"

# -- Self-elevation ------------------------------------------------------------
$currentPrincipal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Requesting administrator privileges..."
    Start-Process powershell.exe "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# -- Paths --------------------------------------------------------------------
$RepoRoot           = Split-Path -Parent $PSCommandPath
$VenvPip            = Join-Path $RepoRoot ".venv\Scripts\pip.exe"
$VenvAlembic        = Join-Path $RepoRoot ".venv\Scripts\alembic.exe"
$VenvPython         = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$VenvUvicorn        = Join-Path $RepoRoot ".venv\Scripts\uvicorn.exe"
$FrontendDir        = Join-Path $RepoRoot "frontend"
$EnvFile            = Join-Path $RepoRoot ".env"
$EnvExample         = Join-Path $RepoRoot ".env.example"
$FrontendEnv        = Join-Path $FrontendDir ".env.local"
$FrontendEnvExample = Join-Path $FrontendDir ".env.example"

# -- Helpers ------------------------------------------------------------------
function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-OK   { param($msg) Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Skip { param($msg) Write-Host "    SKIP: $msg" -ForegroundColor Yellow }
function Fail       {
    param($msg)
    Write-Host "`nERROR: $msg" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# -- Step 1: Preflight checks -------------------------------------------------
Write-Step "Step 1: Preflight checks"

$hints = @{
    python = "Download Python 3.11+ from https://python.org"
    node   = "Download Node 18+ from https://nodejs.org"
    npm    = "Included with Node.js - reinstall Node"
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
} else {
    Fail "Could not parse Python version from: '$pyVer'. Ensure Python 3.11+ is installed and on PATH."
}

$nodeVer = node --version 2>&1
if ($nodeVer -match 'v(\d+)') {
    if ([int]$Matches[1] -lt 18) {
        Fail "Node 18+ required, found: $nodeVer. Download from https://nodejs.org"
    }
} else {
    Fail "Could not parse Node version from: '$nodeVer'. Ensure Node 18+ is installed and on PATH."
}
Write-OK "All prerequisites found"

# -- Step 2: Root .env check --------------------------------------------------
Write-Step "Step 2: Root .env check"

if (-not (Test-Path $EnvFile)) {
    if (-not (Test-Path $EnvExample)) {
        Fail ".env.example not found in repo root. Re-clone the repository or contact the maintainer."
    }
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

# -- Step 2b: Frontend .env.local check ---------------------------------------
Write-Step "Step 2b: Frontend .env.local check"

if (-not (Test-Path $FrontendEnv)) {
    if (-not (Test-Path $FrontendEnvExample)) {
        Fail "frontend/.env.example not found. Re-clone the repository or contact the maintainer."
    }
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

# -- Step 3: Create venv + install Python dependencies ------------------------
Write-Step "Step 3: Create venv and install Python dependencies"

$VenvDir = Join-Path $RepoRoot ".venv"
if (-not (Test-Path $VenvDir)) {
    # Use Python 3.13 (non-Store install) — required for greenlet wheel compatibility
    # and for NSSM service access (Windows Store Python is inaccessible to SYSTEM)
    $py313 = try { py -3.13 -c "import sys; print(sys.executable)" 2>&1 } catch { $null }
    if ($py313 -and (Test-Path $py313)) {
        & $py313 -m venv $VenvDir
    } else {
        Write-Host "  WARNING: Python 3.13 not found via 'py -3.13'. Falling back to default 'python'." -ForegroundColor Yellow
        Write-Host "  Install Python 3.13 from python.org for best compatibility." -ForegroundColor Yellow
        & python -m venv $VenvDir
    }
    if ($LASTEXITCODE -ne 0) { Fail "Failed to create virtual environment" }
    Write-OK "venv created (Python 3.13)"
} else {
    Write-Skip "venv already exists - running pip install anyway to ensure deps are current"
}

& $VenvPip install -r (Join-Path $RepoRoot "requirements.txt") -q
if ($LASTEXITCODE -ne 0) { Fail "pip install failed. Check requirements.txt and your internet connection." }
Write-OK "Python dependencies installed"

# -- Step 4: Run database migrations ------------------------------------------
Write-Step "Step 4: Run database migrations"

Push-Location $RepoRoot
try {
    & $VenvAlembic upgrade head
    if ($LASTEXITCODE -ne 0) { Fail "Alembic migration failed. Ensure DATABASE_URL in .env is correct and PostgreSQL is running." }
    Write-OK "Database migrations applied"
} finally {
    Pop-Location
}

# -- Step 5: Build frontend ---------------------------------------------------
Write-Step "Step 5: Build frontend (this may take a minute)"

Push-Location $FrontendDir
try {
    & npm install --silent --legacy-peer-deps
    if ($LASTEXITCODE -ne 0) { Fail "npm install failed. Check your internet connection." }
    & npm run build
    if ($LASTEXITCODE -ne 0) { Fail "npm run build failed. Check frontend/.env.local has all required values." }
    Write-OK "Frontend built to frontend/dist/"
} finally {
    Pop-Location
}

# -- Step 6: Create log directories -------------------------------------------
Write-Step "Step 6: Create log directories"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Write-OK "Log directory ready: $LogDir"

# -- Step 7: Register NSSM service (idempotent) --------------------------------
Write-Step "Step 7: Register NSSM Windows service"

$svcStatus = try { nssm status $ServiceName 2>&1 } catch { "Can't open service!" }
$svcStatus = "$svcStatus"
if ($svcStatus -notmatch "Can't open service") {
    Write-Skip "Service '$ServiceName' already registered - skipping"
} else {
    & nssm install $ServiceName $VenvPython
    & nssm set $ServiceName AppParameters "-m uvicorn backend.api.main:app --host 0.0.0.0 --port $AppPort"
    & nssm set $ServiceName AppDirectory $RepoRoot
    & nssm set $ServiceName AppEnvironmentExtra "DOTENV_PATH=$EnvFile" "VIRTUAL_ENV=$RepoRoot\.venv"
    & nssm set $ServiceName AppStdout (Join-Path $LogDir "stdout.log")
    & nssm set $ServiceName AppStderr (Join-Path $LogDir "stderr.log")
    & nssm set $ServiceName Start SERVICE_AUTO_START
    Write-OK "Service '$ServiceName' registered (auto-start on boot)"
}

# -- Step 8: Open firewall (idempotent) ----------------------------------------
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
        -Profile     Private, Domain | Out-Null
    Write-OK "Firewall rule created (Private + Domain profiles, inbound TCP port $AppPort)"
}

# -- Step 9: Register nightly update task --------------------------------------
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
$whoami = whoami
$Cred = Get-Credential -Message "Enter your Windows account credentials for the scheduled task" -UserName $whoami

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

# -- Step 9b: Register nightly backup task -------------------------------------
Write-Step "Step 9b: Register nightly backup task (01:00 daily)"

$BackupScript = Join-Path $RepoRoot "backup.ps1"
$BackupAction   = New-ScheduledTaskAction `
                    -Execute  "powershell.exe" `
                    -Argument "-ExecutionPolicy Bypass -File `"$BackupScript`""
$BackupTrigger  = New-ScheduledTaskTrigger -Daily -At "01:00"
$BackupSettings = New-ScheduledTaskSettingsSet `
                    -RestartCount    1 `
                    -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName  "ExperimentTrackerBackup" `
    -Action    $BackupAction `
    -Trigger   $BackupTrigger `
    -Settings  $BackupSettings `
    -User      $Cred.UserName `
    -Password  $Cred.GetNetworkCredential().Password `
    -RunLevel  Highest `
    -Force | Out-Null

Write-OK "Task 'ExperimentTrackerBackup' registered (daily at 01:00)"

# -- Step 10: Start service ----------------------------------------------------
Write-Step "Step 10: Start service"

& nssm start $ServiceName
if ($LASTEXITCODE -ne 0) {
    Write-Host "  The service failed to start. Check the error log:" -ForegroundColor Red
    Write-Host "  type `"$(Join-Path $LogDir 'stderr.log')`"" -ForegroundColor Red
    Fail "Service start failed"
}
Write-OK "Service '$ServiceName' started"

# -- Step 11: Success ----------------------------------------------------------
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
