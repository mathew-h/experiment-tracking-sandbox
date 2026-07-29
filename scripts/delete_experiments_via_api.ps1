<#
.SYNOPSIS
    Delete experiments through the app's own API instead of raw SQL.

.DESCRIPTION
    Reads experiment IDs (one per line) from a text file and calls
    DELETE /api/experiments/{experiment_id} for each one.

    Why the API and not psql:
      - The endpoint (backend/api/routers/experiments.py, delete_experiment) lets
        SQLAlchemy cascade the children (conditions, additives, results, scalar/ICP,
        result files, notes, modifications log, external analyses) instead of relying
        on DB-level ON DELETE clauses that the initial Alembic migration never created.
      - It writes a structured `experiment_deleted` log line with the caller's email,
        so there is an audit trail. Raw SQL leaves none.
      - It is already covered by tests/api/test_experiments.py::test_delete_experiment.

    Defaults to DRY RUN. Nothing is deleted until you pass -Execute.

.PARAMETER BaseUrl
    Root of the app, e.g. http://<lab-pc-hostname>:8000

.PARAMETER IdFile
    Text file with one experiment_id per line. Blank lines and lines starting with
    '#' are ignored.

.PARAMETER Email
    Your @addisenergy.com login. Must be an approved account.

.PARAMETER FirebaseApiKey
    The VITE_FIREBASE_API_KEY value from frontend/.env.local. Used only to exchange
    email + password for an ID token via Firebase's REST endpoint, exactly as the
    React app does in the browser.

.PARAMETER Execute
    Actually perform the deletes.

.EXAMPLE
    # Dry run: report what exists and what data hangs off each ID
    .\delete_experiments_via_api.ps1 -BaseUrl http://labpc:8000 `
        -IdFile .\serum_catalyst_leftovers.txt -Email mhearl@addisenergy.com `
        -FirebaseApiKey AIza...

.EXAMPLE
    # Commit the deletes
    .\delete_experiments_via_api.ps1 -BaseUrl http://labpc:8000 `
        -IdFile .\serum_catalyst_leftovers.txt -Email mhearl@addisenergy.com `
        -FirebaseApiKey AIza... -Execute

.NOTES
    Take a pg_dump before running with -Execute. Deletion is irreversible and the
    app has no undo.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $BaseUrl,
    [Parameter(Mandatory)][string] $IdFile,
    [Parameter(Mandatory)][string] $Email,
    [Parameter(Mandatory)][string] $FirebaseApiKey,
    [switch] $Execute
)

$ErrorActionPreference = 'Stop'
$BaseUrl = $BaseUrl.TrimEnd('/')

# ---------------------------------------------------------------------------
# Load and validate the ID list
# ---------------------------------------------------------------------------
if (-not (Test-Path $IdFile)) { throw "ID file not found: $IdFile" }

$ids = Get-Content $IdFile |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -ne '' -and -not $_.StartsWith('#') } |
    Select-Object -Unique

if ($ids.Count -eq 0) { throw "No experiment IDs found in $IdFile" }
Write-Host "Loaded $($ids.Count) unique experiment ID(s) from $IdFile" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# Sign in to Firebase for an ID token (same flow as the React app)
# ---------------------------------------------------------------------------
$password = Read-Host -Prompt "Password for $Email" -AsSecureString
$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($password))

$signInBody = @{ email = $Email; password = $plain; returnSecureToken = $true } | ConvertTo-Json
$plain = $null

try {
    $auth = Invoke-RestMethod -Method Post -ContentType 'application/json' -Body $signInBody `
        -Uri "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=$FirebaseApiKey"
} catch {
    throw "Firebase sign-in failed. Check the email, password, and that the account is approved. $_"
}

$headers = @{ Authorization = "Bearer $($auth.idToken)" }
Write-Host "Authenticated as $Email" -ForegroundColor Green

# ---------------------------------------------------------------------------
# Pass 1: inspect. Always runs, in both dry-run and execute mode.
# ---------------------------------------------------------------------------
$report = foreach ($id in $ids) {
    $row = [ordered]@{ experiment_id = $id; exists = $false; status = ''; results = 0; notes = 0; note = '' }
    try {
        $detail = Invoke-RestMethod -Method Get -Headers $headers -Uri "$BaseUrl/api/experiments/$id"
        $row.exists = $true
        $row.status = $detail.status
        try {
            $res = Invoke-RestMethod -Method Get -Headers $headers -Uri "$BaseUrl/api/experiments/$id/results"
            $row.results = @($res).Count
        } catch { $row.note = 'results lookup failed' }
        if ($detail.PSObject.Properties.Name -contains 'notes') { $row.notes = @($detail.notes).Count }
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 404) { $row.note = 'not found' }
        else { $row.note = "lookup error: $($_.Exception.Message)" }
    }
    [pscustomobject]$row
}

$report | Format-Table -AutoSize

$missing  = @($report | Where-Object { -not $_.exists })
$withData = @($report | Where-Object { $_.results -gt 0 })

Write-Host ""
Write-Host "Found:        $(@($report | Where-Object exists).Count)" -ForegroundColor Cyan
Write-Host "Not found:    $($missing.Count)" -ForegroundColor $(if ($missing.Count) { 'Yellow' } else { 'Cyan' })
Write-Host "With results: $($withData.Count)" -ForegroundColor $(if ($withData.Count) { 'Red' } else { 'Cyan' })

if ($withData.Count -gt 0) {
    Write-Host ""
    Write-Host "STOP. The following carry result rows. Confirm they are disposable before deleting:" -ForegroundColor Red
    $withData | ForEach-Object { Write-Host "  $($_.experiment_id)  ($($_.results) result(s))" -ForegroundColor Red }
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$reportPath = Join-Path (Split-Path -Parent $IdFile) "delete_preflight_$stamp.csv"
$report | Export-Csv -NoTypeInformation -Path $reportPath
Write-Host ""
Write-Host "Pre-flight report written to $reportPath" -ForegroundColor Cyan

if (-not $Execute) {
    Write-Host ""
    Write-Host "DRY RUN. Nothing was deleted. Re-run with -Execute to proceed." -ForegroundColor Yellow
    return
}

# ---------------------------------------------------------------------------
# Pass 2: delete
# ---------------------------------------------------------------------------
Write-Host ""
$confirm = Read-Host "Delete $(@($report | Where-Object exists).Count) experiment(s)? Type DELETE to confirm"
if ($confirm -ne 'DELETE') { Write-Host "Aborted." -ForegroundColor Yellow; return }

$results = foreach ($row in $report) {
    if (-not $row.exists) {
        [pscustomobject]@{ experiment_id = $row.experiment_id; outcome = 'skipped (not found)' }
        continue
    }
    try {
        Invoke-RestMethod -Method Delete -Headers $headers -Uri "$BaseUrl/api/experiments/$($row.experiment_id)" | Out-Null
        Write-Host "  deleted $($row.experiment_id)" -ForegroundColor Green
        [pscustomobject]@{ experiment_id = $row.experiment_id; outcome = 'deleted' }
    } catch {
        $msg = $_.Exception.Message
        Write-Host "  FAILED  $($row.experiment_id): $msg" -ForegroundColor Red
        [pscustomobject]@{ experiment_id = $row.experiment_id; outcome = "failed: $msg" }
    }
}

$logPath = Join-Path (Split-Path -Parent $IdFile) "delete_results_$stamp.csv"
$results | Export-Csv -NoTypeInformation -Path $logPath

$deleted = @($results | Where-Object { $_.outcome -eq 'deleted' }).Count
$failed  = @($results | Where-Object { $_.outcome -like 'failed*' }).Count
Write-Host ""
Write-Host "Deleted: $deleted   Failed: $failed   Log: $logPath" -ForegroundColor Cyan
if ($failed -gt 0) {
    Write-Host "Re-run against a file containing only the failures, or fall back to" -ForegroundColor Yellow
    Write-Host "scripts/sql/delete_serum_catalyst_leftovers_20260729.sql for those rows." -ForegroundColor Yellow
}
