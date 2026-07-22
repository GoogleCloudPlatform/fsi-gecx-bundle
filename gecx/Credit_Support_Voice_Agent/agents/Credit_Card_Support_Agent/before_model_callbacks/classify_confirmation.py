from __future__ import annotations

import re


AFFIRMATIVE_PHRASES = {
    "confirm",
    "confirmed",
    "correct",
    "go ahead",
    "i can confirm",
    "i confirm",
    "please do",
    "proceed",
    "that is correct",
    "thats correct",
    "yes",
    "yes i can confirm",
    "yes i confirm",
    "yes please",
}

DECLINED_PHRASES = {
    "cancel",
    "do not",
    "dont",
    "no",
    "no thanks",
    "no thank you",
    "stop",
    "thats wrong",
}


def _normalized_customer_text(callback_context) -> str:
    values = []
    for part in callback_context.get_last_user_input() or []:
        value = part.text_or_transcript()
        if value:
            values.append(str(value))
    text = " ".join(values).lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace("'", "")


def _classification(text: str) -> str:
    if text in AFFIRMATIVE_PHRASES:
        return "CONFIRMED"
    if text in DECLINED_PHRASES:
        return "DECLINED"
    return "UNCLEAR"


def before_model_callback(callback_context, llm_request):
    """Classify at most one later customer turn using a strict explicit grammar."""
    proposal_id = str(callback_context.variables.get("proposal_id") or "")
    presentation_turn = str(
        callback_context.variables.get("proposal_presentation_turn_id") or ""
    )
    invocation_id = str(callback_context.invocation_id or "")
    if not proposal_id or not presentation_turn or not invocation_id:
        return None
    if invocation_id == presentation_turn:
        return None
    if invocation_id == str(
        callback_context.variables.get("proposal_last_classified_turn_id") or ""
    ):
        return None

    customer_text = _normalized_customer_text(callback_context)
    if not customer_text:
        return None

    classification = _classification(customer_text)
    callback_context.variables["customer_turn_id"] = invocation_id
    callback_context.variables["proposal_confirmation_turn_id"] = invocation_id
    callback_context.variables["proposal_confirmation_method"] = "EXPLICIT_VERBAL"
    callback_context.variables["proposal_confirmation_classification"] = classification
    callback_context.variables["proposal_last_classified_turn_id"] = invocation_id
    return None
