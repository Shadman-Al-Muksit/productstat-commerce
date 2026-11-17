#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_ROOT="${PRODUCTSTAT_RUNTIME_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/productstat}"
if [[ -f "$PROJECT_ROOT/.env" ]]; then set -a; source "$PROJECT_ROOT/.env"; set +a; fi
NODE_RUNTIME="$RUNTIME_ROOT/node"
if [[ -x "$RUNTIME_ROOT/node22/bin/node" ]] && [[ "$(uname -r)" == 4.4.*Microsoft* ]]; then NODE_RUNTIME="$RUNTIME_ROOT/node22"; fi
export PATH="$NODE_RUNTIME/bin:$RUNTIME_ROOT/.venv/bin:/usr/lib/postgresql/17/bin:$PATH"
export PGHOST="${PGHOST:-127.0.0.1}" PGPORT="${PGPORT:-55433}" PGDATABASE="${PGDATABASE:-productstat}" PGUSER="${PGUSER:-productstat}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:56379/0}"
mkdir -p "$PROJECT_ROOT/.runtime" "$RUNTIME_ROOT/socket"
