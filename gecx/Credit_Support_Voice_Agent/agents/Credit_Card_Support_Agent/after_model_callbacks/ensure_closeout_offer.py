# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Append a required closeout-offer call without replaying native audio."""


_OFFER_TOOL = "banking_service_mcp_toolset_offer_session_closeout"


def _has_offer_call(parts) -> bool:
    for part in parts:
        has_function_call = getattr(part, "has_function_call", None)
        if callable(has_function_call) and has_function_call(_OFFER_TOOL):
            return True
        function_call = getattr(part, "function_call", None)
        if str(getattr(function_call, "name", "") or "").endswith(
            "offer_session_closeout"
        ):
            return True
    return False


def after_model_callback(callback_context, llm_response):
    """Repair a missing offer or complete an authorized native handoff."""
    variables = callback_context.variables
    content = getattr(llm_response, "content", None)
    parts = getattr(content, "parts", None)
    if parts is None:
        return None
    if bool(variables.get("closeout_delegation_authorized")):
        # Suppress the parent's continuation and make the handoff structural.
        # Only the closeout child is allowed to generate farewell audio.
        parts[:] = [
            Part.from_agent_transfer(  # noqa: F821
                agent="Session Closeout Agent"
            )
        ]
        return None
    if (
        not bool(variables.get("closeout_offer_required"))
        or str(variables.get("proposal_id") or "")
        or bool(variables.get("proposal_commit_attempted"))
    ):
        return None
    # Mutate the pending response and return None. Returning a replacement
    # would replay already-streamed Gemini Live audio through CES TTS.
    if not _has_offer_call(parts):
        parts.append(  # noqa: F821
            Part.from_function_call(  # noqa: F821
                name=_OFFER_TOOL,
                args={},
            )
        )
    return None
