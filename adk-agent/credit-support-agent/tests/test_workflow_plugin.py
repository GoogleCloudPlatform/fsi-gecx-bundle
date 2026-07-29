from types import SimpleNamespace

import pytest
from google.adk.events import Event
from google.genai import types

from agent.workflow_authorization import (
    TRIAGE_FRAUD_CASE,
    create_workflow_authorization,
)
from agent.workflow_plugin import FraudWorkflowStatePlugin


def transcript_event(
    *,
    author: str,
    text: str,
    input_event: bool,
    finished: bool = True,
) -> Event:
    kwargs = {
        "id": f"{author}-event",
        "author": author,
        "actions": {},
        "content": types.Content(role=author, parts=[types.Part(text=text)]),
    }
    transcription = types.Transcription(text=text, finished=finished)
    if input_event:
        kwargs["input_transcription"] = transcription
    else:
        kwargs["output_transcription"] = transcription
    return Event(**kwargs)


def prepared_playbook() -> dict:
    authorization = create_workflow_authorization(
        action=TRIAGE_FRAUD_CASE,
        payload={
            "fraud_alert_id": "fraud-123",
            "disputed_authorization_ids": ["auth-1"],
            "disputed_transaction_ids": [],
            "issue_replacement": True,
        },
        session_id="session-1",
        originating_customer_event_id="customer-origin",
    )
    authorization["proposal_id"] = "proposal-123"
    authorization["customer_safe_summary"] = "Banking-owned structured summary."
    return {"workflow_authorization": authorization}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "assistant_text",
    (
        "A natural proposal presentation.",
        "A differently worded proposal presentation.",
        "Does that sound right?",
    ),
)
async def test_completed_proposal_assistant_turn_is_recorded_without_text_parsing(
    assistant_text: str,
) -> None:
    session = SimpleNamespace(
        state={"session_id": "session-1", "fraud_playbook": prepared_playbook()}
    )
    context = SimpleNamespace(session=session)
    plugin = FraudWorkflowStatePlugin()
    event = transcript_event(
        author="agent",
        text=assistant_text,
        input_event=False,
    )

    await plugin.on_event_callback(invocation_context=context, event=event)

    authorization = event.actions.state_delta["fraud_playbook"][
        "workflow_authorization"
    ]
    assert authorization["status"] == "PENDING"
    assert authorization["assistant_event_id"] == "agent-event"
    assert authorization["presented_at_epoch_s"] == event.timestamp


@pytest.mark.asyncio
async def test_incomplete_assistant_stream_does_not_mark_proposal_presented() -> None:
    session = SimpleNamespace(
        state={"session_id": "session-1", "fraud_playbook": prepared_playbook()}
    )
    context = SimpleNamespace(session=session)
    plugin = FraudWorkflowStatePlugin()
    event = transcript_event(
        author="agent",
        text="Partial output",
        input_event=False,
        finished=False,
    )

    await plugin.on_event_callback(invocation_context=context, event=event)

    assert "fraud_playbook" not in event.actions.state_delta


@pytest.mark.asyncio
async def test_customer_transcript_records_turn_identity_but_not_authorization() -> None:
    playbook = prepared_playbook()
    playbook["workflow_authorization"]["status"] = "PENDING"
    playbook["workflow_authorization"]["assistant_event_id"] = "agent-event"
    playbook["workflow_authorization"]["presented_at_epoch_s"] = 1000.0
    session = SimpleNamespace(
        state={"session_id": "session-1", "fraud_playbook": playbook}
    )
    context = SimpleNamespace(session=session)
    observed = []

    def observe_turn(text, **kwargs):
        observed.append((text, kwargs))
        return {"event_id": "protected-customer-turn"}

    plugin = FraudWorkflowStatePlugin(customer_turn_observer=observe_turn)
    event = transcript_event(
        author="user",
        text="Any natural-language response.",
        input_event=True,
    )

    await plugin.on_event_callback(invocation_context=context, event=event)

    assert observed[0][1]["event_id"] == "user-event"
    assert "fraud_playbook" not in event.actions.state_delta
    assert playbook["workflow_authorization"]["status"] == "PENDING"


@pytest.mark.asyncio
async def test_interruption_invalidates_uncommitted_proposal() -> None:
    session = SimpleNamespace(
        state={"session_id": "session-1", "fraud_playbook": prepared_playbook()}
    )
    context = SimpleNamespace(session=session)
    plugin = FraudWorkflowStatePlugin()
    event = Event(
        id="interruption-event",
        author="agent",
        actions={},
        interrupted=True,
    )

    await plugin.on_event_callback(invocation_context=context, event=event)

    authorization = event.actions.state_delta["fraud_playbook"][
        "workflow_authorization"
    ]
    assert authorization["status"] == "INVALIDATED"
    assert authorization["invalidation_reason"] == "MODEL_RESPONSE_INTERRUPTED"


@pytest.mark.asyncio
async def test_unrelated_assistant_turn_without_proposal_does_not_create_gate() -> None:
    session = SimpleNamespace(state={"session_id": "session-1", "fraud_playbook": {}})
    context = SimpleNamespace(session=session)
    plugin = FraudWorkflowStatePlugin()
    event = transcript_event(
        author="agent",
        text="General support response.",
        input_event=False,
    )

    await plugin.on_event_callback(invocation_context=context, event=event)

    assert "fraud_playbook" not in event.actions.state_delta
