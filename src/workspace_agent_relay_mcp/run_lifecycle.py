from __future__ import annotations

from typing import Literal

RunStatus = Literal[
    "draft",
    "sent",
    "pending",
    "running",
    "accepted",
    "waiting",
    "progress",
    "needs_user",
    "question",
    "ask_user",
    "trigger_failed",
    "done",
    "blocked",
    "failed",
    "superseded",
]

TriggerStatus = Literal["draft", "accepted", "failed"]
ResultStatus = Literal["done", "blocked", "failed"]

TERMINAL_STATUSES = frozenset({"done", "blocked", "failed", "superseded"})
# Active runs paused on a human decision (set by ask_user). Steering such a run
# is the operator's ANSWER — it resumes the SAME turn rather than starting a new
# one, so the route labels the steer trigger accordingly and steer_run
# transitions the run out of the question state.
USER_REPLY_STATUSES = frozenset({"needs_user", "question", "ask_user"})
# Agent-settable result statuses. `superseded` is system-only, so record_result
# must reject it. New dashboard sends no longer mark active runs as superseded;
# superseded is retained for historical rows and explicit replacement flows.
VALID_RESULT_STATUSES = frozenset({"done", "blocked", "failed"})
TRIGGER_MUTABLE_RUN_STATUSES = frozenset({"draft", "sent"})


def after_trigger_sent(current_status: str) -> str:
    return "sent" if current_status == "draft" else current_status


def after_trigger_result(current_status: str, *, trigger_status: TriggerStatus) -> str:
    if current_status not in TRIGGER_MUTABLE_RUN_STATUSES:
        return current_status
    if trigger_status == "accepted":
        return "accepted"
    return "trigger_failed"


def after_plan(current_status: str) -> str:
    if current_status == "trigger_failed":
        return "accepted"
    return current_status


def after_progress(current_status: str) -> str:
    if current_status in USER_REPLY_STATUSES:
        return current_status
    return "waiting"


def after_tool_trace(current_status: str) -> str:
    if current_status == "trigger_failed":
        return "waiting"
    return current_status


def after_user_question(_: str) -> str:
    return "needs_user"


def after_operator_steer(current_status: str) -> str:
    return "sent" if current_status in USER_REPLY_STATUSES else current_status
