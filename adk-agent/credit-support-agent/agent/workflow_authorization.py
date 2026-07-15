"""Typed, serializable authorization state for consequential support actions."""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any


TRIAGE_FRAUD_CASE = "TRIAGE_FRAUD_CASE"
TRIAGE_CUSTOMER_REPORTED_FRAUD = "TRIAGE_CUSTOMER_REPORTED_FRAUD"
PUSH_CARD_TO_GOOGLE_WALLET = "PUSH_CARD_TO_GOOGLE_WALLET"
DEFAULT_AUTHORIZATION_TTL_SECONDS = 180

_AFFIRMATIVE_PATTERN = re.compile(
    r"(?:^\s*(?:yes|yeah|yep|sure|absolutely|please do|do it|go ahead|that works|"
    r"sounds good|okay|ok|correct|exactly|affirmative|that(?:'|’)s right|that is right|"
    r"that(?:'|’)s correct|that is correct)\b|"
    r"\b(?:could|can|would)\s+you\s+(?:please\s+)?(?:do that|proceed|go ahead|push|add)\b|"
    r"\bthat(?: would|'d|’d) be (?:great|perfect|helpful)\b|"
    r"\bi(?:'d|’d| would) (?:like|appreciate) that\b|\bi want that\b|\blet(?:'|’)s do it\b)",
    re.IGNORECASE,
)
_DECLINE_PATTERN = re.compile(
    r"\b(?:no|nope|don't|do not|not now|never|skip it|decline|rather not|stop|incorrect|"
    r"that's wrong|that is wrong)\b",
    re.IGNORECASE,
)
_CONFIRMATION_PROMPT_PATTERN = re.compile(
    r"\b(?:confirm|is that (?:right|correct)|does that sound right|did i get that right|"
    r"are you disputing|you (?:do not|don't) recognize)\b",
    re.IGNORECASE,
)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return sorted({str(item).strip() for item in value if str(item).strip()})


def canonical_action_payload(action: str, payload: dict | None) -> dict:
    """Return only trusted, action-relevant fields in a deterministic shape."""
    payload = payload or {}
    if action in {TRIAGE_FRAUD_CASE, TRIAGE_CUSTOMER_REPORTED_FRAUD}:
        canonical = {
            "disputed_authorization_ids": _string_list(
                payload.get("disputed_authorization_ids")
            ),
            "disputed_transaction_ids": _string_list(
                payload.get("disputed_transaction_ids")
            ),
            "issue_replacement": bool(payload.get("issue_replacement", True)),
            "escalate": bool(payload.get("escalate", False)),
        }
        if action == TRIAGE_FRAUD_CASE:
            canonical["fraud_alert_id"] = str(
                payload.get("fraud_alert_id") or ""
            ).strip()
        return canonical
    if action == PUSH_CARD_TO_GOOGLE_WALLET:
        return {
            "card_token": str(payload.get("card_token") or "").strip(),
            "wallet_provider": "GOOGLE_WALLET",
        }
    raise ValueError(f"Unsupported workflow authorization action: {action}")


def action_payload_fingerprint(action: str, payload: dict | None) -> str:
    canonical = canonical_action_payload(action, payload)
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def create_workflow_authorization(
    *,
    action: str,
    payload: dict,
    session_id: str,
    now_epoch_s: float | None = None,
    ttl_seconds: int = DEFAULT_AUTHORIZATION_TTL_SECONDS,
) -> dict:
    now = time.time() if now_epoch_s is None else now_epoch_s
    canonical = canonical_action_payload(action, payload)
    return {
        "schema_version": 1,
        "action": action,
        "payload": canonical,
        "payload_fingerprint": action_payload_fingerprint(action, canonical),
        "session_id": session_id,
        "status": "PREPARED",
        "assistant_event_id": None,
        "customer_event_id": None,
        "issued_at_epoch_s": now,
        "expires_at_epoch_s": now + max(1, ttl_seconds),
        "consumed_at_epoch_s": None,
        "completed_at_epoch_s": None,
        "invalidation_reason": None,
        "invalidation_event_id": None,
    }


def assistant_requested_confirmation(transcript: str | None) -> bool:
    return bool(_CONFIRMATION_PROMPT_PATTERN.search(transcript or ""))


def classify_confirmation_response(transcript: str | None) -> str:
    text = transcript or ""
    if _DECLINE_PATTERN.search(text):
        return "DECLINED"
    if _AFFIRMATIVE_PATTERN.search(text):
        return "CONFIRMED"
    return "UNCLEAR"


def mark_authorization_prompted(
    authorization: dict | None,
    *,
    assistant_event_id: str,
    now_epoch_s: float | None = None,
) -> dict:
    updated = dict(authorization or {})
    if updated.get("status") != "PREPARED":
        return updated
    now = time.time() if now_epoch_s is None else now_epoch_s
    if now >= float(updated.get("expires_at_epoch_s") or 0):
        return invalidate_workflow_authorization(
            updated,
            reason="EXPIRED_BEFORE_PROMPT",
            event_id=assistant_event_id,
            status="EXPIRED",
        )
    updated["status"] = "PENDING"
    updated["assistant_event_id"] = assistant_event_id
    return updated


def apply_customer_authorization_response(
    authorization: dict | None,
    *,
    transcript: str | None,
    customer_event_id: str,
    now_epoch_s: float | None = None,
) -> dict:
    updated = dict(authorization or {})
    if updated.get("status") not in {"PENDING", "CONFIRMED", "UNCLEAR"}:
        return updated
    now = time.time() if now_epoch_s is None else now_epoch_s
    if now >= float(updated.get("expires_at_epoch_s") or 0):
        return invalidate_workflow_authorization(
            updated,
            reason="AUTHORIZATION_EXPIRED",
            event_id=customer_event_id,
            status="EXPIRED",
        )

    classification = classify_confirmation_response(transcript)
    if classification == "UNCLEAR" and updated.get("status") == "CONFIRMED":
        return updated
    updated["customer_event_id"] = customer_event_id
    if classification == "CONFIRMED":
        updated["status"] = "CONFIRMED"
    elif classification == "DECLINED":
        updated = invalidate_workflow_authorization(
            updated,
            reason="CUSTOMER_DECLINED",
            event_id=customer_event_id,
            status="DECLINED",
        )
    else:
        updated["status"] = "UNCLEAR"
    return updated


def invalidate_workflow_authorization(
    authorization: dict | None,
    *,
    reason: str,
    event_id: str | None = None,
    status: str = "INVALIDATED",
) -> dict:
    updated = dict(authorization or {})
    if not updated:
        return updated
    if updated.get("status") in {"COMPLETED", "DECLINED", "EXPIRED", "INVALIDATED"}:
        return updated
    updated["status"] = status
    updated["invalidation_reason"] = reason
    updated["invalidation_event_id"] = event_id
    return updated


def validate_workflow_authorization(
    authorization: dict | None,
    *,
    action: str,
    payload: dict,
    session_id: str,
    now_epoch_s: float | None = None,
) -> str | None:
    authorization = authorization or {}
    if authorization.get("action") != action:
        return f"Prepare and confirm authorization for {action} before executing it."
    if authorization.get("status") != "CONFIRMED":
        return f"Customer authorization for {action} is not confirmed."
    if authorization.get("session_id") != session_id:
        return "Customer authorization belongs to a different support session."
    if not authorization.get("assistant_event_id") or not authorization.get("customer_event_id"):
        return "Customer authorization is missing its confirmation turn evidence."
    now = time.time() if now_epoch_s is None else now_epoch_s
    if now >= float(authorization.get("expires_at_epoch_s") or 0):
        return "Customer authorization has expired. Prepare and confirm the action again."
    if authorization.get("payload_fingerprint") != action_payload_fingerprint(action, payload):
        return "The requested action differs from the exact payload the customer confirmed."
    return None


def mark_authorization_executing(
    authorization: dict,
    *,
    now_epoch_s: float | None = None,
) -> dict:
    updated = dict(authorization)
    updated["status"] = "EXECUTING"
    updated["consumed_at_epoch_s"] = time.time() if now_epoch_s is None else now_epoch_s
    return updated


def mark_authorization_completed(
    authorization: dict | None,
    *,
    now_epoch_s: float | None = None,
) -> dict:
    updated = dict(authorization or {})
    if updated.get("status") != "EXECUTING":
        return updated
    updated["status"] = "COMPLETED"
    updated["completed_at_epoch_s"] = time.time() if now_epoch_s is None else now_epoch_s
    return updated
