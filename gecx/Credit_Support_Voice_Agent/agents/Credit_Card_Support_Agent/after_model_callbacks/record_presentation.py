from __future__ import annotations


def after_model_callback(callback_context, llm_response):
    """Record proposal presentation evidence without replacing native audio."""
    if llm_response.partial is True:
        return None
    if not callback_context.variables.get("proposal_id"):
        return None
    if callback_context.variables.get("proposal_presentation_turn_id"):
        return None

    content = llm_response.content
    parts = content.parts if content and content.parts else []
    output = " ".join(
        str(part.text_or_transcript() or "") for part in parts
    ).strip()
    invocation_id = str(callback_context.invocation_id or "")
    if not output or not invocation_id:
        return None

    callback_context.variables["proposal_presentation_turn_id"] = invocation_id
    return None
