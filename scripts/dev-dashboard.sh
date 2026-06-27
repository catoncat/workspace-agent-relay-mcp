#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

export WORKSPACE_AGENT_RELAY_HOST="${WORKSPACE_AGENT_RELAY_HOST:-127.0.0.1}"
export WORKSPACE_AGENT_RELAY_PORT="${WORKSPACE_AGENT_RELAY_PORT:-8799}"

RELAY_URL="http://${WORKSPACE_AGENT_RELAY_HOST}:${WORKSPACE_AGENT_RELAY_PORT}"
DASHBOARD_URL="http://127.0.0.1:5173"

relay_health_ok() {
  python3 - <<'PY'
import json
import os
import socket
import sys
import urllib.request

host = os.environ["WORKSPACE_AGENT_RELAY_HOST"]
port = int(os.environ["WORKSPACE_AGENT_RELAY_PORT"])
url = f"http://{host}:{port}/.well-known/mcp.json"
try:
    with socket.create_connection((host, port), timeout=0.5):
        pass
    with urllib.request.urlopen(url, timeout=1.5) as response:
        body = json.loads(response.read(4096).decode("utf-8"))
except (OSError, json.JSONDecodeError, ValueError):
    sys.exit(1)
if (
    body.get("serverInfo", {}).get("name") == "workspace-agent-relay-mcp"
    and body.get("transport", {}).get("endpoint") == "/mcp"
):
    sys.exit(0)
sys.exit(1)
PY
}

if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
  echo "Installing frontend dependencies…" >&2
  if command -v pnpm >/dev/null 2>&1; then
    (cd "$ROOT_DIR/frontend" && pnpm install)
  else
    (cd "$ROOT_DIR/frontend" && npm install)
  fi
fi

if ! relay_health_ok; then
  echo "Relay server is not running at ${RELAY_URL}" >&2
  echo "" >&2
  echo "Start the Python backend first, for example:" >&2
  echo "  .venv/bin/python -m workspace_agent_relay_mcp.server" >&2
  echo "  ./scripts/dev-tunnel.sh   # if you also need the cloudflared tunnel" >&2
  exit 1
fi

if [[ -z "${WORKSPACE_AGENT_RELAY_AUTH_TOKEN:-}" ]]; then
  echo "Warning: WORKSPACE_AGENT_RELAY_AUTH_TOKEN is not set in .env." >&2
  echo "The Vite dashboard will start, but API calls will 401 until you paste the token in Settings." >&2
else
  echo "Auth token: loaded from .env (Vite dev seeds localStorage automatically)." >&2
fi

echo "" >&2
echo "Relay (API + MCP):  ${RELAY_URL}" >&2
echo "Dashboard (HMR):    ${DASHBOARD_URL}" >&2
echo "Press Ctrl+C to stop the frontend dev server." >&2
echo "" >&2

cd "$ROOT_DIR/frontend"
if command -v pnpm >/dev/null 2>&1; then
  exec pnpm dev
else
  exec npm run dev
fi
