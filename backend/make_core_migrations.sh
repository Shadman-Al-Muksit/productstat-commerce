#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../scripts/env.sh"
cd "$PROJECT_ROOT/backend"
python manage.py makemigrations commerce "$@"
python manage.py migrate --noinput
