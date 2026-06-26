from pathlib import Path

import pytest

from workspace_agent_relay_mcp.config import RelayConfig, load_config


RELAY_ENV_VARS = (
    "WORKSPACE_AGENT_RELAY_HOST",
    "WORKSPACE_AGENT_RELAY_PORT",
    "WORKSPACE_AGENT_RELAY_STATE_DIR",
    "WORKSPACE_AGENT_RELAY_AUTH_TOKEN",
    "WORKSPACE_AGENT_RELAY_AUTH_MODE",
    "WORKSPACE_AGENT_RELAY_PUBLIC_BASE_URL",
    "WORKSPACE_AGENT_RELAY_OAUTH_LOGIN_TOKEN",
    "WORKSPACE_AGENT_RELAY_OAUTH_SCOPES",
    "WORKSPACE_AGENT_RELAY_OAUTH_TOKEN_TTL_SECONDS",
    "WORKSPACE_AGENT_RELAY_DEBUG_MCP_LOGGING",
    "WORKSPACE_AGENT_RELAY_AGENT_NAME",
    "WORKSPACE_AGENT_RELAY_TRIGGER_URL",
    "WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
    "WORKSPACE_AGENT_RELAY_CLOUDFLARED_CONFIG",
    "WORKSPACE_AGENT_RELAY_TUNNEL_NAME",
)


@pytest.fixture(autouse=True)
def clear_relay_env(monkeypatch) -> None:
    for name in RELAY_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_load_config_uses_safe_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WORKSPACE_AGENT_RELAY_STATE_DIR", str(tmp_path / "state"))

    config = load_config()

    assert isinstance(config, RelayConfig)
    assert config.host == "127.0.0.1"
    assert config.port == 8799
    assert config.state_dir == tmp_path / "state"
    assert config.database_path == tmp_path / "state" / "relay.sqlite"
    assert config.auth_mode == ""
    assert config.auth_token == ""


def test_load_config_reads_dotenv_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("WORKSPACE_AGENT_RELAY_SKIP_DOTENV", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "WORKSPACE_AGENT_RELAY_AUTH_TOKEN=from-dotenv",
                "WORKSPACE_AGENT_RELAY_AGENT_TOKEN=agent-from-dotenv",
                f"WORKSPACE_AGENT_RELAY_STATE_DIR={tmp_path / 'state'}",
            ]
        ),
        encoding="utf-8",
    )

    import workspace_agent_relay_mcp.config as config_module

    config_module._DOTENV_LOADED = False
    config = load_config()

    assert config.auth_token == "from-dotenv"
    assert config.default_agent_token == "agent-from-dotenv"
    assert config.state_dir == tmp_path / "state"
    config_module._DOTENV_LOADED = False


def test_load_config_reads_env_overrides(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WORKSPACE_AGENT_RELAY_HOST", "0.0.0.0")
    monkeypatch.setenv("WORKSPACE_AGENT_RELAY_PORT", "8801")
    monkeypatch.setenv("WORKSPACE_AGENT_RELAY_STATE_DIR", str(tmp_path / "custom-state"))
    monkeypatch.setenv("WORKSPACE_AGENT_RELAY_AUTH_TOKEN", "relay-secret")
    monkeypatch.setenv("WORKSPACE_AGENT_RELAY_AGENT_TOKEN", "agent-secret")
    monkeypatch.setenv("WORKSPACE_AGENT_RELAY_TRIGGER_URL", "https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger")

    config = load_config()

    assert config.host == "0.0.0.0"
    assert config.port == 8801
    assert config.state_dir == tmp_path / "custom-state"
    assert config.auth_token == "relay-secret"
    assert config.default_agent_token == "agent-secret"
    assert config.default_trigger_url.endswith("/agtch_test/trigger")


def test_ensure_runtime_directories_creates_owner_only_state_dir(tmp_path: Path) -> None:
    config = RelayConfig(state_dir=tmp_path / "state")

    config.ensure_runtime_directories()

    assert config.state_dir.is_dir()
    assert oct(config.state_dir.stat().st_mode & 0o777) == "0o700"


def test_ensure_runtime_directories_raises_when_owner_only_permissions_fail(
    monkeypatch,
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_dir.chmod(0o755)
    config = RelayConfig(state_dir=state_dir)

    def ignore_chmod(self: Path, mode: int) -> None:
        return None

    monkeypatch.setattr(Path, "chmod", ignore_chmod)

    with pytest.raises(PermissionError, match="owner-only"):
        config.ensure_runtime_directories()
