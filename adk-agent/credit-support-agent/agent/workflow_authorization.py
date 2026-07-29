"""Typed, serializable authorization state for consequential support actions."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any


TRIAGE_FRAUD_CASE = "TRIAGE_FRAUD_CASE"
TRIAGE_CUSTOMER_REPORTED_FRAUD = "TRIAGE_CUSTOMER_REPORTED_FRAUD"
REISSUE_CARD = "REISSUE_CARD"
PROVISION_GOOGLE_WALLET = "PROVISION_GOOGLE_WALLET"
DEFAULT_AUTHORIZATION_TTL_SECONDS = 180


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
    if action == REISSUE_CARD:
        return {
            "reason": str(payload.get("reason") or "").strip().upper(),
        }
    if action == PROVISION_GOOGLE_WALLET:
        return {
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
    originating_customer_event_id: str | None = None,
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
        "originating_customer_event_id": originating_customer_event_id,
        "assistant_event_id": None,
        "customer_event_id": None,
        "presented_at_epoch_s": None,
        "confirmation_source": None,
        "issued_at_epoch_s": now,
        "expires_at_epoch_s": now + max(1, ttl_seconds),
        "consumed_at_epoch_s": None,
        "completed_at_epoch_s": None,
        "invalidation_reason": None,
        "invalidation_event_id": None,
    }


def mark_authorization_presented(
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
    updated["presented_at_epoch_s"] = now
    return updated


def authorize_from_model_tool_intent(
    authorization: dict | None,
    *,
    action: str,
    payload: dict,
    session_id: str,
    customer_event_id: str,
    customer_observed_at_epoch_s: float,
    now_epoch_s: float | None = None,
) -> dict:
    """Bind the model's typed commit choice to protected later-turn evidence.

    This function deliberately has no transcript argument. The conversational
    model owns semantic interpretation by choosing the consequential tool. This
    deterministic adapter validates only action identity, immutable payload,
    session scope, proposal presentation, turn ordering, and expiry.
    """
    updated = dict(authorization or {})
    if updated.get("status") == "CONFIRMED":
        return updated
    if updated.get("status") != "PENDING":
        return updated
    now = time.time() if now_epoch_s is None else now_epoch_s
    if now >= float(updated.get("expires_at_epoch_s") or 0):
        return invalidate_workflow_authorization(
            updated,
            reason="AUTHORIZATION_EXPIRED",
            event_id=customer_event_id,
            status="EXPIRED",
        )
    if updated.get("action") != action or updated.get("session_id") != session_id:
        return updated
    if updated.get("payload_fingerprint") != action_payload_fingerprint(
        action, payload
    ):
        return updated
    if not customer_event_id:
        return updated
    if customer_event_id == updated.get("originating_customer_event_id"):
        return updated
    if customer_event_id == updated.get("assistant_event_id"):
        return updated
    presented_at = float(updated.get("presented_at_epoch_s") or 0)
    if not presented_at or customer_observed_at_epoch_s <= presented_at:
        return updated
    updated["customer_event_id"] = customer_event_id
    updated["status"] = "CONFIRMED"
    updated["confirmation_source"] = "MODEL_TOOL_INTENT"
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
    if not authorization.get("assistant_event_id") or not authorization.get(
        "customer_event_id"
    ):
        return "Customer authorization is missing its confirmation turn evidence."
    now = time.time() if now_epoch_s is None else now_epoch_s
    if now >= float(authorization.get("expires_at_epoch_s") or 0):
        return (
            "Customer authorization has expired. Prepare and confirm the action again."
        )
    if authorization.get("payload_fingerprint") != action_payload_fingerprint(
        action, payload
    ):
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
    updated["completed_at_epoch_s"] = (
        time.time() if now_epoch_s is None else now_epoch_s
    )
    return updated
