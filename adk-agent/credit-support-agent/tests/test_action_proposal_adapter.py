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

from types import SimpleNamespace

import httpx
import pytest

from agent import agent
from agent.proposal_evidence import (
    AWAITING_DECISION,
    COMMIT_IN_FLIGHT,
    DECISION_ATTESTED,
    create_pending_proposal,
)
from agent.workflow_authorization import TRIAGE_FRAUD_CASE


PROPOSAL_ID = "11111111-1111-4111-8111-111111111111"


def proposal_projection(*, evidence_state: str) -> dict:
    projection = create_pending_proposal(
        proposal_id=PROPOSAL_ID,
        action_type=TRIAGE_FRAUD_CASE,
        contract_version="fraud-triage.v1",
        originating_customer_turn_id="customer-turn-10",
    )
    projection.update(
        {
            "evidence_state": evidence_state,
            "presentation_turn_id": "assistant-turn-10",
            "presentation_observed_at_epoch_s": 2,
            "confirmation_turn_id": (
                "customer-turn-11" if evidence_state != AWAITING_DECISION else None
            ),
        }
    )
    return projection


def tool_context(projection: dict | None) -> SimpleNamespace:
    return SimpleNamespace(
        state={
            "customer_id": "customer-1",
            "session_id": "session-1",
            "reset_generation_token": "3:9",
            "fraud_context": {"fraud_alert_id": "fraud-123"},
            "fraud_playbook": {
                "entry_mode": "FRAUD_ALERT",
                "open_alert_inspected": True,
                "fraud_alert_id": "fraud-123",
                "pending_proposal": projection,
            },
            "_voice_tool_started_at": {},
        }
    )


def allow_reset(monkeypatch) -> None:
    async def generation_is_valid(**kwargs):
        return True, None

    monkeypatch.setattr(agent, "validate_reset_generation", generation_is_valid)
    monkeypatch.setattr(agent, "get_auth_headers", lambda: {})


def test_proposal_trace_event_is_correlation_safe() -> None:
    events = []
    proposal_id = "11111111-1111-4111-8111-111111111111"
    tokens = agent.bind_session_context("customer-1", events.append)
    try:
        agent.notify_proposal_trace({"proposal_id": proposal_id}, "PRESENTED")
    finally:
        agent.reset_session_context(tokens)

    assert events[0]["type"] == "PROPOSAL_PROTOCOL_TRACE"
    assert events[0]["status"] == "PRESENTED"
    assert events[0]["proposal_ref"].startswith("proposal:")
    assert proposal_id not in str(events[0])


@pytest.mark.asyncio
async def test_commit_uses_only_proposal_id_and_protected_transport_evidence(
    monkeypatch,
) -> None:
    allow_reset(monkeypatch)
    context = tool_context(proposal_projection(evidence_state=DECISION_ATTESTED))
    tokens = agent.bind_session_context(
        "customer-1",
        lambda event: event,
        support_session_id="support-1",
        runtime_session_id="session-1",
    )
    try:
        agent.configure_proposal_runtime_context(
            reset_generation="3:9", catalog_snapshot_id="catalog-7"
        )
        assert (
            await agent.before_tool_callback(
                SimpleNamespace(name="commit_fraud_triage"),
                {"proposal_id": PROPOSAL_ID},
                context,
            )
            is None
        )
        projection = context.state["fraud_playbook"]["pending_proposal"]
        assert projection["evidence_state"] == COMMIT_IN_FLIGHT
        assert "payload" not in projection
        assert "payload_fingerprint" not in projection
        assert "expires_at_epoch_s" not in projection
        assert "session_id" not in projection

        headers = agent.proposal_request_header_provider(
            SimpleNamespace(state=context.state)
        )
        assert headers["x-proposal-presentation-turn-id"] == "assistant-turn-10"
        assert headers["x-proposal-confirmation-turn-id"] == "customer-turn-11"
        assert headers["x-customer-turn-id"] == "customer-turn-11"
        assert headers["x-proposal-confirmation-method"] == "EXPLICIT_VERBAL"
        assert headers["x-proposal-confirmation-source"] == "MODEL_TOOL_INTENT"

        request = httpx.Request("POST", "https://banking.example/mcp/")
        async for authorized_request in agent.DynamicGoogleAuth().async_auth_flow(
            request
        ):
            auth_headers = authorized_request.headers
        assert auth_headers["authorization"]
        assert "x-proposal-confirmation-turn-id" not in auth_headers
    finally:
        agent.reset_session_context(tokens)


@pytest.mark.asyncio
async def test_successful_proposal_captures_only_minimal_projection(
    monkeypatch,
) -> None:
    async def account_details():
        return {}

    monkeypatch.setattr(agent, "fetch_updated_account_details", account_details)
    context = tool_context(None)
    proposal_args = {
        "fraud_alert_id": "fraud-123",
        "disputed_authorization_ids": ["auth-1"],
        "issue_replacement": True,
    }
    await agent.after_tool_callback(
        SimpleNamespace(name="propose_fraud_triage"),
        proposal_args,
        context,
        {
            "structuredContent": {
                "success": True,
                "proposal_id": PROPOSAL_ID,
                "contract_version": "fraud-triage.v1",
                "customer_safe_summary": "Confirm the selected fraud actions.",
                "status": "PROPOSED",
            }
        },
    )

    projection = context.state["fraud_playbook"]["pending_proposal"]
    assert projection["proposal_id"] == PROPOSAL_ID
    assert projection["action_type"] == TRIAGE_FRAUD_CASE
    for duplicated_field in (
        "payload",
        "payload_fingerprint",
        "expires_at_epoch_s",
        "session_id",
        "customer_safe_summary",
        "status",
    ):
        assert duplicated_field not in projection


@pytest.mark.asyncio
async def test_commit_without_captured_proposal_fails_closed(monkeypatch) -> None:
    allow_reset(monkeypatch)
    result = await agent.before_tool_callback(
        SimpleNamespace(name="commit_fraud_triage"),
        {"proposal_id": PROPOSAL_ID},
        tool_context(None),
    )
    assert result["status"] == "AUTHORIZATION_REQUIRED"
    assert result["authorization_blocked"] is True


@pytest.mark.asyncio
async def test_new_commit_attestation_emits_confirmed_observability(
    monkeypatch,
) -> None:
    allow_reset(monkeypatch)
    recorded = []
    monkeypatch.setattr(
        agent,
        "record_action_proposal_event",
        lambda **event: recorded.append(event),
    )
    context = tool_context(proposal_projection(evidence_state=AWAITING_DECISION))
    tokens = agent.bind_session_context(
        "customer-1",
        lambda event: event,
        support_session_id="support-1",
        runtime_session_id="session-1",
    )
    try:
        agent.record_customer_turn(
            "Transport evidence only.",
            event_id="customer-turn-11",
            observed_at_epoch_s=3,
        )

        assert (
            await agent.before_tool_callback(
                SimpleNamespace(name="commit_fraud_triage"),
                {"proposal_id": PROPOSAL_ID},
                context,
            )
            is None
        )

        assert [event["outcome"] for event in recorded] == ["CONFIRMED"]
        assert recorded[0]["proposal_id"] == PROPOSAL_ID
        assert recorded[0]["tool"] == "commit_fraud_triage"
    finally:
        agent.reset_session_context(tokens)


def test_wallet_commit_normalizes_provisioning_status_as_banking_outcome(
    monkeypatch,
) -> None:
    recorded = []
    monkeypatch.setattr(
        agent,
        "record_action_proposal_event",
        lambda **event: recorded.append(event),
    )
    state = tool_context(proposal_projection(evidence_state=COMMIT_IN_FLIGHT)).state

    agent._record_commit_proposal_event(
        state=state,
        tool_name="commit_wallet_provisioning",
        args={"proposal_id": PROPOSAL_ID},
        result={
            "status": "COMMITTED",
            "wallet_provisioning_status": "QUEUED",
        },
        outcome="COMMITTED",
        latency_ms=12.5,
    )

    assert recorded[0]["outcome"] == "COMMITTED"
    assert recorded[0]["banking_outcome"] == "QUEUED"


@pytest.mark.asyncio
async def test_failed_commit_retries_once_with_same_request_evidence(
    monkeypatch,
) -> None:
    allow_reset(monkeypatch)
    context = tool_context(proposal_projection(evidence_state=COMMIT_IN_FLIGHT))
    failed_response = {
        "structuredContent": {
            "success": False,
            "error": "COMMIT_RESULT_PENDING",
            "recovery_class": "RETRY_SAME_PROPOSAL",
        }
    }
    tokens = agent.bind_session_context(
        "customer-1",
        lambda event: event,
        support_session_id="session-1",
        runtime_session_id="session-1",
    )
    try:
        first_failure = await agent.after_tool_callback(
            SimpleNamespace(name="commit_fraud_triage"),
            {"proposal_id": PROPOSAL_ID},
            context,
            failed_response,
        )
        recovery = context.state["fraud_playbook"]["pending_proposal"]
        assert recovery["evidence_state"] == "COMMIT_RETRY"
        assert first_failure["structuredContent"]["retry_allowed"] is True

        assert (
            await agent.before_tool_callback(
                SimpleNamespace(name="commit_fraud_triage"),
                {"proposal_id": PROPOSAL_ID},
                context,
            )
            is None
        )
        retry = context.state["fraud_playbook"]["pending_proposal"]
        assert retry["evidence_state"] == COMMIT_IN_FLIGHT
        assert retry["recovery_attempt_count"] == 1
        headers = agent.proposal_request_header_provider(
            SimpleNamespace(state=context.state)
        )
        assert headers["x-proposal-confirmation-turn-id"] == "customer-turn-11"

        second_failure = await agent.after_tool_callback(
            SimpleNamespace(name="commit_fraud_triage"),
            {"proposal_id": PROPOSAL_ID},
            context,
            failed_response,
        )
        assert second_failure["structuredContent"]["retry_allowed"] is False
    finally:
        agent.reset_session_context(tokens)


@pytest.mark.asyncio
async def test_non_commit_decision_attests_later_turn_and_clears_projection(
    monkeypatch,
) -> None:
    async def account_details():
        return {}

    monkeypatch.setattr(agent, "fetch_updated_account_details", account_details)
    context = tool_context(proposal_projection(evidence_state=AWAITING_DECISION))
    tokens = agent.bind_session_context(
        "customer-1",
        lambda event: event,
        support_session_id="support-1",
        runtime_session_id="session-1",
    )
    try:
        agent.record_customer_turn(
            "Transport evidence only.",
            event_id="customer-turn-11",
            observed_at_epoch_s=3,
        )
        assert (
            await agent.before_tool_callback(
                SimpleNamespace(name="decide_action_proposal"),
                {"proposal_id": PROPOSAL_ID, "decision": "REVISE"},
                context,
            )
            is None
        )
        assert (
            context.state["fraud_playbook"]["pending_proposal"]["evidence_state"]
            == DECISION_ATTESTED
        )

        await agent.after_tool_callback(
            SimpleNamespace(name="decide_action_proposal"),
            {"proposal_id": PROPOSAL_ID, "decision": "REVISE"},
            context,
            {
                "structuredContent": {
                    "success": True,
                    "proposal_id": PROPOSAL_ID,
                    "action_type": TRIAGE_FRAUD_CASE,
                    "status": "INVALIDATED",
                }
            },
        )
        assert context.state["fraud_playbook"]["pending_proposal"] is None
    finally:
        agent.reset_session_context(tokens)


@pytest.mark.asyncio
async def test_runtime_does_not_duplicate_banking_conflict_checks() -> None:
    context = tool_context(proposal_projection(evidence_state=AWAITING_DECISION))
    assert (
        await agent.before_tool_callback(
            SimpleNamespace(name="propose_fraud_triage"), {}, context
        )
        is None
    )
    assert (
        await agent.before_tool_callback(
            SimpleNamespace(name="review_fraud_selection"), {}, context
        )
        is None
    )
    assert context.state["fraud_playbook"]["pending_proposal"] is not None


@pytest.mark.asyncio
async def test_unrelated_tool_failure_cannot_change_in_flight_proposal(
    monkeypatch,
) -> None:
    async def account_details():
        return {}

    monkeypatch.setattr(agent, "fetch_updated_account_details", account_details)
    context = tool_context(proposal_projection(evidence_state=COMMIT_IN_FLIGHT))
    await agent.after_tool_callback(
        SimpleNamespace(name="get_transaction_history"),
        {},
        context,
        {"isError": True, "content": [{"type": "text", "text": "Read failed."}]},
    )
    assert (
        context.state["fraud_playbook"]["pending_proposal"]["evidence_state"]
        == COMMIT_IN_FLIGHT
    )
