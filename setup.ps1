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
}

$nodeVer = node --version 2>&1
if ($nodeVer -match 'v(\d+)') {
    if ([int]$Matches[1] -lt 18) {
        Fail "Node 18+ required, found: $nodeVer. Download from https://nodejs.org"
    }
}
Write-OK "All prerequisites found"

# -- Step 2: Root .env check --------------------------------------------------
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

# -- Step 2b: Frontend .env.local check ---------------------------------------
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
