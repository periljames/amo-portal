#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .last_deploy_rev ]]; then
  echo "No .last_deploy_rev found; cannot auto-checkout previous revision"
else
  PREV_REV="$(cat .last_deploy_rev)"
  if [[ -n "$PREV_REV" ]]; then
    git checkout "$PREV_REV"
  fi
fi

docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d --remove-orphans
curl -fsS http://127.0.0.1:8080/healthz >/dev/null

echo "Rollback complete. If schema mismatch exists, restore DB backup manually."
