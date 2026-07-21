"""ADK session-state transitions for the live fraud support workflow."""

from __future__ import annotations

from google.adk.plugins import BasePlugin

from agent.closeout import apply_closeout_transcript_event
from agent.fraud_voice import (
    agent_offered_google_wallet,
    apply_wallet_transcript_event,
    invalidate_wallet_authorization,
)
from agent.workflow_authorization import (
    PUSH_CARD_TO_GOOGLE_WALLET,
    TRIAGE_CUSTOMER_REPORTED_FRAUD,
    TRIAGE_FRAUD_CASE,
    apply_customer_authorization_response,
    assistant_requested_confirmation,
    create_workflow_authorization,
    invalidate_workflow_authorization,
    mark_authorization_prompted,
)
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
        contract_version=str(authorization.get("contract_version") or "fraud-triage.v1"),
        catalog_snapshot_id=guidance.get("snapshot_id"),
        tool="fraud_workflow_state",
        outcome=outcome,
        latency_ms=0,
        invalidation_reason=reason,
    )


class FraudWorkflowStatePlugin(BasePlugin):
    """Persist completed Live transcript transitions into ADK session state."""

    def __init__(self) -> None:
        super().__init__(name="fraud_workflow_state")

    async def on_event_callback(self, *, invocation_context, event):
        playbook = invocation_context.session.state.get("fraud_playbook") or {}
        updated = dict(playbook)

        event_id = event.id or f"event-at-{event.timestamp}"
        if getattr(event, "interrupted", False):
            updated = invalidate_wallet_authorization(
                updated,
                reason="MODEL_RESPONSE_INTERRUPTED",
                event_id=event_id,
            )
            authorization = updated.get("workflow_authorization")
            if authorization:
                updated["workflow_authorization"] = invalidate_workflow_authorization(
                    authorization,
                    reason="MODEL_RESPONSE_INTERRUPTED",
                    event_id=event_id,
                )
                _record_proposal_transition(
                    invocation_context.session.state,
                    updated["workflow_authorization"],
                    "INVALIDATED",
                    "MODEL_RESPONSE_INTERRUPTED",
                )

        input_transcription = getattr(event, "input_transcription", None)
        customer_text = None
        if input_transcription and input_transcription.finished:
            customer_text = input_transcription.text
        elif getattr(event, "author", None) == "user":
            parts = getattr(getattr(event, "content", None), "parts", None) or []
            text_parts = [part.text for part in parts if getattr(part, "text", None)]
            customer_text = "\n".join(text_parts).strip() or None
        if customer_text is not None:
            checkpoint = invocation_context.session.state.get("closeout_checkpoint")
            updated_checkpoint = apply_closeout_transcript_event(
                checkpoint,
                author="user",
                transcript=customer_text,
                event_id=event_id,
            )
            if updated_checkpoint != (checkpoint or {}):
                event.actions.state_delta["closeout_checkpoint"] = updated_checkpoint
            authorization = updated.get("workflow_authorization") or {}
            if authorization.get("status") in {"PENDING", "CONFIRMED", "UNCLEAR"}:
                prior_status = authorization.get("status")
                authorization = apply_customer_authorization_response(
                    authorization,
                    transcript=customer_text,
                    customer_event_id=event_id,
                )
                updated["workflow_authorization"] = authorization
                if authorization.get("status") != prior_status:
                    _record_proposal_transition(
                        invocation_context.session.state,
                        authorization,
                        str(authorization.get("status") or "UNKNOWN"),
                        authorization.get("invalidation_reason"),
                    )
                if authorization.get("action") == PUSH_CARD_TO_GOOGLE_WALLET:
                    updated["wallet_response_status"] = authorization.get("status")
                    updated["wallet_customer_confirmed"] = (
                        authorization.get("status") == "CONFIRMED"
                    )
                    updated["wallet_response_event_id"] = event_id
                    if authorization.get("status") in {"DECLINED", "INVALIDATED", "EXPIRED"}:
                        updated["wallet_push_offered"] = False
            else:
                updated = apply_wallet_transcript_event(
                    updated,
                    author="user",
                    transcript=customer_text,
                    event_id=event_id,
                )

        output_transcription = getattr(event, "output_transcription", None)
        if output_transcription and output_transcription.finished:
            transcript = output_transcription.text
            checkpoint = invocation_context.session.state.get("closeout_checkpoint")
            updated_checkpoint = apply_closeout_transcript_event(
                checkpoint,
                author="agent",
                transcript=transcript,
                event_id=event_id,
            )
            if updated_checkpoint != (checkpoint or {}):
                event.actions.state_delta["closeout_checkpoint"] = updated_checkpoint
            authorization = updated.get("workflow_authorization") or {}
            if agent_offered_google_wallet(transcript):
                if updated.get("replacement_card_token") and not (
                    authorization.get("action") == PUSH_CARD_TO_GOOGLE_WALLET
                    and authorization.get("status") == "CONFIRMED"
                ):
                    authorization = create_workflow_authorization(
                        action=PUSH_CARD_TO_GOOGLE_WALLET,
                        payload={
                            "card_token": updated.get("replacement_card_token"),
                            "wallet_provider": "GOOGLE_WALLET",
                        },
                        session_id=str(invocation_context.session.state.get("session_id") or ""),
                    )
                    authorization = mark_authorization_prompted(
                        authorization,
                        assistant_event_id=event_id,
                    )
                    updated["workflow_authorization"] = authorization
                updated = apply_wallet_transcript_event(
                    updated,
                    author="agent",
                    transcript=transcript,
                    event_id=event_id,
                )
            elif (
                authorization.get("action")
                in {TRIAGE_FRAUD_CASE, TRIAGE_CUSTOMER_REPORTED_FRAUD}
                and authorization.get("status") == "PREPARED"
                and assistant_requested_confirmation(transcript)
            ):
                updated["workflow_authorization"] = mark_authorization_prompted(
                    authorization,
                    assistant_event_id=event_id,
                )
                _record_proposal_transition(
                    invocation_context.session.state,
                    updated["workflow_authorization"],
                    "PRESENTED",
                )

        if updated != playbook:
            event.actions.state_delta["fraud_playbook"] = updated

        return event
