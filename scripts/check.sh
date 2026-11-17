#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$PROJECT_ROOT/backend"
python manage.py check
python manage.py makemigrations --check --dry-run
pytest -q "$@"
bash "$PROJECT_ROOT/scripts/schema.sh"
cd "$PROJECT_ROOT/frontend"
npm run typecheck
npm run format:check
npm run build
