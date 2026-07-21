import inspect
from unittest.mock import MagicMock

import pytest

from routers.mcp.credit_card import commit_fraud_triage, propose_fraud_triage
from routers.mcp import utils as mcp_utils
from services.action_proposal_context import (
    ProposalRuntimeContext,
    RuntimeContextError,
)


def _headers(**overrides) -> dict[str, str]:
    headers = {
        "x-support-session-id": "support-1",
        "x-runtime-name": "ADK_GEMINI_LIVE",
        "x-runtime-session-id": "runtime-1",
        "x-customer-turn-id": "customer-turn-10",
        "x-reset-generation": "3:9",
    }
    headers.update(overrides)
    return headers


def test_model_visible_commit_has_only_opaque_proposal_input() -> None:
    commit_parameters = set(inspect.signature(commit_fraud_triage).parameters)
    propose_parameters = set(inspect.signature(propose_fraud_triage).parameters)

    assert commit_parameters == {"proposal_id", "ctx"}
    forbidden_scope = {
        "customer_id",
        "support_session_id",
        "runtime_name",
        "runtime_session_id",
        "reset_generation",
        "customer_turn_id",
    }
    assert propose_parameters.isdisjoint(forbidden_scope)
    assert commit_parameters.isdisjoint(forbidden_scope)


def test_runtime_context_requires_real_customer_turn() -> None:
    with pytest.raises(RuntimeContextError, match="real customer turn"):
        ProposalRuntimeContext.from_headers(
            _headers(**{"x-customer-turn-id": "unknown-turn"})
        ).require_customer_turn()


def test_confirmation_evidence_is_transport_owned_and_explicit() -> None:
    context = ProposalRuntimeContext.from_headers(
        _headers(
            **{
                "x-customer-turn-id": "customer-turn-11",
                "x-proposal-presentation-turn-id": "assistant-turn-10",
                "x-proposal-confirmation-turn-id": "customer-turn-11",
                "x-proposal-confirmation-method": "EXPLICIT_VERBAL",
                "x-proposal-confirmation-classification": "CONFIRMED",
            }
        )
    )

    context.require_confirmation()
    assert context.presentation_turn_id == "assistant-turn-10"
    assert context.confirmation_turn_id == "customer-turn-11"


@pytest.mark.asyncio
async def test_typed_mcp_projection_injects_identity_and_runtime_context(monkeypatch) -> None:
    runtime_context = ProposalRuntimeContext.from_headers(
        _headers(**{"x-catalog-snapshot-id": "catalog-7"})
    )
    db = MagicMock()
    service = MagicMock()
    service.propose_fraud_triage_for_identity.return_value = {
        "success": True,
        "proposal_id": "11111111-1111-4111-8111-111111111111",
    }
    monkeypatch.setattr("routers.mcp.credit_card.SessionLocal", lambda: db)
    monkeypatch.setattr("routers.mcp.credit_card.ActionProposalService", lambda _: service)
    customer_token = mcp_utils.verified_customer_id_var.set("customer-auth-1")
    runtime_token = mcp_utils.proposal_runtime_context_var.set(runtime_context)
    try:
        result = await propose_fraud_triage.__wrapped__(
            fraud_alert_id="22222222-2222-4222-8222-222222222222",
            disputed_authorization_ids=["auth-1"],
            disputed_transaction_ids=[],
            issue_replacement=True,
            escalate=False,
        )
    finally:
        mcp_utils.proposal_runtime_context_var.reset(runtime_token)
        mcp_utils.verified_customer_id_var.reset(customer_token)

    assert result["success"] is True
    call = service.propose_fraud_triage_for_identity.call_args.kwargs
    assert call["customer_identity"] == "customer-auth-1"
    assert call["runtime_context"] is runtime_context
    assert "customer_id" not in call
    assert "support_session_id" not in call
    db.close.assert_called_once()


@pytest.mark.asyncio
async def test_commit_projection_returns_authoritative_result_when_ui_event_fails(
    monkeypatch,
) -> None:
    runtime_context = ProposalRuntimeContext.from_headers(
        _headers(
            **{
                "x-customer-turn-id": "customer-turn-11",
                "x-proposal-presentation-turn-id": "assistant-turn-10",
                "x-proposal-confirmation-turn-id": "customer-turn-11",
                "x-proposal-confirmation-method": "EXPLICIT_VERBAL",
                "x-proposal-confirmation-classification": "CONFIRMED",
            }
        )
    )
    db = MagicMock()
    service = MagicMock()
    service.commit_fraud_triage_for_identity.return_value = {
        "success": True,
        "status": "COMMITTED",
        "outcome": "CUSTOMER_RECOGNIZED",
    }

    async def event_failure(*args, **kwargs):
        raise RuntimeError("websocket unavailable")

    monkeypatch.setattr("routers.mcp.credit_card.SessionLocal", lambda: db)
    monkeypatch.setattr("routers.mcp.credit_card.ActionProposalService", lambda _: service)
    monkeypatch.setattr("routers.mcp.credit_card.send_session_event", event_failure)
    customer_token = mcp_utils.verified_customer_id_var.set("customer-auth-1")
    runtime_token = mcp_utils.proposal_runtime_context_var.set(runtime_context)
    try:
        result = await commit_fraud_triage.__wrapped__(
            proposal_id="11111111-1111-4111-8111-111111111111"
        )
    finally:
        mcp_utils.proposal_runtime_context_var.reset(runtime_token)
        mcp_utils.verified_customer_id_var.reset(customer_token)

    assert result["status"] == "COMMITTED"
    assert result["outcome"] == "CUSTOMER_RECOGNIZED"
    db.rollback.assert_not_called()
