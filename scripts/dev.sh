#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
mode="${1:-dev}"
[[ "$mode" == dev || "$mode" == --preview ]] || { echo 'Usage: bash scripts/dev.sh [--preview]' >&2; exit 1; }
python - <<'PY'
import socket
for port in (8001, 3000):
    with socket.socket() as connection:
        if connection.connect_ex(('127.0.0.1', port)) == 0:
            raise SystemExit(f'Port {port} is already in use. Review the running ProductStat instance before starting another.')
PY
bash "$PROJECT_ROOT/scripts/database.sh"
pids=()
cleanup() {
  trap - EXIT INT TERM
  for pid in "${pids[@]}"; do kill -TERM -- "-$pid" 2>/dev/null || true; done
  for _ in $(seq 1 30); do
    active=0
    for pid in "${pids[@]}"; do if kill -0 -- "-$pid" 2>/dev/null; then active=1; fi; done
    [[ "$active" == 1 ]] || break
    sleep 0.1
  done
  for pid in "${pids[@]}"; do kill -KILL -- "-$pid" 2>/dev/null || true; done
}
trap cleanup EXIT
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM
start_group() { (cd "$1"; shift; exec setsid "$@") & pids+=("$!"); }
if [[ "$mode" == --preview ]]; then
  start_group "$PROJECT_ROOT/backend" gunicorn config.wsgi:application --bind 127.0.0.1:8001 --workers 4 --threads 4 --timeout 60
  start_group "$PROJECT_ROOT/frontend" npm run start
else
  start_group "$PROJECT_ROOT/backend" python manage.py runserver 127.0.0.1:8001 --noreload
  start_group "$PROJECT_ROOT/frontend" npm run dev
fi
start_group "$PROJECT_ROOT/backend" celery -A config worker --loglevel=INFO --concurrency=2
start_group "$PROJECT_ROOT/backend" celery -A config beat --loglevel=INFO --schedule "$PROJECT_ROOT/.runtime/celerybeat"
echo 'ProductStat: http://localhost:3000 — Ctrl+C stops all owned application process groups.'
wait -n "${pids[@]}"
