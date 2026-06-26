from pathlib import Path

from starlette.testclient import TestClient

from workspace_agent_relay_mcp.config import RelayConfig
from workspace_agent_relay_mcp.db import RelayStore


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
