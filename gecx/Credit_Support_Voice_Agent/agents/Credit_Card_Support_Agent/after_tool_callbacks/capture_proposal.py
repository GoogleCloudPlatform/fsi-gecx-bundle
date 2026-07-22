from __future__ import annotations


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

    if not tool_name.endswith("propose_fraud_triage"):
        return None

    proposal_id = str(payload.get("proposal_id") or "")
    summary = str(payload.get("customer_safe_summary") or "")
    if payload.get("success") is True and proposal_id and summary:
        callback_context.variables["proposal_id"] = proposal_id
        callback_context.variables["proposal_customer_safe_summary"] = summary
        callback_context.variables["fraud_selection_pending"] = False
    return None
