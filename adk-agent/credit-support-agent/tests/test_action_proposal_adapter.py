from types import SimpleNamespace

import httpx
import pytest

from agent import agent
from agent.workflow_authorization import (
    TRIAGE_FRAUD_CASE,
    create_workflow_authorization,
)


@pytest.mark.asyncio
async def test_commit_uses_only_proposal_id_and_protected_transport_evidence(
    monkeypatch,
) -> None:
    async def generation_is_valid(**kwargs):
        return True, None

    monkeypatch.setattr(agent, "validate_reset_generation", generation_is_valid)
    monkeypatch.setattr(agent, "get_auth_headers", lambda: {})
    payload = {
        "fraud_alert_id": "fraud-123",
        "disputed_authorization_ids": ["auth-1"],
        "disputed_transaction_ids": [],
        "issue_replacement": True,
        "escalate": False,
    }
    authorization = create_workflow_authorization(
        action=TRIAGE_FRAUD_CASE,
        payload=payload,
        session_id="session-1",
    )
    authorization.update(
        {
            "proposal_id": "11111111-1111-4111-8111-111111111111",
            "status": "CONFIRMED",
            "assistant_event_id": "assistant-turn-10",
            "customer_event_id": "customer-turn-11",
        }
    )
    context = SimpleNamespace(
        state={
            "session_id": "session-1",
            "reset_generation_token": "3:9",
            "fraud_context": {"fraud_alert_id": "fraud-123"},
            "fraud_playbook": {
                "entry_mode": "FRAUD_ALERT",
                "open_alert_inspected": True,
                "fraud_alert_id": "fraud-123",
                "workflow_authorization": authorization,
            },
        }
    )
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
        result = await agent.before_tool_callback(
            SimpleNamespace(name="commit_fraud_triage"),
            {"proposal_id": authorization["proposal_id"]},
            context,
        )
        assert result is None
        assert context.state["fraud_playbook"]["workflow_authorization"]["status"] == (
            "EXECUTING"
        )

        request = httpx.Request("POST", "https://banking.example/mcp/")
        async for authorized_request in agent.DynamicGoogleAuth().async_auth_flow(
            request
        ):
            headers = authorized_request.headers
        assert headers["x-proposal-presentation-turn-id"] == "assistant-turn-10"
        assert headers["x-proposal-confirmation-turn-id"] == "customer-turn-11"
        assert headers["x-customer-turn-id"] == "customer-turn-11"
        assert headers["x-proposal-confirmation-method"] == "EXPLICIT_VERBAL"
        assert headers["x-proposal-confirmation-source"] == "MODEL_TOOL_INTENT"
        assert "x-proposal-confirmation-classification" not in headers
    finally:
        agent.reset_session_context(tokens)


@pytest.mark.asyncio
async def test_direct_mcp_proposal_is_captured_as_adk_authorization(
    monkeypatch,
) -> None:
    async def account_details():
        return {}

    monkeypatch.setattr(agent, "fetch_updated_account_details", account_details)
    context = SimpleNamespace(
        state={
            "session_id": "session-1",
            "fraud_context": {"fraud_alert_id": "fraud-123"},
            "fraud_playbook": {
                "entry_mode": "FRAUD_ALERT",
                "open_alert_inspected": True,
                "fraud_alert_id": "fraud-123",
                "workflow_authorization": None,
            },
            "_voice_tool_started_at": {},
        }
    )
    payload = {
        "fraud_alert_id": "fraud-123",
        "disputed_authorization_ids": ["auth-1"],
        "disputed_transaction_ids": [],
        "issue_replacement": True,
        "escalate": False,
    }

    await agent.after_tool_callback(
        SimpleNamespace(name="propose_fraud_triage"),
        payload,
        context,
        {
            "structuredContent": {
                "success": True,
                "proposal_id": "11111111-1111-4111-8111-111111111111",
                "contract_version": "fraud-triage.v1",
                "customer_safe_summary": "Confirm the selected fraud actions.",
                "status": "PROPOSED",
            }
        },
    )

    authorization = context.state["fraud_playbook"]["workflow_authorization"]
    assert authorization["status"] == "PREPARED"
    assert authorization["proposal_id"] == "11111111-1111-4111-8111-111111111111"
    assert authorization["payload"] == payload


@pytest.mark.asyncio
async def test_commit_without_captured_proposal_fails_closed_instead_of_crashing(
    monkeypatch,
) -> None:
    async def generation_is_valid(**kwargs):
        return True, None

    monkeypatch.setattr(agent, "validate_reset_generation", generation_is_valid)
    monkeypatch.setattr(agent, "get_auth_headers", lambda: {})
    context = SimpleNamespace(
        state={
            "session_id": "session-1",
            "reset_generation_token": "3:9",
            "fraud_context": {"fraud_alert_id": "fraud-123"},
            "fraud_playbook": {
                "entry_mode": "FRAUD_ALERT",
                "open_alert_inspected": True,
                "workflow_authorization": None,
            },
        }
    )

    result = await agent.before_tool_callback(
        SimpleNamespace(name="commit_fraud_triage"),
        {"proposal_id": "11111111-1111-4111-8111-111111111111"},
        context,
    )

    assert result["status"] == "AUTHORIZATION_REQUIRED"
    assert result["authorization_blocked"] is True


@pytest.mark.asyncio
async def test_typed_non_commit_decision_uses_protected_transport_and_terminates_state(
    monkeypatch,
) -> None:
    async def account_details():
        return {}

    monkeypatch.setattr(agent, "fetch_updated_account_details", account_details)
    proposal_id = "11111111-1111-4111-8111-111111111111"
    payload = {
        "fraud_alert_id": "fraud-123",
        "disputed_authorization_ids": ["auth-1"],
        "disputed_transaction_ids": [],
        "issue_replacement": True,
        "escalate": False,
    }
    authorization = create_workflow_authorization(
        action=TRIAGE_FRAUD_CASE,
        payload=payload,
        session_id="session-1",
        originating_customer_event_id="customer-turn-10",
        now_epoch_s=1,
    )
    authorization.update(
        {
            "proposal_id": proposal_id,
            "contract_version": "fraud-triage.v1",
            "status": "PENDING",
            "assistant_event_id": "assistant-turn-10",
            "presented_at_epoch_s": 2,
            "expires_at_epoch_s": 1_000_000_000_000,
        }
    )
    context = SimpleNamespace(
        state={
            "session_id": "session-1",
            "fraud_context": {"fraud_alert_id": "fraud-123"},
            "fraud_playbook": {
                "entry_mode": "FRAUD_ALERT",
                "open_alert_inspected": True,
                "fraud_alert_id": "fraud-123",
                "workflow_authorization": authorization,
            },
            "_voice_tool_started_at": {},
        }
    )
    tokens = agent.bind_session_context(
        "customer-1",
        lambda event: event,
        support_session_id="support-1",
        runtime_session_id="session-1",
    )
    try:
        agent.configure_proposal_runtime_context(
            reset_generation="3:9",
            catalog_snapshot_id="catalog-7",
        )
        agent.record_customer_turn(
            "Text is transport evidence only.",
            event_id="customer-turn-11",
            observed_at_epoch_s=3,
        )
        result = await agent.before_tool_callback(
            SimpleNamespace(name="decide_action_proposal"),
            {"proposal_id": proposal_id, "decision": "REVISE"},
            context,
        )
        assert result is None
        current = context.state["fraud_playbook"]["workflow_authorization"]
        assert current["status"] == "CONFIRMED"

        request = httpx.Request("POST", "https://banking.example/mcp/")
        async for authorized_request in agent.DynamicGoogleAuth().async_auth_flow(
            request
        ):
            headers = authorized_request.headers
        assert headers["x-proposal-presentation-turn-id"] == "assistant-turn-10"
        assert headers["x-proposal-confirmation-turn-id"] == "customer-turn-11"

        await agent.after_tool_callback(
            SimpleNamespace(name="decide_action_proposal"),
            {"proposal_id": proposal_id, "decision": "REVISE"},
            context,
            {
                "structuredContent": {
                    "success": True,
                    "proposal_id": proposal_id,
                    "action_type": TRIAGE_FRAUD_CASE,
                    "contract_version": "fraud-triage.v1",
                    "status": "INVALIDATED",
                    "decision": "REVISE",
                    "invalidation_reason": "CUSTOMER_REVISED",
                }
            },
        )
        terminal = context.state["fraud_playbook"]["workflow_authorization"]
        assert terminal["status"] == "INVALIDATED"
        assert terminal["decision"] == "REVISE"
        assert terminal["invalidation_reason"] == "CUSTOMER_REVISED"
    finally:
        agent.reset_session_context(tokens)


@pytest.mark.asyncio
async def test_questions_preserve_pending_proposal_and_revision_is_explicit() -> None:
    authorization = create_workflow_authorization(
        action=TRIAGE_FRAUD_CASE,
        payload={
            "fraud_alert_id": "fraud-123",
            "disputed_authorization_ids": ["auth-1"],
            "disputed_transaction_ids": [],
            "issue_replacement": True,
            "escalate": False,
        },
        session_id="session-1",
        now_epoch_s=1,
    )
    authorization.update(
        {
            "proposal_id": "11111111-1111-4111-8111-111111111111",
            "status": "PENDING",
            "assistant_event_id": "assistant-turn-10",
            "presented_at_epoch_s": 2,
            "expires_at_epoch_s": 1_000_000_000_000,
        }
    )
    context = SimpleNamespace(
        state={
            "session_id": "session-1",
            "fraud_context": {"fraud_alert_id": "fraud-123"},
            "fraud_playbook": {
                "entry_mode": "FRAUD_ALERT",
                "open_alert_inspected": True,
                "fraud_alert_id": "fraud-123",
                "workflow_authorization": authorization,
            },
        }
    )

    assert (
        await agent.before_tool_callback(
            SimpleNamespace(name="get_transaction_history"),
            {},
            context,
        )
        is None
    )
    assert context.state["fraud_playbook"]["workflow_authorization"]["status"] == (
        "PENDING"
    )

    blocked = await agent.before_tool_callback(
        SimpleNamespace(name="propose_fraud_triage"),
        {},
        context,
    )
    assert blocked["status"] == "PROPOSAL_DECISION_REQUIRED"
    assert context.state["fraud_playbook"]["workflow_authorization"]["status"] == (
        "PENDING"
    )
    closeout = await agent.before_tool_callback(
        SimpleNamespace(name="offer_session_closeout"),
        {},
        context,
    )
    assert closeout["status"] == "PROPOSAL_DECISION_REQUIRED"
