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
export WORKSPACE_AGENT_RELAY_STATE_DIR="${WORKSPACE_AGENT_RELAY_STATE_DIR:-${HOME}/.workspace-agent-relay-mcp}"

if [[ -z "${WORKSPACE_AGENT_RELAY_AUTH_TOKEN:-}" ]]; then
  echo "Missing WORKSPACE_AGENT_RELAY_AUTH_TOKEN. Set it in .env." >&2
  exit 1
fi

if [[ ! -d "$ROOT_DIR/.venv" ]]; then
  python3 -m venv "$ROOT_DIR/.venv"
fi

# shellcheck disable=SC1091
source "$ROOT_DIR/.venv/bin/activate"
pip install -e ".[dev]"

SERVER_URL="http://${WORKSPACE_AGENT_RELAY_HOST}:${WORKSPACE_AGENT_RELAY_PORT}"
python -m workspace_agent_relay_mcp.server &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

python - <<'PY'
import os
import socket
import time

host = os.environ["WORKSPACE_AGENT_RELAY_HOST"]
port = int(os.environ["WORKSPACE_AGENT_RELAY_PORT"])
deadline = time.time() + 15
while time.time() < deadline:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        if sock.connect_ex((host, port)) == 0:
            raise SystemExit(0)
    time.sleep(0.2)
raise SystemExit(f"Timed out waiting for {host}:{port}")
PY

echo "Dashboard: ${SERVER_URL}/"
echo "MCP endpoint: ${SERVER_URL}/mcp"

if command -v cloudflared >/dev/null 2>&1; then
  if [[ -n "${WORKSPACE_AGENT_RELAY_CLOUDFLARED_CONFIG:-}" ]]; then
    if [[ -n "${WORKSPACE_AGENT_RELAY_TUNNEL_NAME:-}" ]]; then
      cloudflared tunnel --config "${WORKSPACE_AGENT_RELAY_CLOUDFLARED_CONFIG}" run "${WORKSPACE_AGENT_RELAY_TUNNEL_NAME}"
    else
      cloudflared tunnel --config "${WORKSPACE_AGENT_RELAY_CLOUDFLARED_CONFIG}" run
    fi
  else
    cloudflared tunnel --url "${SERVER_URL}"
  fi
else
  echo "cloudflared is not installed; local server is running until Ctrl+C."
  wait "$SERVER_PID"
fi
