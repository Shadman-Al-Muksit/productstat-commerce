#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$PROJECT_ROOT/frontend"
export NEXT_TELEMETRY_DISABLED=1
exec npm run start
