from __future__ import annotations

import asyncio
import threading
from typing import Any


class RunEventBus:
    """In-process pub/sub for run detail updates (SSE subscribers)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._queues: dict[int, list[asyncio.Queue[dict[str, Any]]]] = {}

    def subscribe(self, run_id: int) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        with self._lock:
            self._queues.setdefault(run_id, []).append(queue)
        return queue

    def unsubscribe(self, run_id: int, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            subscribers = self._queues.get(run_id, [])
            if queue in subscribers:
                subscribers.remove(queue)
            if not subscribers:
                self._queues.pop(run_id, None)

    def publish(self, run_id: int, payload: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._queues.get(run_id, []))
        for queue in subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass
