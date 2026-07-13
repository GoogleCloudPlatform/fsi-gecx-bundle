from types import SimpleNamespace

import pytest
from google.adk.events import Event
from google.genai import types

from agent.fraud_voice import build_fraud_playbook
from agent.workflow_plugin import FraudWorkflowStatePlugin


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
