from types import SimpleNamespace

import pytest

from agent import agent
from agent.closeout import closeout_block_reason, open_closeout_checkpoint
from agent.workflow_authorization import (
    PROVISION_GOOGLE_WALLET,
    create_workflow_authorization,
)


def test_closeout_requires_typed_offer_and_later_customer_turn() -> None:
    checkpoint = open_closeout_checkpoint(
        originating_customer_event_id="customer-action-turn",
        now_epoch_s=10,
    )

    assert (
        closeout_block_reason(
            closeout_checkpoint=checkpoint,
            workflow_authorization={"status": "COMPLETED"},
            latest_customer_turn={
                "event_id": "customer-action-turn",
                "observed_at_epoch_s": 10,
            },
        )
        == "LATER_CLOSEOUT_CUSTOMER_TURN_REQUIRED"
    )
    assert (
        closeout_block_reason(
            closeout_checkpoint=checkpoint,
            workflow_authorization={"status": "COMPLETED"},
            latest_customer_turn={
                "event_id": "customer-closeout-turn",
                "observed_at_epoch_s": 11,
            },
        )
        is None
    )


def test_closeout_never_interprets_customer_transcript() -> None:
    checkpoint = open_closeout_checkpoint(
        originating_customer_event_id="customer-action-turn",
        now_epoch_s=10,
    )
    # The runtime accepts protected event provenance only. Whether this later
    # turn means "continue" or "finish" is the model's typed end-tool choice.
    latest_turn = {
        "event_id": "customer-next-turn",
        "observed_at_epoch_s": 11,
        "transcript": "This field must never be inspected by the gate.",
    }
    assert (
        closeout_block_reason(
            closeout_checkpoint=checkpoint,
            workflow_authorization={"status": "COMPLETED"},
            latest_customer_turn=latest_turn,
        )
        is None
    )


def test_unresolved_authorization_blocks_closeout() -> None:
    authorization = create_workflow_authorization(
        action=PROVISION_GOOGLE_WALLET,
        payload={},
        session_id="session-1",
    )

    assert (
        closeout_block_reason(
            closeout_checkpoint=open_closeout_checkpoint(
                originating_customer_event_id="customer-action-turn",
                now_epoch_s=10,
            ),
            workflow_authorization=authorization,
            latest_customer_turn={
                "event_id": "customer-closeout-turn",
                "observed_at_epoch_s": 11,
            },
        )
        == "WORKFLOW_AUTHORIZATION_PREPARED"
    )


def test_commit_recovery_blocks_closeout() -> None:
    assert (
        closeout_block_reason(
            closeout_checkpoint=open_closeout_checkpoint(
                originating_customer_event_id="customer-action-turn",
                now_epoch_s=10,
            ),
            workflow_authorization={"status": "RECOVERY_REQUIRED"},
            latest_customer_turn={
                "event_id": "customer-closeout-turn",
                "observed_at_epoch_s": 11,
            },
        )
        == "WORKFLOW_AUTHORIZATION_RECOVERY_REQUIRED"
    )


@pytest.mark.asyncio
async def test_end_tool_uses_typed_offer_and_event_ordering() -> None:
    tokens = agent.bind_session_context("customer-1", lambda event: event)
    context = SimpleNamespace(
        state={
            "session_id": "session-1",
            "fraud_playbook": {
                "completion_status": "ACTIVE",
                "workflow_authorization": {"status": "COMPLETED"},
            },
        }
    )
    try:
        agent.record_customer_turn("The action is complete.")
        offered = agent.offer_session_closeout(context)
        assert offered["status"] == "CLOSEOUT_OFFERED"

        blocked = await agent.before_tool_callback(
            SimpleNamespace(name="end_consultation"), {}, context
        )
        assert blocked["status"] == "SESSION_CLOSE_CONFIRMATION_REQUIRED"

        agent.record_customer_turn("A later customer turn.")
        allowed = await agent.before_tool_callback(
            SimpleNamespace(name="end_consultation"), {}, context
        )
        assert allowed is None

        result = agent.end_consultation()
        assert result["status"] == "SUCCESS"
        assert agent.is_session_end_requested() is True
    finally:
        agent.reset_session_context(tokens)
