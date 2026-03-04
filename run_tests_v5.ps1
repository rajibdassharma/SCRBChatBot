<#
.SYNOPSIS
    Run automated integration tests for ISD Document Intelligence V5.

.DESCRIPTION
    Prerequisites:
      1. V5 backend must be running:   .\start_v5_backend.ps1
      2. MSSQL (ISDIntelligenceV5) must be accessible
      3. Neo4j must be running on bolt://localhost:7687
      4. Anaconda Python must be in PATH or use full path below

.USAGE
    # Run all tests
    .\run_tests_v5.ps1

    # Run a specific test file
    .\run_tests_v5.ps1 -TestFile test_auth.py

    # Run a specific test class
    .\run_tests_v5.ps1 -TestFilter "TestCaseCRUD"

    # Run with extra verbosity (-s shows print statements)
    .\run_tests_v5.ps1 -Extra "-s"
#>

param(
    [string]$TestFile  = "",
    [string]$TestFilter = "",
    [string]$Extra     = ""
)

$PYTHON   = "C:\Anaconda3\anaconda3\python.exe"
$BACKEND  = "YAIA-main\ISDDocumentIntelligence_V5\backend"
$BASE_URL = "http://localhost:8002"

Set-Location $PSScriptRoot

# ── Check backend is running ───────────────────────────────────────────────
Write-Host "`n=== Checking backend at $BASE_URL ===" -ForegroundColor Cyan
try {
    $health = Invoke-RestMethod -Uri "$BASE_URL/health" -TimeoutSec 5
    if ($health.ok) {
        Write-Host "Backend is UP: $($health.service)" -ForegroundColor Green
    } else {
        Write-Host "Backend returned unexpected response." -ForegroundColor Yellow
    }
} catch {
    Write-Host "ERROR: Cannot reach backend at $BASE_URL" -ForegroundColor Red
    Write-Host "Please start it first: .\start_v5_backend.ps1" -ForegroundColor Yellow
    exit 1
}

# ── Install test dependencies (once) ──────────────────────────────────────
Write-Host "`n=== Installing test dependencies ===" -ForegroundColor Cyan
& $PYTHON -m pip install -q -r "$BACKEND\requirements-test.txt"

# ── Build pytest command ───────────────────────────────────────────────────
$PytestArgs = @()

if ($TestFile) {
    $PytestArgs += "tests/$TestFile"
} elseif ($TestFilter) {
    $PytestArgs += "-k", $TestFilter
}

if ($Extra) {
    $PytestArgs += $Extra.Split(" ")
}

# ── Run tests ──────────────────────────────────────────────────────────────
Write-Host "`n=== Running Tests ===" -ForegroundColor Cyan
Set-Location $BACKEND
& $PYTHON -m pytest @PytestArgs

$ExitCode = $LASTEXITCODE
Set-Location $PSScriptRoot

if ($ExitCode -eq 0) {
    Write-Host "`n=== ALL TESTS PASSED ===" -ForegroundColor Green
} else {
    Write-Host "`n=== SOME TESTS FAILED (exit code $ExitCode) ===" -ForegroundColor Red
}

exit $ExitCode
