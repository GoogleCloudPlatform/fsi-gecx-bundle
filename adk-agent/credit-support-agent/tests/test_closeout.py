from types import SimpleNamespace

import pytest

from agent import agent
from agent.closeout import closeout_block_reason, customer_explicitly_closed
from agent.workflow_authorization import (
    PUSH_CARD_TO_GOOGLE_WALLET,
    create_workflow_authorization,
)


@pytest.mark.parametrize(
    "transcript",
    (
        "No, that's all.",
        "Nothing else, thank you.",
        "I'm all set.",
        "We are done.",
        "Goodbye!",
    ),
)
def test_explicit_customer_closeout_phrases(transcript: str) -> None:
    assert customer_explicitly_closed(transcript) is True


@pytest.mark.parametrize(
    "transcript",
    (
        "That would be great, thank you.",
        "Yeah, please queue it, thanks.",
        "Thank you.",
        "You're welcome.",
        "Are you done adding it?",
    ),
)
def test_action_confirmation_and_gratitude_are_not_closeout(transcript: str) -> None:
    assert customer_explicitly_closed(transcript) is False


def test_unresolved_authorization_blocks_closeout_even_after_goodbye() -> None:
    authorization = create_workflow_authorization(
        action=PUSH_CARD_TO_GOOGLE_WALLET,
        payload={"card_token": "replacement-token"},
        session_id="session-1",
    )

    assert closeout_block_reason(
        latest_customer_transcript="Goodbye",
        workflow_authorization=authorization,
    ) == "WORKFLOW_AUTHORIZATION_PREPARED"


@pytest.mark.asyncio
async def test_end_tool_is_blocked_until_customer_explicitly_closes() -> None:
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
        agent.record_customer_turn("That would be great, thank you.")
        blocked = await agent.before_tool_callback(
            SimpleNamespace(name="end_consultation"), {}, context
        )

        assert blocked["status"] == "SESSION_CLOSE_CONFIRMATION_REQUIRED"
        assert blocked["session_ended"] is False
        assert "anything else" in blocked["customer_response"].lower()
        assert agent.is_session_end_requested() is False

        agent.record_customer_turn("No, that's all.")
        allowed = await agent.before_tool_callback(
            SimpleNamespace(name="end_consultation"), {}, context
        )
        assert allowed is None

        result = agent.end_consultation()
        assert result["status"] == "SUCCESS"
        assert agent.is_session_end_requested() is True
    finally:
        agent.reset_session_context(tokens)
