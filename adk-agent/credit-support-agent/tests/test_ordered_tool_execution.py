# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Ordered tool execution under Gemini 3.x Live asynchronous function calling.

These tests drive ADK 2.4's real Live function-call executor
(``handle_function_calls_live``), which runs every call of one ``tool_call``
message concurrently, through the production callbacks.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from google.adk.agents import LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig
from google.adk.events import Event
from google.adk.flows.llm_flows import functions
from google.adk.models.gemini_llm_connection import GeminiLlmConnection
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
from google.adk.tools.base_tool import BaseTool
from google.genai import types

from agent import agent
from agent.money_locale import stream_with_language_changes
from agent.proposal_evidence import create_pending_proposal, mark_proposal_presented

PROPOSAL_ID = "proposal-limit-1"


class FakeBanking:
    """In-memory banking double with single-use commit semantics."""

    def __init__(self, *, delay: float = 0.02) -> None:
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.timeline: list[tuple[str, str]] = []
        self.handler_executions = 0
        self.committed: set[str] = set()

    async def run(self, name: str, args: dict) -> dict:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.timeline.append(("start", name))
        try:
            await asyncio.sleep(self.delay)
            return self.result(name, args)
        finally:
            self.timeline.append(("end", name))
            self.active -= 1

    def result(self, name: str, args: dict) -> dict:
        if name == "record_playbook_decision":
            return {"structuredContent": {"success": True, "decision": args["decision"]}}
        if name == "prepare_action_proposal":
            return {
                "structuredContent": {
                    "success": True,
                    "proposal_id": PROPOSAL_ID,
                    "action_type": "CREDIT_LIMIT_INCREASE",
                    "contract_version": "limit.v1",
                }
            }
        if name == "commit_action_proposal":
            proposal_id = args["proposal_id"]
            replay = proposal_id in self.committed
            if not replay:
                self.committed.add(proposal_id)
                self.handler_executions += 1
            return {
                "structuredContent": {
                    "success": True,
                    "status": "COMMITTED",
                    "idempotent_replay": replay,
                    "proposal_id": proposal_id,
                    "action_type": "CREDIT_LIMIT_INCREASE",
                    "credit_limit": 6000,
                    "available_credit": 5000,
                }
            }
        raise AssertionError(f"unexpected banking tool {name}")

    def calls(self, name: str) -> int:
        return self.timeline.count(("start", name))


class FakeMcpTool(BaseTool):
    def __init__(self, name: str, banking: FakeBanking) -> None:
        super().__init__(name=name, description=name)
        self._banking = banking

    async def run_async(self, *, args, tool_context):
        return await self._banking.run(self.name, args)


@pytest.fixture
def live_session(monkeypatch):
    async def generation_is_valid(**kwargs):
        return True, None

    async def no_account_refresh():
        return {}

    monkeypatch.setattr(agent, "validate_reset_generation", generation_is_valid)
    monkeypatch.setattr(agent, "get_auth_headers", lambda: {})
    monkeypatch.setattr(agent, "fetch_updated_account_details", no_account_refresh)
    tokens = agent.bind_session_context(
        "customer-1", lambda event: event, support_session_id="session-1"
    )
    yield
    agent.set_tool_processing(False)
    agent.reset_session_context(tokens)


def presented_limit_proposal() -> dict:
    proposal = create_pending_proposal(
        proposal_id=PROPOSAL_ID,
        action_type="CREDIT_LIMIT_INCREASE",
        contract_version="limit.v1",
        originating_customer_turn_id="customer-origin",
    )
    return mark_proposal_presented(
        proposal,
        assistant_turn_id="assistant-presentation",
        observed_at_epoch_s=time.time(),
    )


async def invocation(tools: list[BaseTool], state: dict | None = None):
    service = InMemorySessionService()
    session = await service.create_session(
        app_name="test",
        user_id="customer-1",
        state={"session_id": "session-1", "reset_generation_token": "0:1", **(state or {})},
    )
    voice_agent = LlmAgent(
        name="voice_test",
        model="gemini-3.8-live",
        tools=tools,
        before_tool_callback=agent.before_tool_callback,
        after_tool_callback=agent.after_tool_callback,
        on_tool_error_callback=agent.on_tool_error_callback,
    )
    context = InvocationContext(
        session_service=service,
        invocation_id="invocation-1",
        agent=voice_agent,
        session=session,
        live_request_queue=LiveRequestQueue(),
        run_config=RunConfig(),
    )
    return context, {tool.name: tool for tool in tools}


async def run_tool_call_message(context, tools_dict, *calls: tuple[str, dict]) -> dict:
    """Execute one Live tool_call message; return responses keyed by call id."""
    event = Event(
        author="voice_test",
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        id=f"call-{index}-{name}", name=name, args=args
                    )
                )
                for index, (name, args) in enumerate(calls)
            ],
        ),
    )
    merged = await functions.handle_function_calls_live(context, event, tools_dict)
    return {
        part.function_response.id: part.function_response.response
        for part in merged.content.parts
        if part.function_response
    }


def decision_args() -> dict:
    return {
        "discovery_id": "discovery-1",
        "decision": "SELECT",
        "reason_code": "APPLICABLE",
        "playbook_id": "credit-limit-increase",
        "criterion_index": 0,
    }


def prepare_args(playbook_id: str = "credit-limit-increase") -> dict:
    return {"playbook_id": playbook_id, "revision": 1, "digest": "d", "inputs_json": "{}"}


@pytest.mark.asyncio
async def test_concurrent_decision_and_prepare_run_one_at_a_time_in_order(live_session):
    banking = FakeBanking()
    context, tools = await invocation(
        [FakeMcpTool("record_playbook_decision", banking), FakeMcpTool("prepare_action_proposal", banking)]
    )

    responses = await run_tool_call_message(
        context,
        tools,
        ("record_playbook_decision", decision_args()),
        ("prepare_action_proposal", prepare_args()),
    )

    assert banking.max_active == 1
    assert banking.timeline == [
        ("start", "record_playbook_decision"),
        ("end", "record_playbook_decision"),
        ("start", "prepare_action_proposal"),
        ("end", "prepare_action_proposal"),
    ]
    assert responses["call-1-prepare_action_proposal"]["structuredContent"]["success"] is True


@pytest.mark.asyncio
async def test_prepare_emitted_before_its_decision_is_rejected_retryable_without_banking_call(
    live_session,
):
    banking = FakeBanking()
    context, tools = await invocation(
        [FakeMcpTool("record_playbook_decision", banking), FakeMcpTool("prepare_action_proposal", banking)]
    )

    responses = await run_tool_call_message(
        context,
        tools,
        ("prepare_action_proposal", prepare_args()),
        ("record_playbook_decision", decision_args()),
    )

    refused = responses["call-0-prepare_action_proposal"]
    assert refused["status"] == "PLAYBOOK_DECISION_REQUIRED"
    assert refused["retryable"] is True
    assert "record_playbook_decision" in refused["message"]
    assert banking.calls("prepare_action_proposal") == 0

    retried = await run_tool_call_message(
        context, tools, ("prepare_action_proposal", prepare_args())
    )
    assert retried["call-0-prepare_action_proposal"]["structuredContent"]["success"] is True
    assert banking.calls("prepare_action_proposal") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prior_calls",
    [
        pytest.param([], id="no-decision"),
        pytest.param(
            [("record_playbook_decision", {**decision_args(), "playbook_id": "other-playbook"})],
            id="decision-for-other-playbook",
        ),
        pytest.param(
            [
                ("record_playbook_decision", decision_args()),
                ("discover_playbooks", {"customer_need": "new need"}),
            ],
            id="rediscovered-after-decision",
        ),
        pytest.param(
            [
                (
                    "record_playbook_decision",
                    {**decision_args(), "decision": "CLARIFY", "reason_code": "MISSING_INPUT"},
                )
            ],
            id="clarify-is-not-selection",
        ),
    ],
)
async def test_prepare_requires_current_select_for_the_same_playbook(live_session, prior_calls):
    banking = FakeBanking()

    class Discover(FakeMcpTool):
        async def run_async(self, *, args, tool_context):
            return {"structuredContent": {"success": True, "discovery_id": "discovery-2"}}

    context, tools = await invocation(
        [
            FakeMcpTool("record_playbook_decision", banking),
            FakeMcpTool("prepare_action_proposal", banking),
            Discover("discover_playbooks", banking),
        ]
    )
    for call in prior_calls:
        await run_tool_call_message(context, tools, call)

    responses = await run_tool_call_message(
        context, tools, ("prepare_action_proposal", prepare_args())
    )

    assert responses["call-0-prepare_action_proposal"]["status"] == "PLAYBOOK_DECISION_REQUIRED"
    assert banking.calls("prepare_action_proposal") == 0


@pytest.mark.asyncio
async def test_reissued_commit_after_cancelled_but_executed_commit_never_runs_twice(live_session):
    """Server cancels a pending BLOCKING commit; ADK 2.4 still executes it.

    The model, not having seen the result, re-issues the commit while the
    first is still running. The banking action must run once and the re-issued
    call must report the action as complete, not as "not run".
    """
    banking = FakeBanking(delay=0.05)
    context, tools = await invocation(
        [FakeMcpTool("commit_action_proposal", banking)],
        {"fraud_playbook": {"pending_proposal": presented_limit_proposal()}},
    )
    agent.record_customer_turn(
        "confirmation", event_id="customer-confirmation", observed_at_epoch_s=time.time() + 1
    )

    first, reissued = await asyncio.gather(
        run_tool_call_message(context, tools, ("commit_action_proposal", {"proposal_id": PROPOSAL_ID})),
        run_tool_call_message(context, tools, ("commit_action_proposal", {"proposal_id": PROPOSAL_ID})),
    )

    assert banking.calls("commit_action_proposal") == 1
    assert banking.handler_executions == 1
    assert first["call-0-commit_action_proposal"]["structuredContent"]["success"] is True
    duplicate = reissued["call-0-commit_action_proposal"]
    assert duplicate["status"] == "ALREADY_COMMITTED"
    assert duplicate["action_completed"] is True
    assert duplicate["retryable"] is False
    assert context.session.state[agent.COMPLETED_PROPOSALS_STATE_KEY] == {
        PROPOSAL_ID: agent.COMMITTED_RESOLUTION
    }


@pytest.mark.asyncio
async def test_uncommitted_proposal_never_short_circuits(live_session):
    banking = FakeBanking()
    context, tools = await invocation(
        [FakeMcpTool("commit_action_proposal", banking)],
        {
            "fraud_playbook": {"pending_proposal": presented_limit_proposal()},
            agent.COMPLETED_PROPOSALS_STATE_KEY: {"some-other-proposal": "COMMITTED"},
        },
    )

    # Same turn as presentation: evidence is missing, so the action must not run.
    responses = await run_tool_call_message(
        context, tools, ("commit_action_proposal", {"proposal_id": PROPOSAL_ID})
    )

    blocked = responses["call-0-commit_action_proposal"]
    assert blocked["status"] == "AUTHORIZATION_REQUIRED"
    assert blocked["action_completed"] is False
    assert banking.calls("commit_action_proposal") == 0
    assert PROPOSAL_ID not in context.session.state[agent.COMPLETED_PROPOSALS_STATE_KEY]


@pytest.mark.asyncio
async def test_ledgered_id_never_succeeds_while_a_different_proposal_is_pending(live_session):
    banking = FakeBanking()
    current = presented_limit_proposal()
    current["proposal_id"] = "proposal-limit-2"
    context, tools = await invocation(
        [FakeMcpTool("commit_action_proposal", banking)],
        {
            "fraud_playbook": {"pending_proposal": current},
            agent.COMPLETED_PROPOSALS_STATE_KEY: {PROPOSAL_ID: agent.COMMITTED_RESOLUTION},
        },
    )
    # A later customer turn exists, so the stale call must not attest P2.
    agent.record_customer_turn(
        "confirmation", event_id="customer-confirmation", observed_at_epoch_s=time.time() + 1
    )

    responses = await run_tool_call_message(
        context, tools, ("commit_action_proposal", {"proposal_id": PROPOSAL_ID})
    )

    refused = responses["call-0-commit_action_proposal"]
    assert refused["success"] is False
    assert refused["isError"] is False
    assert refused["retryable"] is False
    assert refused["action_completed"] is False
    assert "NOT been committed" in refused["message"]
    assert banking.calls("commit_action_proposal") == 0
    pending = context.session.state["fraud_playbook"]["pending_proposal"]
    assert pending == current


@pytest.mark.asyncio
async def test_invalid_reset_generation_wins_over_a_ledger_hit(live_session, monkeypatch):
    async def generation_is_invalid(**kwargs):
        return False, "RESET_GENERATION_CHANGED"

    monkeypatch.setattr(agent, "validate_reset_generation", generation_is_invalid)
    banking = FakeBanking()
    context, tools = await invocation(
        [FakeMcpTool("commit_action_proposal", banking)],
        {agent.COMPLETED_PROPOSALS_STATE_KEY: {PROPOSAL_ID: agent.COMMITTED_RESOLUTION}},
    )

    responses = await run_tool_call_message(
        context, tools, ("commit_action_proposal", {"proposal_id": PROPOSAL_ID})
    )

    result = responses["call-0-commit_action_proposal"]
    assert result["error"] == "SESSION_INVALIDATED"
    assert result["success"] is False
    assert banking.calls("commit_action_proposal") == 0


@pytest.mark.asyncio
async def test_short_circuited_duplicate_emits_no_success_telemetry_or_trace(
    live_session, monkeypatch
):
    banking = FakeBanking()
    context, tools = await invocation(
        [FakeMcpTool("commit_action_proposal", banking)],
        {"fraud_playbook": {"pending_proposal": presented_limit_proposal()}},
    )
    agent.record_customer_turn(
        "confirmation", event_id="customer-confirmation", observed_at_epoch_s=time.time() + 1
    )
    await run_tool_call_message(context, tools, ("commit_action_proposal", {"proposal_id": PROPOSAL_ID}))

    events: list[dict] = []
    tool_outcomes: list[str] = []
    proposal_events: list[dict] = []
    monkeypatch.setattr(
        agent, "record_tool_completed", lambda tool, outcome, seconds: tool_outcomes.append(outcome)
    )
    monkeypatch.setattr(
        agent, "record_action_proposal_event", lambda **kwargs: proposal_events.append(kwargs)
    )
    token = agent.session_event_callback_var.set(events.append)
    try:
        responses = await run_tool_call_message(
            context, tools, ("commit_action_proposal", {"proposal_id": PROPOSAL_ID})
        )
    finally:
        agent.session_event_callback_var.reset(token)

    assert responses["call-0-commit_action_proposal"]["status"] == "ALREADY_COMMITTED"
    assert tool_outcomes == ["checkpoint"]
    assert proposal_events == []
    assert not [
        event for event in events
        if event.get("type") == agent.DataChannelEvent.PROPOSAL_PROTOCOL_TRACE.value
    ]
    assert [
        event["outcome"] for event in events
        if event.get("type") == agent.INTERNAL_TOOL_RUNTIME_STATUS
    ] == ["checkpoint"]


@pytest.mark.asyncio
async def test_failed_commit_is_not_ledgered(live_session):
    class RefusingBanking(FakeBanking):
        def result(self, name, args):
            return {
                "structuredContent": {
                    "success": False,
                    "error": "PRODUCT_LIMIT_OUT_OF_BOUNDS",
                    "recovery_class": "CREATE_NEW_PROPOSAL",
                }
            }

    banking = RefusingBanking()
    context, tools = await invocation(
        [FakeMcpTool("commit_action_proposal", banking)],
        {"fraud_playbook": {"pending_proposal": presented_limit_proposal()}},
    )
    agent.record_customer_turn(
        "confirmation", event_id="customer-confirmation", observed_at_epoch_s=time.time() + 1
    )

    await run_tool_call_message(context, tools, ("commit_action_proposal", {"proposal_id": PROPOSAL_ID}))

    assert not context.session.state.get(agent.COMPLETED_PROPOSALS_STATE_KEY)


@pytest.mark.asyncio
async def test_blocked_ordered_call_releases_gate_before_its_task_ends(live_session):
    class Tool:
        name = "prepare_action_proposal"

    context = type("Ctx", (), {"state": {"session_id": "session-1"}})()
    blocked_returned = asyncio.Event()
    may_finish = asyncio.Event()
    blocked_result: dict = {}

    async def blocked_call():
        result = await agent.before_tool_callback(Tool(), prepare_args(), context)
        blocked_result.update(result or {})
        await agent.after_tool_callback(Tool(), prepare_args(), context, result)
        blocked_returned.set()
        await may_finish.wait()

    async def next_ordered_call():
        await agent.before_tool_callback(Tool(), prepare_args(), context)
        await agent.after_tool_callback(Tool(), prepare_args(), context, {})

    first = asyncio.create_task(blocked_call())
    try:
        await asyncio.wait_for(blocked_returned.wait(), timeout=1.0)
        await asyncio.wait_for(next_ordered_call(), timeout=1.0)
        assert not first.done()
        assert blocked_result["status"] == "PLAYBOOK_DECISION_REQUIRED"
    finally:
        may_finish.set()
        await first


@pytest.mark.asyncio
async def test_gate_is_released_after_tool_error(live_session):
    class Failing(FakeMcpTool):
        async def run_async(self, *, args, tool_context):
            raise RuntimeError("transport failure")

    banking = FakeBanking()
    context, tools = await invocation(
        [Failing("record_playbook_decision", banking), FakeMcpTool("prepare_action_proposal", banking)]
    )

    with pytest.raises(RuntimeError):
        await run_tool_call_message(context, tools, ("record_playbook_decision", decision_args()))

    assert not agent.ordered_tool_gate_var.get().locked()


@pytest.mark.asyncio
async def test_gate_is_released_when_a_running_call_is_cancelled(live_session):
    banking = FakeBanking(delay=10)
    context, tools = await invocation([FakeMcpTool("record_playbook_decision", banking)])

    task = asyncio.create_task(
        run_tool_call_message(context, tools, ("record_playbook_decision", decision_args()))
    )
    while banking.active == 0:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    assert not agent.ordered_tool_gate_var.get().locked()


@pytest.mark.asyncio
async def test_language_change_releases_gate_before_live_restart(live_session):
    language_tool = FunctionTool(agent.set_conversation_language)
    context, tools = await invocation([language_tool])
    event = Event(
        author="voice_test",
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        id="call-language", name=language_tool.name, args={"locale": "es-MX"}
                    )
                )
            ],
        ),
    )
    response_event = await functions.handle_function_calls_live(context, event, tools)
    restarted_with: list[str] = []

    async def stream():
        yield response_event

    async def restarted_stream():
        return
        yield

    streams = iter([stream(), restarted_stream()])

    async def restart(locale):
        class Tool:
            name = "record_playbook_decision"

        state_context = type("Ctx", (), {"state": {"session_id": "session-1"}})()
        await asyncio.wait_for(
            agent.before_tool_callback(Tool(), decision_args(), state_context), timeout=1.0
        )
        await agent.after_tool_callback(Tool(), decision_args(), state_context, {})
        restarted_with.append(locale)

    async for _ in stream_with_language_changes(
        stream_factory=streams.__next__,
        current_locale=lambda: "en-US",
        restart=restart,
    ):
        pass

    assert response_event.actions.state_delta["voice_locale"] == "es-MX"
    assert restarted_with == ["es-MX"]


class _FakeLiveSession:
    session_id = "live-session-1"

    def __init__(self, messages):
        self._messages = messages

    async def receive(self):
        for message in self._messages:
            yield message


@pytest.mark.asyncio
async def test_adk_2_4_ignores_server_tool_call_cancellation():
    """Pin the ADK behaviour the ledger guards against.

    ADK 2.4 drops ``tool_call_cancellation``: no event reaches the runner, so
    a BLOCKING call that already started keeps running and its result is
    still delivered. If ADK starts surfacing cancellations, revisit the
    committed-proposal ledger and this test.
    """
    connection = GeminiLlmConnection(
        _FakeLiveSession(
            [
                types.LiveServerMessage(
                    tool_call_cancellation=types.LiveServerToolCallCancellation(
                        ids=["call-0-commit_action_proposal"]
                    )
                )
            ]
        ),
        model_version="gemini-3.8-live",
    )

    responses = [response async for response in connection.receive()]

    assert responses == []
