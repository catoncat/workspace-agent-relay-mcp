#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d "$ROOT_DIR/.venv" ]]; then
  python3 -m venv "$ROOT_DIR/.venv"
fi

# shellcheck disable=SC1091
source "$ROOT_DIR/.venv/bin/activate"

if [[ "${WORKSPACE_AGENT_RELAY_FORCE_PIP:-0}" == "1" ]] \
  || ! python -c "import workspace_agent_relay_mcp" >/dev/null 2>&1; then
  env \
    -u WORKSPACE_AGENT_RELAY_AUTH_TOKEN \
    -u WORKSPACE_AGENT_RELAY_AGENT_TOKEN \
    -u WORKSPACE_AGENT_RELAY_OAUTH_LOGIN_TOKEN \
    pip install -e ".[dev]"
fi

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

export WORKSPACE_AGENT_RELAY_HOST="${WORKSPACE_AGENT_RELAY_HOST:-127.0.0.1}"
export WORKSPACE_AGENT_RELAY_PORT="${WORKSPACE_AGENT_RELAY_PORT:-8799}"
export WORKSPACE_AGENT_RELAY_STATE_DIR="${WORKSPACE_AGENT_RELAY_STATE_DIR:-${HOME}/.workspace-agent-relay-mcp}"
mkdir -p "$WORKSPACE_AGENT_RELAY_STATE_DIR"

if [[ -z "${WORKSPACE_AGENT_RELAY_CLOUDFLARED_CONFIG:-}" ]]; then
  if [[ -f "$ROOT_DIR/cloudflared.local.yml" ]]; then
    export WORKSPACE_AGENT_RELAY_CLOUDFLARED_CONFIG="$ROOT_DIR/cloudflared.local.yml"
  elif [[ -f "$ROOT_DIR/cloudflared.local.yaml" ]]; then
    export WORKSPACE_AGENT_RELAY_CLOUDFLARED_CONFIG="$ROOT_DIR/cloudflared.local.yaml"
  fi
fi

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
PID_FILE="${WORKSPACE_AGENT_RELAY_STATE_DIR}/relay-server.pid"
SERVER_PID=""
SERVER_OWNED=false
CLOUDFLARED_PID=""

relay_health_ok() {
  python - <<'PY'
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

wait_for_relay_health() {
  local deadline=$((SECONDS + 15))
  while (( SECONDS < deadline )); do
    if relay_health_ok; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

port_listener_pids() {
  lsof -n -t -iTCP:"${WORKSPACE_AGENT_RELAY_PORT}" -sTCP:LISTEN 2>/dev/null | sort -u
}

pid_looks_like_relay() {
  local pid="$1"
  local cmd
  cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [[ "$cmd" == *workspace_agent_relay_mcp* ]]
}

reclaim_stale_relay_listeners() {
  local pid
  for pid in $(port_listener_pids); do
    if pid_looks_like_relay "$pid"; then
      echo "Stopping stale relay listener pid=${pid}" >&2
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  sleep 0.5
}

start_owned_server() {
  python -m workspace_agent_relay_mcp.server &
  SERVER_PID=$!
  SERVER_OWNED=true
  echo "$SERVER_PID" >"$PID_FILE"

  if ! wait_for_relay_health; then
    if kill -0 "$SERVER_PID" >/dev/null 2>&1; then
      kill "$SERVER_PID" >/dev/null 2>&1 || true
    fi
    rm -f "$PID_FILE"
    echo "Timed out waiting for relay server at ${SERVER_URL}" >&2
    exit 1
  fi
}

ensure_relay_server() {
  if relay_health_ok; then
    local existing
    existing="$(port_listener_pids | head -1 || true)"
    if [[ -n "$existing" ]]; then
      echo "Reusing healthy relay server at ${SERVER_URL} (pid=${existing})" >&2
    else
      echo "Reusing healthy relay server at ${SERVER_URL}" >&2
    fi
    if [[ -f "$PID_FILE" ]]; then
      local recorded
      recorded="$(cat "$PID_FILE" 2>/dev/null || true)"
      if [[ -n "$recorded" ]] && kill -0 "$recorded" >/dev/null 2>&1; then
        SERVER_PID="$recorded"
        SERVER_OWNED=true
      fi
    fi
    return 0
  fi

  local pid
  for pid in $(port_listener_pids); do
    if pid_looks_like_relay "$pid"; then
      echo "Port ${WORKSPACE_AGENT_RELAY_PORT} is held by unhealthy relay pid=${pid}; restarting." >&2
      kill "$pid" >/dev/null 2>&1 || true
      sleep 0.5
    else
      echo "Port ${WORKSPACE_AGENT_RELAY_PORT} is in use by pid=${pid} (not workspace-agent-relay-mcp)." >&2
      ps -p "$pid" -o command= 2>/dev/null || true
      echo "Stop that process or change WORKSPACE_AGENT_RELAY_PORT." >&2
      exit 1
    fi
  done

  reclaim_stale_relay_listeners
  echo "Starting relay server at ${SERVER_URL}" >&2
  start_owned_server
}

relay_supervisor_healthy() {
  if [[ "$SERVER_OWNED" == true && -n "$SERVER_PID" ]]; then
    if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
      return 1
    fi
  fi
  relay_health_ok
}

cleanup() {
  if [[ -n "$CLOUDFLARED_PID" ]]; then
    kill "$CLOUDFLARED_PID" >/dev/null 2>&1 || true
  fi
  if [[ "$SERVER_OWNED" == true && -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    rm -f "$PID_FILE"
  fi
}
trap cleanup EXIT INT TERM

ensure_relay_server

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
    if ! relay_supervisor_healthy; then
      echo "Relay server became unhealthy; stopping tunnel." >&2
      exit 1
    fi
    if ! kill -0 "$CLOUDFLARED_PID" >/dev/null 2>&1; then
      wait "$CLOUDFLARED_PID"
      exit $?
    fi
    sleep 2
  done
else
  echo "cloudflared is not installed; local server is running until Ctrl+C."
  if [[ "$SERVER_OWNED" == true && -n "$SERVER_PID" ]]; then
    wait "$SERVER_PID"
  else
    while relay_supervisor_healthy; do
      sleep 2
    done
    echo "Relay server became unhealthy." >&2
    exit 1
  fi
fi
