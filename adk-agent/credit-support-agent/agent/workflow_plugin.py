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

"""ADK session-state transitions for the live fraud support workflow."""

from __future__ import annotations

from google.adk.plugins import BasePlugin

from agent.workflow_authorization import mark_authorization_presented
from agent.telemetry import record_action_proposal_event


def _record_proposal_transition(
    state: dict, authorization: dict, outcome: str, reason: str | None = None
) -> None:
    proposal_id = authorization.get("proposal_id")
    if not proposal_id:
        return
    guidance = state.get("support_guidance") or {}
    record_action_proposal_event(
        runtime="ADK_GEMINI_LIVE",
        support_session_id=str(state.get("session_id") or ""),
        proposal_id=str(proposal_id),
        contract_version=str(
            authorization.get("contract_version") or "fraud-triage.v1"
        ),
        catalog_snapshot_id=guidance.get("snapshot_id"),
        tool="fraud_workflow_state",
        outcome=outcome,
        latency_ms=0,
        invalidation_reason=reason,
    )


class FraudWorkflowStatePlugin(BasePlugin):
    """Persist completed Live transcript transitions into ADK session state."""

    def __init__(
        self,
        *,
        customer_turn_observer=None,
    ) -> None:
        super().__init__(name="fraud_workflow_state")
        self._customer_turn_observer = customer_turn_observer

    async def on_event_callback(self, *, invocation_context, event):
        playbook = invocation_context.session.state.get("fraud_playbook") or {}
        updated = dict(playbook)

        event_id = event.id or f"event-at-{event.timestamp}"
        input_transcription = getattr(event, "input_transcription", None)
        customer_text = None
        if input_transcription and input_transcription.finished:
            customer_text = input_transcription.text
        elif getattr(event, "author", None) == "user":
            parts = getattr(getattr(event, "content", None), "parts", None) or []
            text_parts = [part.text for part in parts if getattr(part, "text", None)]
            customer_text = "\n".join(text_parts).strip() or None
        if customer_text is not None:
            if self._customer_turn_observer:
                turn = self._customer_turn_observer(
                    customer_text,
                    event_id=event_id,
                    observed_at_epoch_s=event.timestamp,
                    consume_pending=True,
                )
                if turn and turn.get("event_id"):
                    event_id = str(turn["event_id"])

        output_transcription = getattr(event, "output_transcription", None)
        if output_transcription and output_transcription.finished:
            authorization = updated.get("workflow_authorization") or {}
            if authorization.get("status") == "PREPARED":
                updated["workflow_authorization"] = mark_authorization_presented(
                    authorization,
                    assistant_event_id=event_id,
                    now_epoch_s=event.timestamp,
                )
                _record_proposal_transition(
                    invocation_context.session.state,
                    updated["workflow_authorization"],
                    "PRESENTED",
                )

        if updated != playbook:
            event.actions.state_delta["fraud_playbook"] = updated

        return event
