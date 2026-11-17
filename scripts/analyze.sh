#!/usr/bin/env bash
# Refresh planner statistics after a migration/backfill or a large initial import.
# ANALYZE changes statistics, never business rows or stock balances.
set -euo pipefail
source "$(dirname "$0")/env.sh"
psql --set ON_ERROR_STOP=1 --command ANALYZE
