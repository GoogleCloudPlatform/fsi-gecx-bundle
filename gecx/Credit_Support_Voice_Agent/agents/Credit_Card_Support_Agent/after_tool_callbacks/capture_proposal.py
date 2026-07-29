from __future__ import annotations

_PROPOSAL_ACTIONS = {
    "propose_fraud_triage": "TRIAGE_FRAUD_CASE",
    "propose_card_reissue": "REISSUE_CARD",
    "propose_wallet_provisioning": "PROVISION_GOOGLE_WALLET",
}
_COMMIT_TOOLS = {
    "commit_fraud_triage",
    "commit_card_reissue",
    "commit_wallet_provisioning",
}


def _payload(tool_response):
    if not isinstance(tool_response, dict):
        return {}
    output = tool_response.get("output")
    if isinstance(output, dict):
        return output
    text_output = tool_response.get("text_output")
    if isinstance(text_output, list) and text_output:
        first = text_output[0]
        if isinstance(first, dict):
            return first
    return tool_response


def _clear_current_proposal(callback_context) -> None:
    """Clear CES' projection only after banking resolves the proposal."""
    callback_context.variables["proposal_id"] = ""
    callback_context.variables["proposal_customer_safe_summary"] = ""
    callback_context.variables["proposal_action_type"] = ""
    callback_context.variables["proposal_originating_turn_id"] = ""
    callback_context.variables["proposal_presentation_turn_id"] = ""
    callback_context.variables["proposal_confirmation_turn_id"] = ""
    callback_context.variables["proposal_confirmation_method"] = ""
    callback_context.variables["proposal_confirmation_source"] = ""
    callback_context.variables["proposal_decision_type"] = ""


def after_tool_callback(tool, input, callback_context, tool_response):
    """Capture banking-owned alert state and successful proposal responses."""
    tool_name = str(tool.name or "")
    payload = _payload(tool_response)

    if tool_name.endswith("get_open_fraud_alert"):
        alert = payload.get("fraud_alert")
        if payload.get("success") is True and isinstance(alert, dict):
            alert_id = str(alert.get("fraud_alert_id") or "")
            suspicious = alert.get("suspicious_transactions") or []
            authorization_ids = []
            transaction_ids = []
            for item in suspicious:
                if not isinstance(item, dict):
                    continue
                authorization_id = str(item.get("authorization_id") or "")
                transaction_id = str(item.get("transaction_id") or "")
                if authorization_id:
                    authorization_ids.append(authorization_id)
                if transaction_id:
                    transaction_ids.append(transaction_id)
            if alert_id and (authorization_ids or transaction_ids):
                callback_context.variables["active_fraud_alert_id"] = alert_id
                callback_context.variables["active_fraud_authorization_ids"] = ",".join(
                    authorization_ids
                )
                callback_context.variables["active_fraud_transaction_ids"] = ",".join(
                    transaction_ids
                )
        return None

    if tool_name.endswith("review_fraud_selection"):
        if payload.get("success") is True:
            fingerprint = str(payload.get("selection_fingerprint") or "")
            previous = str(
                callback_context.variables.get("fraud_review_fingerprint") or ""
            )
            callback_context.variables["fraud_review_stage"] = str(
                payload.get("stage") or ""
            )
            callback_context.variables["fraud_review_status"] = str(
                payload.get("selection_status") or ""
            )
            callback_context.variables["fraud_review_fingerprint"] = fingerprint
            callback_context.variables["fraud_review_ready"] = bool(
                payload.get("ready_to_propose")
            )
            if previous and fingerprint and previous != fingerprint:
                callback_context.variables["proposal_id"] = ""
                callback_context.variables["proposal_customer_safe_summary"] = ""
        return None

    commit_tool = next(
        (suffix for suffix in _COMMIT_TOOLS if tool_name.endswith(suffix)),
        None,
    )
    if commit_tool is not None:
        if payload.get("success") is True:
            _clear_current_proposal(callback_context)
            if commit_tool == "commit_fraud_triage":
                callback_context.variables["fraud_review_stage"] = "COMMITTED"
        return None

    if tool_name.endswith("decide_action_proposal"):
        if payload.get("success") is True:
            _clear_current_proposal(callback_context)
            if str(payload.get("action_type") or "") == "TRIAGE_FRAUD_CASE":
                callback_context.variables["fraud_review_stage"] = str(
                    payload.get("status") or ""
                )
                callback_context.variables["fraud_review_ready"] = False
        return None

    proposal_action = next(
        (
            action
            for suffix, action in _PROPOSAL_ACTIONS.items()
            if tool_name.endswith(suffix)
        ),
        None,
    )
    if proposal_action is None:
        return None

    proposal_id = str(payload.get("proposal_id") or "")
    summary = str(payload.get("customer_safe_summary") or "")
    if payload.get("success") is True and proposal_id and summary:
        invocation_id = str(callback_context.invocation_id or "")
        callback_context.variables["customer_turn_id"] = invocation_id
        callback_context.variables["proposal_originating_turn_id"] = invocation_id
        callback_context.variables["proposal_action_type"] = proposal_action
        callback_context.variables["proposal_id"] = proposal_id
        callback_context.variables["proposal_customer_safe_summary"] = summary
        # CES persists after-tool state reliably across invocations. Record the
        # protected proposal-producing invocation here; a commit must still
        # arrive from a different, later customer invocation. Presentation
        # quality is evaluated externally and generated text is never reparsed.
        callback_context.variables["proposal_presentation_turn_id"] = invocation_id
        if tool_name.endswith("propose_fraud_triage"):
            callback_context.variables["fraud_review_stage"] = (
                "AWAITING_ACTION_CONFIRMATION"
            )
            callback_context.variables["fraud_review_status"] = "COMPLETE"
            callback_context.variables["fraud_review_ready"] = True
    return None
