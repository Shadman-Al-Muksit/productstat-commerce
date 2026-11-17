#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$PROJECT_ROOT/backend"
exec celery -A config worker --loglevel=INFO --concurrency=2
