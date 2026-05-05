<#
.SYNOPSIS
    V6 IR Reindex - PART 1: all local Windows phases.

.DESCRIPTION
    Runs Phases 1A through 1E end-to-end on the Windows machine:
      1A - pre-flight checks (CUDA, backend health, folder exists)
      1B - local MySQL + ChromaDB backup (timestamped, never clobbers)
      1C - bulk-index the IR files via bulk_index_ir.py (dry-run first, then real)
      1D - verification: print post-index doc counts
      1E - produce transfer artifacts in C:/Transfer/V6 (mysqldump + chroma copy)

    MySQL credentials are read from backend/.env. The IR files folder is
    the only thing you change between runs - pass via -Folder.

.PARAMETER Folder
    Required. Folder containing the IR DOCX/DOC/PDF files. Subfolders are
    recursed automatically.

.PARAMETER Password
    Optional. Backend admin password for /docs/upload login. If omitted,
    you'll be prompted (recommended for security).

.PARAMETER Username
    Optional. Backend admin username. Defaults to "admin".

.PARAMETER BackupDir
    Optional. Where to write pre-index backups. Defaults to C:/Backups/V6.

.PARAMETER TransferDir
    Optional. Where to write USB-bound artifacts. Defaults to C:/Transfer/V6.

.PARAMETER BackendUrl
    Optional. Backend base URL. Defaults to http://localhost:8003.

.PARAMETER DryRun
    If set, runs only the bulk-index dry-run (Phase 1C step 1) and exits.

.PARAMETER SkipBackup
    If set, skips Phase 1B (local backup). Use if you already have a fresh
    backup from a previous run that you want to keep as the rollback point.

.PARAMETER SkipTransfer
    If set, skips Phase 1E (transfer artifact prep). Use if you only want
    to index locally without preparing a server deploy.

.EXAMPLE
    .\reindex_local.ps1 -Folder "C:/IR_Files_Batch2026May"

.EXAMPLE
    .\reindex_local.ps1 -Folder "C:/IR_Files_Batch2026May" -DryRun
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Folder,

    [string]$Password,
    [string]$Username = "admin",
    [string]$BackupDir = "C:/Backups/V6",
    [string]$TransferDir = "C:/Transfer/V6",
    [string]$BackendUrl = "http://localhost:8003",
    [switch]$DryRun,
    [switch]$SkipBackup,
    [switch]$SkipTransfer
)

$ErrorActionPreference = "Stop"

# Resolve paths from script location (so the script is portable)
$ScriptDir   = $PSScriptRoot
$ProjectRoot = (Resolve-Path "$ScriptDir/..").Path
$BackendDir  = "$ProjectRoot/backend"
$Timestamp   = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupRun   = "$BackupDir/$Timestamp"

function Write-Phase($title) {
    Write-Host ""
    Write-Host ("=" * 62) -ForegroundColor Cyan
    Write-Host "  $title" -ForegroundColor Cyan
    Write-Host ("=" * 62) -ForegroundColor Cyan
}

function Get-EnvValue($name) {
    $envFile = "$BackendDir/.env"
    if (-not (Test-Path $envFile)) { return $null }
    foreach ($line in Get-Content $envFile) {
        if ($line -match "^\s*$name\s*=\s*(.+?)\s*$") {
            return $Matches[1].Trim('"').Trim("'")
        }
    }
    return $null
}

# Read MySQL creds from backend/.env (with fallbacks to defaults)
$MysqlUser = (Get-EnvValue "MYSQL_USER")     ; if (-not $MysqlUser)     { $MysqlUser     = "root" }
$MysqlPwd  = (Get-EnvValue "MYSQL_PASSWORD") ; if ($null -eq $MysqlPwd) { $MysqlPwd      = "" }
$MysqlDb   = (Get-EnvValue "MYSQL_DATABASE") ; if (-not $MysqlDb)       { $MysqlDb       = "ISDIntelligence" }

function Invoke-Mysql($sql) {
    & mysql -u $MysqlUser "-p$MysqlPwd" $MysqlDb -e $sql
    if ($LASTEXITCODE -ne 0) { throw "mysql command failed (exit $LASTEXITCODE)" }
}

# ============================================================
# Phase 1A - Pre-flight
# ============================================================
Write-Phase "Phase 1A - Pre-flight"

if (-not (Test-Path $Folder)) {
    Write-Error "IR files folder not found: $Folder"
    exit 1
}
Write-Host "IR folder: $Folder"

Write-Host "Checking CUDA..."
# Use a temp .py file - PS 5.1 native-command quoting strips inner double
# quotes when passing python -c "..." with embedded quotes/parens. Writing
# to a file sidesteps the entire quoting problem.
$cudaCheckPy = @'
import torch
ok = torch.cuda.is_available()
print("CUDA:", "True" if ok else "False")
print("GPU:", torch.cuda.get_device_name(0) if ok else "NONE")
'@
$tmpPy = [System.IO.Path]::Combine($env:TEMP, "v6_cuda_check_$([guid]::NewGuid().ToString('N')).py")
Set-Content -Path $tmpPy -Value $cudaCheckPy -Encoding ASCII
try {
    $cudaOut = python $tmpPy
    $cudaOut | ForEach-Object { Write-Host "  $_" }
    # NOTE: $cudaOut is an array. -match / -notmatch on arrays return
    # the matching/non-matching elements (not a boolean), so naive
    # `if ($arr -notmatch "...")` is always truthy when ANY element
    # doesn't match. Join to a single string before the check.
    $cudaJoined = $cudaOut -join "`n"
    if ($cudaJoined -notmatch "CUDA:\s*True") {
        Write-Warning "CUDA not available - embeddings will run on CPU and be much slower."
        $confirm = Read-Host "Continue anyway? (y/N)"
        if ($confirm -ne "y") { exit 1 }
    }
} finally {
    Remove-Item -Force $tmpPy -ErrorAction SilentlyContinue
}

Write-Host "Checking backend health at $BackendUrl..."
try {
    $health = Invoke-RestMethod "$BackendUrl/health" -TimeoutSec 5
    Write-Host "  Backend OK: $($health | ConvertTo-Json -Compress)"
} catch {
    Write-Error "Backend not reachable at $BackendUrl. Start it first (uvicorn app:app --port 8003)."
    exit 1
}

New-Item -ItemType Directory -Force $BackupDir   | Out-Null
New-Item -ItemType Directory -Force $TransferDir | Out-Null

Write-Host "Baseline counts (before indexing):"
Invoke-Mysql "SELECT COUNT(DISTINCT doc_id) AS ir_docs, COUNT(*) AS ir_field_rows FROM ir_reports;"

# ============================================================
# Phase 1B - Local backup
# ============================================================
if ($SkipBackup) {
    Write-Phase "Phase 1B - Local backup (SKIPPED)"
} else {
    Write-Phase "Phase 1B - Local backup -> $BackupRun"
    New-Item -ItemType Directory -Force $BackupRun | Out-Null

    $backupSql = "$BackupRun/local_pre_index_ISDIntelligence.sql"
    Write-Host "Dumping MySQL -> $backupSql"
    # IMPORTANT: --result-file=, NOT shell redirection. PS5.1's > and Out-File
    # default to UTF-16 LE with BOM AND treat the binary stream as text -
    # which truncates dumps at \0 bytes and produces tiny/corrupt files.
    & mysqldump -u $MysqlUser "-p$MysqlPwd" --single-transaction --routines `
        "--result-file=$backupSql" $MysqlDb
    if ($LASTEXITCODE -ne 0) { Write-Error "mysqldump failed"; exit 1 }
    $sqlSize = (Get-Item $backupSql).Length
    Write-Host "  Done - $sqlSize bytes"

    # NOTE: deliberately NOT named $folder - that would case-insensitively
    # clobber the $Folder parameter (PS variable names are case-insensitive).
    foreach ($chromaDir in @("chroma_db_ir_v6", "chroma_db_smac_v6")) {
        $src = "$BackendDir/$chromaDir"
        $dst = "$BackupRun/local_pre_index_$chromaDir"
        if (Test-Path $src) {
            Write-Host "Copying $chromaDir -> $dst"
            Copy-Item -Recurse -Force $src $dst
        }
    }

    $progressDb = "$ScriptDir/.ir_bulk_progress.db"
    if (Test-Path $progressDb) {
        Copy-Item $progressDb "$BackupRun/local_pre_index_ir_progress.db"
        Write-Host "  Copied .ir_bulk_progress.db (resume state)"
    }
}

# ============================================================
# Phase 1C - Local indexing
# ============================================================
Write-Phase "Phase 1C - Local indexing"

if (-not $Password) {
    $sec  = Read-Host "Backend password for $Username" -AsSecureString
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    $Password = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
}

Push-Location $ScriptDir
try {
    Write-Host "Dry-run (file discovery)..."
    python bulk_index_ir.py --folder $Folder --dry-run
    if ($LASTEXITCODE -ne 0) { Write-Error "Dry-run failed"; exit 1 }

    if ($DryRun) {
        Write-Host "Dry-run only - stopping here."
        exit 0
    }

    Write-Host ""
    $confirm = Read-Host "Proceed with real indexing? (y/N)"
    if ($confirm -ne "y") { exit 1 }

    Write-Host "Real run starting..."
    python bulk_index_ir.py --folder $Folder --username $Username --password $Password --backend-url $BackendUrl
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "bulk_index_ir.py exited non-zero - some files failed. Check logfiles/bulk_index_ir.log; re-run this script to retry only failed files."
    }
} finally {
    Pop-Location
}

# ============================================================
# Phase 1D - Verification
# ============================================================
Write-Phase "Phase 1D - Local verification"
Write-Host "Counts after indexing (compare to Phase 1A baseline):"
Invoke-Mysql "SELECT COUNT(DISTINCT doc_id) AS ir_docs, COUNT(*) AS ir_field_rows FROM ir_reports;"
Write-Host ""
Write-Host "-> Now spot-check 1-2 new files via the frontend Q&A before the transfer."

# ============================================================
# Phase 1E - Transfer artifacts
# ============================================================
if ($SkipTransfer) {
    Write-Phase "Phase 1E - Transfer artifacts (SKIPPED)"
} else {
    Write-Phase "Phase 1E - Prepare transfer artifacts"

    # Fresh transfer dir each run (safe - old USB content is gone after deploy)
    if (Test-Path "$TransferDir/chroma_db_ir_v6") {
        Remove-Item -Recurse -Force "$TransferDir/chroma_db_ir_v6"
    }
    foreach ($oldFile in @("post_index_ISDIntelligence_no_ranking.sql", "ir_reports_only.sql")) {
        $oldPath = "$TransferDir/$oldFile"
        if (Test-Path $oldPath) { Remove-Item -Force $oldPath }
    }

    # Single-table approach: only dump the ir_reports table. Server-side
    # restore will DROP+CREATE+INSERT just that one table, leaving every
    # other table on the server (users, cases, smac_reports, entities,
    # answer_ratings, etc.) completely untouched. Much safer than
    # restoring the whole DB and relying on --ignore-table.
    # Use --result-file= (NOT > or Out-File) so the binary stream isn't
    # mangled by PS5.1 text-mode redirection.
    $transferSql = "$TransferDir/ir_reports_only.sql"
    Write-Host "Dumping ir_reports table -> $transferSql"
    & mysqldump -u $MysqlUser "-p$MysqlPwd" --single-transaction `
        "--result-file=$transferSql" $MysqlDb ir_reports
    if ($LASTEXITCODE -ne 0) { Write-Error "Transfer mysqldump failed"; exit 1 }
    $transferSize = (Get-Item $transferSql).Length
    Write-Host "  Done - $transferSize bytes"

    Write-Host "Copying chroma_db_ir_v6 -> $TransferDir"
    Copy-Item -Recurse "$BackendDir/chroma_db_ir_v6" "$TransferDir/chroma_db_ir_v6"

    Write-Host ""
    Write-Host ("=" * 62) -ForegroundColor Green
    Write-Host "  PART 1 COMPLETE - Windows work done" -ForegroundColor Green
    Write-Host ("=" * 62) -ForegroundColor Green
    Write-Host ""
    Write-Host "Next: copy ${TransferDir} to USB -> server /opt/transfer/v6/"
    Write-Host "Then on server: sudo bash /opt/isd/ISDDocumentIntelligence_V6/dbscripts/reindex_server.sh"
}
