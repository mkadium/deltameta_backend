#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "Running alembic upgrade head"
if [ -x "./venv/bin/alembic" ]; then
  ./venv/bin/alembic upgrade head
else
  echo "alembic not found in venv; ensure requirements are installed"
  exit 1
fi

