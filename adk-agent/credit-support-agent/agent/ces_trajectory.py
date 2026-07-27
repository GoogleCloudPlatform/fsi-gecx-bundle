"""Normalize CES conversation resources into runtime-neutral trajectory events."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Iterable


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _elapsed_ms(value: str | None, start: datetime | None) -> float:
    current = _timestamp(value)
    if current is None or start is None:
        return 0.0
    return round((current - start).total_seconds() * 1000, 3)


def _tool_name(payload: dict[str, Any]) -> str:
    toolset_tool = payload.get("toolsetTool") or {}
    name = toolset_tool.get("toolId") or payload.get("tool") or ""
    return str(name).rsplit("/", 1)[-1]


def _tool_outputs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_outputs = (payload.get("response") or {}).get("text_output") or []
    outputs: list[dict[str, Any]] = []
    for raw in raw_outputs:
        if isinstance(raw, dict):
            outputs.append(raw)
            continue
        if not isinstance(raw, str):
            continue
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            outputs.append(decoded)
    return outputs


def _messages(conversation: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for turn in conversation.get("turns") or []:
        yield from turn.get("messages") or []


def normalize_ces_conversation(
    conversation: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return ordered contract events without retaining tool arguments or identifiers."""
    start = _timestamp(conversation.get("startTime"))
    events: list[dict[str, Any]] = []
    session_started = False
    guidance_recorded = False
    presented_turn_id: str | None = None
    confirmation_state: str | None = None
    proposal_committed = False
    saw_end_session = False

    for message in _messages(conversation):
        elapsed_ms = _elapsed_ms(message.get("eventTime"), start)
        role = str(message.get("role") or "")
        for chunk in message.get("chunks") or []:
            updated = chunk.get("updatedVariables")
            if isinstance(updated, dict):
                if not session_started and updated.get("runtime_name"):
                    events.append(
                        {
                            "type": "SESSION_STARTED",
                            "reset_generation": updated.get("reset_generation"),
                            "runtime_name": updated.get("runtime_name"),
                            "runtime_version": conversation.get("appVersion")
                            or updated.get("ces_version_or_deployment_id"),
                            "deployment": conversation.get("deployment"),
                            "elapsed_ms": elapsed_ms,
                        }
                    )
                    session_started = True

                review_stage = updated.get("fraud_review_stage")
                if review_stage:
                    ready = bool(updated.get("fraud_review_ready")) or (
                        str(review_stage).upper() == "READY_TO_PROPOSE"
                    )
                    events.append(
                        {
                            "type": "FRAUD_REVIEW",
                            "stage": str(review_stage),
                            "ready_to_propose": ready,
                            "elapsed_ms": elapsed_ms,
                        }
                    )

                current_presented = updated.get("proposal_presentation_turn_id")
                if current_presented and current_presented != presented_turn_id:
                    events.append(
                        {
                            "type": "ACTION_PROPOSAL",
                            "outcome": "PRESENTED",
                            "elapsed_ms": elapsed_ms,
                        }
                    )
                    presented_turn_id = str(current_presented)

                current_confirmation = str(
                    updated.get("proposal_confirmation_classification") or ""
                ).upper()
                if (
                    current_confirmation
                    and current_confirmation != "UNCLASSIFIED"
                    and current_confirmation != confirmation_state
                    and not proposal_committed
                ):
                    outcome = {
                        "EXPLICIT_CONFIRMATION": "CONFIRMED",
                        "CONFIRMED": "CONFIRMED",
                        "EXPLICIT_DECLINE": "DECLINED",
                        "DECLINED": "DECLINED",
                        "AMBIGUOUS": "UNCLEAR",
                        "UNCLEAR": "UNCLEAR",
                    }.get(current_confirmation, current_confirmation)
                    events.append(
                        {
                            "type": "ACTION_PROPOSAL",
                            "outcome": outcome,
                            "elapsed_ms": elapsed_ms,
                        }
                    )
                    confirmation_state = current_confirmation

            transcript = chunk.get("transcript")
            if isinstance(transcript, str) and transcript.strip():
                events.append(
                    {
                        "type": "TRANSCRIPT",
                        "author": "customer" if role == "user" else "agent",
                        "text": transcript,
                        "elapsed_ms": elapsed_ms,
                    }
                )

            tool_call = chunk.get("toolCall")
            if isinstance(tool_call, dict):
                tool = _tool_name(tool_call)
                if tool == "end_session":
                    saw_end_session = True
                else:
                    events.append(
                        {
                            "type": "TOOL_CALL",
                            "tool": tool,
                            "elapsed_ms": elapsed_ms,
                        }
                    )

            tool_response = chunk.get("toolResponse")
            if not isinstance(tool_response, dict):
                continue
            tool = _tool_name(tool_response)
            outputs = _tool_outputs(tool_response)
            output = outputs[-1] if outputs else {}
            success = output.get("success") is True
            events.append(
                {
                    "type": "TOOL_RESULT",
                    "tool": tool,
                    "success": success,
                    "elapsed_ms": elapsed_ms,
                }
            )

            guidance = output.get("support_guidance")
            if isinstance(guidance, dict) and not guidance_recorded:
                events.append(
                    {
                        "type": "GUIDANCE_SNAPSHOT",
                        "source": guidance.get("source") or "knowledge_catalog",
                        "topic_ids": guidance.get("topic_ids") or [],
                        "snapshot_id": guidance.get("snapshot_id"),
                        "content_version": guidance.get("content_version"),
                        "elapsed_ms": elapsed_ms,
                    }
                )
                guidance_recorded = True

            status = str(output.get("status") or "").upper()
            contract_version = output.get("contract_version")
            if tool == "propose_fraud_triage" and success:
                events.append(
                    {
                        "type": "ACTION_PROPOSAL",
                        "outcome": status or "PROPOSED",
                        "contract_version": contract_version,
                        "elapsed_ms": elapsed_ms,
                    }
                )
            elif tool == "commit_fraud_triage":
                if success:
                    events.append(
                        {
                            "type": "ACTION_PROPOSAL",
                            "outcome": status or "COMMITTED",
                            "contract_version": contract_version,
                            "banking_outcome": output.get("outcome"),
                            "elapsed_ms": elapsed_ms,
                        }
                    )
                    proposal_committed = True
                else:
                    error_outcome = {
                        "EXPIRED": "EXPIRED",
                        "INVALIDATED": "INVALIDATED",
                    }.get(status, "TOOL_ERROR")
                    events.append(
                        {
                            "type": "ACTION_PROPOSAL",
                            "outcome": error_outcome,
                            "contract_version": contract_version,
                            "elapsed_ms": elapsed_ms,
                        }
                    )

    if not session_started:
        events.insert(
            0,
            {
                "type": "SESSION_STARTED",
                "reset_generation": None,
                "runtime_name": None,
                "runtime_version": conversation.get("appVersion"),
                "deployment": conversation.get("deployment"),
                "elapsed_ms": 0.0,
            },
        )
    end = _timestamp(conversation.get("endTime"))
    duration_ms = (
        round((end - start).total_seconds() * 1000, 3)
        if end is not None and start is not None
        else 0.0
    )
    events.append(
        {
            "type": "SESSION_ENDED",
            "outcome": "NORMAL_DISCONNECT" if saw_end_session else "UNEXPECTED_DISCONNECT",
            "elapsed_ms": duration_ms,
        }
    )
    return events


def safe_conversation_identity(conversation: dict[str, Any]) -> dict[str, Any]:
    """Return resource provenance safe to persist in qualification artifacts."""
    return {
        "conversation": conversation.get("name"),
        "source": conversation.get("source"),
        "start_time": conversation.get("startTime"),
        "end_time": conversation.get("endTime"),
        "turn_count": conversation.get("turnCount"),
        "channel_type": conversation.get("channelType"),
        "language_code": conversation.get("languageCode"),
        "app_version": conversation.get("appVersion"),
        "deployment": conversation.get("deployment"),
    }
