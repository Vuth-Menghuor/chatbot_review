# Start Orchestrator Service v2 - Simple Non-Blocking Version
# Starts service in new window so VS Code doesnt freeze

$repoRoot = Split-Path -Parent -Path (Split-Path -Parent -Path (Split-Path -Parent -Path $MyInvocation.MyCommand.Definition))
$pythonExe = Join-Path $repoRoot "env\Scripts\python.exe"

Write-Host "[*] Starting Orchestrator Service v2..." -ForegroundColor Cyan
Write-Host "[*] Service will run on http://127.0.0.1:8001" -ForegroundColor Cyan
Write-Host ""

# Kill any process on port 8001
try {
    $processes = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue
    if ($processes) {
        foreach ($proc in $processes) {
            Stop-Process -Id $proc.OwningProcess -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 500
        }
    }
}
catch {
}

# Start service in new window
$cmdLine = "cd '$repoRoot'; & '$pythonExe' -m uvicorn services_version2.orchestrator_version2.app:app --host 127.0.0.1 --port 8001 --workers 1"

Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmdLine -WindowStyle Normal

Write-Host "[+] Service started in new window" -ForegroundColor Green
Write-Host "[*] Waiting for service to initialize..." -ForegroundColor Cyan

# Wait for service to be ready
$maxAttempts = 15
$attempts = 0

while ($attempts -lt $maxAttempts) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8001/health" -ErrorAction SilentlyContinue -TimeoutSec 1
        if ($response.StatusCode -eq 200) {
            Write-Host ""
            Write-Host "[+] Service is ready!" -ForegroundColor Green
            Write-Host ""
            Write-Host "Endpoints:" -ForegroundColor Yellow
            Write-Host "  - API Docs:    http://127.0.0.1:8001/docs" -ForegroundColor White
            Write-Host "  - Health:      http://127.0.0.1:8001/health" -ForegroundColor White
            Write-Host "  - Query (POST):http://127.0.0.1:8001/query" -ForegroundColor White
            Write-Host ""
            exit 0
        }
    }
    catch {
    }
    
    Write-Host "." -NoNewline
    Start-Sleep -Seconds 1
    $attempts++
}

Write-Host ""
Write-Host "[!] Service did not respond. Check the service window for errors." -ForegroundColor Yellow
