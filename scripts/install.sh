#!/usr/bin/env bash
# =========================================================================
# AMO Portal - one-command production installer for a fresh Linux server.
#
# Brings up the entire platform (API, workers, scheduler, platform-ops gateway
# + worker, rostering automation, frontend) with a bundled PostgreSQL, runs
# database migrations, creates the first platform superuser and verifies health.
#
# Prerequisites: Docker Engine + the Docker Compose plugin.
#
#   sudo ./scripts/install.sh
#
# Environment toggles:
#   USE_BUNDLED_DB=0   Use an external managed database (set DATABASE_WRITE_URL
#                      in .env yourself; skips the bundled Postgres service).
#   SEED_DEMO=1        Also load demonstration tenants/invoices/tickets.
# =========================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="$ROOT_DIR/.env"
ENV_TEMPLATE="$ROOT_DIR/.env.production.example"
USE_BUNDLED_DB="${USE_BUNDLED_DB:-1}"
SEED_DEMO="${SEED_DEMO:-0}"

log()  { printf '\n\033[1;36m[install]\033[0m %s\n' "$*"; }
warn() { printf '\n\033[1;33m[install]\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31m[install]\033[0m %s\n' "$*" >&2; exit 1; }

gen_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

# ---------------------------------------------------------------------------
# 1. Prerequisites
# ---------------------------------------------------------------------------
log "Checking prerequisites"
command -v docker >/dev/null 2>&1 || die "Docker is not installed. See https://docs.docker.com/engine/install/"
if ! docker compose version >/dev/null 2>&1; then
  die "The Docker Compose plugin is not available. Install docker-compose-plugin."
fi
docker info >/dev/null 2>&1 || die "The Docker daemon is not reachable. Start Docker (and run with sufficient privileges)."

COMPOSE_FILES=(-f docker-compose.prod.yml)
if [ "$USE_BUNDLED_DB" = "1" ]; then
  COMPOSE_FILES+=(-f docker-compose.postgres.yml)
fi
compose() { docker compose "${COMPOSE_FILES[@]}" "$@"; }

# ---------------------------------------------------------------------------
# 2. Environment file + secret generation
# ---------------------------------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
  [ -f "$ENV_TEMPLATE" ] || die "Missing $ENV_TEMPLATE"
  log "Creating .env from template"
  cp "$ENV_TEMPLATE" "$ENV_FILE"

  secret_key="$(gen_secret)"
  pepper="$(gen_secret)"
  db_password="$(gen_secret)"
  superuser_password="$(gen_secret | cut -c1-24)"

  sed -i "s#CHANGE_ME_SECRET_KEY#${secret_key}#g" "$ENV_FILE"
  sed -i "s#CHANGE_ME_PEPPER#${pepper}#g" "$ENV_FILE"
  sed -i "s#CHANGE_ME_DB#${db_password}#g" "$ENV_FILE"
  sed -i "s#CHANGE_ME_SUPERUSER#${superuser_password}#g" "$ENV_FILE"

  log "Generated secrets and wrote $ENV_FILE"
  warn "First superuser password: ${superuser_password}  (also stored in .env as AMO_SUPERUSER_PASSWORD)"
else
  log ".env already exists; leaving it untouched"
fi

# Refuse to continue while template placeholders remain.
if grep -Eq "CHANGE_ME_|PLACEHOLDER__SET_IN_SECRET_STORE|UNKNOWN__FILL_ME" "$ENV_FILE"; then
  die ".env still contains placeholders. Fill them in before continuing:
$(grep -nE 'CHANGE_ME_|PLACEHOLDER__SET_IN_SECRET_STORE|UNKNOWN__FILL_ME' "$ENV_FILE")"
fi

# ---------------------------------------------------------------------------
# 3. Build images
# ---------------------------------------------------------------------------
log "Building container images (this can take several minutes on first run)"
compose build

# ---------------------------------------------------------------------------
# 4. Database: start bundled Postgres (if enabled) and run migrations
# ---------------------------------------------------------------------------
if [ "$USE_BUNDLED_DB" = "1" ]; then
  log "Starting bundled PostgreSQL"
  compose up -d db
  log "Waiting for the database to become healthy"
  for _ in $(seq 1 60); do
    state="$(compose ps -q db | xargs -r docker inspect -f '{{.State.Health.Status}}' 2>/dev/null || true)"
    [ "$state" = "healthy" ] && break
    sleep 2
  done
  [ "${state:-}" = "healthy" ] || die "Database did not become healthy in time"
fi

log "Running database migrations (alembic upgrade heads)"
compose run --rm backend bash -lc 'cd /app/backend/amodb && alembic -c alembic.ini upgrade heads'

# ---------------------------------------------------------------------------
# 5. First platform superuser (idempotent)
# ---------------------------------------------------------------------------
log "Ensuring the platform superuser exists"
compose run --rm backend python -m amodb.scripts.seed_superuser

# ---------------------------------------------------------------------------
# 6. Start the full stack
# ---------------------------------------------------------------------------
log "Starting all services"
compose up -d --remove-orphans

# ---------------------------------------------------------------------------
# 7. Health verification
# ---------------------------------------------------------------------------
log "Verifying service health"
ok=0
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8080/healthz >/dev/null 2>&1; then ok=1; break; fi
  sleep 2
done
[ "$ok" = "1" ] || die "Backend /healthz did not return healthy. Inspect: docker compose ${COMPOSE_FILES[*]} logs backend"
curl -fsS http://127.0.0.1:8090/healthz >/dev/null 2>&1 && log "Platform Ops gateway healthy" || warn "Platform Ops gateway health check did not pass yet"

# ---------------------------------------------------------------------------
# 8. Optional demo data
# ---------------------------------------------------------------------------
if [ "$SEED_DEMO" = "1" ]; then
  log "Seeding demonstration data"
  compose exec -T backend python -m amodb.scripts.seed_platform_demo || warn "Demo seed did not complete"
fi

su_email="$(grep -E '^AMO_SUPERUSER_EMAIL=' "$ENV_FILE" | cut -d= -f2-)"
log "Install complete."
cat <<EOF

  Portal (frontend):     http://127.0.0.1:3000
  API health:            http://127.0.0.1:8080/healthz
  Platform Ops gateway:  http://127.0.0.1:8090/healthz

  Sign in as the platform superuser:
    email:    ${su_email:-admin@example.com}
    password: see AMO_SUPERUSER_PASSWORD in .env

  Put a TLS-terminating reverse proxy in front of port 3000 for public access,
  and set PORTAL_DOMAIN / CORS_ALLOWED_ORIGINS in .env to your domain.
EOF
