#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$PROJECT_ROOT/backend"
python manage.py spectacular --file "$PROJECT_ROOT/docs/openapi.yaml" --validate
cd "$PROJECT_ROOT/frontend"
npx openapi-typescript ../docs/openapi.yaml -o src/lib/schema.d.ts
