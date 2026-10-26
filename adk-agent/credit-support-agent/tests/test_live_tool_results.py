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

"""Agent-produced tool results and their telemetry classification."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent import agent
from agent.avatar_runtime import LIVE_AVATAR_VIDEO_FORMAT
from agent.instructions import (
    LIVE_TOOL_RETRY_POLICY,
    INSTRUCTION_TEXT,
    compose_session_instruction,
)
from agent.log_safety import (
    tool_response_is_domain_refusal,
    tool_response_is_expected_checkpoint,
    tool_response_succeeded,
)
from agent.terminal_outcome import TerminalOutcome, ToolFailureTracker


@pytest.fixture
def session(monkeypatch):
    async def generation_is_invalid(**kwargs):
        return False, "RESET_GENERATION_CHANGED"

    monkeypatch.setattr(agent, "validate_reset_generation", generation_is_invalid)
    monkeypatch.setattr(agent, "get_auth_headers", lambda: {})
    monkeypatch.setattr(agent, "notify_event", lambda event: None)
    tokens = agent.bind_session_context("customer-1", lambda event: event)
    yield
    agent.set_tool_processing(False)
    agent.reset_session_context(tokens)


def tool_context(**state) -> SimpleNamespace:
    return SimpleNamespace(state={"session_id": "session-1", **state})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "args", "state", "status"),
    [
        ("push_card_to_google_wallet", {}, {}, "LEGACY_DIRECT_ACTION_DISABLED"),
        ("end_consultation", {}, {}, "SESSION_CLOSE_CONFIRMATION_REQUIRED"),
        ("commit_action_proposal", {"proposal_id": "p-1"}, {}, "AUTHORIZATION_REQUIRED"),
        ("prepare_action_proposal", {"playbook_id": "x"}, {}, "PLAYBOOK_DECISION_REQUIRED"),
        (
            "commit_action_proposal",
            {"proposal_id": "p-1"},
            {"completed_proposals": {"p-1": "COMMITTED"}},
            "ALREADY_COMMITTED",
        ),
        (
            "decide_action_proposal",
            {"proposal_id": "p-1", "decision": "DECLINE"},
            {"completed_proposals": {"p-1": "DECLINE"}},
            "PROPOSAL_ALREADY_RESOLVED",
        ),
        ("unfreeze_card", {}, {}, "SESSION_INVALIDATED"),
    ],
)
async def test_callback_blocked_results_declare_retryable(
    session, tool_name, args, state, status
) -> None:
    result = await agent.before_tool_callback(
        SimpleNamespace(name=tool_name), args, tool_context(**state)
    )

    assert status in {result.get("status"), result.get("error")}
    assert isinstance(result["retryable"], bool)
    assert result["retryable"] is (status == "PLAYBOOK_DECISION_REQUIRED")


def test_local_tool_results_declare_retryable(session) -> None:
    results = [
        agent.end_consultation(),
        agent.transfer_to_human("customer request"),
        agent.prepare_customer_reported_fraud_confirmation(
            [], [], False, SimpleNamespace(state={})
        ),
        agent.set_conversation_language("es-MX", SimpleNamespace(state={})),
        agent.set_conversation_language("xx-XX", SimpleNamespace(state={})),
    ]

    assert all(result["retryable"] is False for result in results)


PRODUCT_LIMIT_REFUSAL = {
    "structuredContent": {
        "success": False,
        "error": "PRODUCT_LIMIT_OUT_OF_BOUNDS",
        "recovery_class": "CORRECT_REQUEST",
        "message": "The requested limit is outside the product range.",
    }
}


@pytest.mark.parametrize(
    ("response", "refusal"),
    [
        pytest.param(PRODUCT_LIMIT_REFUSAL, True, id="bank-policy-refusal"),
        pytest.param(
            {"success": False, "recovery_class": "REFRESH_SESSION"}, True, id="top-level"
        ),
        pytest.param(
            {"isError": True, "structuredContent": PRODUCT_LIMIT_REFUSAL["structuredContent"]},
            False,
            id="mcp-error",
        ),
        pytest.param({"error": "ConnectError"}, False, id="transport-error"),
        pytest.param(
            {"structuredContent": {"success": False, "error": "PLAYBOOK_REQUEST_FAILED"}},
            False,
            id="failure-without-recovery-class",
        ),
        pytest.param(
            {"structuredContent": {"success": False, "recovery_class": "RETRY_SAME_PROPOSAL"}},
            False,
            id="transient-retry",
        ),
        pytest.param({"structuredContent": {"success": True}}, False, id="success"),
    ],
)
def test_domain_refusal_classification(response, refusal) -> None:
    assert tool_response_is_domain_refusal(response) is refusal


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (PRODUCT_LIMIT_REFUSAL, TerminalOutcome.NORMAL_DISCONNECT),
        ({"isError": True, "error": "boom"}, TerminalOutcome.TOOL_FAILURE),
        (
            {"structuredContent": {"success": False, "recovery_class": "RETRY_SAME_PROPOSAL"}},
            TerminalOutcome.TOOL_FAILURE,
        ),
    ],
)
async def test_bank_refusal_does_not_end_session_as_tool_failure(
    monkeypatch, response, expected
) -> None:
    tracker = ToolFailureTracker()

    def on_event(event):
        if event.get("type") == agent.INTERNAL_TOOL_RUNTIME_STATUS:
            tracker.record(event["tool"], event["outcome"])

    tokens = agent.bind_session_context("customer-1", on_event)
    try:
        await agent.after_tool_callback(
            SimpleNamespace(name="prepare_action_proposal"),
            {"playbook_id": "credit-limit-increase"},
            tool_context(),
            response,
        )
    finally:
        agent.reset_session_context(tokens)

    assert tracker.terminal_outcome(TerminalOutcome.NORMAL_DISCONNECT) == expected


@pytest.mark.parametrize(
    "status", ["PLAYBOOK_DECISION_REQUIRED", "PROPOSAL_ALREADY_RESOLVED"]
)
def test_runtime_checkpoints_are_not_tool_failures(status) -> None:
    assert tool_response_is_expected_checkpoint({"success": False, "status": status})


def test_already_committed_is_a_successful_result() -> None:
    assert tool_response_succeeded(
        "commit_action_proposal", {"success": True, "status": "ALREADY_COMMITTED"}
    )


def test_session_instructions_carry_the_live_tool_retry_cap() -> None:
    assert LIVE_TOOL_RETRY_POLICY == (
        "When a tool returns no results, inform the user before calling the tool "
        "again. Never issue more than two consecutive function calls without "
        "speaking back to the user."
    )
    assert LIVE_TOOL_RETRY_POLICY in INSTRUCTION_TEXT
    assert LIVE_TOOL_RETRY_POLICY in compose_session_instruction(avatar_name="Nova")


def test_live_avatar_format_matches_gemini_3_8_portrait_stream() -> None:
    video = LIVE_AVATAR_VIDEO_FORMAT

    assert (video.width, video.height, video.fps) == (704, 1280, 24)
    assert video.frame_bytes == 704 * 1280 * 4
    args = video.decoder_args(audio_port=5555)
    assert args[args.index("-vf") + 1] == "scale=704:1280"
    assert args[-1] == "tcp://127.0.0.1:5555"
