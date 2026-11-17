#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
export DJANGO_DEBUG=0
python "$PROJECT_ROOT/scripts/prepare-load.py"
cd "$PROJECT_ROOT/backend"
gunicorn config.wsgi:application --bind 127.0.0.1:8002 --workers 4 --threads 4 --timeout 60 --error-logfile "$PROJECT_ROOT/.runtime/load-server.log" > "$PROJECT_ROOT/.runtime/load-requests.log" 2>&1 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT
ready=0
for attempt in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:8002/api/v1/health/ >/dev/null 2>&1; then ready=1; break; fi
  sleep 0.5
done
[[ "$ready" == 1 ]] || { echo 'Load server did not become healthy.' >&2; exit 1; }
cd "$PROJECT_ROOT/load"
export AUTH_FILE="$PROJECT_ROOT/.runtime/load-auth.json" RESULT_FILE="$PROJECT_ROOT/.runtime/k6-summary.json"
"$RUNTIME_ROOT/tools/k6" run k6.js
