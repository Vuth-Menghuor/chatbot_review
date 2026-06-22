#!/usr/bin/env pwsh
<#
.SYNOPSIS
Start GDCE Trade Query Service v2

.DESCRIPTION
Starts Trade Query v2 FastAPI service on port 8004 by default.

.EXAMPLE
.\start_trade_query.ps1

.EXAMPLE
.\start_trade_query.ps1 -Reload -Debug -Port 8004
#>

param(
    [switch]$Reload,
    [switch]$Debug,
    [string]$Port = "8004"
)

$green = [System.ConsoleColor]::Green
$red = [System.ConsoleColor]::Red
$yellow = [System.ConsoleColor]::Yellow
$cyan = [System.ConsoleColor]::Cyan

function Write-Header {
    param([string]$Message)
    Write-Host "============================================================" -ForegroundColor $cyan
    Write-Host $Message -ForegroundColor $cyan
    Write-Host "============================================================" -ForegroundColor $cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[+] $Message" -ForegroundColor $green
}

function Write-CustomError {
    param([string]$Message)
    Write-Host "[-] $Message" -ForegroundColor $red
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[!] $Message" -ForegroundColor $yellow
}

function Write-Info {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor $cyan
}

function Stop-PortProcess {
    param([int]$TargetPort)

    try {
        $netstatOutput = netstat -ano | Select-String ":$TargetPort\s"
        if ($netstatOutput) {
            foreach ($line in $netstatOutput) {
                $parts = $line -split '\s+' | Where-Object { $_ }
                $processId = $parts[-1]
                if ($processId -and $processId -match '^\d+$') {
                    Write-Warning "Killing process $processId using port $TargetPort..."
                    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
                    Start-Sleep -Milliseconds 500
                }
            }
            Write-Success "Port $TargetPort cleaned up"
        }
        else {
            Write-Info "Port $TargetPort is already free"
        }
    }
    catch {
        Write-Info "Port cleanup skipped: $($_.Exception.Message)"
    }
}

Write-Header "GDCE Trade Query Service v2 - Startup"

$scriptDir = Split-Path -Parent -Path $MyInvocation.MyCommand.Definition
$repoRoot = Split-Path -Parent -Path (Split-Path -Parent -Path $scriptDir)
$serviceDir = Join-Path $repoRoot "services_version2\trade_query_version2"
$venvDir = Join-Path $repoRoot "env"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"

Write-Info "Repository Root  : $repoRoot"
Write-Info "Service Dir      : $serviceDir"
Write-Info "Python Exe       : $pythonExe"
Write-Info "Service Port     : $Port"
Write-Host ""

if (-not (Test-Path $serviceDir)) {
    Write-CustomError "Service directory not found: $serviceDir"
    exit 1
}

if (-not (Test-Path $pythonExe)) {
    Write-CustomError "Python executable not found: $pythonExe"
    Write-Info "Create environment first: python -m venv env"
    exit 1
}

Set-Location $repoRoot
$env:PYTHONPATH = "$repoRoot;$($repoRoot)\services_version2"
$env:PYTHONUNBUFFERED = "1"
$env:TRADE_SERVICE_PORT = "$Port"

if ($Debug) {
    $env:DEBUG = "true"
}

Write-Info "Cleaning and checking port $Port..."
Stop-PortProcess -TargetPort ([int]$Port)
Start-Sleep -Seconds 1

Write-Header "Startup Information"
Write-Info "URL       : http://127.0.0.1:$Port"
Write-Info "Docs      : http://127.0.0.1:$Port/docs"
Write-Info "Health    : http://127.0.0.1:$Port/health"
Write-Info "Module    : services_version2.trade_query_version2.app:app"
Write-Host ""

$logLevel = if ($Debug) { "debug" } else { "info" }
$uvicornArgs = @(
    "-m", "uvicorn",
    "services_version2.trade_query_version2.app:app",
    "--host", "127.0.0.1",
    "--port", "$Port",
    "--log-level", $logLevel
)

if ($Reload) {
    $uvicornArgs += "--reload"
}

try {
    Write-Info "Starting Trade Query v2..."
    & $pythonExe @uvicornArgs
    Write-Warning "Service stopped"
}
catch {
    Write-CustomError "Failed to start service: $($_.Exception.Message)"
    exit 1
}
