# Rebuild and smoke-test orchestrator + trade after pulling latest code.
# Usage: .\scripts\test-orchestrator-trade-docker.ps1

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not (docker network ls --filter "name=^gdce-network$" --format "{{.Name}}")) {
    docker network create gdce-network | Out-Null
    Write-Host "Created network: gdce-network" -ForegroundColor Cyan
}

$stacks = @(
    @{ Name = "trade";        Path = "services_version2\trade";        Health = "http://localhost:8004/health" },
    @{ Name = "orchestrator"; Path = "services_version2\orchestrator"; Health = "http://localhost:8001/health" }
)

foreach ($stack in $stacks) {
    Write-Host ""
    Write-Host "=== Rebuilding $($stack.Name) ===" -ForegroundColor Yellow
    Push-Location (Join-Path $root $stack.Path)
    try {
        cmd /c "docker compose down 2>nul"
        docker compose up -d --build
        if ($LASTEXITCODE -ne 0) { throw "docker compose failed for $($stack.Name)" }
    } finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "Waiting for services to become healthy..." -ForegroundColor Cyan
Start-Sleep -Seconds 15

$failures = 0
foreach ($stack in $stacks) {
    try {
        $resp = Invoke-RestMethod -Uri $stack.Health -TimeoutSec 30
        Write-Host "OK: $($stack.Name) -> $($stack.Health) => $($resp.status)" -ForegroundColor Green
    } catch {
        Write-Host "FAIL: $($stack.Name) health check at $($stack.Health)" -ForegroundColor Red
        Write-Host $_.Exception.Message
        $failures++
    }
}

Write-Host ""
Write-Host "Recent container logs:" -ForegroundColor Cyan
foreach ($name in @("trade", "orchestrator")) {
    Write-Host "--- $name ---" -ForegroundColor Yellow
    docker logs --tail 20 $name 2>&1
}

if ($failures -gt 0) {
    throw "$failures health check(s) failed"
}

Write-Host ""
Write-Host "Orchestrator and trade are up and healthy." -ForegroundColor Green
