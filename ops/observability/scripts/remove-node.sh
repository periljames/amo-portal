#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
NODE_ID="${1:-}"

[[ "$NODE_ID" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "Usage: $0 NODE_ID" >&2; exit 2; }
rm -f "${ROOT_DIR}/runtime/targets/node-exporter/${NODE_ID}.json" "${ROOT_DIR}/runtime/targets/cadvisor/${NODE_ID}.json"
echo "Removed ${NODE_ID} from Prometheus file discovery."
