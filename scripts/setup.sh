#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
[[ -x /usr/lib/postgresql/17/bin/initdb ]] && command -v redis-server >/dev/null || { echo 'Run sudo bash scripts/install-system.sh first.' >&2; exit 1; }
python3 "$PROJECT_ROOT/scripts/init_env.py" "$PROJECT_ROOT/.env"
source "$PROJECT_ROOT/scripts/env.sh"
if ! node --version >/dev/null 2>&1; then bash "$PROJECT_ROOT/scripts/install-node.sh"; source "$PROJECT_ROOT/scripts/env.sh"; fi
[[ -x "$RUNTIME_ROOT/.venv/bin/python" ]] || python3 -m venv "$RUNTIME_ROOT/.venv"
python -m pip install -r "$PROJECT_ROOT/backend/requirements.txt"
bash "$PROJECT_ROOT/scripts/database.sh"
cd "$PROJECT_ROOT/backend"
python manage.py migrate --noinput
cd "$PROJECT_ROOT/frontend"
npm ci
printf '\nSetup ready. Seed: bash scripts/seed.sh; start: bash scripts/dev.sh\n'
