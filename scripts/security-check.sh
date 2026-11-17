#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$PROJECT_ROOT/frontend"
npm audit --omit=dev --audit-level=high --json > "$PROJECT_ROOT/.runtime/npm-audit.json"
# Keep audit tooling out of the application dependency environment and lockfile.
python3 -m venv "$RUNTIME_ROOT/audit-venv"
"$RUNTIME_ROOT/audit-venv/bin/python" -m pip install --quiet 'pip-audit==2.10.1'
"$RUNTIME_ROOT/audit-venv/bin/pip-audit" -r "$PROJECT_ROOT/backend/requirements.lock.txt" \
  --no-deps --disable-pip --format=json --output "$PROJECT_ROOT/.runtime/python-audit.json"
