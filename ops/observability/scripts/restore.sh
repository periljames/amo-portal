#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE="${1:-}"
[[ -d "$SOURCE" ]] || { echo "Usage: $0 BACKUP_DIRECTORY" >&2; exit 2; }

ENV_FILE="${ROOT_DIR}/.env"
[[ -f "$ENV_FILE" ]] || ENV_FILE="${ROOT_DIR}/.env.example"
COMPOSE=(docker compose --env-file "$ENV_FILE" -f "${ROOT_DIR}/docker-compose.observability.yml")

"${COMPOSE[@]}" --profile agent --profile hub down

volume_empty() {
  local volume="$1"
  docker run --rm -v "${volume}:/target:ro" alpine:3.22 sh -c \
    'test -z "$(find /target -mindepth 1 -maxdepth 1 -print -quit)"'
}

for item in prometheus:amo-observability-prometheus-data alertmanager:amo-observability-alertmanager-data grafana:amo-observability-grafana-data; do
  name="${item%%:*}"
  volume="${item#*:}"
  archive="${SOURCE}/${name}-data.tgz"
  [[ -f "$archive" ]] || continue
  docker volume create "$volume" >/dev/null
  if ! volume_empty "$volume"; then
    echo "Refusing to overwrite non-empty Docker volume '${volume}'. Move or remove it explicitly before restore." >&2
    exit 1
  fi
  docker run --rm \
    -v "${volume}:/target" \
    -v "${SOURCE}:/backup:ro" \
    alpine:3.22 sh -c "tar -xzf /backup/${name}-data.tgz -C /target"
done

if [[ -f "${SOURCE}/configuration.tgz" ]]; then
  echo "Data volumes restored. Configuration archive is at ${SOURCE}/configuration.tgz."
  echo "Review it before restoring deployment-local .env or version-controlled configuration."
else
  echo "Data volumes restored; no configuration archive was present."
fi
