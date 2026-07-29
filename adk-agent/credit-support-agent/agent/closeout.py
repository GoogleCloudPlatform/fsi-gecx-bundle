"""Transport-attested voice-session closeout checkpoints."""

from __future__ import annotations

import time


_OPEN_CLOSEOUT_STATUSES = {"OFFERED"}


def open_closeout_checkpoint(
    *,
    originating_customer_event_id: str,
    now_epoch_s: float | None = None,
) -> dict:
    """Record the model's typed choice to offer final assistance."""
    return {
        "status": "OFFERED",
        "originating_customer_event_id": originating_customer_event_id,
        "offered_at_epoch_s": time.time() if now_epoch_s is None else now_epoch_s,
        "customer_event_id": None,
    }


def invalidate_closeout_checkpoint(checkpoint: dict | None, *, reason: str) -> dict:
    """Invalidate an open checkpoint when another action intervenes."""
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
    latest_customer_turn: dict | None,
) -> str | None:
    """Validate only action state and later-turn provenance, never transcript text."""
    authorization_status = (workflow_authorization or {}).get("status")
    if authorization_status in {
        "PREPARED",
        "PENDING",
        "CONFIRMED",
        "EXECUTING",
        "RECOVERY_REQUIRED",
    }:
        return f"WORKFLOW_AUTHORIZATION_{authorization_status}"

    checkpoint = closeout_checkpoint or {}
    if checkpoint.get("status") != "OFFERED":
        return "CLOSEOUT_OFFER_REQUIRED"
    latest = latest_customer_turn or {}
    latest_event_id = str(latest.get("event_id") or "")
    if not latest_event_id:
        return "CLOSEOUT_CUSTOMER_TURN_REQUIRED"
    if latest_event_id == str(checkpoint.get("originating_customer_event_id") or ""):
        return "LATER_CLOSEOUT_CUSTOMER_TURN_REQUIRED"
    if float(latest.get("observed_at_epoch_s") or 0) <= float(
        checkpoint.get("offered_at_epoch_s") or 0
    ):
        return "LATER_CLOSEOUT_CUSTOMER_TURN_REQUIRED"
    return None
