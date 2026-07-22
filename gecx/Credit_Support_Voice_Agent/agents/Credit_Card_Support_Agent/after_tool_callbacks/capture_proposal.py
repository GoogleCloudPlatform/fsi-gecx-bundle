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
    """Capture only a successful banking-authored proposal response."""
    tool_name = str(tool.name or "")
    if not tool_name.endswith("propose_fraud_triage"):
        return None

    payload = _payload(tool_response)
    proposal_id = str(payload.get("proposal_id") or "")
    summary = str(payload.get("customer_safe_summary") or "")
    if payload.get("success") is True and proposal_id and summary:
        callback_context.variables["proposal_id"] = proposal_id
        callback_context.variables["proposal_customer_safe_summary"] = summary
    return None
