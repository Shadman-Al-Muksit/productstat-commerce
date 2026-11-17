#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$PROJECT_ROOT/backend"
exec python manage.py runserver 0.0.0.0:8001 --noreload
