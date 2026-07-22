from __future__ import annotations

import re

# CES injects LlmResponse, Content, Part, and FunctionCall into callback globals.
# ruff: noqa: F821


ALL_DISPUTED = re.compile(
    r"^(?:"
    r"no(?:pe)?(?:\s+i\s+(?:do\s+not|dont))?"
    r"|none(?:\s+of\s+(?:them|those|these))?"
    r"|(?:all|every)(?:\s+of)?\s+(?:them|those|these)"
    r"|i\s+(?:do\s+not|dont)\s+recognize\s+(?:any|all|them|those|these|the\s+transactions?)"
    r")$"
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


def _ids(value) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def before_model_callback(callback_context, llm_request):
    """Force the catalog-defined transition for a clear all-disputed answer."""
    if callback_context.variables.get("proposal_id"):
        return None
    if callback_context.variables.get("fraud_selection_pending") is not True:
        return None

    prompt_turn = str(
        callback_context.variables.get("fraud_selection_prompt_turn_id") or ""
    )
    invocation_id = str(callback_context.invocation_id or "")
    alert_id = str(callback_context.variables.get("active_fraud_alert_id") or "")
    if not prompt_turn or not invocation_id or invocation_id == prompt_turn or not alert_id:
        return None

    customer_text = _normalized_customer_text(callback_context)
    if not ALL_DISPUTED.fullmatch(customer_text):
        return None

    authorization_ids = _ids(
        callback_context.variables.get("active_fraud_authorization_ids")
    )
    transaction_ids = _ids(
        callback_context.variables.get("active_fraud_transaction_ids")
    )
    if not authorization_ids and not transaction_ids:
        return None

    callback_context.variables["fraud_selection_pending"] = False
    return LlmResponse(
        content=Content(
            parts=[
                Part(
                    function_call=FunctionCall(
                        name="propose_fraud_triage",
                        args={
                            "fraud_alert_id": alert_id,
                            "disputed_authorization_ids": authorization_ids,
                            "disputed_transaction_ids": transaction_ids,
                            "issue_replacement": True,
                            "escalate": False,
                        },
                    )
                )
            ],
            role="model",
        )
    )
