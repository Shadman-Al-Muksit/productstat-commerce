#!/usr/bin/env bash
# Ubuntu 24.04 prerequisites; run as root. Existing clusters are not removed.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run: sudo bash scripts/install-system.sh' >&2; exit 1; }
apt-get update -qq
apt-get install -y --no-install-recommends curl ca-certificates gnupg python3-venv redis-server
if [[ ! -x /usr/lib/postgresql/17/bin/initdb ]]; then
  install -d /usr/share/postgresql-common/pgdg
  curl -fsS https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
  fingerprint="$(gpg --show-keys --with-colons /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc | awk -F: '$1=="fpr" {print $10;exit}')"
  [[ "$fingerprint" == B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8 ]] || { echo 'PostgreSQL signing key mismatch' >&2; exit 1; }
  . /etc/os-release
  printf 'Types: deb\nURIs: https://apt.postgresql.org/pub/repos/apt\nSuites: %s-pgdg\nComponents: main\nSigned-By: /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc\n' "$VERSION_CODENAME" > /etc/apt/sources.list.d/productstat-pgdg.sources
  apt-get update -qq
  apt-get install -y --no-install-recommends postgresql-17
fi
