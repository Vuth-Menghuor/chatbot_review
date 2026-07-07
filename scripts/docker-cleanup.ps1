# Remove duplicate/stale GDCE chatbot containers from old compose runs.
# Does NOT touch vithey, frappe, or other projects.

$names = @(
    "api", "api-postgres", "api-redis",
    "api-layer-api-layer-1", "api-layer-api-postgres-1", "api-layer-api-redis-1",
    "orchestrator", "orchestrator-service",
    "retrieval", "retrieval-service",
    "general", "general-service",
    "calculator", "trade", "trade-service",
    "qdrant", "qdrant-retrieval", "qdrant-general", "redis-general",
    "frontend", "frontend-frontend-1"
)

foreach ($name in $names) {
    docker rm -f $name 2>$null
}

Write-Host "Removed duplicate GDCE chatbot containers." -ForegroundColor Green
docker ps -a --format "{{.Names}}" | Select-String -Pattern "^(api|orchestrator|retrieval|general|calculator|trade|qdrant|redis-general|frontend)"
