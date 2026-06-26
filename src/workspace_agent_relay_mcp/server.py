from __future__ import annotations

import argparse
from typing import Any

from fastmcp import FastMCP
import uvicorn

from . import __version__
from .config import APP_NAME, RelayConfig, load_config
from .db import RelayStore
from .oauth import OAuthRuntimeConfig


config: RelayConfig = load_config()
store = RelayStore(config.database_path)


def _current_auth_token() -> str:
    return globals().get("config", config).auth_token


def _current_debug_mcp_logging() -> bool:
    return bool(globals().get("config", config).debug_mcp_logging)


def _current_oauth_config() -> OAuthRuntimeConfig:
    active = globals().get("config", config)
    return OAuthRuntimeConfig(
        auth_mode=active.auth_mode,
        auth_token=active.auth_token,
        public_base_url=active.public_base_url,
        state_dir=active.state_dir,
        oauth_login_token=active.oauth_login_token,
        oauth_scopes=active.oauth_scopes,
        oauth_token_ttl_seconds=active.oauth_token_ttl_seconds,
    )

READ_ONLY_TOOL = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

LOCAL_STATE_TOOL = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": False,
}

MCP_INSTRUCTIONS = (
    "This server is a narrow callback relay for Workspace Agent runs. "
    "Use record_progress for meaningful progress, ask_user when blocked on a human decision, "
    "and record_result before finishing. Do not expect shell, filesystem, or git tools here."
)

mcp = FastMCP(APP_NAME, instructions=MCP_INSTRUCTIONS)


async def _tool_names() -> list[str]:
    list_tools = getattr(mcp, "_list_tools")
    try:
        registered = await list_tools()
    except TypeError:
        registered = await list_tools(None)
    return sorted(tool.name for tool in registered)


@mcp.tool(
    name="server_info",
    title="Server Info",
    annotations=READ_ONLY_TOOL,
    description="Return relay server metadata, state path, auth mode, version, and registered tool names.",
)
async def server_info() -> dict[str, Any]:
    return {
        "success": True,
        "app_name": APP_NAME,
        "version": __version__,
        "state_dir": str(config.state_dir),
        "database_path": str(config.database_path),
        "auth": config.auth_mode or ("shared_token" if config.auth_token else "none"),
        "tools": await _tool_names(),
    }


@mcp.tool(
    name="record_progress",
    title="Record Progress",
    annotations=LOCAL_STATE_TOOL,
    description="Record a progress update for an open relay run. Requires request_id, conversation_key, and callback_token.",
)
def record_progress(
    request_id: str,
    callback_token: str,
    conversation_key: str,
    message: str,
    title: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return store.record_progress(
        request_id=request_id,
        conversation_key=conversation_key,
        callback_token=callback_token,
        message=message,
        title=title,
        payload=payload,
    )


@mcp.tool(
    name="record_result",
    title="Record Result",
    annotations=LOCAL_STATE_TOOL,
    description="Record the final Markdown result for an open relay run. This should be called before the agent finishes.",
)
def record_result(
    request_id: str,
    callback_token: str,
    conversation_key: str,
    status: str,
    title: str,
    markdown: str,
    artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return store.record_result(
        request_id=request_id,
        conversation_key=conversation_key,
        callback_token=callback_token,
        status=status,
        title=title,
        markdown=markdown,
        artifacts=artifacts,
    )


@mcp.tool(
    name="ask_user",
    title="Ask User",
    annotations=LOCAL_STATE_TOOL,
    description="Record a question that the local user must answer before the run can continue.",
)
def ask_user(
    request_id: str,
    callback_token: str,
    conversation_key: str,
    question: str,
    choices: list[str] | None = None,
    context: str | None = None,
) -> dict[str, Any]:
    return store.ask_user(
        request_id=request_id,
        conversation_key=conversation_key,
        callback_token=callback_token,
        question=question,
        choices=choices,
        context=context,
    )


@mcp.tool(
    name="get_run_context",
    title="Get Run Context",
    annotations=READ_ONLY_TOOL,
    description="Return recent run summaries for a conversation_key. Does not return secrets or callback tokens.",
)
def get_run_context(conversation_key: str, limit: int = 5) -> dict[str, Any]:
    return store.get_run_context(conversation_key, limit=limit)


def build_http_app():
    from .web import build_app

    streamable_app = mcp.http_app(path="/mcp", transport="streamable-http")
    legacy_sse_app = mcp.http_app(path="/mcp", transport="sse")
    return build_app(
        mcp=mcp,
        streamable_app=streamable_app,
        legacy_sse_app=legacy_sse_app,
        store=store,
        config=config,
        get_auth_token=_current_auth_token,
        get_oauth_config=_current_oauth_config,
        get_debug_enabled=_current_debug_mcp_logging,
        instructions=MCP_INSTRUCTIONS,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Workspace Agent Relay MCP server.")
    parser.parse_args(argv)
    config.ensure_runtime_directories()
    app = build_http_app()
    uvicorn.run(app, host=config.host, port=config.port)
