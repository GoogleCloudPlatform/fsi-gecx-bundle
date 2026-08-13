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

import inspect
from typing import get_args
from unittest.mock import MagicMock

import pytest

from models.authentication import ValidatedToken
from routers.mcp.credit_card import (
    _safe_protocol_failure,
    commit_card_reissue,
    commit_fraud_triage,
    commit_wallet_provisioning,
    decide_action_proposal,
    propose_fraud_triage,
    review_fraud_selection,
)
from routers.mcp import utils as mcp_utils
from services.action_proposal_context import (
    ProposalRuntimeContext,
    RuntimeContextError,
)
from services.action_proposals import (
    ActiveProposalExistsError,
    ProposalTransitionError,
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
    commit_signatures = (
        inspect.signature(commit_fraud_triage),
        inspect.signature(commit_card_reissue),
        inspect.signature(commit_wallet_provisioning),
    )
    commit_parameters = set(commit_signatures[0].parameters)
    decision_parameters = set(inspect.signature(decide_action_proposal).parameters)
    propose_parameters = set(inspect.signature(propose_fraud_triage).parameters)
    review_parameters = set(inspect.signature(review_fraud_selection).parameters)

    assert commit_parameters == {"proposal_id", "ctx"}
    assert decision_parameters == {"proposal_id", "decision", "ctx"}
    assert set(
        get_args(
            inspect.signature(decide_action_proposal).parameters["decision"].annotation
        )
    ) == {"DECLINE", "REVISE", "CANCEL"}
    assert all(
        set(signature.parameters) == {"proposal_id", "ctx"}
        for signature in commit_signatures
    )
    forbidden_scope = {
        "customer_id",
        "support_session_id",
        "runtime_name",
        "runtime_session_id",
        "reset_generation",
        "customer_turn_id",
    }
    assert propose_parameters.isdisjoint(forbidden_scope)
    assert review_parameters.isdisjoint(forbidden_scope)
    assert commit_parameters.isdisjoint(forbidden_scope)
    assert decision_parameters.isdisjoint(forbidden_scope)


def test_runtime_context_requires_real_customer_turn() -> None:
    with pytest.raises(RuntimeContextError, match="real customer turn"):
        ProposalRuntimeContext.from_headers(
            _headers(**{"x-customer-turn-id": "unknown-turn"})
        ).require_customer_turn()


def test_model_safe_failure_projection_hides_operator_detail() -> None:
    active = MagicMock(
        id="11111111-1111-4111-8111-111111111111",
        action_type="TRIAGE_FRAUD_CASE",
        status="PRESENTED",
    )
    error = ActiveProposalExistsError(
        "database row and internal correlation detail",
        proposal=active,
    )

    result = _safe_protocol_failure(error, fallback_error="PROPOSAL_REJECTED")

    assert result["error"] == "ACTIVE_PROPOSAL_EXISTS"
    assert result["recovery_class"] == "RESOLVE_ACTIVE_PROPOSAL"
    assert result["proposal_id"] == str(active.id)
    assert "database" not in result["message"]


def test_read_only_mcp_tool_ignores_partial_proposal_headers() -> None:
    partial_headers = {
        "x-support-session-id": "support-1",
        "x-runtime-name": "CES_GEMINI_LIVE",
        "x-runtime-session-id": "runtime-1",
        "x-reset-generation": "3:9",
    }

    assert (
        mcp_utils._proposal_context_for_tool("get_open_fraud_alert", partial_headers)
        is None
    )
    with pytest.raises(RuntimeContextError, match="x-customer-turn-id"):
        mcp_utils._proposal_context_for_tool("propose_fraud_triage", partial_headers)


def test_retired_closeout_tool_has_no_runtime_context_registration() -> None:
    headers = {
        "x-support-session-id": "support-session-1",
        "x-runtime-name": "CES_GEMINI_LIVE",
        "x-runtime-session-id": "runtime-session-1",
        "x-customer-turn-id": "customer-turn-1",
        "x-reset-generation": "generation-1",
    }
    assert "offer_session_closeout" not in mcp_utils.PROPOSAL_CONTEXT_TOOL_NAMES
    assert (
        mcp_utils._proposal_context_for_tool("offer_session_closeout", headers) is None
    )
    assert mcp_utils._runtime_context_for_tool("offer_session_closeout", headers) is None


def test_ces_capability_identity_rejects_stale_reset_generation(monkeypatch) -> None:
    claims = MagicMock(
        customer_identity="firebase-user-1",
        customer_id="customer-1",
        runtime_name="CES_GEMINI_LIVE",
        reset_generation="3:9",
    )
    db = MagicMock()
    monkeypatch.setattr(mcp_utils, "validate_ces_session_capability", lambda *_: claims)
    monkeypatch.setattr(mcp_utils, "SessionLocal", lambda: db)
    checked_identities = []

    def get_generation(_db, customer_identity):
        checked_identities.append(customer_identity)
        return {"token": "3:10"}

    monkeypatch.setattr(mcp_utils, "get_reset_generation", get_generation)

    with pytest.raises(PermissionError, match="demo reset"):
        mcp_utils._identity_from_ces_capability("opaque-capability", _headers())
    assert checked_identities == ["firebase-user-1"]
    db.close.assert_called_once()


@pytest.mark.asyncio
async def test_mcp_decorator_prefers_ces_capability_over_reusable_assertion(
    monkeypatch,
) -> None:
    headers = _headers(
        **{
            "x-banking-session-capability": "opaque-capability",
            "x-ces-app-id": "app-1",
            "x-ces-version-or-deployment-id": "deployment-7",
        }
    )
    context = MagicMock()
    context.request_context.request.headers = headers
    monkeypatch.setattr(mcp_utils, "is_running_locally", lambda: True)
    monkeypatch.setattr(
        mcp_utils,
        "_identity_from_ces_capability",
        lambda *_: "firebase-user-1",
    )
    monkeypatch.setattr(
        mcp_utils,
        "validate_firebase_token",
        lambda *_: pytest.fail("Firebase token must not reach CES MCP auth"),
    )

    @mcp_utils.requires_user_assertion
    async def read_tool(*, ctx=None, verified_customer_id=None):
        return verified_customer_id

    assert await read_tool(ctx=context) == "firebase-user-1"


@pytest.mark.asyncio
async def test_mcp_decorator_accepts_project_ces_service_agent_for_capability(
    monkeypatch,
) -> None:
    ces_email = "service-123@gcp-sa-ces.iam.gserviceaccount.com"
    headers = _headers(
        **{
            "authorization": "Bearer google-id-token",
            "x-banking-session-capability": "opaque-capability",
            "x-ces-app-id": "app-1",
            "x-ces-version-or-deployment-id": "deployment-7",
        }
    )
    context = MagicMock()
    context.request_context.request.headers = headers
    monkeypatch.setenv("CES_SERVICE_AGENT_EMAIL", ces_email)
    monkeypatch.setattr(mcp_utils, "is_running_locally", lambda: False)
    monkeypatch.setattr(
        "utils.auth.validate_google_id_token",
        lambda *_: ValidatedToken(claims={"email": ces_email}),
    )
    monkeypatch.setattr(
        mcp_utils,
        "_identity_from_ces_capability",
        lambda *_: "firebase-user-1",
    )

    @mcp_utils.requires_user_assertion
    async def read_tool(*, ctx=None, verified_customer_id=None):
        return verified_customer_id

    assert await read_tool(ctx=context) == "firebase-user-1"


@pytest.mark.asyncio
async def test_mcp_decorator_rejects_other_google_caller_for_ces_capability(
    monkeypatch,
) -> None:
    headers = _headers(
        **{
            "authorization": "Bearer google-id-token",
            "x-banking-session-capability": "opaque-capability",
            "x-ces-app-id": "app-1",
            "x-ces-version-or-deployment-id": "deployment-7",
        }
    )
    context = MagicMock()
    context.request_context.request.headers = headers
    monkeypatch.setenv(
        "CES_SERVICE_AGENT_EMAIL",
        "service-123@gcp-sa-ces.iam.gserviceaccount.com",
    )
    monkeypatch.setattr(mcp_utils, "is_running_locally", lambda: False)
    monkeypatch.setattr(
        "utils.auth.validate_google_id_token",
        lambda *_: ValidatedToken(claims={"email": "support@google.com"}),
    )

    @mcp_utils.requires_user_assertion
    async def read_tool(*, ctx=None, verified_customer_id=None):
        return verified_customer_id

    with pytest.raises(PermissionError, match="authorized service caller"):
        await read_tool(ctx=context)


def test_confirmation_evidence_is_transport_owned_and_explicit() -> None:
    context = ProposalRuntimeContext.from_headers(
        _headers(
            **{
                "x-customer-turn-id": "customer-turn-11",
                "x-proposal-presentation-turn-id": "assistant-turn-10",
                "x-proposal-confirmation-turn-id": "customer-turn-11",
                "x-proposal-confirmation-method": "EXPLICIT_VERBAL",
                "x-proposal-confirmation-source": "MODEL_TOOL_INTENT",
            }
        )
    )

    context.require_confirmation()
    assert context.presentation_turn_id == "assistant-turn-10"
    assert context.confirmation_turn_id == "customer-turn-11"
    assert context.confirmation_source == "MODEL_TOOL_INTENT"


@pytest.mark.asyncio
async def test_typed_mcp_projection_injects_identity_and_runtime_context(
    monkeypatch,
) -> None:
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
    monkeypatch.setattr(
        "routers.mcp.credit_card.ActionProposalService", lambda _: service
    )
    review_service = MagicMock()
    review_service.review_open_alert_selection.return_value = {
        "success": True,
        "ready_to_propose": True,
    }
    monkeypatch.setattr(
        "routers.mcp.credit_card.FraudAlertService", lambda _: review_service
    )
    customer_token = mcp_utils.verified_customer_id_var.set("customer-auth-1")
    runtime_token = mcp_utils.proposal_runtime_context_var.set(runtime_context)
    try:
        result = await propose_fraud_triage.__wrapped__(
            fraud_alert_id="22222222-2222-4222-8222-222222222222",
            selection_status="COMPLETE",
            disputed_authorization_ids=["auth-1"],
            disputed_transaction_ids=[],
            recognized_authorization_ids=[],
            recognized_transaction_ids=[],
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
                "x-proposal-confirmation-source": "MODEL_TOOL_INTENT",
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
    monkeypatch.setattr(
        "routers.mcp.credit_card.ActionProposalService", lambda _: service
    )
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


@pytest.mark.asyncio
async def test_commit_projection_returns_scoped_terminal_disposition(
    monkeypatch,
) -> None:
    runtime_context = ProposalRuntimeContext.from_headers(
        _headers(
            **{
                "x-customer-turn-id": "customer-turn-11",
                "x-proposal-presentation-turn-id": "assistant-turn-10",
                "x-proposal-confirmation-turn-id": "customer-turn-11",
                "x-proposal-confirmation-method": "EXPLICIT_VERBAL",
                "x-proposal-confirmation-source": "MODEL_TOOL_INTENT",
            }
        )
    )
    db = MagicMock()
    service = MagicMock()
    service.commit_fraud_triage_for_identity.side_effect = ProposalTransitionError(
        "Action proposal has expired."
    )
    service.proposal_disposition_for_identity.return_value = {
        "proposal_id": "11111111-1111-4111-8111-111111111111",
        "contract_version": "fraud-triage.v1",
        "status": "EXPIRED",
        "invalidation_reason": "TTL_EXPIRED",
    }
    monkeypatch.setattr("routers.mcp.credit_card.SessionLocal", lambda: db)
    monkeypatch.setattr(
        "routers.mcp.credit_card.ActionProposalService", lambda _: service
    )
    customer_token = mcp_utils.verified_customer_id_var.set("customer-auth-1")
    runtime_token = mcp_utils.proposal_runtime_context_var.set(runtime_context)
    try:
        result = await commit_fraud_triage.__wrapped__(
            proposal_id="11111111-1111-4111-8111-111111111111"
        )
    finally:
        mcp_utils.proposal_runtime_context_var.reset(runtime_token)
        mcp_utils.verified_customer_id_var.reset(customer_token)

    assert result["success"] is False
    assert result["status"] == "EXPIRED"
    assert result["invalidation_reason"] == "TTL_EXPIRED"
    service.proposal_disposition_for_identity.assert_called_once_with(
        "11111111-1111-4111-8111-111111111111",
        customer_identity="customer-auth-1",
        runtime_context=runtime_context,
    )
    db.rollback.assert_called_once()
