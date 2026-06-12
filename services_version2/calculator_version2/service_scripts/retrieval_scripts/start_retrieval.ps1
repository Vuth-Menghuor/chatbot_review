param(
    [string]$Host = "127.0.0.1",
    [int]$Port = 8003,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"

# Resolve repository root from this script location.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")

Write-Host "[Retrieval] Repo root: $RepoRoot" -ForegroundColor Cyan
Set-Location $RepoRoot

# Activate local virtual environment if available.
$ActivatePath = Join-Path $RepoRoot "env\Scripts\Activate.ps1"
if (Test-Path $ActivatePath) {
    Write-Host "[Retrieval] Activating virtual environment..." -ForegroundColor Yellow
    . $ActivatePath
} else {
    Write-Host "[Retrieval] env\Scripts\Activate.ps1 not found. Continuing with current Python." -ForegroundColor DarkYellow
}

$env:RETRIEVAL_HOST = $Host
$env:RETRIEVAL_PORT = "$Port"
$env:RETRIEVAL_RELOAD = if ($Reload) { "true" } else { "false" }

Write-Host "[Retrieval] Starting service on $Host`:$Port (reload=$($Reload.IsPresent))" -ForegroundColor Green

# Uses centralized config in services_version2.retrieval_version2.main
python -m services_version2.retrieval_version2.main
