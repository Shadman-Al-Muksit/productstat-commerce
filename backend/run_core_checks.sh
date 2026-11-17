#!/usr/bin/env bash
set -euo pipefail
source /mnt/d/Shadman-Desktop/Career/productstat/scripts/env.sh
cd "$PROJECT_ROOT/backend"
python manage.py check
python manage.py makemigrations commerce --check --dry-run
pytest tests/test_core.py -q
