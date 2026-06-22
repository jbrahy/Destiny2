#!/usr/bin/env bash
# Build the frontend and start the single-server app at https://localhost:8443
# (the backend serves both the API and the built frontend).
#
# Requires a MySQL 8 instance — set DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
# (and the other secrets) in backend/.env or export them before running this script.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Load .env if present (does not override already-exported vars)
if [ -f "$ROOT/backend/.env" ]; then
  set -a; source "$ROOT/backend/.env"; set +a
fi

echo "==> Building frontend"
( cd "$ROOT/frontend" && npm install && npm run build )

echo "==> Running database migrations"
( cd "$ROOT/backend" && pip install -e ".[dev]" >/dev/null && python -m scripts.migrate )

echo "==> Starting backend at https://localhost:8443 (Ctrl+C to stop)"
( cd "$ROOT/backend" && python -m app.main )
