from __future__ import annotations

import re


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def after_model_callback(callback_context, llm_response):
    """Ensure the customer hears the exact banking-authored proposal summary."""
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
    invocation_id = str(callback_context.invocation_id or "")
    if not invocation_id:
        return None

    callback_context.variables["proposal_presentation_turn_id"] = invocation_id
    if _normalized(summary) in _normalized(output):
        return None

    # A protected commit must not depend on the model reproducing an exact
    # banking-authored string. Replace paraphrases deterministically so the
    # recorded presentation evidence matches what the customer actually hears.
    return LlmResponse.from_parts(parts=[Part.from_text(text=summary)])
