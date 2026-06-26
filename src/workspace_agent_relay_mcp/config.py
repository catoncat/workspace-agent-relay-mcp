from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


APP_NAME = "workspace-agent-relay-mcp"
DEFAULT_SCOPE = "workspace-agent-relay"


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RelayConfig:
    host: str = "127.0.0.1"
    port: int = 8799
    state_dir: Path = Path.home() / ".workspace-agent-relay-mcp"
    auth_token: str = ""
    auth_mode: str = ""
    public_base_url: str = ""
    oauth_login_token: str = ""
    oauth_scopes: tuple[str, ...] = (DEFAULT_SCOPE,)
    oauth_token_ttl_seconds: int = 86400
    debug_mcp_logging: bool = False
    default_agent_name: str = "default"
    default_trigger_url: str = ""
    default_agent_token: str = ""

    @property
    def database_path(self) -> Path:
        return self.state_dir / "relay.sqlite"

    def ensure_runtime_directories(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.state_dir.chmod(0o700)
        except OSError as exc:
            raise PermissionError(
                f"Could not set owner-only permissions on state directory: {self.state_dir}"
            ) from exc
        mode = self.state_dir.stat().st_mode & 0o777
        if mode != 0o700:
            raise PermissionError(
                f"State directory must have owner-only permissions 0o700, got {oct(mode)}: {self.state_dir}"
            )


def load_config() -> RelayConfig:
    scopes = tuple(
        scope
        for scope in os.environ.get("WORKSPACE_AGENT_RELAY_OAUTH_SCOPES", DEFAULT_SCOPE).split()
        if scope
    )
    return RelayConfig(
        host=os.environ.get("WORKSPACE_AGENT_RELAY_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=int(os.environ.get("WORKSPACE_AGENT_RELAY_PORT", "8799")),
        state_dir=Path(
            os.environ.get(
                "WORKSPACE_AGENT_RELAY_STATE_DIR",
                str(Path.home() / ".workspace-agent-relay-mcp"),
            )
        ).expanduser().resolve(),
        auth_token=os.environ.get("WORKSPACE_AGENT_RELAY_AUTH_TOKEN", "").strip(),
        auth_mode=os.environ.get("WORKSPACE_AGENT_RELAY_AUTH_MODE", "").strip().lower(),
        public_base_url=os.environ.get("WORKSPACE_AGENT_RELAY_PUBLIC_BASE_URL", "").strip().rstrip("/"),
        oauth_login_token=os.environ.get("WORKSPACE_AGENT_RELAY_OAUTH_LOGIN_TOKEN", "").strip(),
        oauth_scopes=scopes or (DEFAULT_SCOPE,),
        oauth_token_ttl_seconds=int(os.environ.get("WORKSPACE_AGENT_RELAY_OAUTH_TOKEN_TTL_SECONDS", "86400")),
        debug_mcp_logging=_env_flag("WORKSPACE_AGENT_RELAY_DEBUG_MCP_LOGGING", default=False),
        default_agent_name=os.environ.get("WORKSPACE_AGENT_RELAY_AGENT_NAME", "default").strip() or "default",
        default_trigger_url=os.environ.get("WORKSPACE_AGENT_RELAY_TRIGGER_URL", "").strip(),
        default_agent_token=os.environ.get("WORKSPACE_AGENT_RELAY_AGENT_TOKEN", "").strip(),
    )
