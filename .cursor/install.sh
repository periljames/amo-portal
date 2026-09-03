#!/usr/bin/env bash
# Idempotent development bootstrap for the AMO Portal Cloud Agent environment.
# Safe to run repeatedly. Installs system packages, Python/Node dependencies,
# provisions a local PostgreSQL database, generates .env.development, runs
# migrations, and seeds a local superuser.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

log() { printf '\n[install] %s\n' "$*"; }

# ---------------------------------------------------------------------------
# 1. System packages (PostgreSQL + document/OCR toolchain used by the backend)
# ---------------------------------------------------------------------------
log "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
  postgresql postgresql-contrib \
  python3-venv python3-dev build-essential \
  libpq-dev \
  poppler-utils tesseract-ocr tesseract-ocr-eng \
  libreoffice-writer \
  fontconfig fonts-dejavu-core fonts-liberation2 fonts-noto-core \
  curl

# ---------------------------------------------------------------------------
# 2. Ensure the PostgreSQL cluster is running (needed to provision the DB)
# ---------------------------------------------------------------------------
PG_VERSION="$(ls /etc/postgresql 2>/dev/null | sort -n | tail -1 || true)"
PG_VERSION="${PG_VERSION:-16}"
log "Starting PostgreSQL cluster ${PG_VERSION}/main"
sudo pg_ctlcluster "$PG_VERSION" main start || true
# Wait for the socket to accept connections.
for _ in $(seq 1 30); do
  if sudo -u postgres pg_isready -q; then break; fi
  sleep 1
done

# ---------------------------------------------------------------------------
# 3. Provision roles, database and required extensions (idempotent)
# ---------------------------------------------------------------------------
log "Provisioning database roles, database and extensions"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='amodb_app') THEN
    CREATE ROLE amodb_app LOGIN PASSWORD 'amodb_app_dev';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='amodb_migrator') THEN
    CREATE ROLE amodb_migrator LOGIN PASSWORD 'amodb_migrator_dev';
  END IF;
END $$;
SQL

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='amodb'" | grep -q 1; then
  sudo -u postgres createdb -O amodb_migrator amodb
fi

sudo -u postgres psql -v ON_ERROR_STOP=1 -d amodb <<'SQL'
GRANT ALL ON SCHEMA public TO amodb_migrator;
GRANT ALL ON SCHEMA public TO amodb_app;
ALTER DEFAULT PRIVILEGES FOR ROLE amodb_migrator IN SCHEMA public GRANT ALL ON TABLES TO amodb_app;
ALTER DEFAULT PRIVILEGES FOR ROLE amodb_migrator IN SCHEMA public GRANT ALL ON SEQUENCES TO amodb_app;
-- Extensions require superuser; the application/migrations only reference them.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS ltree;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS citext;
SQL

# ---------------------------------------------------------------------------
# 4. Python virtual environment + backend dependencies
# ---------------------------------------------------------------------------
log "Creating Python virtualenv and installing backend dependencies"
if [ ! -x "$REPO_ROOT/.venv/bin/python" ]; then
  rm -rf "$REPO_ROOT/.venv"
  python3 -m venv "$REPO_ROOT/.venv"
fi
"$REPO_ROOT/.venv/bin/python" -m pip install --upgrade pip wheel setuptools
"$REPO_ROOT/.venv/bin/pip" install -r "$REPO_ROOT/backend/requirements.txt"

# ---------------------------------------------------------------------------
# 5. Frontend dependencies
# ---------------------------------------------------------------------------
log "Installing frontend dependencies"
( cd "$REPO_ROOT/frontend" && npm install )

# ---------------------------------------------------------------------------
# 6. Local upload directories + .env.development
# ---------------------------------------------------------------------------
log "Creating writable upload directories"
mkdir -p \
  "$REPO_ROOT/backend/uploads/amo_assets" \
  "$REPO_ROOT/backend/uploads/training" \
  "$REPO_ROOT/backend/uploads/aircraft_documents" \
  "$REPO_ROOT/backend/uploads/ehm" \
  "$REPO_ROOT/backend/uploads/procurement-documents" \
  "$REPO_ROOT/backend/uploads/local" \
  "$REPO_ROOT/var/amo-object-cache"

if [ ! -f "$REPO_ROOT/.env.development" ]; then
  log "Generating .env.development from template"
  sed "s#__REPO_ROOT__#${REPO_ROOT}#g" \
    "$REPO_ROOT/.cursor/env.development.example" > "$REPO_ROOT/.env.development"
else
  log ".env.development already exists; leaving it untouched"
fi

# ---------------------------------------------------------------------------
# 7. Database migrations
# ---------------------------------------------------------------------------
log "Running Alembic migrations"
set -a
# shellcheck disable=SC1091
. "$REPO_ROOT/.env.development"
set +a
( cd "$REPO_ROOT/backend" && "$REPO_ROOT/.venv/bin/alembic" -c amodb/alembic.ini upgrade heads )

# ---------------------------------------------------------------------------
# 8. Seed a local platform superuser (idempotent)
# ---------------------------------------------------------------------------
log "Seeding local platform superuser (admin@venspera.dev / DevAdmin123!)"
( cd "$REPO_ROOT/backend" && \
  AMO_SUPERUSER_EMAIL="${AMO_SUPERUSER_EMAIL:-admin@venspera.dev}" \
  AMO_SUPERUSER_PASSWORD="${AMO_SUPERUSER_PASSWORD:-DevAdmin123!}" \
  PYTHONPATH="$REPO_ROOT/backend" \
  "$REPO_ROOT/.venv/bin/python" -m amodb.scripts.seed_superuser )

log "Install complete."
