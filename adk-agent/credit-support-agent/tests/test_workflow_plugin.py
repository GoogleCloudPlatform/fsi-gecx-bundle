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

from types import SimpleNamespace

import pytest
from google.adk.events import Event
from google.genai import types

from agent.proposal_evidence import create_pending_proposal
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
    proposal = create_pending_proposal(
        proposal_id="proposal-123",
        action_type="TRIAGE_FRAUD_CASE",
        contract_version="fraud-triage.v1",
        originating_customer_turn_id="customer-origin",
    )
    return {"pending_proposal": proposal}


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

    proposal = event.actions.state_delta["fraud_playbook"]["pending_proposal"]
    assert proposal["evidence_state"] == "AWAITING_DECISION"
    assert proposal["presentation_turn_id"] == "agent-event"
    assert proposal["presentation_observed_at_epoch_s"] == event.timestamp


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
async def test_customer_transcript_records_turn_identity_but_not_authorization() -> (
    None
):
    playbook = prepared_playbook()
    playbook["pending_proposal"]["evidence_state"] = "AWAITING_DECISION"
    playbook["pending_proposal"]["presentation_turn_id"] = "agent-event"
    playbook["pending_proposal"]["presentation_observed_at_epoch_s"] = 1000.0
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
    assert playbook["pending_proposal"]["evidence_state"] == "AWAITING_DECISION"


@pytest.mark.asyncio
async def test_interruption_does_not_change_uncommitted_proposal() -> None:
    playbook = prepared_playbook()
    session = SimpleNamespace(
        state={"session_id": "session-1", "fraud_playbook": playbook}
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

    assert "fraud_playbook" not in event.actions.state_delta
    assert playbook["pending_proposal"]["evidence_state"] == ("AWAITING_PRESENTATION")


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
