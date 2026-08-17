#!/usr/bin/env bash
set -euo pipefail
docker compose -f "$(dirname "$0")/docker-compose.postgres.yml" up -d --wait
trap 'docker compose -f "$(dirname "$0")/docker-compose.postgres.yml" down -v' EXIT
export TEST_DATABASE_URL=postgresql://amo_test:amo_test@127.0.0.1:55432/amo_resilience_test
pytest -q "$(dirname "$0")/test_postgres_resilience.py"
