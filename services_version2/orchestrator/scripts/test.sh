#!/usr/bin/env bash
# test.sh — Run the full orchestrator test suite

set -e

echo "============================================"
echo "  Running Orchestrator Test Suite"
echo "============================================"

# Run from the repo root so imports resolve correctly
cd "$(dirname "$0")/../../../.."

python -m pytest services_version2/orchestrator/tests/ \
  --tb=short \
  -v \
  "$@"
