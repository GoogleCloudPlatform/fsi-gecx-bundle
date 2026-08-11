# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Mark a complete farewell turn without terminating its audio stream."""


def _is_end_session_call(part) -> bool:
    has_function_call = getattr(part, "has_function_call", None)
    if callable(has_function_call) and has_function_call("end_session"):
        return True
    function_call = getattr(part, "function_call", None)
    return str(getattr(function_call, "name", "") or "").endswith(
        "end_session"
    )


def after_model_callback(callback_context, llm_response):
    variables = callback_context.variables
    if bool(variables.get("closeout_end_attempted")):
        return None
    if not bool(variables.get("closeout_delegation_authorized")):
        return None

    content = getattr(llm_response, "content", None)
    parts = getattr(content, "parts", None)
    if parts is None:
        return None

    retained_parts = [part for part in parts if not _is_end_session_call(part)]
    has_spoken_text = any(
        bool(str(getattr(part, "text", "") or "").strip())
        for part in retained_parts
    )
    if not has_spoken_text:
        parts[:] = retained_parts
        return None

    variables["closeout_checkpoint_state"] = "FAREWELL_READY"
    variables["closeout_farewell_ready"] = True
    variables["closeout_playout_acknowledged"] = False
    # Mutate rather than replace the streamed response so CES does not replay
    # native Gemini Live audio through a second TTS path. The proxy identifies
    # this turn from CES diagnostic agent metadata at turn completion.
    parts[:] = retained_parts
    return None
