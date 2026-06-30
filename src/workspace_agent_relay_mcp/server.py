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
    "Trigger inputs use protocol: local-agent-shell/v1 and turn_mode: initial|continuation|steer|answer. "
    "Local context sections contain references only: selected_files are metadata pointers with content: not_included, "
    "and available_skills are SKILL.md frontmatter summaries shown only on a newly created conversation's first turn. "
    "Use selected file paths or skill paths with your local execution MCP when useful; this relay does not expose file contents. "
    "Relay workflow: on a newly created conversation's first turn, update_conversation_title once after reading the user task (≤15 characters) → record_plan → bind_relay_run on your local execution MCP → batch record_progress(step_updates) → "
    "record_result once when the turn truly ends (done/failed/blocked). Plan changes use record_plan or skipped steps, not record_result. "
    "Do not use record_progress as the final answer channel; when you have delivered the requested answer or work, put the final Markdown in record_result and close the turn. "
    "A queued/new request arrives with a fresh request_id and needs its own record_result. A mid-turn follow-up (steer) arrives as another trigger with the SAME request_id (keep using that request_id for all further callbacks); treat it as guidance on the CURRENT turn — update the plan, do not start a new turn. The operator's answer to your ask_user arrives the same way, labeled 'Operator answered:'. "
    "Do not call update_conversation_title on steer, continuation, or later queued requests in the same conversation. "
    "If the trigger includes working_directory, treat it as the default cwd for that request_id; verify it before filesystem/git operations, do not guess a different repository, and explain before leaving it. "
    "Use list_local_conversations/create_local_conversation/read_local_conversation for bounded relay-stored local conversation context; these tools are local-state only and do not dispatch Workspace Agent triggers. "
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
    name="update_conversation_title",
    title="Update Conversation Title",
    annotations=LOCAL_STATE_TOOL,
    description=(
        "Use this once in the first turn of a newly created conversation, after reading the user task, "
        "to replace the dashboard's timestamp fallback title. The title must be concise and no longer than 15 characters. "
        "This updates only the conversation attached to the given request_id and conversation_key, and returns the updated conversation.\n"
        "Example: title=\"修复登录错误\""
    ),
)
def update_conversation_title(
    request_id: Annotated[str, Field(description="The request_id from the trigger header.")],
    conversation_key: Annotated[str, Field(description="The conversation_key from the trigger header.")],
    title: Annotated[str, Field(description="Concise conversation title, 1-15 characters.", json_schema_extra={"minLength": 1, "maxLength": 15})],
) -> dict[str, Any]:
    return store.update_conversation_title(
        request_id=request_id,
        conversation_key=conversation_key,
        title=title,
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


@mcp.tool(
    name="list_local_conversations",
    title="List Local Conversations",
    annotations=READ_ONLY_TOOL,
    description=(
        "List relay-stored local conversations for context discovery. "
        "Returns public conversation fields plus a bounded latest-run summary. "
        "Does not return agent access tokens, dashboard auth tokens, or local files."
    ),
)
def list_local_conversations(
    workspace_id: Annotated[int | None, Field(description="Optional workspace id filter.")] = None,
    agent_id: Annotated[int | None, Field(description="Optional agent/backend id filter.")] = None,
    limit: Annotated[int, Field(description="Maximum conversations to return, clamped to 1-100.", json_schema_extra={"minimum": 1, "maximum": 100})] = 50,
    include_archived: Annotated[bool, Field(description="Whether to include archived conversations.")] = False,
) -> dict[str, Any]:
    try:
        conversations = store.list_local_conversations(
            workspace_id=workspace_id,
            agent_id=agent_id,
            limit=limit,
            include_archived=include_archived,
        )
    except (TypeError, ValueError) as exc:
        return {"success": False, "error": {"code": "invalid_request", "message": str(exc)}}
    return {"success": True, "conversations": conversations}


@mcp.tool(
    name="create_local_conversation",
    title="Create Local Conversation",
    annotations=LOCAL_STATE_TOOL,
    description=(
        "Create a relay-local conversation record without dispatching a Workspace Agent trigger. "
        "If conversation_key is omitted, the relay generates one. Defaults to the current agent/workspace settings."
    ),
)
def create_local_conversation(
    name: Annotated[str, Field(description="Conversation display name.")],
    conversation_key: Annotated[str | None, Field(description="Optional stable conversation_key.")] = None,
    agent_id: Annotated[int | None, Field(description="Optional agent/backend id. Defaults to current agent.")] = None,
    workspace_id: Annotated[int | None, Field(description="Optional workspace id. Defaults to current workspace when configured.")] = None,
) -> dict[str, Any]:
    try:
        resolved_workspace_id = workspace_id if workspace_id is not None else store.resolve_default_workspace_id()
        conversation = store.create_local_conversation(
            name=name,
            conversation_key=conversation_key,
            agent_id=agent_id,
            workspace_id=resolved_workspace_id,
        )
    except (KeyError, ValueError) as exc:
        return {"success": False, "error": {"code": "invalid_request", "message": str(exc)}}
    except Exception as exc:
        return {"success": False, "error": {"code": "create_failed", "message": str(exc)}}
    return {"success": True, "conversation": conversation}


@mcp.tool(
    name="read_local_conversation",
    title="Read Local Conversation",
    annotations=READ_ONLY_TOOL,
    description=(
        "Read bounded relay-stored conversation context by conversation_id or conversation_key. "
        "Returns public conversation fields, recent run summaries, plans, bounded event excerpts, and artifact metadata. "
        "Artifact content is omitted unless include_artifacts=true, and even then content is excerpted."
    ),
)
def read_local_conversation(
    conversation_id: Annotated[int | None, Field(description="Conversation id. Provide exactly one of conversation_id or conversation_key.")] = None,
    conversation_key: Annotated[str | None, Field(description="Conversation key. Provide exactly one of conversation_id or conversation_key.")] = None,
    run_limit: Annotated[int, Field(description="Recent runs to return, clamped to 1-20.", json_schema_extra={"minimum": 1, "maximum": 20})] = 5,
    event_limit_per_run: Annotated[int, Field(description="Events per run, clamped to 0-50.", json_schema_extra={"minimum": 0, "maximum": 50})] = 10,
    include_artifacts: Annotated[bool, Field(description="Include bounded artifact content excerpts. Metadata is always safe to return.")] = False,
) -> dict[str, Any]:
    try:
        return store.read_local_conversation(
            conversation_id=conversation_id,
            conversation_key=conversation_key,
            run_limit=run_limit,
            event_limit_per_run=event_limit_per_run,
            include_artifacts=include_artifacts,
        )
    except KeyError as exc:
        return {"success": False, "error": {"code": "not_found", "message": str(exc)}}
    except (TypeError, ValueError) as exc:
        return {"success": False, "error": {"code": "invalid_request", "message": str(exc)}}


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
