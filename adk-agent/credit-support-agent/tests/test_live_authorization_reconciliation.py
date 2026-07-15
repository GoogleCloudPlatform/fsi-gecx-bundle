import asyncio
from types import SimpleNamespace

import pytest

from agent import agent
from agent.workflow_authorization import (
    TRIAGE_FRAUD_CASE,
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


def test_latest_typed_or_voice_turn_closes_live_event_ordering_gap() -> None:
    tokens = agent.bind_session_context("customer-1", lambda event: event)
    try:
        agent.record_customer_turn(
            "That's correct.",
            event_id="typed-message-1",
            observed_at_epoch_s=1002.0,
        )
        reconciled, changed = agent.apply_latest_customer_turn_to_authorization(
            pending_playbook()
        )
    finally:
        agent.reset_session_context(tokens)

    assert changed is True
    assert reconciled["workflow_authorization"]["status"] == "CONFIRMED"
    assert reconciled["workflow_authorization"]["customer_event_id"] == (
        "typed-message-1"
    )


def test_confirmation_before_payload_preparation_is_not_reused() -> None:
    tokens = agent.bind_session_context("customer-1", lambda event: event)
    try:
        agent.record_customer_turn(
            "Correct",
            event_id="customer-before-prepare",
            observed_at_epoch_s=999.0,
        )
        reconciled, changed = agent.apply_latest_customer_turn_to_authorization(
            pending_playbook(issued_at=1000.0)
        )
    finally:
        agent.reset_session_context(tokens)

    assert changed is False
    assert reconciled["workflow_authorization"]["status"] == "PENDING"


@pytest.mark.asyncio
async def test_customer_turn_recorded_by_child_listener_is_shared() -> None:
    tokens = agent.bind_session_context("customer-1", lambda event: event)
    try:
        await asyncio.create_task(
            asyncio.to_thread(
                agent.record_customer_turn,
                "Yes",
                event_id="child-listener-turn",
                observed_at_epoch_s=1002.0,
            )
        )
        reconciled, changed = agent.apply_latest_customer_turn_to_authorization(
            pending_playbook()
        )
    finally:
        agent.reset_session_context(tokens)

    assert changed is True
    assert reconciled["workflow_authorization"]["status"] == "CONFIRMED"


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
