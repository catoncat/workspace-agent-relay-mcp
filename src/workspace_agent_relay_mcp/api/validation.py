from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from ..config import AGENT_TOKEN_ENV_PREFIX


# token_ref grammar:
# - "env:<VAR_NAME>" — legacy; resolved from RelayConfig.agent_tokens snapshot
# - "local:<agent_id>" — token stored in relay SQLite (dashboard-managed)
TOKEN_REF_PREFIX = "env:"
LOCAL_TOKEN_REF_PREFIX = "local:"
TOKEN_ENV_VAR_PREFIX = AGENT_TOKEN_ENV_PREFIX

# The default token_ref: resolves to WORKSPACE_AGENT_RELAY_AGENT_TOKEN. Kept for
# existing single-agent deployments that bootstrap from .env.
SUPPORTED_AGENT_TOKEN_REF = f"{TOKEN_REF_PREFIX}{TOKEN_ENV_VAR_PREFIX}"

WORKSPACE_AGENT_TRIGGER_HOST = "api.chatgpt.com"
WORKSPACE_AGENT_TRIGGER_PREFIX = "/v1/workspace_agents/"
WORKSPACE_AGENT_TRIGGER_SUFFIX = "/trigger"


def validate_trigger_url(trigger_url: str) -> None:
    parsed = urlparse(trigger_url)
    trigger_id = ""
    if parsed.path.startswith(WORKSPACE_AGENT_TRIGGER_PREFIX) and parsed.path.endswith(WORKSPACE_AGENT_TRIGGER_SUFFIX):
        trigger_id = parsed.path[len(WORKSPACE_AGENT_TRIGGER_PREFIX) : -len(WORKSPACE_AGENT_TRIGGER_SUFFIX)]
    if (
        parsed.scheme != "https"
        or parsed.netloc != WORKSPACE_AGENT_TRIGGER_HOST
        or not trigger_id
        or "/" in trigger_id
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("trigger_url must be a ChatGPT Workspace Agent trigger endpoint")


def _local_agent_id_from_token_ref(token_ref: str) -> int:
    if not token_ref.startswith(LOCAL_TOKEN_REF_PREFIX):
        raise ValueError(
            f"unsupported token_ref: {token_ref!r} (expected format '{LOCAL_TOKEN_REF_PREFIX}<agent_id>')"
        )
    raw = token_ref[len(LOCAL_TOKEN_REF_PREFIX) :]
    if not raw.isdigit() or int(raw) <= 0:
        raise ValueError(f"unsupported token_ref: {token_ref!r} (invalid local agent id)")
    return int(raw)


def _env_var_from_token_ref(token_ref: str) -> str:
    if not token_ref.startswith(TOKEN_REF_PREFIX):
        raise ValueError(
            f"unsupported token_ref: {token_ref!r} (expected format '{TOKEN_REF_PREFIX}<VAR_NAME>')"
        )
    var_name = token_ref[len(TOKEN_REF_PREFIX) :]
    if not var_name:
        raise ValueError(f"unsupported token_ref: {token_ref!r} (missing env var name after '{TOKEN_REF_PREFIX}')")
    # Whitelist: VAR_NAME must be exactly the default token var, or a named
    # extension under the same namespace (WORKSPACE_AGENT_RELAY_AGENT_TOKEN_*).
    # This blocks token_ref values like "env:HOME" or "env:AWS_SECRET_KEY".
    if var_name != TOKEN_ENV_VAR_PREFIX and not var_name.startswith(TOKEN_ENV_VAR_PREFIX + "_"):
        raise ValueError(
            f"unsupported token_ref: {token_ref!r} "
            f"(env var must be {TOKEN_ENV_VAR_PREFIX} or start with {TOKEN_ENV_VAR_PREFIX}_)"
        )
    # Guard against trivially malformed names that would never resolve anyway.
    if not var_name.replace("_", "").isalnum():
        raise ValueError(f"unsupported token_ref: {token_ref!r} (invalid env var name)")
    return var_name


def validate_agent_token_ref(token_ref: str) -> None:
    if token_ref.startswith(LOCAL_TOKEN_REF_PREFIX):
        _local_agent_id_from_token_ref(token_ref)
        return
    _env_var_from_token_ref(token_ref)


def _agent_token_from_env(config: Any, token_ref: str) -> str:
    var_name = _env_var_from_token_ref(token_ref)
    agent_tokens = getattr(config, "agent_tokens", {}) or {}
    token = str(agent_tokens.get(var_name, "") or "").strip()
    if not token and var_name == TOKEN_ENV_VAR_PREFIX:
        token = str(getattr(config, "default_agent_token", "") or "").strip()
    if not token:
        raise ValueError(
            f"{var_name} is not configured on the relay server. "
            "Paste the Workspace Agent access token in Settings, or set it in .env "
            "and restart workspace-agent-relay-mcp."
        )
    return token


def resolve_agent_token(config: Any, store: Any, token_ref: str) -> str:
    if token_ref.startswith(LOCAL_TOKEN_REF_PREFIX):
        agent_id = _local_agent_id_from_token_ref(token_ref)
        token = store.get_agent_access_token(agent_id)
        if not token:
            raise ValueError(
                "This agent has no access token configured. "
                "Open Settings and paste the Workspace Agent access token."
            )
        return token
    return _agent_token_from_env(config, token_ref)


def agent_token(config: Any, token_ref: str) -> str:
    """Resolve env-backed token_refs only. Prefer resolve_agent_token in routes."""
    return _agent_token_from_env(config, token_ref)


def agent_token_configured(config: Any, store: Any, agent: dict[str, Any]) -> bool:
    try:
        resolve_agent_token(config, store, str(agent["token_ref"]))
    except ValueError:
        return False
    return True


def list_configured_token_refs(config: Any) -> list[dict[str, Any]]:
    """Return env-backed token_refs that have a non-empty value in the config snapshot.

    Legacy helper for deployments that still manage tokens via .env. Dashboard
    create-agent flows should prefer `access_token` (stored as local:<id>).
    """
    agent_tokens = getattr(config, "agent_tokens", {}) or {}
    refs: list[dict[str, Any]] = []
    for key in agent_tokens:
        if key != TOKEN_ENV_VAR_PREFIX and not key.startswith(TOKEN_ENV_VAR_PREFIX + "_"):
            continue
        if not str(agent_tokens.get(key, "") or "").strip():
            continue
        refs.append(
            {
                "token_ref": f"{TOKEN_REF_PREFIX}{key}",
                "env_var": key,
                "is_default": key == TOKEN_ENV_VAR_PREFIX,
            }
        )
    refs.sort(key=lambda item: (0 if item["is_default"] else 1, item["env_var"]))
    return refs


def missing_fields(payload: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [field for field in fields if payload.get(field) in (None, "")]
