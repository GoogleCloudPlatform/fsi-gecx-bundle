"""Deterministic voice-session closeout validation."""

from __future__ import annotations

import re


_EXPLICIT_CLOSEOUT_PATTERN = re.compile(
    r"(?:"
    r"^\s*(?:no|nope|nah)\s*[,.;!?-]*\s*(?:thank\s+you|thanks)?\s*$|"
    r"\b(?:no|nothing)\s+(?:else|more)\b|"
    r"\b(?:that(?:'|’)s|that\s+is)\s+(?:all|everything)\b|"
    r"\b(?:that(?:'|’)s|that\s+is)\s+(?:about\s+)?it\b|"
    r"\b(?:that(?:'|’)ll|that\s+will)\s+be\s+all\b|"
    r"\bi(?:'|’)m\s+(?:all\s+)?(?:set|done|good)\b|"
    r"\bi\s+am\s+(?:all\s+)?(?:set|done|good)\b|"
    r"\b(?:we(?:'|’)re|we\s+are)\s+(?:all\s+)?(?:set|done|good)\b|"
    r"\b(?:goodbye|good-bye|bye)\b|"
    r"^\s*(?:all\s+set|i(?:'|’)m\s+finished|done)\s*[,.;!?]*\s*$"
    r")",
    re.IGNORECASE,
)

_CLOSEOUT_PROMPT_PATTERN = re.compile(
    r"(?:"
    r"\b(?:is there|do you (?:have|need)|would you like)\b.{0,80}"
    r"\b(?:anything|something)\s+(?:else|more)\b|"
    r"\b(?:can|may)\s+i\b.{0,50}\bhelp\b.{0,40}"
    r"\b(?:anything|something)\s+(?:else|more)\b|"
    r"\b(?:anything|something)\s+(?:else|more)\b.{0,50}\b(?:help|assist)\b"
    r")",
    re.IGNORECASE,
)

_OPEN_CLOSEOUT_STATUSES = {"PENDING", "CONFIRMED"}


def customer_explicitly_closed(transcript: str | None) -> bool:
    """Return whether the customer explicitly said no further help is needed."""
    return bool(_EXPLICIT_CLOSEOUT_PATTERN.search(transcript or ""))


def assistant_requested_closeout(transcript: str | None) -> bool:
    """Return whether the agent explicitly opened the final closeout checkpoint."""
    return bool(_CLOSEOUT_PROMPT_PATTERN.search(transcript or ""))


def apply_closeout_transcript_event(
    checkpoint: dict | None,
    *,
    author: str,
    transcript: str | None,
    event_id: str,
) -> dict:
    """Advance closeout consent using ordered, finalized ADK transcript events."""
    current = dict(checkpoint or {})
    if author == "agent":
        if not assistant_requested_closeout(transcript):
            return current
        return {
            "status": "PENDING",
            "assistant_event_id": event_id,
            "customer_event_id": None,
        }

    if author != "user" or current.get("status") not in _OPEN_CLOSEOUT_STATUSES:
        return current
    current["customer_event_id"] = event_id
    current["status"] = (
        "CONFIRMED" if customer_explicitly_closed(transcript) else "CONTINUE"
    )
    return current


def invalidate_closeout_checkpoint(checkpoint: dict | None, *, reason: str) -> dict:
    """Invalidate stale closeout consent when another tool action intervenes."""
    current = dict(checkpoint or {})
    if current.get("status") not in _OPEN_CLOSEOUT_STATUSES:
        return current
    current["status"] = "INVALIDATED"
    current["invalidation_reason"] = reason
    return current


def closeout_block_reason(
    *,
    closeout_checkpoint: dict | None,
    workflow_authorization: dict | None,
) -> str | None:
    """Return a stable reason when the model tries to end too early."""
    authorization_status = (workflow_authorization or {}).get("status")
    if authorization_status in {
        "PREPARED",
        "PENDING",
        "CONFIRMED",
        "UNCLEAR",
        "EXECUTING",
    }:
        return f"WORKFLOW_AUTHORIZATION_{authorization_status}"
    checkpoint = closeout_checkpoint or {}
    if checkpoint.get("status") != "CONFIRMED":
        return "EXPLICIT_CUSTOMER_CLOSEOUT_REQUIRED"
    if not checkpoint.get("assistant_event_id") or not checkpoint.get(
        "customer_event_id"
    ):
        return "CLOSEOUT_TURN_EVIDENCE_REQUIRED"
    return None
