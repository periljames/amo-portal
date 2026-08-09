#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEST="${1:-${ROOT_DIR}/backups/$(date -u +%Y%m%dT%H%M%SZ)}"

mkdir -p "$DEST"
if [[ -f "${ROOT_DIR}/.env" ]]; then
  tar -C "$ROOT_DIR" -czf "${DEST}/configuration.tgz" prometheus alertmanager otel grafana runtime/targets .env
else
  tar -C "$ROOT_DIR" -czf "${DEST}/configuration.tgz" prometheus alertmanager otel grafana runtime/targets
fi

for item in prometheus:amo-observability-prometheus-data alertmanager:amo-observability-alertmanager-data grafana:amo-observability-grafana-data; do
  name="${item%%:*}"
  volume="${item#*:}"
  if docker volume inspect "$volume" >/dev/null 2>&1; then
    docker run --rm \
      -v "${volume}:/source:ro" \
      -v "${DEST}:/backup" \
      alpine:3.22 sh -c "cd /source && tar -czf /backup/${name}-data.tgz ."
  fi
done

chmod -R go-rwx "$DEST"
echo "Backup written to $DEST"
