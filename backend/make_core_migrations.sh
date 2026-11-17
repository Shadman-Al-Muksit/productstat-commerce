#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../scripts/env.sh"
cd "$PROJECT_ROOT/backend"
python manage.py makemigrations commerce --name commerce_integrity_tax_and_recovery
python manage.py migrate --noinput
