#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
NODE_ID=""
ADDRESS=""
NODE_EXPORTER_TARGET=""
CADVISOR_TARGET=""
ENVIRONMENT="production"
CLUSTER_ID="amo-portal"

usage() {
  cat >&2 <<'EOF'
Usage: add-node.sh --node-id ID [--address PRIVATE_IP_OR_DNS] [options]
  --address ADDRESS                 Builds ADDRESS:9100 and ADDRESS:8081 targets.
  --node-exporter-target HOST:PORT  Explicit Node Exporter target.
  --cadvisor-target HOST:PORT       Explicit cAdvisor target.
  --environment NAME
  --cluster-id ID
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --node-id) NODE_ID="${2:-}"; shift 2 ;;
    --address) ADDRESS="${2:-}"; shift 2 ;;
    --node-exporter-target) NODE_EXPORTER_TARGET="${2:-}"; shift 2 ;;
    --cadvisor-target) CADVISOR_TARGET="${2:-}"; shift 2 ;;
    --environment) ENVIRONMENT="${2:-}"; shift 2 ;;
    --cluster-id) CLUSTER_ID="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

[[ "$NODE_ID" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "Invalid --node-id" >&2; exit 2; }
if [[ -n "$ADDRESS" ]]; then
  [[ "$ADDRESS" != "0.0.0.0" && "$ADDRESS" != "::" ]] || { echo "Wildcard addresses are forbidden" >&2; exit 2; }
  NODE_EXPORTER_TARGET="${NODE_EXPORTER_TARGET:-${ADDRESS}:9100}"
  CADVISOR_TARGET="${CADVISOR_TARGET:-${ADDRESS}:8081}"
fi
[[ -n "$NODE_EXPORTER_TARGET" && -n "$CADVISOR_TARGET" ]] || {
  echo "Provide --address or both explicit targets." >&2
  exit 2
}

mkdir -p "${ROOT_DIR}/runtime/targets/node-exporter" "${ROOT_DIR}/runtime/targets/cadvisor"

write_target() {
  local path="$1"
  local target="$2"
  python3 - "$path" "$target" "$NODE_ID" "$ENVIRONMENT" "$CLUSTER_ID" <<'PY'
import json
import os
import sys
import tempfile

path, target, node_id, environment, cluster_id = sys.argv[1:]
payload = [{
    "targets": [target],
    "labels": {
        "node_id": node_id,
        "environment": environment,
        "cluster_id": cluster_id,
    },
}]
os.makedirs(os.path.dirname(path), exist_ok=True)
fd, tmp = tempfile.mkstemp(prefix=".target-", dir=os.path.dirname(path), text=True)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, separators=(",", ":"))
    handle.write("\n")
os.replace(tmp, path)
PY
}

write_target "${ROOT_DIR}/runtime/targets/node-exporter/${NODE_ID}.json" "$NODE_EXPORTER_TARGET"
write_target "${ROOT_DIR}/runtime/targets/cadvisor/${NODE_ID}.json" "$CADVISOR_TARGET"
echo "Registered ${NODE_ID}: node-exporter=${NODE_EXPORTER_TARGET}, cadvisor=${CADVISOR_TARGET}."
