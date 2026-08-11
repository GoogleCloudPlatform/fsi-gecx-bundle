# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Reject standby handoffs that lack a trusted closeout checkpoint."""


def before_agent_callback(callback_context):
    variables = callback_context.variables
    checkpoint_state = str(variables.get("closeout_checkpoint_state") or "")
    if checkpoint_state == "FAREWELL_READY":
        continuation_authorized = bool(
            variables.get("closeout_delegation_authorized")
            and variables.get("closeout_farewell_ready")
            and not str(variables.get("proposal_id") or "")
            and not bool(variables.get("proposal_commit_attempted"))
        )
        variables["closeout_delegation_authorized"] = continuation_authorized
        if continuation_authorized:
            return None
    authorized = bool(
        variables.get("closeout_delegation_authorized")
        and checkpoint_state == "OFFERED"
        and not str(variables.get("proposal_id") or "")
        and not bool(variables.get("proposal_commit_attempted"))
    )
    variables["closeout_delegation_authorized"] = authorized
    variables["closeout_end_attempted"] = False
    variables["closeout_farewell_ready"] = False
    variables["closeout_playout_acknowledged"] = False
    if authorized:
        return None
    return Content(  # noqa: F821
        parts=[
            Part.from_agent_transfer(  # noqa: F821
                agent="Credit Card Support Agent"
            )
        ]
    )
