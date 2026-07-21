from types import SimpleNamespace

import httpx
import pytest

from agent import agent
from agent.workflow_authorization import (
    TRIAGE_FRAUD_CASE,
    create_workflow_authorization,
)


class _ProposalResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "success": True,
            "proposal_id": "11111111-1111-4111-8111-111111111111",
            "action_type": TRIAGE_FRAUD_CASE,
            "contract_version": "fraud-triage.v1",
            "status": "PROPOSED",
            "confirmation_policy": "EXPLICIT_VERBAL",
            "customer_safe_summary": "Confirm the selected charge and replacement card.",
            "display_selection": {"fraud_alert_id": "fraud-123"},
            "expires_at": "2026-07-21T12:00:00+00:00",
        }


class _ProposalClient:
    last_request = None

    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def post(self, url, *, headers, json):
        type(self).last_request = (url, headers, json)
        return _ProposalResponse()


def _active_state() -> dict:
    return {
        "session_id": "session-1",
        "fraud_context": {
            "suspicious_transactions": [
                {"authorization_id": "auth-1", "merchant_name": "Cafe"}
            ]
        },
        "fraud_playbook": {
            "entry_mode": "FRAUD_ALERT",
            "open_alert_inspected": True,
            "fraud_alert_id": "fraud-123",
            "workflow_authorization": None,
        },
    }


def test_prepare_confirmation_creates_banking_proposal(monkeypatch) -> None:
    monkeypatch.setattr(agent.httpx, "Client", _ProposalClient)
    monkeypatch.setattr(
        agent, "get_auth_headers", lambda: {"Authorization": "Bearer test"}
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
        agent.record_customer_turn("I do not recognize it", event_id="customer-turn-10")
        context = SimpleNamespace(state=_active_state())

        result = agent.prepare_fraud_triage_confirmation(
            fraud_alert_id="fraud-123",
            disputed_authorization_ids=["auth-1"],
            disputed_transaction_ids=[],
            issue_replacement=True,
            tool_context=context,
        )

        authorization = context.state["fraud_playbook"]["workflow_authorization"]
        assert result["proposal_id"] == "11111111-1111-4111-8111-111111111111"
        assert result["customer_safe_summary"].startswith("Confirm")
        assert authorization["proposal_id"] == result["proposal_id"]
        _, headers, request = _ProposalClient.last_request
        assert headers["x-support-session-id"] == "support-1"
        assert headers["x-customer-turn-id"] == "customer-turn-10"
        assert headers["x-reset-generation"] == "3:9"
        assert headers["x-catalog-snapshot-id"] == "catalog-7"
        assert request["fraud_alert_id"] == "fraud-123"
    finally:
        agent.reset_session_context(tokens)


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
        assert headers["x-proposal-confirmation-classification"] == "CONFIRMED"
    finally:
        agent.reset_session_context(tokens)
