param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$workspace = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path

if (-not (docker network ls --filter "name=^gdce-network$" --format "{{.Name}}")) {
    docker network create gdce-network | Out-Null
    Write-Host "Created docker network: gdce-network"
}

function Start-Stack([string]$Path) {
    Push-Location (Join-Path $workspace $Path)
    try {
        if ($SkipBuild) {
            docker compose up -d
        } else {
            docker compose up -d --build
        }
        if ($LASTEXITCODE -ne 0) { throw "Failed to start $Path" }
    } finally {
        Pop-Location
    }
}

# One docker-compose per service folder — start each stack separately
Start-Stack "services_version2\retrieval"
Start-Stack "services_version2\general"
Start-Stack "services_version2\calculator"
Start-Stack "services_version2\trade"
Start-Stack "services_version2\orchestrator"
Start-Stack "backend\api-layer"

python (Join-Path $PSScriptRoot "check_integration.py")
