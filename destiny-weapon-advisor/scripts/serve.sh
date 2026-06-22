#!/usr/bin/env bash
# Run the backend with auto-restart (single-server at https://localhost:8443).
# Assumes the frontend has already been built (run.sh does that). Ctrl+C to stop.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"

while true; do
  echo "$(date '+%H:%M:%S') starting backend on https://localhost:8443 …"
  python -m app.main
  code=$?
  echo "$(date '+%H:%M:%S') backend exited ($code); restarting in 3s (Ctrl+C to stop) …"
  sleep 3
done
