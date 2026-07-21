from __future__ import annotations


def _clear_confirmation(callback_context) -> None:
    callback_context.variables["proposal_presentation_turn_id"] = ""
    callback_context.variables["proposal_confirmation_turn_id"] = ""
    callback_context.variables["proposal_confirmation_method"] = ""
    callback_context.variables["proposal_confirmation_classification"] = ""
    callback_context.variables["proposal_last_classified_turn_id"] = ""


def before_tool_callback(tool, input, callback_context):
    """Bind proposal tools to CES-owned state and fail closed before commit."""
    tool_name = str(tool.name or "")
    invocation_id = str(callback_context.invocation_id or "")

    if tool_name.endswith("propose_fraud_triage"):
        callback_context.variables["customer_turn_id"] = invocation_id
        callback_context.variables["proposal_originating_turn_id"] = invocation_id
        callback_context.variables["proposal_id"] = ""
        callback_context.variables["proposal_customer_safe_summary"] = ""
        _clear_confirmation(callback_context)
        return None

    if not tool_name.endswith("commit_fraud_triage"):
        return None

    proposal_id = str(callback_context.variables.get("proposal_id") or "")
    requested_id = str(input.get("proposal_id") or "")
    presentation_turn = str(
        callback_context.variables.get("proposal_presentation_turn_id") or ""
    )
    confirmation_turn = str(
        callback_context.variables.get("proposal_confirmation_turn_id") or ""
    )
    classification = str(
        callback_context.variables.get("proposal_confirmation_classification") or ""
    )
    method = str(
        callback_context.variables.get("proposal_confirmation_method") or ""
    )

    valid = all(
        (
            proposal_id,
            requested_id == proposal_id,
            presentation_turn,
            confirmation_turn,
            confirmation_turn != presentation_turn,
            invocation_id == confirmation_turn,
            classification == "CONFIRMED",
            method == "EXPLICIT_VERBAL",
        )
    )
    if not valid:
        return {
            "success": False,
            "error": "PROTECTED_CONFIRMATION_REQUIRED",
            "message": "A later explicit customer confirmation is required.",
        }

    callback_context.variables["customer_turn_id"] = confirmation_turn
    return None
