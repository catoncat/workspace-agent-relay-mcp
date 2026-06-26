from pathlib import Path

from workspace_agent_relay_mcp.config import RelayConfig, load_config


def test_load_config_uses_safe_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("WORKSPACE_AGENT_RELAY_HOST", raising=False)
    monkeypatch.delenv("WORKSPACE_AGENT_RELAY_PORT", raising=False)
    monkeypatch.setenv("WORKSPACE_AGENT_RELAY_STATE_DIR", str(tmp_path / "state"))

    config = load_config()

    assert isinstance(config, RelayConfig)
    assert config.host == "127.0.0.1"
    assert config.port == 8799
    assert config.state_dir == tmp_path / "state"
    assert config.database_path == tmp_path / "state" / "relay.sqlite"
    assert config.auth_mode == ""
    assert config.auth_token == ""


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
