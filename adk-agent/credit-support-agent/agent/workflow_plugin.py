"""ADK session-state transitions for the live fraud support workflow."""

from __future__ import annotations

from google.adk.plugins import BasePlugin

from agent.fraud_voice import apply_wallet_transcript_event, invalidate_wallet_authorization


class FraudWorkflowStatePlugin(BasePlugin):
    """Persist completed Live transcript transitions into ADK session state."""

    def __init__(self) -> None:
        super().__init__(name="fraud_workflow_state")

    async def on_event_callback(self, *, invocation_context, event):
        playbook = invocation_context.session.state.get("fraud_playbook") or {}
        updated = playbook

        event_id = event.id or f"event-at-{event.timestamp}"
        if getattr(event, "interrupted", False):
            updated = invalidate_wallet_authorization(
                updated,
                reason="MODEL_RESPONSE_INTERRUPTED",
                event_id=event_id,
            )

        input_transcription = getattr(event, "input_transcription", None)
        if input_transcription and input_transcription.finished:
            updated = apply_wallet_transcript_event(
                updated,
                author="user",
                transcript=input_transcription.text,
                event_id=event_id,
            )

        output_transcription = getattr(event, "output_transcription", None)
        if output_transcription and output_transcription.finished:
            updated = apply_wallet_transcript_event(
                updated,
                author="agent",
                transcript=output_transcription.text,
                event_id=event_id,
            )

        if updated != playbook:
            event.actions.state_delta["fraud_playbook"] = updated

        return event
