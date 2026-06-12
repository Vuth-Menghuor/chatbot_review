# Start GDCE Orchestrator Service v2
# This script activates the Python virtual environment and starts the orchestrator service

param(
    [switch] $Interactive = $false
)

# Get script directory
$scriptDir = Split-Path -Parent -Path $MyInvocation.MyCommand.Definition
$repoRoot = Split-Path -Parent -Path (Split-Path -Parent -Path $scriptDir)
$serviceDir = Join-Path $repoRoot "services_version2\orchestrator_version2"
$venvDir = Join-Path $repoRoot "env"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"

# Colors for output
$green = [System.ConsoleColor]::Green
$red = [System.ConsoleColor]::Red
$yellow = [System.ConsoleColor]::Yellow
$cyan = [System.ConsoleColor]::Cyan

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
                    Write-Warning "Killing process $processId using port $Port..."
                    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
                    Start-Sleep -Milliseconds 500
                }
            }
            Write-Success "Port $Port cleaned up"
        }
    }
    catch {
        Write-Info "No processes found on port $Port (or already clean)"
    }
}

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

# =============================================================================
# CHECKS
# =============================================================================

Write-Header "GDCE Orchestrator Service v2 - Startup"

# Set working directory and environment BEFORE any checks
Set-Location $repoRoot
$env:PYTHONPATH = "$repoRoot;$($repoRoot)\services_version2"
$env:PYTHONUNBUFFERED = "1"

# Check 1: Verify repository root exists
Write-Info "Checking repository structure..."
if (-not (Test-Path $repoRoot)) {
    Write-CustomError "Repository root not found: $repoRoot"
    exit 1
}
Write-Success "Repository root found"

# Check 2: Verify service directory exists
if (-not (Test-Path $serviceDir)) {
    Write-CustomError "Service directory not found: $serviceDir"
    exit 1
}
Write-Success "Service directory found"

# Check 3: Verify virtual environment exists
if (-not (Test-Path $venvDir)) {
    Write-CustomError "Virtual environment not found at: $venvDir"
    Write-Info "Create it with: python -m venv $venvDir"
    exit 1
}
Write-Success "Virtual environment found"

# Check 4: Verify Python executable exists
if (-not (Test-Path $pythonExe)) {
    Write-CustomError "Python executable not found: $pythonExe"
    exit 1
}
Write-Success "Python executable found"

# Check 5: Verify main.py exists
$mainPy = Join-Path $serviceDir "main.py"
if (-not (Test-Path $mainPy)) {
    Write-CustomError "main.py not found: $mainPy"
    exit 1
}
Write-Success "main.py found"

# Check 6: Verify app.py exists
$appPy = Join-Path $serviceDir "app.py"
if (-not (Test-Path $appPy)) {
    Write-CustomError "app.py not found: $appPy"
    exit 1
}
Write-Success "app.py found"

# Check 7: Verify config.py exists
$configPy = Join-Path $serviceDir "config.py"
if (-not (Test-Path $configPy)) {
    Write-CustomError "config.py not found: $configPy"
    exit 1
}
Write-Success "config.py found"

Write-Host ""

# =============================================================================
# CHECK PORT AVAILABILITY & CLEANUP
# =============================================================================

Write-Info "Checking and cleaning port 8001..."
Stop-PortProcess -Port 8001
Start-Sleep -Seconds 1

Write-Host ""

# =============================================================================
# STARTUP INFORMATION
# =============================================================================

Write-Header "Startup Information"
Write-Info "Repository Root  : $repoRoot"
Write-Info "Service Dir      : $serviceDir"
Write-Info "Virtual Env      : $venvDir"
Write-Info "Python Exe       : $pythonExe"
Write-Info "Service Port     : 8001"
Write-Info "API Docs URL     : http://localhost:8001/docs"
Write-Info "Startup Script   : $scriptDir"
Write-Host ""

# =============================================================================
# START SERVICE
# =============================================================================

Write-Info "Starting GDCE Orchestrator Service v2..."
Write-Info "This may take 10-20 seconds for initialization..."
Write-Host ""

try {
    # Run the service using uvicorn with the module:app pattern
    # This is the same pattern used for calculator service and works reliably
    # Note: Windows has issues with multiple workers + socket reuse, use single worker
    & $pythonExe -m uvicorn `
        services_version2.orchestrator_version2.main:app `
        --host 127.0.0.1 `
        --port 8001 `
        --workers 1
    
    # If we reach here, the service was stopped
    Write-Warning "Service stopped"
}
catch {
    $errorMsg = $_.Exception.Message
    Write-CustomError "Failed to start service: $errorMsg"
    exit 1
}
