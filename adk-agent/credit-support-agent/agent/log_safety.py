"""Bounded, non-sensitive summaries for voice workflow telemetry."""

from __future__ import annotations

import hashlib
from typing import Any


EXPECTED_TOOL_CHECKPOINT_STATUSES = {
    "AUTHORIZATION_REQUIRED",
    "SESSION_CLOSE_CONFIRMATION_REQUIRED",
}


def stable_log_reference(value: Any, *, prefix: str = "ref") -> str | None:
    """Return a stable, non-reversible reference suitable for correlation logs."""
    if value in (None, ""):
        return None
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def tool_args_log_summary(tool_name: str, args: dict | None) -> dict[str, Any]:
    args = args or {}
    summary: dict[str, Any] = {"keys": sorted(args.keys())}
    if "disputed_authorization_ids" in args:
        summary["disputed_authorization_count"] = len(
            args.get("disputed_authorization_ids") or []
        )
    if "disputed_transaction_ids" in args:
        summary["disputed_transaction_count"] = len(
            args.get("disputed_transaction_ids") or []
        )
    for key in ("issue_replacement", "escalate", "wallet_provider"):
        if key in args:
            summary[key] = args[key]
    if tool_name == "push_card_to_google_wallet":
        summary["trusted_card_token_present"] = bool(args.get("card_token"))
    return summary


def tool_result_log_summary(tool_response: Any) -> dict[str, Any]:
    if not isinstance(tool_response, dict):
        return {"response_type": type(tool_response).__name__}
    structured = tool_response.get("structuredContent")
    summary: dict[str, Any] = {
        "is_error": bool(tool_response.get("isError")),
        "status": tool_response.get("status"),
        "structured": isinstance(structured, dict),
    }
    if isinstance(structured, dict):
        summary.update(
            {
                "success": structured.get("success"),
                "outcome": structured.get("outcome"),
                "voided_authorization_count": len(
                    structured.get("voided_authorizations") or []
                ),
                "provisional_credit_count": len(
                    structured.get("provisional_credits") or []
                ),
                "replacement_card_issued": bool(
                    structured.get("replacement_card")
                ),
                "secure_message_sent": bool(structured.get("secure_message")),
                "wallet_provisioning_status": structured.get(
                    "wallet_provisioning_status"
                ),
            }
        )
    elif tool_response.get("error"):
        # MCP error strings are provider-controlled and can include request
        # values. Preserve only the failure signal in operational logs.
        summary["error_present"] = True
    return {key: value for key, value in summary.items() if value is not None}


def tool_response_succeeded(tool_name: str, tool_response: Any) -> bool:
    """Classify execution success without confusing an empty domain result."""
    if not isinstance(tool_response, dict):
        return False
    if tool_response.get("isError") is True or tool_response.get("error"):
        return False
    if tool_response.get("status") == "SUCCESS":
        return True
    if "success" in tool_response:
        return tool_response.get("success") is True
    structured = tool_response.get("structuredContent")
    if not isinstance(structured, dict):
        return False
    if structured.get("isError") is True or structured.get("error"):
        return False
    if tool_name == "get_open_fraud_alert" and "fraud_alert" in structured:
        # No alert is a valid read result and is the entry condition for the
        # customer-reported fraud workflow.
        return True
    if "success" in structured:
        return structured.get("success") is True
    return True


def tool_response_is_expected_checkpoint(tool_response: Any) -> bool:
    """Return whether a blocked local tool call is an expected control checkpoint."""
    return bool(
        isinstance(tool_response, dict)
        and tool_response.get("status") in EXPECTED_TOOL_CHECKPOINT_STATUSES
        and tool_response.get("isError") is not True
    )
