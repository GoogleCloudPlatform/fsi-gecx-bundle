from types import SimpleNamespace

import pytest
from google.adk.events import Event
from google.genai import types

from agent.fraud_voice import build_fraud_playbook
from agent.workflow_plugin import FraudWorkflowStatePlugin
from agent.workflow_authorization import (
    PUSH_CARD_TO_GOOGLE_WALLET,
    TRIAGE_FRAUD_CASE,
    create_workflow_authorization,
    invalidate_workflow_authorization,
)


def transcript_event(*, author: str, text: str, input_event: bool) -> Event:
    kwargs = {
        "id": f"{author}-event",
        "author": author,
        "actions": {},
        "content": types.Content(role=author, parts=[types.Part(text=text)]),
    }
    if input_event:
        kwargs["input_transcription"] = types.Transcription(text=text, finished=True)
    else:
        kwargs["output_transcription"] = types.Transcription(text=text, finished=True)
    return Event(**kwargs)


@pytest.mark.asyncio
async def test_plugin_writes_wallet_transitions_to_adk_state_delta() -> None:
    playbook = build_fraud_playbook(
        {
            "has_active_fraud_alert": True,
            "fraud_alert": {"fraud_alert_id": "fraud-123", "card_last_four": "4242"},
        }
    )
    playbook["replacement_issued"] = True
    session = SimpleNamespace(state={"fraud_playbook": playbook})
    context = SimpleNamespace(session=session)
    plugin = FraudWorkflowStatePlugin()

    offer_event = transcript_event(
        author="agent",
        text="I can push the virtual card to Google Wallet. Should I do that?",
        input_event=False,
    )
    await plugin.on_event_callback(invocation_context=context, event=offer_event)
    offered = offer_event.actions.state_delta["fraud_playbook"]
    session.state["fraud_playbook"] = offered

    user_event = transcript_event(
        author="user",
        text="Could you please, that would be great.",
        input_event=True,
    )
    await plugin.on_event_callback(invocation_context=context, event=user_event)
    confirmed = user_event.actions.state_delta["fraud_playbook"]

    assert offered["wallet_response_status"] == "PENDING"
    assert confirmed["wallet_response_status"] == "CONFIRMED"
    assert confirmed["wallet_customer_confirmed"] is True


@pytest.mark.asyncio
async def test_plugin_persists_ordered_closeout_checkpoint() -> None:
    session = SimpleNamespace(state={"fraud_playbook": {}})
    context = SimpleNamespace(session=session)
    plugin = FraudWorkflowStatePlugin()

    prompt_event = transcript_event(
        author="agent",
        text="Is there anything else I can help you with?",
        input_event=False,
    )
    await plugin.on_event_callback(invocation_context=context, event=prompt_event)
    checkpoint = prompt_event.actions.state_delta["closeout_checkpoint"]
    session.state["closeout_checkpoint"] = checkpoint

    customer_event = transcript_event(
        author="user",
        text="No, that's all.",
        input_event=True,
    )
    await plugin.on_event_callback(invocation_context=context, event=customer_event)

    assert customer_event.actions.state_delta["closeout_checkpoint"] == {
        "status": "CONFIRMED",
        "assistant_event_id": "agent-event",
        "customer_event_id": "user-event",
    }


@pytest.mark.asyncio
async def test_plugin_does_not_treat_fraud_answer_as_closeout() -> None:
    session = SimpleNamespace(state={"fraud_playbook": {}})
    context = SimpleNamespace(session=session)
    plugin = FraudWorkflowStatePlugin()
    customer_event = transcript_event(
        author="user",
        text="No, I don't recognize those charges.",
        input_event=True,
    )

    await plugin.on_event_callback(invocation_context=context, event=customer_event)

    assert "closeout_checkpoint" not in customer_event.actions.state_delta


@pytest.mark.asyncio
async def test_plugin_invalidates_wallet_authorization_on_interruption() -> None:
    playbook = build_fraud_playbook(
        {
            "has_active_fraud_alert": True,
            "fraud_alert": {"fraud_alert_id": "fraud-123", "card_last_four": "4242"},
        }
    )
    playbook["wallet_push_offered"] = True
    playbook["wallet_customer_confirmed"] = True
    playbook["wallet_response_status"] = "CONFIRMED"
    session = SimpleNamespace(state={"fraud_playbook": playbook})
    context = SimpleNamespace(session=session)
    plugin = FraudWorkflowStatePlugin()
    event = Event(
        id="interruption-event",
        author="agent",
        actions={},
        interrupted=True,
    )

    await plugin.on_event_callback(invocation_context=context, event=event)

    invalidated = event.actions.state_delta["fraud_playbook"]
    assert invalidated["wallet_response_status"] == "INVALIDATED"
    assert invalidated["wallet_invalidation_reason"] == "MODEL_RESPONSE_INTERRUPTED"


@pytest.mark.asyncio
async def test_plugin_creates_fresh_wallet_authorization_after_failed_attempt() -> None:
    playbook = build_fraud_playbook(
        {
            "has_active_fraud_alert": True,
            "fraud_alert": {"fraud_alert_id": "fraud-123", "card_last_four": "4242"},
        }
    )
    playbook.update(
        {
            "replacement_issued": True,
            "replacement_card_token": "trusted-replacement-token",
            "wallet_push_offered": True,
            "wallet_customer_confirmed": True,
            "wallet_response_status": "CONFIRMED",
        }
    )
    failed_authorization = create_workflow_authorization(
        action=PUSH_CARD_TO_GOOGLE_WALLET,
        payload={
            "card_token": "trusted-replacement-token",
            "wallet_provider": "GOOGLE_WALLET",
        },
        session_id="session-1",
    )
    failed_authorization["status"] = "EXECUTING"
    playbook["workflow_authorization"] = invalidate_workflow_authorization(
        failed_authorization,
        reason="TOOL_RESULT_NOT_SUCCESSFUL:push_card_to_google_wallet",
    )
    session = SimpleNamespace(
        state={"session_id": "session-1", "fraud_playbook": playbook}
    )
    context = SimpleNamespace(session=session)
    plugin = FraudWorkflowStatePlugin()

    retry_offer = transcript_event(
        author="agent",
        text="I couldn't queue it. Would you like me to try Google Wallet again?",
        input_event=False,
    )
    await plugin.on_event_callback(invocation_context=context, event=retry_offer)
    prompted = retry_offer.actions.state_delta["fraud_playbook"]
    session.state["fraud_playbook"] = prompted

    retry_confirmation = transcript_event(
        author="user",
        text="Yes, please try again.",
        input_event=True,
    )
    await plugin.on_event_callback(
        invocation_context=context,
        event=retry_confirmation,
    )
    confirmed = retry_confirmation.actions.state_delta["fraud_playbook"]

    assert prompted["workflow_authorization"]["status"] == "PENDING"
    assert prompted["workflow_authorization"]["payload"]["card_token"] == (
        "trusted-replacement-token"
    )
    assert confirmed["workflow_authorization"]["status"] == "CONFIRMED"


@pytest.mark.asyncio
async def test_plugin_confirms_prepared_triage_only_after_separate_turns() -> None:
    playbook = build_fraud_playbook(
        {
            "has_active_fraud_alert": True,
            "fraud_alert": {"fraud_alert_id": "fraud-123", "card_last_four": "4242"},
        }
    )
    playbook["workflow_authorization"] = create_workflow_authorization(
        action=TRIAGE_FRAUD_CASE,
        payload={
            "fraud_alert_id": "fraud-123",
            "disputed_authorization_ids": ["auth-1"],
            "disputed_transaction_ids": [],
            "issue_replacement": True,
        },
        session_id="session-1",
    )
    session = SimpleNamespace(state={"session_id": "session-1", "fraud_playbook": playbook})
    context = SimpleNamespace(session=session)
    plugin = FraudWorkflowStatePlugin()

    prompt_event = transcript_event(
        author="agent",
        text="To confirm, you are disputing the charge linked to auth-1. Is that correct?",
        input_event=False,
    )
    await plugin.on_event_callback(invocation_context=context, event=prompt_event)
    prompted = prompt_event.actions.state_delta["fraud_playbook"]
    session.state["fraud_playbook"] = prompted

    customer_event = transcript_event(
        author="user",
        text="Yes, that's right.",
        input_event=True,
    )
    await plugin.on_event_callback(invocation_context=context, event=customer_event)
    confirmed = customer_event.actions.state_delta["fraud_playbook"]

    assert prompted["workflow_authorization"]["status"] == "PENDING"
    assert prompted["workflow_authorization"]["assistant_event_id"] == "agent-event"
    assert confirmed["workflow_authorization"]["status"] == "CONFIRMED"
    assert confirmed["workflow_authorization"]["customer_event_id"] == "user-event"


@pytest.mark.asyncio
async def test_plugin_accepts_typed_customer_confirmation() -> None:
    playbook = build_fraud_playbook(
        {
            "has_active_fraud_alert": True,
            "fraud_alert": {"fraud_alert_id": "fraud-123", "card_last_four": "4242"},
        }
    )
    authorization = create_workflow_authorization(
        action=TRIAGE_FRAUD_CASE,
        payload={
            "fraud_alert_id": "fraud-123",
            "disputed_authorization_ids": ["auth-1"],
            "disputed_transaction_ids": [],
            "issue_replacement": True,
        },
        session_id="session-1",
    )
    authorization["status"] = "PENDING"
    authorization["assistant_event_id"] = "agent-prompt"
    playbook["workflow_authorization"] = authorization
    session = SimpleNamespace(
        state={"session_id": "session-1", "fraud_playbook": playbook}
    )
    context = SimpleNamespace(session=session)
    plugin = FraudWorkflowStatePlugin()
    event = Event(
        id="typed-user-event",
        author="user",
        actions={},
        content=types.Content(
            role="user", parts=[types.Part(text="Yes, that is correct.")]
        ),
    )

    await plugin.on_event_callback(invocation_context=context, event=event)

    updated = event.actions.state_delta["fraud_playbook"]
    assert updated["workflow_authorization"]["status"] == "CONFIRMED"
    assert updated["workflow_authorization"]["customer_event_id"] == (
        "typed-user-event"
    )
