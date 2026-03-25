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
    & python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Fail "Failed to create virtual environment" }
    Write-OK "venv created"
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
    & npm install --silent
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

Write-Host "`n[Steps 7-11 not yet implemented]"
Read-Host "Press Enter to exit"
