#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
: "${PGPASSWORD:?Missing local .env; run setup.sh}"
if [[ ! -f "$RUNTIME_ROOT/pgdata/PG_VERSION" ]]; then
  initdb -D "$RUNTIME_ROOT/pgdata" --username="$PGUSER" --pwfile=<(printf '%s\n' "$PGPASSWORD") --auth-local=scram-sha-256 --auth-host=scram-sha-256 > "$PROJECT_ROOT/.runtime/initdb.log"
fi
if ! pg_ctl -D "$RUNTIME_ROOT/pgdata" status >/dev/null 2>&1; then
  pg_ctl -D "$RUNTIME_ROOT/pgdata" -l "$PROJECT_ROOT/.runtime/postgres.log" -o "-p $PGPORT -h 127.0.0.1 -k $RUNTIME_ROOT/socket" -w start
fi
if [[ "$(psql -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname = 'productstat'")" != 1 ]]; then createdb "$PGDATABASE"; fi
if ! redis-cli -p 56379 ping >/dev/null 2>&1; then
  redis-server --bind 127.0.0.1 --port 56379 --daemonize yes --pidfile "$RUNTIME_ROOT/redis.pid" --dir "$RUNTIME_ROOT" --appendonly yes --logfile "$PROJECT_ROOT/.runtime/redis.log"
fi
