from __future__ import annotations

import argparse
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field
import uvicorn

from . import __version__
from .app import build_app
from .config import APP_NAME, RelayConfig, load_config
from .store import RelayStore, RunEventBus


config: RelayConfig = load_config()
event_bus = RunEventBus()
store = RelayStore(config.database_path, event_bus=event_bus)


def _current_auth_token() -> str:
    return globals().get("config", config).auth_token


def _current_debug_mcp_logging() -> bool:
    return bool(globals().get("config", config).debug_mcp_logging)


def _current_oauth_config() -> Any:
    from .oauth import OAuthRuntimeConfig

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
    "This server (workspace-agent-relay-mcp) is the local operator's only window into the current turn. "
    "They cannot see ChatGPT-side planning, reasoning, or chat replies — only what you write here "
    "(and local tool traces after bind_relay_run on your local-ops MCP).\n"
    "Relay workflow: record_plan first → bind_relay_run on your local execution MCP → batch record_progress(step_updates) → "
    "record_result once when the turn truly ends (done/failed/blocked). Plan changes use record_plan or skipped steps, not record_result. "
    "A mid-turn follow-up (steer) arrives as another trigger with the SAME request_id (keep using that request_id for all further callbacks); treat it as guidance on the CURRENT turn — update the plan, do not start a new turn. The operator's answer to your ask_user arrives the same way, labeled 'Operator answered:'. "
    "Keep record_plan user-visible: do not list relay binding, server_info, or routine tool setup as steps unless debugging that plumbing. "
    "ask_user pauses the turn; it is not completion — the operator's answer resumes the SAME turn (as a steer), so do not start a new turn when it arrives. blocked is for external hard blockers only.\n"
    "Every call returns the current plan snapshot. No shell/filesystem/git on this server — use your local-ops MCP for execution."
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
    description="Use this to orient yourself: returns the relay app name, version, state paths, auth mode, and the list of tool names available on this server. Read-only.",
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
    name="record_plan",
    title="Record Plan",
    annotations=LOCAL_STATE_TOOL,
    description=(
        "Use this at the START of a turn to share your step plan with the local operator. "
        "The operator cannot see your ChatGPT-side plan, so this is their only way to know what you are about to do. "
        "Each step needs a stable id (reuse the same ids in record_progress step_updates) and a short title. "
        "Use user-visible work steps; do not include relay binding, server_info, or routine tool setup unless that plumbing is the task. "
        "Call it again to REVISE your plan when the direction changes — a plan revision is NOT a finished turn, so do not call record_result for it; instead skip the old steps via record_progress or replace them here. "
        "Returns the current plan and run status.\n"
        "Example: steps=[{\"id\":\"s1\",\"title\":\"Confirm changed files\"}, {\"id\":\"s2\",\"title\":\"Fix Header sizing\"}, {\"id\":\"s3\",\"title\":\"Run build\"}]"
    ),
)
def record_plan(
    request_id: Annotated[str, Field(description="The request_id from the trigger header.")],
    conversation_key: Annotated[str, Field(description="The conversation_key from the trigger header.")],
    steps: Annotated[
        list[dict[str, Any]],
        Field(
            description=(
                "1-20 steps. Each step: {id, title, status?, note?}. "
                "id: stable string reused in step_updates. title: <=200 chars. "
                "status: pending|in_progress|done|skipped (defaults pending)."
            ),
            json_schema_extra={"minItems": 1, "maxItems": 20},
        ),
    ],
) -> dict[str, Any]:
    return store.record_plan(
        request_id=request_id,
        conversation_key=conversation_key,
        steps=steps,
    )


@mcp.tool(
    name="record_progress",
    title="Record Progress",
    annotations=LOCAL_STATE_TOOL,
    description=(
        "Use this after completing a chunk of work to batch-sync plan step statuses back to the operator. "
        "Pass step_updates to flip one or more step ids to a new status (done/in_progress/skipped) — use skipped to abandon a step when the direction changes, instead of ending the turn. "
        "Optionally include a one-line message summarizing what you just did. "
        "Do not call this once per tiny tool call — batch several completed steps into one call. "
        "Unknown step ids are ignored and listed in the returned ignored_step_ids. "
        "Returns the updated plan and run status.\n"
        "Example: step_updates=[{\"id\":\"s1\",\"status\":\"done\",\"note\":\"boundaries confirmed\"}, {\"id\":\"s2\",\"status\":\"in_progress\"}], message=\"Boundaries done, fixing Header\""
    ),
)
def record_progress(
    request_id: Annotated[str, Field(description="The request_id from the trigger header.")],
    conversation_key: Annotated[str, Field(description="The conversation_key from the trigger header.")],
    message: Annotated[str, Field(description="Optional one-line summary of what you just did. Keep it short; full detail goes in record_result.")],
    title: Annotated[str | None, Field(description="Optional short title for this progress beat.")] = None,
    payload: Annotated[dict[str, Any] | None, Field(description="Optional structured extras.")] = None,
    step_updates: Annotated[
        list[dict[str, Any]] | None,
        Field(
            description=(
                "Optional batch of step status changes. Each: {id, status?, note?}. "
                "status: pending|in_progress|done|skipped. Unknown ids are ignored."
            ),
        ),
    ] = None,
) -> dict[str, Any]:
    return store.record_progress(
        request_id=request_id,
        conversation_key=conversation_key,
        message=message,
        title=title,
        payload=payload,
        step_updates=step_updates,
    )


@mcp.tool(
    name="record_result",
    title="Record Result",
    annotations=LOCAL_STATE_TOOL,
    description=(
        "Use this EXACTLY ONCE when this turn is truly over. Records the final status, a title, and the full Markdown answer. "
        "This is what the operator reads as the result — do not only answer in the ChatGPT conversation. "
        "status: done when delivered, failed on an execution error, blocked ONLY for an external hard blocker (missing access/resource/dependency) — never use blocked to mean 'the plan changed' (revise the plan with record_plan / step_updates instead). "
        "Attach text artifacts if useful. "
        "Returns the final run status.\n"
        "Example: status=\"done\", title=\"UI fixes applied\", markdown=\"## Summary\\n...\", artifacts=[{\"name\":\"diff.md\",\"mime_type\":\"text/markdown\",\"content\":\"...\"}]"
    ),
)
def record_result(
    request_id: Annotated[str, Field(description="The request_id from the trigger header.")],
    conversation_key: Annotated[str, Field(description="The conversation_key from the trigger header.")],
    status: Annotated[str, Field(description="Final status: done | blocked | failed.", json_schema_extra={"enum": ["done", "blocked", "failed"]})],
    title: Annotated[str, Field(description="Short headline for the result, e.g. \"UI fixes applied\".")],
    markdown: Annotated[str, Field(description="Full Markdown answer the operator will read. This is the deliverable.")],
    artifacts: Annotated[
        list[dict[str, Any]] | None,
        Field(description="Optional text artifacts: each {name, mime_type, content, metadata?}."),
    ] = None,
) -> dict[str, Any]:
    return store.record_result(
        request_id=request_id,
        conversation_key=conversation_key,
        status=status,
        title=title,
        markdown=markdown,
        artifacts=artifacts,
    )


@mcp.tool(
    name="ask_user",
    title="Ask User",
    annotations=LOCAL_STATE_TOOL,
    description=(
        "Use this when you are genuinely blocked on a human decision and cannot make progress without an answer. "
        "Do NOT use this for status updates — use record_progress for those. "
        "The operator answers via a follow-up trigger, not inline, so phrase a single clear question. "
        "Returns a question id.\n"
        "Example: question=\"Which branch should I target?\", choices=[\"main\",\"dev\"], context=\"Need the target before editing.\""
    ),
)
def ask_user(
    request_id: Annotated[str, Field(description="The request_id from the trigger header.")],
    conversation_key: Annotated[str, Field(description="The conversation_key from the trigger header.")],
    question: Annotated[str, Field(description="One clear question the operator must answer.")],
    choices: Annotated[list[str] | None, Field(description="Optional list of answer options to pick from.")] = None,
    context: Annotated[str | None, Field(description="Optional short reason why this decision matters.")] = None,
) -> dict[str, Any]:
    return store.ask_user(
        request_id=request_id,
        conversation_key=conversation_key,
        question=question,
        choices=choices,
        context=context,
    )


@mcp.tool(
    name="get_run_context",
    title="Get Run Context",
    annotations=READ_ONLY_TOOL,
    description=(
        "Use this to re-orient when your ChatGPT conversation state is incomplete: returns recent run summaries, "
        "their progress/result event titles, and short markdown excerpts for a conversation_key. "
        "Capped to <=20 runs and short excerpts to keep your context lean."
    ),
)
def get_run_context(
    conversation_key: Annotated[str, Field(description="The conversation_key to look up recent runs for.")],
    limit: Annotated[int, Field(description="How many recent runs to return (1-20).", json_schema_extra={"minimum": 1, "maximum": 20})] = 5,
) -> dict[str, Any]:
    return store.get_run_context(conversation_key, limit=limit)


def build_http_app():
    streamable_app = mcp.http_app(path="/mcp", transport="streamable-http")
    legacy_sse_app = mcp.http_app(path="/mcp", transport="sse")
    return build_app(
        mcp=mcp,
        streamable_app=streamable_app,
        legacy_sse_app=legacy_sse_app,
        store=store,
        config=config,
        event_bus=event_bus,
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


if __name__ == "__main__":
    main()
