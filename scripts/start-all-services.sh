#!/usr/bin/env bash
set -euo pipefail

# Create shared Docker network once
if ! docker network inspect gdce-network >/dev/null 2>&1; then
  docker network create gdce-network
  echo "Created docker network: gdce-network"
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

start_stack() {
  local dir="$1"
  echo "Starting $dir ..."
  (cd "$ROOT/$dir" && docker compose up -d --build)
}

start_stack "services_version2/retrieval"
start_stack "services_version2/general"
start_stack "services_version2/calculator"
start_stack "services_version2/trade"
start_stack "services_version2/orchestrator"
start_stack "backend/api-layer"

echo "All service stacks started."
