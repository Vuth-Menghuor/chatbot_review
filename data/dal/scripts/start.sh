#!/bin/sh
# Entrypoint script: run migrations, seed, then start the app
set -e

echo "==> Running Alembic migrations..."
alembic upgrade head

# echo "==> Seeding metadata database..."
# python -m scripts.seed_metadata

# echo "==> Seeding operational database..."
# python -m scripts.seed_operational

echo "==> Starting FastAPI server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
