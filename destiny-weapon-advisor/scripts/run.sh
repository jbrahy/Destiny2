#!/usr/bin/env bash
# Build the frontend and start the single-server app at https://localhost:8443
# (the backend serves both the API and the built frontend).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Building frontend"
( cd "$ROOT/frontend" && npm install && npm run build )

echo "==> Starting backend at https://localhost:8443 (Ctrl+C to stop)"
( cd "$ROOT/backend" && pip install -e ".[dev]" >/dev/null && python -m app.main )
