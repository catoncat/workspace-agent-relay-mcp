import asyncio

from workspace_agent_relay_mcp.store.bus import RunEventBus


def test_run_event_bus_publishes_to_subscriber() -> None:
    async def _run() -> None:
        bus = RunEventBus()
        queue = bus.subscribe(42)
        bus.publish(42, {"run": {"id": 42, "status": "running"}})
        payload = await asyncio.wait_for(queue.get(), timeout=1)
        assert payload["run"]["id"] == 42
        bus.unsubscribe(42, queue)

    asyncio.run(_run())
