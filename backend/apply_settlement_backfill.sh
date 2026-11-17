#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../scripts/env.sh"
cd "$PROJECT_ROOT/backend"
python manage.py migrate --noinput
python manage.py check
python manage.py makemigrations --check --dry-run
