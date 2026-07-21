from __future__ import annotations

import re


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def after_model_callback(callback_context, llm_response):
    """Record presentation only when the complete model output contains the summary."""
    if llm_response.partial is True:
        return None
    summary = str(
        callback_context.variables.get("proposal_customer_safe_summary") or ""
    )
    if not summary or callback_context.variables.get("proposal_presentation_turn_id"):
        return None

    content = llm_response.content
    parts = content.parts if content and content.parts else []
    output = " ".join(
        str(part.text_or_transcript() or "") for part in parts
    )
    if _normalized(summary) in _normalized(output):
        callback_context.variables["proposal_presentation_turn_id"] = str(
            callback_context.invocation_id or ""
        )
    return None
