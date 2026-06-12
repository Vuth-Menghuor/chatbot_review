#!/usr/bin/env pwsh
<#
.SYNOPSIS
Start GDCE Calculator Service v2

.DESCRIPTION
Launches the Calculator Service v2 (port 8002) with Qdrant, PostgreSQL, and CSV data source support.
Uses KHR-first methodology for all import tax calculations.

.EXAMPLE
.\start_calculator_v2.ps1

.NOTES
- Service runs on http://127.0.0.1:8002
- API docs available at http://127.0.0.1:8002/docs
- Main endpoint: POST /v1/calculate_import_taxes
- Environment: configs/.env and services_version2/calculator_version2/.env
#>

param(
    [switch]$Reload,
    [switch]$Debug,
    [string]$Port = "8002"
)

# =============================================================================
# FUNCTIONS
# =============================================================================

function Stop-PortProcess {
    <#
    .SYNOPSIS
    Stop any process using a specific port
    
    .PARAMETER Port
    The port number to clean up
    #>
    param([int]$Port)
    
    try {
        $netstatOutput = netstat -ano | Select-String ":$Port\s"
        if ($netstatOutput) {
            foreach ($line in $netstatOutput) {
                $parts = $line -split '\s+' | Where-Object { $_ }
                $processId = $parts[-1]
                if ($processId -and $processId -match '^\d+$') {
                    Write-Host "[!] Killing process $processId using port $Port..." -ForegroundColor Yellow
                    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
                    Start-Sleep -Milliseconds 500
                }
            }
            Write-Host "[+] Port $Port cleaned up" -ForegroundColor Green
        }
    }
    catch {
        Write-Host "[*] No processes found on port $Port (or already clean)" -ForegroundColor Cyan
    }
}

# =============================================================================
# HEADER
# =============================================================================

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  GDCE Calculator Service v2 - Startup Script" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""

# Set root directory (absolute path)
$RootDir = "e:\GDCE-Intern\RAG\GDCE-ChatBot"
$ServiceDir = Join-Path $RootDir "services_version2\calculator_version2"
$EnvFile = Join-Path $ServiceDir ".env"

Write-Host "[*] Configuration:" -ForegroundColor Green
Write-Host "    Root Directory: $RootDir" -ForegroundColor White
Write-Host "    Service Path: $ServiceDir" -ForegroundColor White
Write-Host "    Port: $Port" -ForegroundColor White
Write-Host "    Environment: $EnvFile" -ForegroundColor White
Write-Host ""

# Verify service directory exists
if (-not (Test-Path $ServiceDir)) {
    Write-Host "[ERROR] Service directory not found: $ServiceDir" -ForegroundColor Red
    Write-Host "Please ensure the calculator_version2 service is installed." -ForegroundColor Yellow
    exit 1
}

# Verify .env file exists
if (-not (Test-Path $EnvFile)) {
    Write-Host "[WARNING] .env file not found at $EnvFile" -ForegroundColor Yellow
    Write-Host "         Using default configuration..." -ForegroundColor Yellow
}

# Set environment variables
Write-Host "[*] Setting up environment..." -ForegroundColor Green
Set-Location $RootDir
$env:PYTHONPATH = "$RootDir;$($RootDir)\services_version2"
$env:PYTHONUNBUFFERED = "1"

if ($Debug) {
    $env:DEBUG = "true"
    Write-Host "    Debug mode: ENABLED" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "[*] Data Sources:" -ForegroundColor Green
Write-Host "    - Qdrant:     172.25.3.243:6333 (gdce_hs_code collection)" -ForegroundColor White
Write-Host "    - PostgreSQL: 172.25.3.243:5432 (gdce_hs_code database)" -ForegroundColor White
Write-Host "    - CSV:        data/raw/tables/Duty & Tax.csv (fallback)" -ForegroundColor White
Write-Host ""

Write-Host "[*] Starting Calculator Service v2..." -ForegroundColor Green
Write-Host "    Endpoint: http://127.0.0.1:$Port" -ForegroundColor Cyan
Write-Host "    API Docs: http://127.0.0.1:$Port/docs" -ForegroundColor Cyan
Write-Host "    Health:   http://127.0.0.1:$Port/health" -ForegroundColor Cyan
Write-Host ""
Write-Host "[!] Waiting 3 seconds before starting..." -ForegroundColor Yellow
Write-Host ""

Start-Sleep -Seconds 3

# =============================================================================
# CLEAN UP PORT
# =============================================================================

Write-Host "[*] Cleaning up port $Port..." -ForegroundColor Green
Stop-PortProcess -Port $Port
Start-Sleep -Seconds 1

# =============================================================================
# START SERVICE
# =============================================================================

# Run the service
try {
    Write-Host "[>] Launching FastAPI server..." -ForegroundColor Green
    Write-Host ""
    
    $pythonExe = Join-Path $RootDir "env\Scripts\python.exe"
    $reloadFlag = if ($Reload) { "--reload" } else { "" }
    $logLevel = if ($Debug) { "debug" } else { "info" }
    
    & $pythonExe -m uvicorn `
        calculator_version2.main:app `
        --host 127.0.0.1 `
        --port $Port `
        $reloadFlag `
        --log-level $logLevel
}
catch {
    Write-Host "[ERROR] Failed to start service: $_" -ForegroundColor Red
    exit 1
}
