#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
bash "$PROJECT_ROOT/scripts/database.sh"
cd "$PROJECT_ROOT/backend"
python manage.py makemigrations commerce --skip-checks
python -m pip freeze > requirements.lock.txt
