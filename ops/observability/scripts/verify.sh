#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ROLE="${1:-all}"
ENV_FILE="${ROOT_DIR}/.env"
[[ -f "$ENV_FILE" ]] || ENV_FILE="${ROOT_DIR}/.env.example"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

COMPOSE=(docker compose --env-file "$ENV_FILE" -f "${ROOT_DIR}/docker-compose.observability.yml")

need_running() {
  local service="$1"
  "${COMPOSE[@]}" ps --status running --services | grep -Fxq "$service" || {
    echo "FAIL: $service is not running" >&2
    return 1
  }
  echo "OK: $service running"
}

curl_ok() {
  local label="$1" url="$2"
  curl --fail --silent --show-error --max-time 5 "$url" >/dev/null || {
    echo "FAIL: $label health check" >&2
    return 1
  }
  echo "OK: $label healthy"
}

case "$ROLE" in
  agent|all)
    need_running node-exporter
    need_running cadvisor
    need_running otel-agent
    curl_ok node-exporter "http://${OBSERVABILITY_AGENT_BIND_ADDRESS}:9100/metrics"
    curl_ok cadvisor "http://${OBSERVABILITY_AGENT_BIND_ADDRESS}:8081/healthz"
    ;;
  hub) ;;
  *) echo "Role must be agent, hub or all" >&2; exit 2 ;;
esac

case "$ROLE" in
  hub|all)
    need_running prometheus
    need_running alertmanager
    need_running grafana
    need_running otel-hub
    curl_ok prometheus "http://${OBSERVABILITY_HUB_BIND_ADDRESS}:9090/-/healthy"
    curl_ok alertmanager "http://${OBSERVABILITY_HUB_BIND_ADDRESS}:9093/-/healthy"
    curl_ok grafana "http://${OBSERVABILITY_HUB_BIND_ADDRESS}:3001/api/health"
    ;;
esac

echo "Observability role '${ROLE}' passed local health verification."
