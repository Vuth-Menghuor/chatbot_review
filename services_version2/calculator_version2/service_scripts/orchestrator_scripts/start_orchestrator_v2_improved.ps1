# Start GDCE Orchestrator Service v2 in Separate Window (Non-Blocking)
# This script starts the service in a new PowerShell window so VS Code doesn't freeze

param(
    [switch] $NoWindow = $false,
    [switch] $Verbose = $false
)

# Get script directory
$scriptDir = Split-Path -Parent -Path $MyInvocation.MyCommand.Definition
$repoRoot = Split-Path -Parent -Path (Split-Path -Parent -Path $scriptDir)
$serviceDir = Join-Path $repoRoot "services_version2\orchestrator_version2"
$venvDir = Join-Path $repoRoot "env"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"
$logFile = Join-Path $repoRoot "orchestrator_service.log"

# Colors for output
$green = [System.ConsoleColor]::Green
$yellow = [System.ConsoleColor]::Yellow
$cyan = [System.ConsoleColor]::Cyan

function Write-Info {
    Write-Host "[*] $args" -ForegroundColor $cyan
}

function Write-Success {
    Write-Host "[+] $args" -ForegroundColor $green
}

function Write-Warning {
    Write-Host "[!] $args" -ForegroundColor $yellow
}

# Verify Python exists
if (-not (Test-Path $pythonExe)) {
    Write-Warning "Python executable not found: $pythonExe"
    exit 1
}

Write-Info "Starting GDCE Orchestrator Service v2..."
Write-Info "Service will run on http://127.0.0.1:8001"
Write-Info "API Docs: http://127.0.0.1:8001/docs"
Write-Info "Logs: $logFile"
Write-Host ""

# Kill any existing process on port 8001
try {
    $netstatOutput = netstat -ano | Select-String ":8001\s"
    if ($netstatOutput) {
        $parts = $netstatOutput -split '\s+' | Where-Object { $_ }
        $processId = $parts[-1]
        if ($processId -match '^\d+$') {
            Write-Warning "Killing existing process on port 8001 (PID: $processId)..."
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
        }
    }
}
catch {
    # Ignore errors
}

# Start service in separate window or background job
if ($NoWindow) {
    Write-Info "Starting in current window (blocking)..."
    & $pythonExe -m uvicorn `
        services_version2.orchestrator_version2.app:app `
        --host 127.0.0.1 `
        --port 8001 `
        --workers 1
}
else {
    Write-Info "Starting in new PowerShell window (non-blocking)..."
    
    $cmdArgs = @(
        "-NoExit",
        "-Command",
        "cd '$repoRoot'; & '$pythonExe' -m uvicorn services_version2.orchestrator_version2.app:app --host 127.0.0.1 --port 8001 --workers 1"
    )
    
    # Start in new window
    Start-Process -FilePath "powershell.exe" -ArgumentList $cmdArgs -WindowStyle Normal
    
    # Wait a moment for service to start
    Write-Info "Waiting for service to initialize..."
    Start-Sleep -Seconds 3
    
    # Try to connect
    $maxRetries = 10
    $retry = 0
    while ($retry -lt $maxRetries) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8001/health" -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) {
                Write-Success "Service is running!"
                Write-Host ""
                Write-Host "Available endpoints:"
                Write-Host "  - Health Check: http://127.0.0.1:8001/health"
                Write-Host "  - API Docs:    http://127.0.0.1:8001/docs"
                Write-Host "  - Redoc:       http://127.0.0.1:8001/redoc"
                Write-Host ""
                Write-Host "Query endpoint: POST http://127.0.0.1:8001/query"
                Write-Host ""
                Write-Warning "Service is running in a separate window. Keep that window open."
                Write-Warning "To stop: Close the service window or press Ctrl+C there"
                exit 0
            }
        }
        catch {
            $retry++
            if ($retry -lt $maxRetries) {
                Write-Host "." -NoNewline
                Start-Sleep -Seconds 1
            }
        }
    }
    
    Write-Warning "Service did not respond within timeout. Check the separate window for errors."
    Write-Info "Try the health endpoint manually: http://127.0.0.1:8001/health"
}
