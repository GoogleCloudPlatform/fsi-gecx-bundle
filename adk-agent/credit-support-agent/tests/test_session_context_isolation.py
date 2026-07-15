import asyncio
import httpx
import pytest

from agent import agent


async def observe_context(customer_id: str):
    def callback(event):
        return event

    tokens = agent.bind_session_context(customer_id, callback)
    try:
        await asyncio.sleep(0)
        request = httpx.Request("GET", "https://banking.example/mcp/")
        async for authorized in agent.DynamicGoogleAuth().async_auth_flow(request):
            customer_header = authorized.headers["x-target-customer-id"]
        return (
            agent.active_customer_id_var.get(),
            agent.session_event_callback_var.get(),
            customer_header,
        )
    finally:
        agent.reset_session_context(tokens)


def test_parallel_session_context_and_mcp_auth_isolation(monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "true")

    async def run():
        return await asyncio.gather(
            observe_context("customer-a"),
            observe_context("customer-b"),
        )

    first, second = asyncio.run(run())

    assert first[0] == "customer-a"
    assert second[0] == "customer-b"
    assert first[1] is not second[1]
    assert first[2] == "customer-a"
    assert second[2] == "customer-b"


@pytest.mark.asyncio
async def test_child_tool_task_signals_are_visible_to_parent_voice_loop() -> None:
    tokens = agent.bind_session_context("customer-a", lambda event: event)
    try:
        async def tool_callback_task() -> None:
            agent.set_tool_processing(True)
            agent.request_session_end()

        await asyncio.create_task(tool_callback_task())

        assert agent.is_tool_processing() is True
        assert agent.is_session_end_requested() is True

        agent.set_tool_processing(False)
        agent.clear_session_end_request()
        assert agent.is_tool_processing() is False
        assert agent.is_session_end_requested() is False
    finally:
        agent.reset_session_context(tokens)
