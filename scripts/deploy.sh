#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ROOT_DIR}/.env"
BACKUP_DIR="/opt/amo-portal/shared/backups"
mkdir -p "$BACKUP_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing .env file"
  exit 1
fi

source "$ENV_FILE"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="$BACKUP_DIR/predeploy_${TIMESTAMP}.dump"

backup_db() {
  if [[ -z "${DATABASE_WRITE_URL:-}" ]]; then
    echo "DATABASE_WRITE_URL not set"
    exit 1
  fi

  if command -v pg_dump >/dev/null 2>&1; then
    pg_dump --format=custom --file "$BACKUP_FILE" "$DATABASE_WRITE_URL"
  else
    echo "pg_dump not found; skipping backup generation (ASSUMPTION__REVIEW)"
  fi
}

if [[ "${1:-}" == "--backup-only" ]]; then
  backup_db
  exit 0
fi

backup_db

# Save previous revision for rollback
PREV_REV="$(git rev-parse --short HEAD || true)"
echo "$PREV_REV" > .last_deploy_rev

docker compose -f docker-compose.prod.yml build

docker compose -f docker-compose.prod.yml run --rm backend \
  bash -lc 'cd /app/backend/amodb && alembic -c alembic.ini upgrade heads'

docker compose -f docker-compose.prod.yml up -d --remove-orphans

curl -fsS http://127.0.0.1:8080/healthz >/dev/null
echo "Deploy complete"
