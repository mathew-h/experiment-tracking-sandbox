#Requires -Version 5.1
<#
.SYNOPSIS
    Daily PostgreSQL backup for the Experiment Tracker database.
    Designed to run via Task Scheduler. Can also be run manually.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# -- Configuration ------------------------------------------------------------
$PgBin       = "C:\Program Files\PostgreSQL\18\bin"
$DbName      = "experiments"
$DbUser      = "postgres"
$BackupDir   = "C:\Backups\experiments"
$LogFile     = "C:\Logs\experiment-tracker\backup.log"
$RetainDays  = 30    # Delete backups older than this

# -- Helpers ------------------------------------------------------------------
function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "$ts  $msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line
}

# -- Main ---------------------------------------------------------------------
try {
    # Ensure directories exist
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupFile = Join-Path $BackupDir "experiments_$timestamp.sql"

    Log "Starting backup -> $backupFile"

    # Set PGPASSWORD so pg_dump doesn't prompt
    $env:PGPASSWORD = "password"

    & "$PgBin\pg_dump.exe" -U $DbUser -h localhost -F c -f $backupFile $DbName
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }

    $sizeMB = [math]::Round((Get-Item $backupFile).Length / 1MB, 2)
    Log "Backup complete: $backupFile ($sizeMB MB)"

    # -- Prune old backups --------------------------------------------------------
    $cutoff = (Get-Date).AddDays(-$RetainDays)
    $removed = 0
    Get-ChildItem -Path $BackupDir -Filter "experiments_*.sql" | Where-Object {
        $_.LastWriteTime -lt $cutoff
    } | ForEach-Object {
        Log "Removing old backup: $($_.Name)"
        Remove-Item $_.FullName -Force
        $removed++
    }
    if ($removed -gt 0) { Log "Pruned $removed backup(s) older than $RetainDays days" }

    Log "Done"
}
catch {
    Log "FAILED: $_"
    exit 1
}
finally {
    $env:PGPASSWORD = $null
}
