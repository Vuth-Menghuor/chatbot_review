# Build and start each GDCE service stack one by one.
# Usage: .\scripts\docker-build-one-by-one.ps1

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not (docker network ls --filter "name=^gdce-network$" --format "{{.Name}}")) {
    docker network create gdce-network | Out-Null
    Write-Host "Created network: gdce-network" -ForegroundColor Cyan
}

$stacks = @(
    @{ Name = "retrieval";   Path = "services_version2\retrieval";   Port = 8003 },
    @{ Name = "general";     Path = "services_version2\general";     Port = 8005 },
    @{ Name = "calculator";  Path = "services_version2\calculator";  Port = 8002 },
    @{ Name = "trade";       Path = "services_version2\trade";       Port = 8004 },
    @{ Name = "orchestrator";Path = "services_version2\orchestrator";Port = 8001 },
    @{ Name = "api";         Path = "backend\api-layer";            Port = 8000 }
)

# orchestrator needs services_version2/orchestrator/.env (copy from .env.example)
# trade needs services_version2/trade/.env with DAL_BASE_URL=http://dal-app:8000 on gdce-network

foreach ($stack in $stacks) {
    Write-Host ""
    Write-Host "=== Building $($stack.Name) (port $($stack.Port)) ===" -ForegroundColor Yellow
    Push-Location (Join-Path $root $stack.Path)
    try {
        docker compose up -d --build
        if ($LASTEXITCODE -ne 0) { throw "docker compose failed for $($stack.Name)" }
        Write-Host "OK: $($stack.Name) is up" -ForegroundColor Green
    } finally {
        Pop-Location
    }
    Start-Sleep -Seconds 3
}

Write-Host ""
Write-Host "All services built. Running containers:" -ForegroundColor Cyan
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" |
    Select-String -Pattern "^(NAMES|api$|orchestrator|retrieval|general|calculator|trade|api-|qdrant|redis-general)"
