from __future__ import annotations

import re


def after_model_callback(callback_context, llm_response):
    """Bind a recognition question to the next completed customer turn."""
    if llm_response.partial is True:
        return None
    if callback_context.variables.get("proposal_id"):
        return None
    if not callback_context.variables.get("active_fraud_alert_id"):
        return None

    content = llm_response.content
    parts = content.parts if content and content.parts else []
    output = " ".join(str(part.text_or_transcript() or "") for part in parts)
    normalized = re.sub(r"\s+", " ", output).strip().lower()
    if "recogniz" not in normalized or "?" not in output:
        return None

    invocation_id = str(callback_context.invocation_id or "")
    if invocation_id:
        callback_context.variables["fraud_selection_prompt_turn_id"] = invocation_id
        callback_context.variables["fraud_selection_pending"] = True
    return None
