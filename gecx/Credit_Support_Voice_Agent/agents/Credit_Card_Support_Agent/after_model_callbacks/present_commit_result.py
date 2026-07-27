from __future__ import annotations

# CES injects LlmResponse and Part into callback globals.
# ruff: noqa: F821


def after_model_callback(callback_context, llm_response):
    """Present only banking-authored fraud outcome language after commit."""
    if llm_response.partial is True:
        return None
    if callback_context.variables.get("fraud_result_pending") is not True:
        return None
    summary = str(
        callback_context.variables.get("fraud_customer_safe_result_summary") or ""
    ).strip()
    if not summary:
        return None

    callback_context.variables["fraud_result_pending"] = False
    return LlmResponse.from_parts(
        parts=[
            Part.from_text(
                text=f"{summary} Is there anything else I can help you with today?"
            )
        ]
    )
