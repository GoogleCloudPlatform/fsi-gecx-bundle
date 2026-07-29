from __future__ import annotations


def after_model_callback(callback_context, llm_response):
    """Record the completed assistant turn associated with an active proposal.

    The callback intentionally does not inspect generated text. Conversation
    quality is evaluated outside the production authorization path. The
    workflow gate needs only protected evidence that the proposal-producing
    invocation completed an assistant turn before a later customer invocation.
    """
    if llm_response.partial is True:
        return None
    if not callback_context.variables.get("proposal_id"):
        return None
    if callback_context.variables.get("proposal_presentation_turn_id"):
        return None

    content = llm_response.content
    parts = content.parts if content and content.parts else []
    has_output = any(part.text_or_transcript() for part in parts)
    invocation_id = str(callback_context.invocation_id or "")
    if not has_output or not invocation_id:
        return None

    callback_context.variables["proposal_presentation_turn_id"] = invocation_id
    return None
