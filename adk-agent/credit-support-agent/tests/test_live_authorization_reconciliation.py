from types import SimpleNamespace
import time

import pytest

from agent import agent
from agent.workflow_authorization import (
    TRIAGE_FRAUD_CASE,
    create_workflow_authorization,
    mark_authorization_presented,
)


def triage_payload() -> dict:
    return {
        "fraud_alert_id": "fraud-123",
        "disputed_authorization_ids": ["auth-1"],
        "disputed_transaction_ids": [],
        "issue_replacement": True,
    }


def pending_playbook(*, issued_at: float | None = None) -> dict:
    issued_at = time.time() if issued_at is None else issued_at
    authorization = create_workflow_authorization(
        action=TRIAGE_FRAUD_CASE,
        payload=triage_payload(),
        session_id="session-1",
        originating_customer_event_id="customer-origin",
        now_epoch_s=issued_at,
    )
    authorization["proposal_id"] = "proposal-123"
    authorization = mark_authorization_presented(
        authorization,
        assistant_event_id="assistant-presentation",
        now_epoch_s=issued_at + 1,
    )
    return {
        "entry_mode": "FRAUD_ALERT",
        "fraud_alert_id": "fraud-123",
        "open_alert_inspected": True,
        "triage_submitted": False,
        "resolution_completed": False,
        "workflow_authorization": authorization,
    }


def context_for(playbook: dict) -> SimpleNamespace:
    return SimpleNamespace(
        state={
            "session_id": "session-1",
            "reset_generation_token": "0:1",
            "fraud_playbook": playbook,
            "fraud_context": {"fraud_alert_id": "fraud-123"},
        }
    )


@pytest.fixture
def valid_reset(monkeypatch):
    async def generation_is_valid(**kwargs):
        return True, None

    monkeypatch.setattr(agent, "validate_reset_generation", generation_is_valid)
    monkeypatch.setattr(agent, "get_auth_headers", lambda: {})


def test_raw_customer_turn_does_not_change_authorization() -> None:
    tokens = agent.bind_session_context("customer-1", lambda event: event)
    playbook = pending_playbook()
    try:
        agent.record_customer_turn(
            "Any natural-language content",
            event_id="customer-confirmation",
            observed_at_epoch_s=1002.0,
        )
    finally:
        agent.reset_session_context(tokens)

    assert playbook["workflow_authorization"]["status"] == "PENDING"


@pytest.mark.asyncio
async def test_commit_tool_choice_binds_to_later_protected_customer_turn(
    valid_reset,
) -> None:
    tokens = agent.bind_session_context(
        "customer-1",
        lambda event: event,
        support_session_id="session-1",
    )
    context = context_for(pending_playbook())
    try:
        presented_at = context.state["fraud_playbook"]["workflow_authorization"][
            "presented_at_epoch_s"
        ]
        agent.record_customer_turn(
            "The runtime records this only as turn evidence.",
            event_id="customer-confirmation",
            observed_at_epoch_s=presented_at + 1,
        )
        result = await agent.before_tool_callback(
            SimpleNamespace(name="commit_fraud_triage"),
            {"proposal_id": "proposal-123"},
            context,
        )
    finally:
        agent.set_tool_processing(False)
        agent.reset_session_context(tokens)

    assert result is None
    authorization = context.state["fraud_playbook"]["workflow_authorization"]
    assert authorization["status"] == "EXECUTING"
    assert authorization["customer_event_id"] == "customer-confirmation"
    assert authorization["confirmation_source"] == "MODEL_TOOL_INTENT"


@pytest.mark.asyncio
async def test_commit_tool_choice_on_originating_turn_is_blocked(valid_reset) -> None:
    tokens = agent.bind_session_context(
        "customer-1",
        lambda event: event,
        support_session_id="session-1",
    )
    context = context_for(pending_playbook())
    try:
        presented_at = context.state["fraud_playbook"]["workflow_authorization"][
            "presented_at_epoch_s"
        ]
        agent.record_customer_turn(
            "The proposal-originating customer turn.",
            event_id="customer-origin",
            observed_at_epoch_s=presented_at + 1,
        )
        result = await agent.before_tool_callback(
            SimpleNamespace(name="commit_fraud_triage"),
            {"proposal_id": "proposal-123"},
            context,
        )
    finally:
        agent.reset_session_context(tokens)

    assert result["status"] == "AUTHORIZATION_REQUIRED"
    assert context.state["fraud_playbook"]["workflow_authorization"]["status"] == (
        "PENDING"
    )


@pytest.mark.asyncio
async def test_commit_tool_choice_before_presentation_is_blocked(valid_reset) -> None:
    playbook = pending_playbook()
    authorization = dict(playbook["workflow_authorization"])
    authorization["status"] = "PREPARED"
    authorization["assistant_event_id"] = None
    authorization["presented_at_epoch_s"] = None
    playbook["workflow_authorization"] = authorization
    context = context_for(playbook)
    tokens = agent.bind_session_context(
        "customer-1",
        lambda event: event,
        support_session_id="session-1",
    )
    try:
        presented_at = time.time()
        agent.record_customer_turn(
            "A later turn cannot bypass missing presentation.",
            event_id="customer-confirmation",
            observed_at_epoch_s=presented_at,
        )
        result = await agent.before_tool_callback(
            SimpleNamespace(name="commit_fraud_triage"),
            {"proposal_id": "proposal-123"},
            context,
        )
    finally:
        agent.reset_session_context(tokens)

    assert result["status"] == "AUTHORIZATION_REQUIRED"


def test_typed_ingress_id_becomes_canonical_adk_turn_id() -> None:
    tokens = agent.bind_session_context("customer-1", lambda event: event)
    try:
        agent.record_customer_turn(
            "Customer input.",
            event_id="typed-message-1",
            observed_at_epoch_s=1002.0,
            pending_ingress=True,
        )
        turn = agent.record_customer_turn(
            " customer   input. ",
            event_id="adk-event-9",
            observed_at_epoch_s=1002.1,
            consume_pending=True,
        )
    finally:
        agent.reset_session_context(tokens)

    assert turn["event_id"] == "typed-message-1"
    assert turn["runtime_event_id"] == "adk-event-9"
    assert turn["pending_ingress"] is False
