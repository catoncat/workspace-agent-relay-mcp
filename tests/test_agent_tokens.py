from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from workspace_agent_relay_mcp.api.validation import (
    agent_token,
    agent_token_configured,
    list_configured_token_refs,
    resolve_agent_token,
    validate_agent_token_ref,
)
from workspace_agent_relay_mcp.config import RelayConfig
from workspace_agent_relay_mcp.store.relay_store import RelayStore

# Reuse the web-api test harness instead of duplicating it.
from tests.test_web_api import _client

DEFAULT = "WORKSPACE_AGENT_RELAY_AGENT_TOKEN"
SECOND = "WORKSPACE_AGENT_RELAY_AGENT_TOKEN_2"


def _cfg(agent_tokens: dict[str, str] | None = None, default_agent_token: str = "") -> RelayConfig:
    return RelayConfig(agent_tokens=agent_tokens or {}, default_agent_token=default_agent_token)


def test_validate_accepts_local_token_ref() -> None:
    validate_agent_token_ref("local:1")
    validate_agent_token_ref("local:42")


@pytest.mark.parametrize("bad", ["local:0", "local:-1", "local:abc", "local:"])
def test_validate_rejects_invalid_local_token_ref(bad: str) -> None:
    with pytest.raises(ValueError):
        validate_agent_token_ref(bad)


def test_resolve_agent_token_reads_local_store(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.create_agent(
        name="work",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_work/trigger",
        access_token="at-local",
    )
    cfg = _cfg()
    assert resolve_agent_token(cfg, store, agent["token_ref"]) == "at-local"
    assert agent_token_configured(cfg, store, agent) is True


def test_agent_token_configured_false_when_local_token_missing(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(
        name="legacy",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        token_ref="env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
    )
    cfg = _cfg(agent_tokens={}, default_agent_token="")
    assert agent_token_configured(cfg, store, agent) is False


def test_validate_accepts_default_token_ref() -> None:
    validate_agent_token_ref(f"env:{DEFAULT}")


def test_validate_accepts_namespaced_extension() -> None:
    validate_agent_token_ref(f"env:{SECOND}")
    validate_agent_token_ref("env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN_SECOND_ACCOUNT")


@pytest.mark.parametrize(
    "bad",
    [
        "env:OTHER",
        "env:HOME",
        "env:AWS_SECRET_KEY",
        "env:WORKSPACE_AGENT_RELAY_AGENT",
        "env:WORKSPACE_AGENT_RELAY_AUTH_TOKEN",
        "env:",
        "env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN-2",
        "WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
        "",
    ],
)
def test_validate_rejects_non_namespaced_token_ref(bad: str) -> None:
    with pytest.raises(ValueError):
        validate_agent_token_ref(bad)


def test_agent_token_resolves_named_extension_from_snapshot() -> None:
    cfg = _cfg(agent_tokens={DEFAULT: "default-tok", SECOND: "tok-2"})
    assert agent_token(cfg, f"env:{SECOND}") == "tok-2"


def test_agent_token_falls_back_to_config_default_for_default_ref() -> None:
    cfg = _cfg(agent_tokens={}, default_agent_token="default-tok")
    assert agent_token(cfg, f"env:{DEFAULT}") == "default-tok"


def test_agent_token_prefers_snapshot_over_config_default() -> None:
    cfg = _cfg(agent_tokens={DEFAULT: "snap-tok"}, default_agent_token="default-tok")
    assert agent_token(cfg, f"env:{DEFAULT}") == "snap-tok"


def test_agent_token_raises_with_var_name_when_missing() -> None:
    cfg = _cfg(agent_tokens={}, default_agent_token="")
    with pytest.raises(ValueError) as exc:
        agent_token(cfg, "env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN_3")
    assert "WORKSPACE_AGENT_RELAY_AGENT_TOKEN_3" in str(exc.value)


def test_list_configured_token_refs_lists_namespaced_non_empty() -> None:
    cfg = _cfg(agent_tokens={DEFAULT: "a", SECOND: "b"})
    refs = list_configured_token_refs(cfg)
    assert [r["env_var"] for r in refs] == [DEFAULT, SECOND]
    assert refs[0]["is_default"] is True
    assert refs[1]["is_default"] is False
    for r in refs:
        assert r["token_ref"].startswith("env:")
        assert "value" not in r


def test_list_configured_token_refs_skips_empty() -> None:
    cfg = _cfg(agent_tokens={DEFAULT: "a", SECOND: "   "})
    refs = list_configured_token_refs(cfg)
    assert [r["env_var"] for r in refs] == [DEFAULT]


def test_list_configured_token_refs_default_first_then_alpha() -> None:
    cfg = _cfg(
        agent_tokens={
            DEFAULT: "a",
            "WORKSPACE_AGENT_RELAY_AGENT_TOKEN_B": "b",
            "WORKSPACE_AGENT_RELAY_AGENT_TOKEN_A": "a2",
        }
    )
    refs = [r["env_var"] for r in list_configured_token_refs(cfg)]
    assert refs == [DEFAULT, "WORKSPACE_AGENT_RELAY_AGENT_TOKEN_A", "WORKSPACE_AGENT_RELAY_AGENT_TOKEN_B"]


def test_api_lists_configured_token_refs_without_values(tmp_path: Path) -> None:
    client, _ = _client(
        tmp_path,
        agent_tokens={DEFAULT: "tok-default", SECOND: "tok-2"},
    )

    with client:
        resp = client.get("/api/agents/token-refs")

    assert resp.status_code == 200
    refs = resp.json()
    assert [r["env_var"] for r in refs] == [DEFAULT, SECOND]
    for r in refs:
        assert "value" not in r


def test_api_create_agent_accepts_namespaced_token_ref(tmp_path: Path) -> None:
    client, _ = _client(tmp_path, agent_tokens={SECOND: "tok-2"})

    with client:
        resp = client.post(
            "/api/agents",
            json={
                "name": "second",
                "trigger_url": "https://api.chatgpt.com/v1/workspace_agents/agtch_second/trigger",
                "token_ref": f"env:{SECOND}",
            },
        )

    assert resp.status_code == 200
    agent = resp.json()
    assert agent["token_ref"] == f"env:{SECOND}"
    assert agent["trigger_id"] == "agtch_second"


def test_api_create_agent_rejects_non_namespaced_token_ref(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    with client:
        resp = client.post(
            "/api/agents",
            json={
                "name": "bad",
                "trigger_url": "https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
                "token_ref": "env:HOME",
            },
        )

    assert resp.status_code == 400


def test_api_two_agents_trigger_with_their_own_tokens(tmp_path: Path) -> None:
    client, trigger_client = _client(
        tmp_path,
        agent_tokens={DEFAULT: "tok-A", SECOND: "tok-B"},
    )

    with client:
        agent_a = client.post(
            "/api/agents",
            json={
                "name": "A",
                "trigger_url": "https://api.chatgpt.com/v1/workspace_agents/agtch_a/trigger",
                "token_ref": f"env:{DEFAULT}",
            },
        ).json()
        agent_b = client.post(
            "/api/agents",
            json={
                "name": "B",
                "trigger_url": "https://api.chatgpt.com/v1/workspace_agents/agtch_b/trigger",
                "token_ref": f"env:{SECOND}",
            },
        ).json()
        conv_a = client.post(
            "/api/conversations",
            json={"agent_id": agent_a["id"], "name": "ca", "conversation_key": "k:a"},
        ).json()
        conv_b = client.post(
            "/api/conversations",
            json={"agent_id": agent_b["id"], "name": "cb", "conversation_key": "k:b"},
        ).json()
        run_a = client.post(
            f"/api/conversations/{conv_a['id']}/runs", json={"input_markdown": "hi A"}
        )
        run_b = client.post(
            f"/api/conversations/{conv_b['id']}/runs", json={"input_markdown": "hi B"}
        )

    assert run_a.status_code == 200
    assert run_b.status_code == 200
    tokens = {c["access_token"] for c in trigger_client.calls}
    assert "tok-A" in tokens
    assert "tok-B" in tokens
