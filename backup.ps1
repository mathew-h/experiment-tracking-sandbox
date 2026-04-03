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
$PublicDir   = "C:\Users\LabPC\Addis Energy\All Company - Addis Energy\01_R&D\11_Modeling\01_Internal Database\03_Backups"
$LogFile     = "C:\Logs\experiment-tracker\backup.log"
$RetainDays  = 30    # Delete backups older than this

# -- Helpers ------------------------------------------------------------------
function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "$ts  $msg"
    Write-Host $line
    # Use .NET FileStream with FileShare.ReadWrite to avoid locking conflicts
    # with antivirus or other processes. Retry once on failure.
    for ($i = 0; $i -lt 2; $i++) {
        try {
            $fs = [System.IO.FileStream]::new(
                $LogFile,
                [System.IO.FileMode]::Append,
                [System.IO.FileAccess]::Write,
                [System.IO.FileShare]::ReadWrite)
            $sw = [System.IO.StreamWriter]::new($fs)
            $sw.WriteLine($line)
            $sw.Close()
            $fs.Close()
            return
        } catch {
            if ($i -eq 0) { Start-Sleep -Milliseconds 500 }
            else { Write-Warning "Could not write to log: $_" }
        }
    }
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

    # -- Public copy (SharePoint-synced folder) -----------------------------------
    New-Item -ItemType Directory -Force -Path $PublicDir | Out-Null
    $publicFile = Join-Path $PublicDir "experiments_$timestamp.sql"
    & "$PgBin\pg_dump.exe" -U $DbUser -h localhost -F c -f $publicFile $DbName
    if ($LASTEXITCODE -ne 0) { throw "pg_dump (public copy) failed with exit code $LASTEXITCODE" }
    $publicSizeMB = [math]::Round((Get-Item $publicFile).Length / 1MB, 2)
    Log "Public copy complete: $publicFile ($publicSizeMB MB)"

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
    if ($removed -gt 0) { Log "Pruned $removed backup(s) older than $RetainDays days from local" }

    # Prune public dir
    $removedPublic = 0
    Get-ChildItem -Path $PublicDir -Filter "experiments_*.sql" | Where-Object {
        $_.LastWriteTime -lt $cutoff
    } | ForEach-Object {
        Log "Removing old public backup: $($_.Name)"
        Remove-Item $_.FullName -Force
        $removedPublic++
    }
    if ($removedPublic -gt 0) { Log "Pruned $removedPublic backup(s) older than $RetainDays days from public" }

    Log "Done"
}
catch {
    Log "FAILED: $_"
    exit 1
}
finally {
    $env:PGPASSWORD = $null
}
