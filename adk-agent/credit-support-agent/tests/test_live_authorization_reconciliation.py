import asyncio
from types import SimpleNamespace

import pytest

from agent import agent
from agent.workflow_authorization import (
    PUSH_CARD_TO_GOOGLE_WALLET,
    TRIAGE_FRAUD_CASE,
    apply_customer_authorization_response,
    create_workflow_authorization,
    mark_authorization_prompted,
)


def triage_payload() -> dict:
    return {
        "fraud_alert_id": "fraud-123",
        "disputed_authorization_ids": ["auth-1"],
        "disputed_transaction_ids": [],
        "issue_replacement": True,
    }


def pending_playbook(*, issued_at: float = 1000.0) -> dict:
    authorization = create_workflow_authorization(
        action=TRIAGE_FRAUD_CASE,
        payload=triage_payload(),
        session_id="session-1",
        now_epoch_s=issued_at,
    )
    authorization = mark_authorization_prompted(
        authorization,
        assistant_event_id="assistant-prompt",
        now_epoch_s=issued_at + 1,
    )
    return {"workflow_authorization": authorization}


def confirmed_decision(*, event_id: str = "typed-message-1") -> dict:
    return apply_customer_authorization_response(
        pending_playbook()["workflow_authorization"],
        transcript="That's correct.",
        customer_event_id=event_id,
        now_epoch_s=1002.0,
    )


def test_plugin_decision_closes_live_event_ordering_gap() -> None:
    tokens = agent.bind_session_context("customer-1", lambda event: event)
    try:
        agent.record_customer_turn(
            "That's correct.",
            event_id="typed-message-1",
            observed_at_epoch_s=1002.0,
        )
        agent.record_customer_authorization_decision(confirmed_decision())
        reconciled, changed = agent.apply_recorded_authorization_decision(
            pending_playbook()
        )
    finally:
        agent.reset_session_context(tokens)

    assert changed is True
    assert reconciled["workflow_authorization"]["status"] == "CONFIRMED"
    assert reconciled["workflow_authorization"]["customer_event_id"] == (
        "typed-message-1"
    )


def test_raw_customer_turn_is_not_independently_classified() -> None:
    tokens = agent.bind_session_context("customer-1", lambda event: event)
    try:
        agent.record_customer_turn(
            "That's correct.",
            event_id="customer-turn-1",
            observed_at_epoch_s=1002.0,
        )
        reconciled, changed = agent.apply_recorded_authorization_decision(
            pending_playbook()
        )
    finally:
        agent.reset_session_context(tokens)

    assert changed is False
    assert reconciled["workflow_authorization"]["status"] == "PENDING"


@pytest.mark.asyncio
async def test_plugin_decision_recorded_by_child_listener_is_shared() -> None:
    tokens = agent.bind_session_context("customer-1", lambda event: event)
    try:
        agent.record_customer_turn(
            "Yes",
            event_id="child-listener-turn",
            observed_at_epoch_s=1002.0,
        )
        await asyncio.create_task(
            asyncio.to_thread(
                agent.record_customer_authorization_decision,
                confirmed_decision(event_id="child-listener-turn"),
            )
        )
        reconciled, changed = agent.apply_recorded_authorization_decision(
            pending_playbook()
        )
    finally:
        agent.reset_session_context(tokens)

    assert changed is True
    assert reconciled["workflow_authorization"]["status"] == "CONFIRMED"


def test_decision_for_different_authorization_is_not_reused() -> None:
    tokens = agent.bind_session_context("customer-1", lambda event: event)
    try:
        agent.record_customer_turn(
            "That's correct.",
            event_id="typed-message-1",
            observed_at_epoch_s=1002.0,
        )
        decision = confirmed_decision()
        decision["issued_at_epoch_s"] = 999.0
        agent.record_customer_authorization_decision(decision)
        reconciled, changed = agent.apply_recorded_authorization_decision(
            pending_playbook()
        )
    finally:
        agent.reset_session_context(tokens)

    assert changed is False
    assert reconciled["workflow_authorization"]["status"] == "PENDING"


def test_new_customer_turn_clears_buffered_decision() -> None:
    tokens = agent.bind_session_context("customer-1", lambda event: event)
    try:
        agent.record_customer_turn(
            "That's correct.",
            event_id="customer-turn-1",
            observed_at_epoch_s=1002.0,
        )
        agent.record_customer_authorization_decision(
            confirmed_decision(event_id="customer-turn-1")
        )
        agent.record_customer_turn(
            "Wait a moment.",
            event_id="customer-turn-2",
            observed_at_epoch_s=1003.0,
        )
        reconciled, changed = agent.apply_recorded_authorization_decision(
            pending_playbook()
        )
    finally:
        agent.reset_session_context(tokens)

    assert changed is False
    assert reconciled["workflow_authorization"]["status"] == "PENDING"


def test_typed_ingress_id_becomes_canonical_adk_turn_id() -> None:
    tokens = agent.bind_session_context("customer-1", lambda event: event)
    try:
        agent.record_customer_turn(
            "Yes, that's right.",
            event_id="typed-message-1",
            observed_at_epoch_s=1002.0,
            pending_ingress=True,
        )
        turn = agent.record_customer_turn(
            "  yes,   that's right. ",
            event_id="adk-event-9",
            observed_at_epoch_s=1002.1,
            consume_pending=True,
        )
    finally:
        agent.reset_session_context(tokens)

    assert turn["event_id"] == "typed-message-1"
    assert turn["runtime_event_id"] == "adk-event-9"
    assert turn["pending_ingress"] is False


@pytest.mark.asyncio
async def test_early_tool_attempt_returns_recoverable_authorization_checkpoint(
    monkeypatch,
) -> None:
    async def generation_is_valid(**kwargs):
        return True, None

    monkeypatch.setattr(agent, "validate_reset_generation", generation_is_valid)
    monkeypatch.setattr(agent, "get_auth_headers", lambda: {})
    playbook = pending_playbook()
    context = SimpleNamespace(
        state={
            "session_id": "session-1",
            "reset_generation_token": "0:1",
            "fraud_playbook": playbook,
            "fraud_context": {"fraud_alert_id": "fraud-123"},
        }
    )

    result = await agent.before_tool_callback(
        SimpleNamespace(name="triage_fraud_case"),
        triage_payload(),
        context,
    )

    assert result["status"] == "AUTHORIZATION_REQUIRED"
    assert result["isError"] is False
    assert result["authorization_blocked"] is True
    assert "not a technical failure" in result["model_instruction"]


@pytest.mark.asyncio
async def test_blocked_wallet_call_reports_not_queued_and_forbids_false_success(
    monkeypatch,
) -> None:
    async def generation_is_valid(**kwargs):
        return True, None

    monkeypatch.setattr(agent, "validate_reset_generation", generation_is_valid)
    monkeypatch.setattr(agent, "get_auth_headers", lambda: {})
    authorization = create_workflow_authorization(
        action=PUSH_CARD_TO_GOOGLE_WALLET,
        payload={"card_token": "replacement-token"},
        session_id="session-1",
        now_epoch_s=1000.0,
    )
    context = SimpleNamespace(
        state={
            "session_id": "session-1",
            "reset_generation_token": "0:1",
            "fraud_playbook": {
                "replacement_card_token": "replacement-token",
                "workflow_authorization": authorization,
            },
            "fraud_context": {},
        }
    )

    result = await agent.before_tool_callback(
        SimpleNamespace(name="push_card_to_google_wallet"),
        {"card_token": "invented-token"},
        context,
    )

    assert result["status"] == "AUTHORIZATION_REQUIRED"
    assert result["action_completed"] is False
    assert result["wallet_provisioning_status"] == "NOT_QUEUED"
    assert "DID NOT RUN" in result["model_instruction"]
    assert "not queued" in result["customer_response"]
