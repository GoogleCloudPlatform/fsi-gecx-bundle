"""Validation and acknowledgement protocol for LiveKit typed customer turns."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any


CUSTOMER_TEXT_INPUT = "CUSTOMER_TEXT_INPUT"
CUSTOMER_TEXT_ACCEPTED = "CUSTOMER_TEXT_ACCEPTED"
CUSTOMER_TEXT_REJECTED = "CUSTOMER_TEXT_REJECTED"
MAX_TYPED_MESSAGE_LENGTH = 1000
_MESSAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


@dataclass(frozen=True)
class CustomerTextMessage:
    message_id: str
    text: str


class TypedInputError(ValueError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def validate_typed_turn_availability(
    *,
    tool_processing: bool,
    voice_input_active: bool,
    typed_turn_active: bool,
    runtime_transition_active: bool,
    session_ending: bool,
    human_handoff_active: bool,
) -> None:
    """Serialize typed turns with voice, tools, terminal state, and handoff."""
    if tool_processing:
        raise TypedInputError(
            "TOOL_IN_PROGRESS",
            "The current account action is still processing. Try again in a moment.",
            retryable=True,
        )
    if voice_input_active:
        raise TypedInputError(
            "VOICE_INPUT_ACTIVE",
            "Finish the current spoken message before sending typed input.",
            retryable=True,
        )
    if typed_turn_active:
        raise TypedInputError(
            "TURN_IN_PROGRESS",
            "Wait for the current assistant response before sending another message.",
            retryable=True,
        )
    if runtime_transition_active:
        raise TypedInputError(
            "RUNTIME_TRANSITION",
            "The consultation is switching to voice-only mode. Try again in a moment.",
            retryable=True,
        )
    if session_ending:
        raise TypedInputError("SESSION_ENDING", "This consultation is ending.")
    if human_handoff_active:
        raise TypedInputError(
            "HUMAN_HANDOFF_ACTIVE",
            "Typed AI messages are unavailable during a representative handoff.",
        )


def parse_customer_text_packet(
    data: bytes,
    *,
    participant_identity: str | None,
    expected_identity: str,
    seen_message_ids: set[str],
) -> CustomerTextMessage | None:
    try:
        payload: dict[str, Any] = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
        raise TypedInputError("INVALID_PAYLOAD", "Typed input was not valid JSON.") from error
    if payload.get("type") != CUSTOMER_TEXT_INPUT:
        return None
    if participant_identity != expected_identity:
        raise TypedInputError("UNAUTHORIZED_PARTICIPANT", "Typed input was rejected.")
    message_id = str(payload.get("message_id") or "").strip()
    if not _MESSAGE_ID_PATTERN.fullmatch(message_id):
        raise TypedInputError("INVALID_MESSAGE_ID", "Typed input message id is invalid.")
    text = str(payload.get("text") or "").strip()
    if not text:
        raise TypedInputError("EMPTY_MESSAGE", "Type a message before sending.")
    if len(text) > MAX_TYPED_MESSAGE_LENGTH:
        raise TypedInputError(
            "MESSAGE_TOO_LONG",
            f"Typed messages are limited to {MAX_TYPED_MESSAGE_LENGTH} characters.",
        )
    if message_id in seen_message_ids:
        raise TypedInputError("DUPLICATE_MESSAGE", "This message was already accepted.")
    return CustomerTextMessage(message_id=message_id, text=text)


def typed_input_ack(
    *,
    message_id: str | None,
    accepted: bool,
    code: str | None = None,
    message: str | None = None,
    retryable: bool = False,
) -> str:
    return json.dumps(
        {
            "type": CUSTOMER_TEXT_ACCEPTED if accepted else CUSTOMER_TEXT_REJECTED,
            "message_id": message_id,
            "code": code,
            "message": message,
            "retryable": retryable,
        }
    )
