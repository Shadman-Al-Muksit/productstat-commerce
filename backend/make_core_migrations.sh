#!/usr/bin/env bash
set -euo pipefail
source /mnt/d/Shadman-Desktop/Career/productstat/scripts/env.sh
cd "$PROJECT_ROOT/backend"
python manage.py makemigrations commerce --name commerce_integrity_tax_and_recovery
python manage.py migrate --noinput
