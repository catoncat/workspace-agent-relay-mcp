from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


SUPPORTED_AGENT_TOKEN_REF = "env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN"
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


def validate_agent_token_ref(token_ref: str) -> None:
    if token_ref != SUPPORTED_AGENT_TOKEN_REF:
        raise ValueError(f"unsupported token_ref: {token_ref}")


def agent_token(config: Any, token_ref: str) -> str:
    validate_agent_token_ref(token_ref)
    token = str(config.default_agent_token)
    if not token:
        raise ValueError(
            "WORKSPACE_AGENT_RELAY_AGENT_TOKEN is not configured on the relay server. "
            "Set the ChatGPT Workspace Agent access token in .env and restart "
            "workspace-agent-relay-mcp. This is not the dashboard API token "
            "(WORKSPACE_AGENT_RELAY_AUTH_TOKEN)."
        )
    return token


def missing_fields(payload: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [field for field in fields if payload.get(field) in (None, "")]
