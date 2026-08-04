# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""CES closeout checkpoints, intentionally separate from proposal evidence."""


def _has_customer_input(callback_context) -> bool:
    for part in callback_context.get_last_user_input() or []:
        if part.text_or_transcript():
            return True
    return False


def before_tool_callback(tool, input, callback_context):
    tool_name = str(tool.name or "")
    invocation_id = str(callback_context.invocation_id or "")
    if tool_name.endswith("offer_session_closeout"):
        if str(callback_context.variables.get("proposal_id") or ""):
            return {
                "success": False,
                "error": "PROPOSAL_DECISION_REQUIRED",
                "message": "Resolve the current proposal before offering closeout.",
            }
        callback_context.variables["customer_turn_id"] = invocation_id
        callback_context.variables["closeout_originating_turn_id"] = invocation_id
        return None
    if not tool_name.endswith("end_session"):
        callback_context.variables["closeout_originating_turn_id"] = ""
        return None
    originating_turn = str(
        callback_context.variables.get("closeout_originating_turn_id") or ""
    )
    if (
        not originating_turn
        or not invocation_id
        or invocation_id == originating_turn
        or not _has_customer_input(callback_context)
    ):
        return {
            "success": False,
            "error": "CLOSEOUT_CHECKPOINT_REQUIRED",
            "message": "Offer final assistance and wait for a later customer turn.",
        }
    return None
