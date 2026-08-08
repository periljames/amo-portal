#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ROLE=""
BIND_ADDRESS=""
HUB_ADDRESS=""
ENVIRONMENT="production"
CLUSTER_ID="amo-portal-production"
NODE_ID="$(hostname -s 2>/dev/null || hostname)"

usage() {
  cat <<'EOF'
Usage: sudo ./install-ubuntu.sh --role agent|hub|all [options]
  --bind-address PRIVATE_IP   Explicit trusted bind address. Wildcards are rejected.
  --hub-address PRIVATE_IP    Required for a remote agent unless already configured.
  --cluster-id ID             Stable observability cluster identifier.
  --node-id ID                Stable node identifier.
  --environment NAME          Environment label (default: production).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --role) ROLE="${2:-}"; shift 2 ;;
    --bind-address) BIND_ADDRESS="${2:-}"; shift 2 ;;
    --hub-address) HUB_ADDRESS="${2:-}"; shift 2 ;;
    --cluster-id) CLUSTER_ID="${2:-}"; shift 2 ;;
    --node-id) NODE_ID="${2:-}"; shift 2 ;;
    --environment) ENVIRONMENT="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)." >&2; exit 1; }
[[ "$ROLE" =~ ^(agent|hub|all)$ ]] || { usage; exit 2; }
[[ "$NODE_ID" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "Invalid node id" >&2; exit 2; }

# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || { echo "This installer supports Ubuntu Server only." >&2; exit 1; }

install_docker() {
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl gnupg python3
  if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    local arch codename
    arch="$(dpkg --print-architecture)"
    codename="${UBUNTU_CODENAME:-${VERSION_CODENAME}}"
    echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${codename} stable" > /etc/apt/sources.list.d/docker.list
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  fi
  systemctl enable --now docker
}

private_address() {
  python3 - <<'PY'
import ipaddress
import socket

seen = []
try:
    seen.extend(socket.gethostbyname_ex(socket.gethostname())[2])
except OSError:
    pass
for raw in seen:
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        continue
    if ip.version == 4 and ip.is_private and not ip.is_loopback:
        print(raw)
        raise SystemExit(0)
raise SystemExit(1)
PY
}

reject_wildcard() {
  [[ "$1" != "0.0.0.0" && "$1" != "::" ]] || {
    echo "Wildcard monitoring binds are forbidden." >&2
    exit 2
  }
}

install_docker
mkdir -p "${ROOT_DIR}/runtime/targets/node-exporter" "${ROOT_DIR}/runtime/targets/cadvisor"
chmod 0750 "${ROOT_DIR}/runtime" "${ROOT_DIR}/runtime/targets" "${ROOT_DIR}/runtime/targets/node-exporter" "${ROOT_DIR}/runtime/targets/cadvisor"

EXISTING_ENV="${ROOT_DIR}/.env"
if [[ -f "$EXISTING_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$EXISTING_ENV"
  set +a
fi

if [[ -z "$BIND_ADDRESS" ]]; then
  if [[ "$ROLE" == "hub" ]]; then
    BIND_ADDRESS="${OBSERVABILITY_HUB_BIND_ADDRESS:-127.0.0.1}"
  else
    BIND_ADDRESS="${OBSERVABILITY_AGENT_BIND_ADDRESS:-$(private_address || true)}"
    [[ -n "$BIND_ADDRESS" ]] || {
      echo "No trusted private IPv4 address detected; pass --bind-address." >&2
      exit 2
    }
  fi
fi
reject_wildcard "$BIND_ADDRESS"

AGENT_BIND="${OBSERVABILITY_AGENT_BIND_ADDRESS:-$BIND_ADDRESS}"
HUB_BIND="${OBSERVABILITY_HUB_BIND_ADDRESS:-$BIND_ADDRESS}"
if [[ "$ROLE" == "agent" ]]; then
  AGENT_BIND="$BIND_ADDRESS"
  HUB_ADDRESS="${HUB_ADDRESS:-${OBSERVABILITY_HUB_ADDRESS:-}}"
  if [[ -z "$HUB_ADDRESS" && -t 0 ]]; then
    read -r -p "Observability hub private address: " HUB_ADDRESS
  fi
  [[ -n "$HUB_ADDRESS" ]] || {
    echo "Remote agent requires --hub-address or OBSERVABILITY_HUB_ADDRESS in existing .env." >&2
    exit 2
  }
elif [[ "$ROLE" == "hub" ]]; then
  HUB_BIND="$BIND_ADDRESS"
  HUB_ADDRESS="${HUB_ADDRESS:-${OBSERVABILITY_HUB_ADDRESS:-$HUB_BIND}}"
else
  AGENT_BIND="$BIND_ADDRESS"
  HUB_BIND="$BIND_ADDRESS"
  HUB_ADDRESS="${HUB_ADDRESS:-$BIND_ADDRESS}"
fi
reject_wildcard "$AGENT_BIND"
reject_wildcard "$HUB_BIND"
reject_wildcard "$HUB_ADDRESS"

GRAFANA_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-}"
GENERATED_SECRET="false"
if [[ "$ROLE" != "agent" && -z "$GRAFANA_PASSWORD" ]]; then
  GRAFANA_PASSWORD="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
  GENERATED_SECRET="true"
fi
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-unused-agent-role}"

if [[ "$ROLE" == "all" ]]; then
  OTLP_ENDPOINT="otel-hub:4317"
else
  OTLP_ENDPOINT="${HUB_ADDRESS}:14317"
fi

umask 077
cat > "$EXISTING_ENV" <<EOF
OBSERVABILITY_CLUSTER_ID=${CLUSTER_ID}
OBSERVABILITY_NODE_ID=${NODE_ID}
OBSERVABILITY_ENVIRONMENT=${ENVIRONMENT}
OBSERVABILITY_AGENT_BIND_ADDRESS=${AGENT_BIND}
OBSERVABILITY_HUB_BIND_ADDRESS=${HUB_BIND}
OBSERVABILITY_HUB_ADDRESS=${HUB_ADDRESS}
OTEL_EXPORTER_OTLP_ENDPOINT=${OTLP_ENDPOINT}
OTEL_EXPORTER_OTLP_INSECURE=true
GRAFANA_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
EOF
chmod 0600 "$EXISTING_ENV"

COMPOSE=(docker compose --env-file "$EXISTING_ENV" -f "${ROOT_DIR}/docker-compose.observability.yml")
case "$ROLE" in
  agent)
    "${COMPOSE[@]}" --profile agent up -d
    ;;
  hub)
    "${COMPOSE[@]}" --profile hub up -d
    ;;
  all)
    "${SCRIPT_DIR}/add-node.sh" --node-id "$NODE_ID" --address "$AGENT_BIND" --environment "$ENVIRONMENT" --cluster-id "$CLUSTER_ID"
    "${COMPOSE[@]}" --profile agent --profile hub up -d
    ;;
esac

"${SCRIPT_DIR}/verify.sh" "$ROLE"
if [[ "$GENERATED_SECRET" == "true" ]]; then
  echo "Grafana admin password (generated now; stored in ${EXISTING_ENV} mode 0600): ${GRAFANA_PASSWORD}"
fi
if [[ "$ROLE" == "agent" ]]; then
  echo "Register this node on the hub: ./scripts/add-node.sh --node-id ${NODE_ID} --address ${AGENT_BIND} --environment ${ENVIRONMENT} --cluster-id ${CLUSTER_ID}"
fi
echo "Observability role '${ROLE}' installed. Monitoring ports are bound only to ${BIND_ADDRESS}; verify firewall/VPN policy before use."
