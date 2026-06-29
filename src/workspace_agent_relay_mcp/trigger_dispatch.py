from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable

from starlette.concurrency import run_in_threadpool

from .trigger import TriggerClient, redact_secret

logger = logging.getLogger("workspace_agent_relay_mcp.trigger")


class TriggerDispatcher:
    """App-owned background adapter for ChatGPT trigger dispatch.

    Trigger API calls are intentionally fire-and-record: routes return after the
    run is locally marked `sent`, then this adapter records the asynchronous
    HTTP result. On shutdown this prototype waits briefly for in-flight tasks;
    it does not persist or replay dispatch jobs across process death.
    """

    def __init__(self, store: Any, *, log: logging.Logger | None = None) -> None:
        self._store = store
        self._log = log or logger
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def active_count(self) -> int:
        return len(self._tasks)

    async def dispatch_trigger_result(
        self,
        *,
        trigger_client: Any,
        trigger_url: str,
        access_token: str,
        conversation_key: str,
        input_text: str,
        idempotency_key: str,
        request_id: str,
        action: str,
    ) -> None:
        try:
            trigger_result = await run_in_threadpool(
                trigger_client.trigger,
                trigger_url=trigger_url,
                access_token=access_token,
                conversation_key=conversation_key,
                input_text=input_text,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            # trigger() normally catches HTTPError/URLError/TimeoutError/OSError
            # itself and returns a TriggerResult. Reaching here means something
            # unexpected blew up (e.g. opener misconfiguration). Preserve the
            # real exception type+message but redact the access token.
            trigger_error = redact_secret(f"{type(exc).__name__}: {exc}", access_token)
            self._log.exception("%s trigger dispatch raised unexpectedly for request_id=%s", action, request_id)
            self._store.update_run_trigger_result(
                request_id=request_id,
                trigger_http_status=0,
                trigger_x_request_id=None,
                conversation_url=None,
                trigger_error=trigger_error,
            )
            return
        self._store.update_run_trigger_result(
            request_id=request_id,
            trigger_http_status=trigger_result.http_status,
            trigger_x_request_id=trigger_result.x_request_id,
            conversation_url=trigger_result.conversation_url,
            trigger_error=trigger_result.error,
        )

    def schedule(self, coro: Awaitable[None]) -> asyncio.Task[None]:
        task = asyncio.create_task(coro)
        self._tasks.add(task)

        def cleanup(completed: asyncio.Task[None]) -> None:
            self._tasks.discard(completed)
            try:
                completed.result()
            except asyncio.CancelledError:
                return
            except Exception:
                self._log.exception("trigger dispatch task crashed")

        task.add_done_callback(cleanup)
        return task

    async def drain(self, *, timeout: float = 2.0) -> None:
        if not self._tasks:
            return
        pending = set(self._tasks)
        done, still_pending = await asyncio.wait(pending, timeout=timeout)
        for task in done:
            try:
                task.result()
            except asyncio.CancelledError:
                pass
            except Exception:
                self._log.exception("trigger dispatch task crashed during shutdown drain")
        for task in still_pending:
            task.cancel()
        if still_pending:
            await asyncio.gather(*still_pending, return_exceptions=True)
