from pathlib import Path

from starlette.applications import Starlette
from starlette.testclient import TestClient

from workspace_agent_relay_mcp.config import RelayConfig
from workspace_agent_relay_mcp.db import RelayStore
from workspace_agent_relay_mcp.http_compat import _summarize_rpc_body, build_http_compat_app
from workspace_agent_relay_mcp.oauth import OAuthRuntimeConfig


def _client(tmp_path: Path, *, auth_token: str = "") -> TestClient:
    from workspace_agent_relay_mcp import server

    server.config = RelayConfig(state_dir=tmp_path / "state", auth_token=auth_token)
    server.store = RelayStore(server.config.database_path)
    return TestClient(server.build_http_app())


def test_server_card_is_public_and_describes_mcp_endpoint(tmp_path: Path) -> None:
    with _client(tmp_path, auth_token="secret") as client:
        response = client.get("/.well-known/mcp.json")

    assert response.status_code == 200
    body = response.json()
    assert body["transport"] == {"type": "streamable-http", "endpoint": "/mcp"}
    assert body["authentication"] == {"required": True, "schemes": ["bearer"]}
    assert body["serverInfo"]["name"] == "workspace-agent-relay-mcp"


def test_mcp_requires_bearer_when_auth_token_is_set(tmp_path: Path) -> None:
    with _client(tmp_path, auth_token="secret") as client:
        missing = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
        allowed = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"Authorization": "Bearer secret"},
        )

    assert missing.status_code == 401
    assert allowed.status_code != 401


def test_head_and_options_are_allowed_without_auth(tmp_path: Path) -> None:
    with _client(tmp_path, auth_token="secret") as client:
        head = client.head("/mcp")
        options = client.options("/mcp")

    assert head.status_code == 204
    assert options.status_code == 204


def test_plain_get_mcp_returns_server_card_when_auth_disabled(tmp_path: Path) -> None:
    with _client(tmp_path, auth_token="") as client:
        response = client.get("/mcp", headers={"Accept": "*/*"})

    assert response.status_code == 200
    assert response.json()["transport"]["endpoint"] == "/mcp"


def test_debug_rpc_summary_redacts_callback_token_argument() -> None:
    body = b"""{
      "jsonrpc": "2.0",
      "id": 1,
      "method": "tools/call",
      "params": {
        "name": "record_result",
        "arguments": {
          "request_id": "relay_1",
          "callback_token": "secret-callback",
          "conversation_key": "research:sherlog"
        }
      }
    }"""

    summary = _summarize_rpc_body(body)
    rendered = str(summary)

    assert "secret-callback" not in rendered
    assert "[redacted]" in rendered
    assert summary["entries"][0]["tool"] == "record_result"


def test_oauth_metadata_uses_latest_runtime_config(tmp_path: Path) -> None:
    active_config = {
        "value": OAuthRuntimeConfig(
            auth_mode="oauth",
            auth_token="",
            public_base_url="https://old.example",
            state_dir=tmp_path / "old",
            oauth_login_token="login-old",
            oauth_scopes=("workspace-agent-relay",),
            oauth_token_ttl_seconds=3600,
        )
    }
    app = build_http_compat_app(
        streamable_app=Starlette(),
        legacy_sse_app=Starlette(),
        app_name="workspace-agent-relay-mcp",
        mcp_path="/mcp",
        get_auth_token=lambda: "",
        get_oauth_config=lambda: active_config["value"],
        get_debug_enabled=lambda: False,
        instructions="test",
    )
    active_config["value"] = OAuthRuntimeConfig(
        auth_mode="oauth",
        auth_token="",
        public_base_url="https://new.example",
        state_dir=tmp_path / "new",
        oauth_login_token="login-new",
        oauth_scopes=("workspace-agent-relay",),
        oauth_token_ttl_seconds=3600,
    )

    with TestClient(app) as client:
        response = client.get("/.well-known/oauth-authorization-server")

    assert response.status_code == 200
    assert response.json()["issuer"] == "https://new.example"
