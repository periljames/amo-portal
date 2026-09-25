#!/usr/bin/env bash
# Forced SSH command for a restricted host backup key; no caller arguments.
set -euo pipefail
ROOT=/var/backups/amo-postgres
LATEST=$(find "$ROOT" -mindepth 1 -maxdepth 1 -type d -name '20??????T??????Z' -printf '%f\n' | sort | tail -1)
test -n "$LATEST"
exec tar -C "$ROOT/$LATEST" -cf - amodb.dump globals.sql contents.txt SHA256SUMS
