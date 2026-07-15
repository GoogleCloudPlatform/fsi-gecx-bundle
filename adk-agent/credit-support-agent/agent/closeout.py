"""Deterministic voice-session closeout validation."""

from __future__ import annotations

import re


_EXPLICIT_CLOSEOUT_PATTERN = re.compile(
    r"(?:"
    r"^\s*(?:no|nope|nah)\s*[,.;!?-]*\s*(?:thank\s+you|thanks)?\s*$|"
    r"\b(?:no|nothing)\s+(?:else|more)\b|"
    r"\b(?:that(?:'|’)s|that\s+is)\s+(?:all|everything)\b|"
    r"\bi(?:'|’)m\s+(?:all\s+)?(?:set|done|good)\b|"
    r"\bi\s+am\s+(?:all\s+)?(?:set|done|good)\b|"
    r"\b(?:we(?:'|’)re|we\s+are)\s+(?:all\s+)?(?:set|done|good)\b|"
    r"\b(?:goodbye|good-bye|bye)\b|"
    r"^\s*(?:all\s+set|i(?:'|’)m\s+finished|done)\s*[,.;!?]*\s*$"
    r")",
    re.IGNORECASE,
)


def customer_explicitly_closed(transcript: str | None) -> bool:
    """Return whether the customer explicitly said no further help is needed."""
    return bool(_EXPLICIT_CLOSEOUT_PATTERN.search(transcript or ""))


def closeout_block_reason(
    *,
    latest_customer_transcript: str | None,
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
    if not customer_explicitly_closed(latest_customer_transcript):
        return "EXPLICIT_CUSTOMER_CLOSEOUT_REQUIRED"
    return None
