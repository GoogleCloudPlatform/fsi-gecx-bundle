from __future__ import annotations

import re


AFFIRMATIVE_PHRASES = {
    "absolutely",
    "approve",
    "confirm",
    "confirmed",
    "correct",
    "do it",
    "go ahead",
    "i can firm",
    "i can confirm",
    "i confirm",
    "lets do it",
    "please do",
    "proceed",
    "sounds good",
    "sounds right",
    "that is correct",
    "that is what i want",
    "that would be great",
    "thats correct",
    "thats what i want",
    "yes that would be great",
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

DECLINE_PATTERN = re.compile(
    r"\b(?:cancel|decline|do not|dont|no|not|stop|wait|wrong)\b"
)

AFFIRMATIVE_PATTERN = re.compile(
    r"(?:"
    r"^(?:yes|correct|confirmed|absolutely|certainly|sure)\b"
    r"|\b(?:i|we)\s+(?:can\s+|do\s+)?confirm\b"
    r"|\b(?:i|we)\s+(?:approve|agree|consent)\b"
    r"|\b(?:that|it)\s+(?:is|sounds)\s+(?:correct|good|right)\b"
    r"|\b(?:that|it)(?:s|\s+is)\s+what\s+i\s+want\b"
    r"|\b(?:go ahead|please do|proceed|do it|lets do it)\b"
    r")"
)


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
    # A negative or qualification always wins over an affirmative token. This
    # keeps phrases such as "yes, but don't block the card" from authorizing
    # the immutable proposal.
    if text in DECLINED_PHRASES or DECLINE_PATTERN.search(text):
        return "DECLINED"
    if text in AFFIRMATIVE_PHRASES or AFFIRMATIVE_PATTERN.search(text):
        return "CONFIRMED"

    # Customers may confirm by restating the complete protected fraud action
    # instead of using a magic word. Require all three action concepts so a
    # partial request cannot authorize the proposal.
    disputes_activity = bool(re.search(r"\bdisput(?:e|ing)\b", text))
    blocks_card = bool(re.search(r"\bblock(?:ed|ing)?\b", text)) and bool(
        re.search(r"\bcard\b", text)
    )
    replaces_card = bool(
        re.search(r"\b(?:replacement|replace|replaced|replacing|reissue|reissued)\b", text)
    )
    if disputes_activity and blocks_card and replaces_card:
        return "CONFIRMED"
    return "UNCLEAR"


def before_model_callback(callback_context, llm_request):
    """Classify one later customer turn with a bounded semantic grammar."""
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
