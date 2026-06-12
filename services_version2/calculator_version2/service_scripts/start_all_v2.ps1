#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Start GDCE v2 Services (Orchestrator + Calculator + Retrieval + Trade Query) and Interactive Chat
    
.DESCRIPTION
    Starts the Orchestrator Service (port 8001), Calculator Service (port 8002),
    Retrieval Service (port 8003), and Trade Query Service (port 8004), waits for all required services to be ready,
    then launches the interactive chat interface.
    
.PARAMETER OrchestratorPort
    Port for Orchestrator service (default: 8001)
    
.PARAMETER CalculatorPort
    Port for Calculator service (default: 8002)

.PARAMETER RetrievalPort
    Port for Retrieval service (default: 8003)

.PARAMETER TradeQueryPort
    Port for Trade Query service (default: 8004)
    
.EXAMPLE
    .\start_all_v2.ps1
    
.NOTES
    Version: 1.2
    Date: 2026-04-06
#>

param(
    [int]$OrchestratorPort = 8001,
    [int]$CalculatorPort = 8002,
    [int]$RetrievalPort = 8003,
    [int]$TradeQueryPort = 8004,
    [bool]$OrchestratorReload = $true,
    [switch]$SkipCalculator = $false,
    [switch]$SkipRetrieval = $false,
    [switch]$SkipTradeQuery = $false,
    [int]$HealthCheckTimeout = 60
)

# On Windows, disable uvicorn reload to avoid multiprocessing/lifespan race
# which can cause asyncio CancelledError / KeyboardInterrupt when using the
# reloader in long-running orchestration scripts.
if ($env:OS -eq 'Windows_NT' -and $OrchestratorReload) {
    Write-Host '⚠️ Detected Windows; disabling Orchestrator reload to avoid uvicorn reloader issues.'
    $OrchestratorReload = $false
}

# =====================================================================
# CONFIGURATION
# =====================================================================
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# Get script directory and project root
$scriptDir = $PSScriptRoot
if (-not $scriptDir) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommandPath
}
if (-not $scriptDir) {
    $scriptDir = Get-Location
}

# Project root is parent of service_scripts folder
$projectRoot = Split-Path -Parent $scriptDir

# Service paths
$orchestratorPath = Join-Path $projectRoot 'services_version2' | ForEach-Object { Join-Path $_ 'orchestrator_version2' }
$calculatorPath = Join-Path $projectRoot 'services_version2' | ForEach-Object { Join-Path $_ 'calculator_version2' }
$retrievalPath = Join-Path $projectRoot 'services_version2' | ForEach-Object { Join-Path $_ 'retrieval_version2' }
$tradeQueryPath = Join-Path $projectRoot 'services_version2' | ForEach-Object { Join-Path $_ 'trade_query_version2' }
$interactiveChatScript = Join-Path $scriptDir 'interactive_chat.ps1'

# URLs
$OrchestratorUrl = 'http://127.0.0.1:{0}' -f $OrchestratorPort
$CalculatorUrl = 'http://127.0.0.1:{0}' -f $CalculatorPort
$RetrievalUrl = 'http://127.0.0.1:{0}' -f $RetrievalPort
$TradeQueryUrl = 'http://127.0.0.1:{0}' -f $TradeQueryPort

# =====================================================================
# FUNCTIONS
# =====================================================================

function Write-Header {
    param([string]$Title)
    Write-Host '' -ForegroundColor Cyan
    Write-Host ('=' * 70) -ForegroundColor Cyan
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ('=' * 70) -ForegroundColor Cyan
}

function Write-Status {
    param([string]$Message, [string]$Color = 'White')
    Write-Host $Message -ForegroundColor $Color
}

function Test-ServiceReady {
    param(
        [string]$ServiceName,
        [string]$Url,
        [string]$HealthPath = '/health',
        [int]$TimeoutSeconds = 60
    )
    
    $endTime = (Get-Date).AddSeconds($TimeoutSeconds)
    $attempt = 0
    
    while ((Get-Date) -lt $endTime) {
        $attempt++
        try {
            $normalizedHealthPath = if ($HealthPath.StartsWith('/')) { $HealthPath } else { "/$HealthPath" }
            $response = Invoke-WebRequest -Uri "$Url$normalizedHealthPath" -Method GET -ErrorAction Stop -TimeoutSec 3
            # Accept any response (200, 503, etc) as long as service is responding
            Write-Status ('[OK] {0} is responding at {1}' -f $ServiceName, $Url) 'Green'
            return $true
        }
        catch {
            # If we can connect but get an error, that still means the service is up
            if ($_.Exception.Message -like '*500*' -or $_.Exception.Message -like '*503*') {
                Write-Status ('[OK] {0} is running at {1} (partial health)' -f $ServiceName, $Url) 'Green'
                return $true
            }
            
            if ($attempt % 10 -eq 0) {
                Write-Host -NoNewline '*'
            } else {
                Write-Host -NoNewline '.'
            }
            Start-Sleep -Seconds 1
        }
    }
    
    Write-Status ('[FAIL] {0} failed to respond within {1} seconds' -f $ServiceName, $TimeoutSeconds) 'Yellow'
    return $false
}

function Start-Service {
    param(
        [string]$ServiceName,
        [string]$ServicePath,
        [string]$ModulePath,
        [int]$Port,
        [bool]$Reload = $false,
        [hashtable]$EnvironmentVariables = @{}
    )
    
    Write-Status ('Starting {0}...' -f $ServiceName) 'Yellow'
    
    if (-not (Test-Path $ServicePath)) {
        Write-Status ('ERROR: Service path not found: {0}' -f $ServicePath) 'Red'
        return $null
    }
    
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'python'
    $reloadArgs = if ($Reload) { ' --reload' } else { '' }
    $psi.Arguments = '-m uvicorn {0} --host 127.0.0.1 --port {1} --log-level info{2}' -f $ModulePath, $Port, $reloadArgs
    $psi.WorkingDirectory = $projectRoot
    $psi.UseShellExecute = $false
    
    # Add environment variables if provided
    foreach ($key in $EnvironmentVariables.Keys) {
        $psi.EnvironmentVariables[$key] = $EnvironmentVariables[$key]
    }
    
    $process = [System.Diagnostics.Process]::Start($psi)
    Write-Status ('  Process started with PID: {0}' -f $process.Id) 'Gray'
    
    # Return process object compatible with PassThru
    if ($process) {
        return $process
    }
    
    if ($process) {
        Write-Status ('  Process started with PID: {0}' -f $process.Id) 'Gray'
        return $process
    }
    else {
        Write-Status 'ERROR: Failed to start process' 'Red'
        return $null
    }
}

# =====================================================================
# CLEANUP FUNCTIONS
# =====================================================================

function Kill-ProcessOnPort {
    param(
        [int]$Port,
        [string]$ServiceName = "",
        [switch]$Force = $false
    )
    
    try {
        # Try to find the process listening on the port
        $cmd = "netstat -ano | findstr `:$Port"
        $result = Invoke-Expression $cmd -ErrorAction SilentlyContinue
        
        if ($result) {
            # Extract PIDs from netstat output
            $pids = @()
            foreach ($line in $result) {
                if ($line -match '\s+(\d+)\s*$') {
                    $pid = [int]$matches[1]
                    if ($pid -gt 0 -and $pids -notcontains $pid) {
                        $pids += $pid
                    }
                }
            }
            
            # Kill each process
            foreach ($pid in $pids) {
                try {
                    $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
                    if ($proc) {
                        if ($Force) {
                            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                            Write-Status "  [OK] Killed process $($proc.Name) (PID: $pid) on port $Port" 'Yellow'
                        } else {
                            Stop-Process -Id $pid -ErrorAction SilentlyContinue
                            Start-Sleep -Milliseconds 500
                            if (Get-Process -Id $pid -ErrorAction SilentlyContinue) {
                                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                            }
                            Write-Status "  [OK] Killed $ServiceName process (PID: $pid) on port $Port" 'Yellow'
                        }
                    }
                }
                catch {
                    # Silently continue if process is already gone
                }
            }
        }
    }
    catch {
        # Silently continue if no process found
    }
}

function Kill-AllServices {
    param([switch]$Force = $false)
    
    Write-Status 'Cleaning up services on ports 8001-8004...' 'Yellow'
    
    $ports = @(
        @{Port = 8001; Name = 'Orchestrator'},
        @{Port = 8002; Name = 'Calculator'},
        @{Port = 8003; Name = 'Retrieval'},
        @{Port = 8004; Name = 'Trade Query'}
    )
    
    foreach ($portInfo in $ports) {
        Kill-ProcessOnPort -Port $portInfo.Port -ServiceName $portInfo.Name -Force:$Force
    }
    
    # Give processes time to clean up
    Start-Sleep -Milliseconds 1000
    Write-Host ''
}

# =====================================================================
# MAIN PROGRAM
# =====================================================================

Clear-Host
Write-Header 'GDCE v2 Services Launcher'

# Kill any existing services on the service ports
Kill-AllServices -Force

Write-Status ('Project Root: {0}' -f $projectRoot) 'Gray'
Write-Status ('Orchestrator Service: {0}' -f $orchestratorPath) 'Gray'
Write-Status ('Calculator Service: {0}' -f $calculatorPath) 'Gray'
Write-Status ('Retrieval Service: {0}' -f $retrievalPath) 'Gray'
Write-Status ('Trade Query Service: {0}' -f $tradeQueryPath) 'Gray'
Write-Host ''

# Check if services are already running
Write-Status 'Checking for existing service instances...' 'Cyan'
$orchestratorRunning = $false
$calculatorRunning = $false
$retrievalRunning = $false
$tradeQueryRunning = $false

try {
    $resp = Invoke-WebRequest -Uri "$OrchestratorUrl/health" -Method GET -ErrorAction Stop -TimeoutSec 2
    if ($resp.StatusCode -eq 200) {
        $orchestratorRunning = $true
        Write-Status '[OK] Orchestrator is already running' 'Green'
    }
}
catch { }

try {
    $resp = Invoke-WebRequest -Uri "$CalculatorUrl/health" -Method GET -ErrorAction Stop -TimeoutSec 2
    if ($resp.StatusCode -eq 200) {
        $calculatorRunning = $true
        Write-Status '[OK] Calculator is already running' 'Green'
    }
}
catch { }

try {
    $resp = Invoke-WebRequest -Uri "$RetrievalUrl/v1/health" -Method GET -ErrorAction Stop -TimeoutSec 2
    if ($resp.StatusCode -eq 200) {
        $retrievalRunning = $true
        Write-Status '[OK] Retrieval is already running' 'Green'
    }
}
catch { }

try {
    $resp = Invoke-WebRequest -Uri "$TradeQueryUrl/health" -Method GET -ErrorAction Stop -TimeoutSec 2
    if ($resp.StatusCode -eq 200) {
        $tradeQueryRunning = $true
        Write-Status '[OK] Trade Query is already running' 'Green'
    }
}
catch { }

# Start services if not already running
$processes = @()

if (-not $orchestratorRunning) {
    $proc = Start-Service -ServiceName 'Orchestrator' `
        -ServicePath $orchestratorPath `
        -ModulePath 'services_version2.orchestrator_version2.main:app' `
        -Port $OrchestratorPort `
        -Reload:$OrchestratorReload
    
    if ($proc) {
        $processes += $proc
        Write-Status 'Waiting for Orchestrator to be ready...' 'Yellow'
        if (Test-ServiceReady -ServiceName 'Orchestrator' -Url $OrchestratorUrl -TimeoutSeconds $HealthCheckTimeout) {
            Write-Host ''
        }
        else {
            Write-Status 'WARNING: Orchestrator may not be fully ready, but continuing...' 'Yellow'
            Write-Host ''
            Start-Sleep -Seconds 3
        }
    }
}

if (-not $SkipCalculator -and -not $calculatorRunning) {
    $proc = Start-Service -ServiceName 'Calculator' `
        -ServicePath $calculatorPath `
        -ModulePath 'services_version2.calculator_version2.main:app' `
        -Port $CalculatorPort
    
    if ($proc) {
        $processes += $proc
        Write-Status 'Waiting for Calculator to be ready...' 'Yellow'
        if (Test-ServiceReady -ServiceName 'Calculator' -Url $CalculatorUrl -TimeoutSeconds $HealthCheckTimeout) {
            Write-Host ''
        }
        else {
            Write-Status 'WARNING: Calculator may not be fully ready' 'Yellow'
            Write-Host ''
        }
    }
}

if (-not $SkipRetrieval -and -not $retrievalRunning) {
    $proc = Start-Service -ServiceName 'Retrieval' `
        -ServicePath $retrievalPath `
        -ModulePath 'services_version2.retrieval_version2.app:app' `
        -Port $RetrievalPort `
        -EnvironmentVariables @{'QDRANT_HOST'='172.25.3.243'}

    if ($proc) {
        $processes += $proc
        Write-Status 'Waiting for Retrieval to be ready...' 'Yellow'
        if (Test-ServiceReady -ServiceName 'Retrieval' -Url $RetrievalUrl -HealthPath '/v1/health' -TimeoutSeconds $HealthCheckTimeout) {
            Write-Host ''
        }
        else {
            Write-Status 'WARNING: Retrieval may not be fully ready' 'Yellow'
            Write-Host ''
        }
    }
}

if (-not $SkipTradeQuery -and -not $tradeQueryRunning) {
    $proc = Start-Service -ServiceName 'Trade Query' `
        -ServicePath $tradeQueryPath `
        -ModulePath 'services_version2.trade_query_version2.app:app' `
        -Port $TradeQueryPort

    if ($proc) {
        $processes += $proc
        Write-Status 'Waiting for Trade Query to be ready...' 'Yellow'
        if (Test-ServiceReady -ServiceName 'Trade Query' -Url $TradeQueryUrl -TimeoutSeconds $HealthCheckTimeout) {
            Write-Host ''
        }
        else {
            Write-Status 'WARNING: Trade Query may not be fully ready' 'Yellow'
            Write-Host ''
        }
    }
}

Write-Header 'Services Ready'
Write-Status ('Orchestrator: {0}' -f $OrchestratorUrl) 'Green'
if (-not $SkipCalculator) {
    Write-Status ('Calculator:  {0}' -f $CalculatorUrl) 'Green'
}
if (-not $SkipRetrieval) {
    Write-Status ('Retrieval:   {0}' -f $RetrievalUrl) 'Green'
}
if (-not $SkipTradeQuery) {
    Write-Status ('TradeQuery:  {0}' -f $TradeQueryUrl) 'Green'
}
Write-Host ''

# Launch interactive chat
Write-Status 'Launching Interactive Chat...' 'Cyan'
Write-Host ''

$chatParams = @(
    '-File', $interactiveChatScript
)

if ($processes.Count -gt 0) {
    # Services were started by this script, keep track to clean them up
    Write-Status 'Press Ctrl+C to stop all services and exit' 'Gray'
    Write-Host ''
    
    & powershell @chatParams
    
    # Clean up processes
    Write-Status 'Stopping services...' 'Yellow'
    $processes | Stop-Process -Force
    Write-Status 'Services stopped' 'Green'
}
else {
    # Services were already running, just run the chat
    & powershell @chatParams
}
