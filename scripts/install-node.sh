#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
major=24
target="$RUNTIME_ROOT/node"
# WSL1's old ELF loader rejects the current Node24 executable; Node22 LTS supports Next16.
if [[ "$(uname -r)" == 4.4.*Microsoft* ]]; then major=22; target="$RUNTIME_ROOT/node22"; fi
mkdir -p "$RUNTIME_ROOT/downloads" "$target"
cd "$RUNTIME_ROOT/downloads"
curl -fsS --retry 2 "https://nodejs.org/dist/latest-v$major.x/SHASUMS256.txt" -o SHASUMS256.txt
archive="$(awk '/linux-x64.tar.xz$/ {print $2}' SHASUMS256.txt)"
[[ -n "$archive" ]]
curl -fsS --retry 2 "https://nodejs.org/dist/latest-v$major.x/$archive" -o "$archive"
grep " $archive$" SHASUMS256.txt | sha256sum -c -
tar -xJf "$archive" -C "$target" --strip-components=1
"$target/bin/node" --version
