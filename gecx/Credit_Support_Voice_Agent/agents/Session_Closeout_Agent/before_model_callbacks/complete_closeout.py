# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Emit native termination only after the gateway confirms farewell playout."""


_PLAYOUT_COMPLETE_EVENT = "<event>sys.closeout_playout_complete</event>"


def _is_playout_complete_event(callback_context) -> bool:
    for part in callback_context.get_last_user_input() or []:
        if str(part.text_or_transcript() or "") == _PLAYOUT_COMPLETE_EVENT:
            return True
    return False


def before_model_callback(callback_context, llm_request):
    if not _is_playout_complete_event(callback_context):
        return None

    variables = callback_context.variables
    authorized = bool(
        variables.get("closeout_delegation_authorized")
        and variables.get("closeout_farewell_ready")
        and str(variables.get("closeout_checkpoint_state") or "")
        == "FAREWELL_READY"
        and not str(variables.get("proposal_id") or "")
        and not bool(variables.get("proposal_commit_attempted"))
        and not bool(variables.get("closeout_end_attempted"))
    )
    if not authorized:
        return None

    variables["closeout_checkpoint_state"] = "ENDING"
    variables["closeout_playout_acknowledged"] = True
    variables["closeout_end_attempted"] = True
    return LlmResponse.from_parts(  # noqa: F821
        parts=[Part.from_end_session(reason="customer_query_ended")]  # noqa: F821
    )
