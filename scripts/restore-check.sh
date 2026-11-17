#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
python "$PROJECT_ROOT/scripts/verify_restore.py" "$@"
