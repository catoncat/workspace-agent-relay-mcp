#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d "$ROOT_DIR/.venv" ]]; then
  python3 -m venv "$ROOT_DIR/.venv"
fi

# shellcheck disable=SC1091
source "$ROOT_DIR/.venv/bin/activate"
env \
  -u WORKSPACE_AGENT_RELAY_AUTH_TOKEN \
  -u WORKSPACE_AGENT_RELAY_AGENT_TOKEN \
  -u WORKSPACE_AGENT_RELAY_OAUTH_LOGIN_TOKEN \
  pip install -e ".[dev]"

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

case "$WORKSPACE_AGENT_RELAY_AUTH_TOKEN" in
  replace-me|local-mcp-token|change-me|changeme|paste-output-from-openssl-rand-hex-32|replace-me-with-openssl-rand-hex-32|"<paste the output of openssl rand -hex 32>")
    echo "WORKSPACE_AGENT_RELAY_AUTH_TOKEN still uses a placeholder value." >&2
    echo "Generate one with: openssl rand -hex 32" >&2
    exit 1
    ;;
esac

if [[ "${#WORKSPACE_AGENT_RELAY_AUTH_TOKEN}" -lt 32 ]]; then
  echo "WORKSPACE_AGENT_RELAY_AUTH_TOKEN must be at least 32 characters for tunnel use." >&2
  echo "Generate one with: openssl rand -hex 32" >&2
  exit 1
fi

SERVER_URL="http://${WORKSPACE_AGENT_RELAY_HOST}:${WORKSPACE_AGENT_RELAY_PORT}"
python -m workspace_agent_relay_mcp.server &
SERVER_PID=$!
CLOUDFLARED_PID=""

cleanup() {
  if [[ -n "$CLOUDFLARED_PID" ]]; then
    kill "$CLOUDFLARED_PID" >/dev/null 2>&1 || true
  fi
  kill "$SERVER_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

python - "$SERVER_PID" <<'PY'
import os
import json
import socket
import sys
import time
import urllib.request

host = os.environ["WORKSPACE_AGENT_RELAY_HOST"]
port = int(os.environ["WORKSPACE_AGENT_RELAY_PORT"])
server_pid = int(sys.argv[1])
url = f"http://{host}:{port}/.well-known/mcp.json"
deadline = time.time() + 15
while time.time() < deadline:
    try:
        os.kill(server_pid, 0)
    except ProcessLookupError:
        raise SystemExit("Relay server exited before it became ready.")
    try:
        with socket.create_connection((host, port), timeout=0.5):
            pass
        with urllib.request.urlopen(url, timeout=1.0) as response:
            body = json.loads(response.read(4096).decode("utf-8"))
        if (
            body.get("serverInfo", {}).get("name") == "workspace-agent-relay-mcp"
            and body.get("transport", {}).get("endpoint") == "/mcp"
        ):
            raise SystemExit(0)
    except (OSError, json.JSONDecodeError):
        pass
    time.sleep(0.2)
raise SystemExit(f"Timed out waiting for relay server at {host}:{port}")
PY

echo "Dashboard: ${SERVER_URL}/"
echo "MCP endpoint: ${SERVER_URL}/mcp"

if command -v cloudflared >/dev/null 2>&1; then
  if [[ -n "${WORKSPACE_AGENT_RELAY_CLOUDFLARED_CONFIG:-}" ]]; then
    if [[ -n "${WORKSPACE_AGENT_RELAY_TUNNEL_NAME:-}" ]]; then
      env -u WORKSPACE_AGENT_RELAY_AUTH_TOKEN -u WORKSPACE_AGENT_RELAY_AGENT_TOKEN -u WORKSPACE_AGENT_RELAY_OAUTH_LOGIN_TOKEN \
        cloudflared tunnel --config "${WORKSPACE_AGENT_RELAY_CLOUDFLARED_CONFIG}" run "${WORKSPACE_AGENT_RELAY_TUNNEL_NAME}" &
    else
      env -u WORKSPACE_AGENT_RELAY_AUTH_TOKEN -u WORKSPACE_AGENT_RELAY_AGENT_TOKEN -u WORKSPACE_AGENT_RELAY_OAUTH_LOGIN_TOKEN \
        cloudflared tunnel --config "${WORKSPACE_AGENT_RELAY_CLOUDFLARED_CONFIG}" run &
    fi
  else
    env -u WORKSPACE_AGENT_RELAY_AUTH_TOKEN -u WORKSPACE_AGENT_RELAY_AGENT_TOKEN -u WORKSPACE_AGENT_RELAY_OAUTH_LOGIN_TOKEN \
      cloudflared tunnel --url "${SERVER_URL}" &
  fi
  CLOUDFLARED_PID=$!
  while true; do
    if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
      echo "Relay server exited; stopping tunnel." >&2
      exit 1
    fi
    if ! kill -0 "$CLOUDFLARED_PID" >/dev/null 2>&1; then
      wait "$CLOUDFLARED_PID"
      exit $?
    fi
    sleep 1
  done
else
  echo "cloudflared is not installed; local server is running until Ctrl+C."
  wait "$SERVER_PID"
fi
