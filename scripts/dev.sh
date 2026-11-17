#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
bash "$PROJECT_ROOT/scripts/database.sh"
pids=()
cleanup() { for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM
(cd "$PROJECT_ROOT/backend" && python manage.py runserver 127.0.0.1:8001 --noreload) & pids+=("$!")
(cd "$PROJECT_ROOT/backend" && celery -A config worker --loglevel=INFO --concurrency=2) & pids+=("$!")
(cd "$PROJECT_ROOT/backend" && celery -A config beat --loglevel=INFO --schedule "$PROJECT_ROOT/.runtime/celerybeat") & pids+=("$!")
(cd "$PROJECT_ROOT/frontend" && npm run dev -- --hostname 0.0.0.0 --port 3000) & pids+=("$!")
echo 'ProductStat: http://localhost:3000 — Ctrl+C stops application processes.'
wait -n "${pids[@]}"
