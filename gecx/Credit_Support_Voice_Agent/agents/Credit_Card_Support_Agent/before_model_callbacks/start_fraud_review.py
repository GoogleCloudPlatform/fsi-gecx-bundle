from __future__ import annotations

# CES injects LlmResponse, Content, Part, and FunctionCall into callback globals.
# ruff: noqa: F821


def _is_welcome_event(callback_context) -> bool:
    text = " ".join(
        str(part.text_or_transcript() or "")
        for part in (callback_context.get_last_user_input() or [])
    )
    return "<event>sys.welcome</event>" in text


def before_model_callback(callback_context, llm_request):
    """Route fraud-led session startup directly to the banking alert read."""
    if callback_context.variables.get("has_active_fraud_alert") is not True:
        return None
    if callback_context.variables.get("fraud_welcome_routed") is True:
        return None
    if callback_context.variables.get("active_fraud_alert_id"):
        return None
    if not _is_welcome_event(callback_context):
        return None

    callback_context.variables["fraud_welcome_routed"] = True
    return LlmResponse(
        content=Content(
            parts=[
                Part(
                    function_call=FunctionCall(
                        name="banking_service_mcp_toolset_get_open_fraud_alert",
                        args={},
                    )
                )
            ],
            role="model",
        )
    )
