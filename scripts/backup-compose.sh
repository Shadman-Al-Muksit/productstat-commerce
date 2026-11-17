#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
exec docker compose --env-file .env.production --profile maintenance run --rm backup scripts/backup.py
