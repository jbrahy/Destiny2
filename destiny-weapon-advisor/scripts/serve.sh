#!/usr/bin/env bash
# Run the backend with auto-restart (single-server at https://localhost:8443).
# Requires a MySQL 8 instance — set DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
# (and the other secrets) in backend/.env or export them before running this script.
# Assumes the frontend has already been built (run.sh does that). Ctrl+C to stop.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"

# Load .env if present (does not override already-exported vars)
if [ -f .env ]; then
  set -a; source .env; set +a
fi

echo "$(date '+%H:%M:%S') running database migrations …"
python -m scripts.migrate

while true; do
  echo "$(date '+%H:%M:%S') starting backend on https://localhost:8443 …"
  python -m app.main
  code=$?
  echo "$(date '+%H:%M:%S') backend exited ($code); restarting in 3s (Ctrl+C to stop) …"
  sleep 3
done
