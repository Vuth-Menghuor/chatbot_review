#!/usr/bin/env bash
# run_dev.sh — Start orchestrator in development mode with auto-reload

set -e

# Load .env if present
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

HOST="${ORCHESTRATOR_HOST:-127.0.0.1}"
PORT="${ORCHESTRATOR_PORT:-8001}"

echo "Starting orchestrator on http://$HOST:$PORT"
echo "API docs: http://$HOST:$PORT/docs"
echo ""

# Run from the repo root so relative imports resolve correctly
cd "$(dirname "$0")/../../../.."

uvicorn services_version2.orchestrator.app.main:app \
  --host "$HOST" \
  --port "$PORT" \
  --reload \
  --log-level info
