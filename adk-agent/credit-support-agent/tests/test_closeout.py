from types import SimpleNamespace

import pytest

from agent import agent
from agent.closeout import (
    apply_closeout_transcript_event,
    assistant_requested_closeout,
    closeout_block_reason,
    customer_explicitly_closed,
)
from agent.workflow_authorization import (
    PUSH_CARD_TO_GOOGLE_WALLET,
    create_workflow_authorization,
)


@pytest.mark.parametrize(
    "transcript",
    (
        "No, that's all.",
        "Nothing else, thank you.",
        "No, that's it.",
        "No, that is about it.",
        "That'll be all.",
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


@pytest.mark.parametrize(
    "transcript",
    (
        "Is there anything else I can help you with?",
        "Can I help you with anything else today?",
        "Do you need anything more?",
    ),
)
def test_agent_closeout_prompt_variants(transcript: str) -> None:
    assert assistant_requested_closeout(transcript) is True


def test_no_only_confirms_after_agent_opens_closeout_checkpoint() -> None:
    missing_checkpoint = apply_closeout_transcript_event(
        None,
        author="user",
        transcript="No, I don't recognize those charges.",
        event_id="customer-fraud-answer",
    )
    assert missing_checkpoint == {}

    pending = apply_closeout_transcript_event(
        None,
        author="agent",
        transcript="Is there anything else I can help you with?",
        event_id="agent-closeout-prompt",
    )
    confirmed = apply_closeout_transcript_event(
        pending,
        author="user",
        transcript="No, that's all.",
        event_id="customer-closeout",
    )

    assert confirmed == {
        "status": "CONFIRMED",
        "assistant_event_id": "agent-closeout-prompt",
        "customer_event_id": "customer-closeout",
    }


def test_unresolved_authorization_blocks_closeout_even_after_goodbye() -> None:
    authorization = create_workflow_authorization(
        action=PUSH_CARD_TO_GOOGLE_WALLET,
        payload={"card_token": "replacement-token"},
        session_id="session-1",
    )

    assert closeout_block_reason(
        closeout_checkpoint={
            "status": "CONFIRMED",
            "assistant_event_id": "agent-closeout-prompt",
            "customer_event_id": "customer-closeout",
        },
        workflow_authorization=authorization,
    ) == "WORKFLOW_AUTHORIZATION_PREPARED"


@pytest.mark.asyncio
async def test_end_tool_uses_event_ordered_state_not_lagging_stream_holder() -> None:
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
        # Reproduce the production race: the outer run_live consumer still has
        # the earlier Wallet authorization turn when the internal ADK plugin
        # has already processed the finalized closeout response.
        agent.record_customer_turn("That would be great, thank you.")
        blocked = await agent.before_tool_callback(
            SimpleNamespace(name="end_consultation"), {}, context
        )

        assert blocked["status"] == "SESSION_CLOSE_CONFIRMATION_REQUIRED"
        assert blocked["session_ended"] is False
        assert "anything else" in blocked["customer_response"].lower()
        assert agent.is_session_end_requested() is False

        context.state["closeout_checkpoint"] = {
            "status": "CONFIRMED",
            "assistant_event_id": "agent-closeout-prompt",
            "customer_event_id": "customer-closeout",
        }
        allowed = await agent.before_tool_callback(
            SimpleNamespace(name="end_consultation"), {}, context
        )
        assert allowed is None

        result = agent.end_consultation()
        assert result["status"] == "SUCCESS"
        assert agent.is_session_end_requested() is True
    finally:
        agent.reset_session_context(tokens)
