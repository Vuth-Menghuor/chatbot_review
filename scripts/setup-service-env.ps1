# Create .env from .env.example for each service folder (skips if .env already exists).
# Usage: .\scripts\setup-service-env.ps1

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

$services = @(
    "services_version2\orchestrator",
    "services_version2\trade",
    "services_version2\calculator",
    "services_version2\general",
    "services_version2\retrieval",
    "backend\api-layer",
    "data\dal",
    "frontend",
    "image-worker"
)

$created = 0
$skipped = 0

foreach ($rel in $services) {
    $dir = Join-Path $root $rel
    $example = Join-Path $dir ".env.example"
    $envFile = Join-Path $dir ".env"

    if (-not (Test-Path $example)) {
        Write-Host "SKIP (no .env.example): $rel" -ForegroundColor DarkGray
        continue
    }

    if (Test-Path $envFile) {
        Write-Host "OK  (exists):        $rel\.env" -ForegroundColor Green
        $skipped++
        continue
    }

    Copy-Item $example $envFile
    Write-Host "NEW (created):      $rel\.env  <- edit secrets before deploy" -ForegroundColor Yellow
    $created++
}

Write-Host ""
Write-Host "Done. Created $created file(s), skipped $skipped existing .env file(s)." -ForegroundColor Cyan
Write-Host "Edit each .env and set GEMINI_API_KEY, JWT_SECRET_KEY, DB passwords, DAL_API_KEY, etc." -ForegroundColor Cyan
