from __future__ import annotations

_PROPOSAL_ACTIONS = {
    "propose_fraud_triage": "TRIAGE_FRAUD_CASE",
    "propose_card_reissue": "REISSUE_CARD",
    "propose_wallet_provisioning": "PROVISION_GOOGLE_WALLET",
}
_COMMIT_ACTIONS = {
    "commit_fraud_triage": "TRIAGE_FRAUD_CASE",
    "commit_card_reissue": "REISSUE_CARD",
    "commit_wallet_provisioning": "PROVISION_GOOGLE_WALLET",
}


def _matching_action(tool_name, actions):
    for suffix, action in actions.items():
        if tool_name.endswith(suffix):
            return action
    return None


def _clear_confirmation(callback_context) -> None:
    callback_context.variables["proposal_presentation_turn_id"] = ""
    callback_context.variables["proposal_confirmation_turn_id"] = ""
    callback_context.variables["proposal_confirmation_method"] = ""
    callback_context.variables["proposal_confirmation_source"] = ""


def _has_customer_input(callback_context) -> bool:
    """Return whether CES supplied a customer turn, without interpreting it."""
    for part in callback_context.get_last_user_input() or []:
        if part.text_or_transcript():
            return True
    return False


def before_tool_callback(tool, input, callback_context):
    """Bind proposal tools to CES-owned state and fail closed before commit."""
    tool_name = str(tool.name or "")
    invocation_id = str(callback_context.invocation_id or "")

    if tool_name.endswith("offer_session_closeout"):
        callback_context.variables["customer_turn_id"] = invocation_id
        callback_context.variables["closeout_originating_turn_id"] = invocation_id
        return None

    if tool_name.endswith("end_session"):
        originating_turn = str(
            callback_context.variables.get("closeout_originating_turn_id") or ""
        )
        if (
            not originating_turn
            or not invocation_id
            or invocation_id == originating_turn
            or not _has_customer_input(callback_context)
        ):
            return {
                "success": False,
                "error": "CLOSEOUT_CHECKPOINT_REQUIRED",
                "message": "Offer final assistance and wait for a later customer turn.",
            }
        return None

    proposal_action = _matching_action(tool_name, _PROPOSAL_ACTIONS)
    if proposal_action:
        callback_context.variables["closeout_originating_turn_id"] = ""
        callback_context.variables["customer_turn_id"] = invocation_id
        callback_context.variables["proposal_originating_turn_id"] = invocation_id
        callback_context.variables["proposal_action_type"] = proposal_action
        callback_context.variables["proposal_id"] = ""
        callback_context.variables["proposal_customer_safe_summary"] = ""
        _clear_confirmation(callback_context)
        return None

    commit_action = _matching_action(tool_name, _COMMIT_ACTIONS)
    if not commit_action:
        callback_context.variables["closeout_originating_turn_id"] = ""
        return None
    callback_context.variables["closeout_originating_turn_id"] = ""

    proposal_id = str(callback_context.variables.get("proposal_id") or "")
    requested_id = str(input.get("proposal_id") or "")
    # The opaque proposal identifier is trusted workflow state captured from
    # banking, not conversational content the model should have to repeat.
    # Bind it when omitted, but reject a conflicting model-authored value.
    if proposal_id and not requested_id:
        input["proposal_id"] = proposal_id
        requested_id = proposal_id
    presentation_turn = str(
        callback_context.variables.get("proposal_presentation_turn_id") or ""
    )
    originating_turn = str(
        callback_context.variables.get("proposal_originating_turn_id") or ""
    )
    has_later_customer_turn = bool(
        presentation_turn
        and originating_turn
        and invocation_id
        and invocation_id != presentation_turn
        and invocation_id != originating_turn
        and _has_customer_input(callback_context)
    )
    if has_later_customer_turn:
        callback_context.variables["customer_turn_id"] = invocation_id
        callback_context.variables["proposal_confirmation_turn_id"] = invocation_id
        callback_context.variables["proposal_confirmation_method"] = "EXPLICIT_VERBAL"
        callback_context.variables["proposal_confirmation_source"] = (
            "MODEL_TOOL_INTENT"
        )

    valid = all(
        (
            proposal_id,
            requested_id == proposal_id,
            callback_context.variables.get("proposal_action_type") == commit_action,
            presentation_turn,
            has_later_customer_turn,
        )
    )
    if not valid:
        return {
            "success": False,
            "error": "PROTECTED_CONFIRMATION_REQUIRED",
            "message": "A later explicit customer confirmation is required.",
        }
    return None
