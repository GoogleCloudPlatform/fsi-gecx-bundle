# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Finish the spoken turn and defer native termination until playout drains."""


_COMPLETE_TOOL_SUFFIX = "complete_consultation"
_END_REASON = "customer_query_ended"


def _function_call(part):
    return getattr(part, "function_call", None)


def _is_complete_consultation_call(part) -> bool:
    call = _function_call(part)
    return str(getattr(call, "name", "") or "").endswith(
        _COMPLETE_TOOL_SUFFIX
    )


def _call_reason(part) -> str:
    call = _function_call(part)
    args = getattr(call, "args", None)
    if isinstance(args, dict):
        return str(args.get("reason") or "")
    get = getattr(args, "get", None)
    if callable(get):
        return str(get("reason") or "")
    return ""


def after_model_callback(callback_context, llm_response):
    """Convert only a trusted wrapper call after streamed farewell output."""
    variables = callback_context.variables
    authorized = bool(
        variables.get("closeout_delegation_authorized")
        and str(variables.get("closeout_checkpoint_state") or "") == "OFFERED"
        and not str(variables.get("proposal_id") or "")
        and not bool(variables.get("proposal_commit_attempted"))
        and not bool(variables.get("closeout_end_attempted"))
    )
    if not authorized:
        return None

    content = getattr(llm_response, "content", None)
    parts = getattr(content, "parts", None)
    if parts is None:
        return None

    wrapper_indexes = [
        index
        for index, part in enumerate(parts)
        if _is_complete_consultation_call(part)
    ]
    if len(wrapper_indexes) != 1:
        return None

    wrapper_index = wrapper_indexes[0]
    if _call_reason(parts[wrapper_index]) != _END_REASON:
        return None

    # Gemini Live streams farewell text/audio before emitting a tool-only model
    # response. Replace that tool chunk with a non-spoken payload so the wrapper
    # never executes and the already-streamed farewell can complete normally.
    # The gateway releases the separate native terminal turn after playout.
    variables["closeout_checkpoint_state"] = "FAREWELL_READY"
    variables["closeout_farewell_ready"] = True
    variables["closeout_playout_acknowledged"] = False
    return LlmResponse.from_parts(  # noqa: F821
        parts=[Part.from_json(data='{"status":"FAREWELL_READY"}')]  # noqa: F821
    )
