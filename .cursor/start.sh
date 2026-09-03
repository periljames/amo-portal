#!/usr/bin/env bash
# Per-boot startup for the AMO Portal Cloud Agent environment.
# Ensures PostgreSQL is running before the dev runtime terminal starts.
set -euo pipefail

PG_VERSION="$(ls /etc/postgresql 2>/dev/null | sort -n | tail -1 || true)"
PG_VERSION="${PG_VERSION:-16}"

echo "[start] Starting PostgreSQL cluster ${PG_VERSION}/main"
sudo pg_ctlcluster "$PG_VERSION" main start || true

# Wait until PostgreSQL accepts connections so dependent services start cleanly.
for _ in $(seq 1 30); do
  if sudo -u postgres pg_isready -q; then
    echo "[start] PostgreSQL is ready"
    break
  fi
  sleep 1
done
