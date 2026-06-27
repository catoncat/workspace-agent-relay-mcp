from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path


APP_NAME = "workspace-agent-relay-mcp"
DEFAULT_SCOPE = "workspace-agent-relay"
_DOTENV_LOADED = False

# Env var namespace for ChatGPT Workspace Agent access tokens. The default
# token lives in WORKSPACE_AGENT_RELAY_AGENT_TOKEN; additional agents use
# WORKSPACE_AGENT_RELAY_AGENT_TOKEN_<suffix>. load_config() snapshots every
# non-empty var in this namespace into RelayConfig.agent_tokens so that
# per-agent token resolution is config-driven and insulated from runtime
# os.environ mutation (and from test dotenv side effects).
AGENT_TOKEN_ENV_PREFIX = "WORKSPACE_AGENT_RELAY_AGENT_TOKEN"


def _parse_dotenv_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].strip()
    if "=" not in stripped:
        return None
    key, _, value = stripped.partition("=")
    key = key.strip()
    if not key:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def _dotenv_candidates() -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        candidates.append(resolved)

    cwd = Path.cwd()
    for path in [cwd, *cwd.parents]:
        add(path / ".env")
    package_root = Path(__file__).resolve().parents[2]
    add(package_root / ".env")
    return candidates


def _load_dotenv_files() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    if _env_flag("WORKSPACE_AGENT_RELAY_SKIP_DOTENV", default=False):
        _DOTENV_LOADED = True
        return
    for path in _dotenv_candidates():
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            parsed = _parse_dotenv_line(line)
            if parsed is None:
                continue
            key, value = parsed
            os.environ.setdefault(key, value)
        break
    _DOTENV_LOADED = True


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
    # env var name -> token value, populated by load_config() from every
    # non-empty WORKSPACE_AGENT_RELAY_AGENT_TOKEN* env var. agent_token() and
    # list_configured_token_refs() read from this snapshot instead of live
    # os.environ, so token resolution is deterministic and test-isolated.
    agent_tokens: dict[str, str] = field(default_factory=dict)

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
    _load_dotenv_files()
    scopes = tuple(
        scope
        for scope in os.environ.get("WORKSPACE_AGENT_RELAY_OAUTH_SCOPES", DEFAULT_SCOPE).split()
        if scope
    )
    agent_tokens: dict[str, str] = {}
    for key in os.environ:
        if key != AGENT_TOKEN_ENV_PREFIX and not key.startswith(AGENT_TOKEN_ENV_PREFIX + "_"):
            continue
        value = os.environ.get(key, "").strip()
        if value:
            agent_tokens[key] = value
    default_agent_token = os.environ.get("WORKSPACE_AGENT_RELAY_AGENT_TOKEN", "").strip()
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
        default_agent_token=default_agent_token,
        agent_tokens=agent_tokens,
    )
