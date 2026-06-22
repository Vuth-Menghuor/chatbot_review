#!/usr/bin/env bash
set -euo pipefail

# Create the external Qdrant volume once, if it doesn't already exist:
#   docker volume create general_version2_qdrant_data

docker compose up -d
