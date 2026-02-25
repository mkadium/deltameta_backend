#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONUNBUFFERED=1

# Run migrations first (safe to be no-op if none)
if [ -x "./venv/bin/alembic" ]; then
  ./venv/bin/alembic upgrade head || true
fi

# Start Gunicorn with Uvicorn workers
exec gunicorn -k uvicorn.workers.UvicornWorker -w 4 "app.main:app" -b 0.0.0.0:8000 --log-level info

