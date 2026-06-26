import base64
import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
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


def _runtime_config(
    tmp_path: Path,
    *,
    auth_mode: str = "",
    auth_token: str = "",
    public_base_url: str = "https://relay.example",
    oauth_login_token: str = "",
) -> OAuthRuntimeConfig:
    return OAuthRuntimeConfig(
        auth_mode=auth_mode,
        auth_token=auth_token,
        public_base_url=public_base_url,
        state_dir=tmp_path / "state",
        oauth_login_token=oauth_login_token,
        oauth_scopes=("workspace-agent-relay",),
        oauth_token_ttl_seconds=3600,
    )


def _fake_asgi_app(name: str, calls: list[dict[str, Any]] | None = None):
    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if calls is not None:
            calls.append(
                {
                    "name": name,
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "headers": {
                        key.decode("latin-1").lower(): value.decode("latin-1")
                        for key, value in scope.get("headers", [])
                    },
                }
            )
        await JSONResponse({"app": name, "path": scope.get("path")})(scope, receive, send)

    return app


def _compat_app(
    tmp_path: Path,
    *,
    config: OAuthRuntimeConfig | None = None,
    stream_calls: list[dict[str, Any]] | None = None,
    legacy_calls: list[dict[str, Any]] | None = None,
):
    active_config = config or _runtime_config(tmp_path)
    return build_http_compat_app(
        streamable_app=_fake_asgi_app("streamable", stream_calls),
        legacy_sse_app=_fake_asgi_app("legacy", legacy_calls),
        app_name="workspace-agent-relay-mcp",
        mcp_path="/mcp",
        get_auth_token=lambda: active_config.auth_token,
        get_oauth_config=lambda: active_config,
        get_debug_enabled=lambda: False,
        instructions="test instructions",
    )


def _pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


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
    body = b"""[
      {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
          "name": "record_result",
          "arguments": {
            "request_id": "relay_1",
            "callback_token": "secret-callback",
            "conversation_key": "research:sherlog",
            "nested": {
              "api_key": "api-secret",
              "access_key": "access-secret"
            }
          }
        }
      },
      {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "notifications/initialized",
        "params": {
          "authorization": "Bearer bearer-secret",
          "safe": "visible"
        }
      }
    ]"""

    summary = _summarize_rpc_body(body)
    rendered = str(summary)

    assert "secret-callback" not in rendered
    assert "Bearer bearer-secret" not in rendered
    assert "api-secret" not in rendered
    assert "access-secret" not in rendered
    assert "[REDACTED]" in rendered
    assert "visible" in rendered
    assert summary["entries"][0]["tool"] == "record_result"


def test_build_http_compat_app_rejects_unknown_auth_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="auth_mode"):
        _compat_app(tmp_path, config=_runtime_config(tmp_path, auth_mode="bogus"))


def test_build_http_compat_app_rejects_explicit_shared_token_without_token(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="auth_token"):
        _compat_app(tmp_path, config=_runtime_config(tmp_path, auth_mode="shared_token", auth_token=""))


def test_build_http_compat_app_rejects_oauth_without_login_token(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="login token"):
        _compat_app(tmp_path, config=_runtime_config(tmp_path, auth_mode="oauth", auth_token="", oauth_login_token=""))


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


def test_oauth_metadata_and_www_authenticate_challenge(tmp_path: Path) -> None:
    config = _runtime_config(tmp_path, auth_mode="oauth", oauth_login_token="login-secret")
    app = _compat_app(tmp_path, config=config)

    with TestClient(app) as client:
        authorization = client.get("/.well-known/oauth-authorization-server")
        protected = client.get("/.well-known/oauth-protected-resource/mcp")
        missing = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})

    assert authorization.status_code == 200
    assert authorization.json()["issuer"] == "https://relay.example"
    assert authorization.json()["token_endpoint"] == "https://relay.example/oauth/token"
    assert protected.status_code == 200
    assert protected.json()["resource"] == "https://relay.example/mcp"
    assert protected.json()["resource_name"] == "workspace-agent-relay-mcp"
    assert missing.status_code == 401
    assert (
        'resource_metadata="https://relay.example/.well-known/oauth-protected-resource/mcp"'
        in missing.headers["www-authenticate"]
    )


def test_dynamic_oauth_flow_token_allows_mcp_access(tmp_path: Path) -> None:
    stream_calls: list[dict[str, Any]] = []
    config = _runtime_config(tmp_path, auth_mode="oauth", oauth_login_token="login-secret")
    app = _compat_app(tmp_path, config=config, stream_calls=stream_calls)
    verifier = "verifier-" + ("a" * 64)
    redirect_uri = "http://localhost/callback"

    with TestClient(app) as client:
        registration = client.post(
            "/oauth/register",
            json={"client_name": "Test Client", "redirect_uris": [redirect_uri]},
        )
        client_id = registration.json()["client_id"]
        authorize = client.post(
            "/oauth/authorize",
            data={
                "login_token": "login-secret",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "code_challenge_method": "S256",
                "code_challenge": _pkce_s256(verifier),
                "resource": "https://relay.example/mcp",
                "scope": "workspace-agent-relay",
                "state": "state-1",
            },
            follow_redirects=False,
        )
        location = authorize.headers["location"]
        query = parse_qs(urlparse(location).query)
        token = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code": query["code"][0],
                "code_verifier": verifier,
                "resource": "https://relay.example/mcp",
            },
        )
        access_token = token.json()["access_token"]
        mcp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert registration.status_code == 201
    assert authorize.status_code == 303
    assert query["state"] == ["state-1"]
    assert token.status_code == 200
    assert mcp.status_code == 200
    assert mcp.json()["app"] == "streamable"
    assert stream_calls[-1]["path"] == "/mcp"


def test_legacy_sse_fallback_and_session_routing_use_fake_apps(tmp_path: Path) -> None:
    stream_calls: list[dict[str, Any]] = []
    legacy_calls: list[dict[str, Any]] = []
    app = _compat_app(tmp_path, stream_calls=stream_calls, legacy_calls=legacy_calls)

    with TestClient(app) as client:
        legacy = client.get("/mcp", headers={"Accept": "text/event-stream"})
        streamable = client.get(
            "/mcp",
            headers={"Accept": "text/event-stream", "mcp-session-id": "session-1"},
        )

    assert legacy.status_code == 200
    assert legacy.json()["app"] == "legacy"
    assert streamable.status_code == 200
    assert streamable.json()["app"] == "streamable"
    assert legacy_calls[-1]["path"] == "/mcp"
    assert stream_calls[-1]["headers"]["mcp-session-id"] == "session-1"


def test_legacy_messages_path_requires_bearer_and_routes_when_authorized(tmp_path: Path) -> None:
    legacy_calls: list[dict[str, Any]] = []
    config = _runtime_config(tmp_path, auth_mode="shared_token", auth_token="secret")
    app = _compat_app(tmp_path, config=config, legacy_calls=legacy_calls)

    with TestClient(app) as client:
        missing = client.post("/messages", json={"id": 1})
        allowed = client.post(
            "/messages",
            json={"id": 1},
            headers={"Authorization": "Bearer secret"},
        )

    assert missing.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["app"] == "legacy"
    assert legacy_calls[-1]["path"] == "/messages"


def test_malformed_oauth_request_bodies_return_controlled_400(tmp_path: Path) -> None:
    config = _runtime_config(tmp_path, auth_mode="oauth", oauth_login_token="login-secret")
    app = _compat_app(tmp_path, config=config)

    with TestClient(app) as client:
        malformed_json = client.post(
            "/oauth/register",
            content=b"{",
            headers={"content-type": "application/json"},
        )
        malformed_form = client.post(
            "/oauth/register",
            content=b"\xff",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    assert malformed_json.status_code == 400
    assert malformed_form.status_code == 400
