# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Reject standby handoffs that lack a trusted closeout checkpoint."""


def before_agent_callback(callback_context):
    variables = callback_context.variables
    checkpoint_state = str(variables.get("closeout_checkpoint_state") or "")
    authorized = bool(
        variables.get("closeout_delegation_authorized")
        and checkpoint_state == "OFFERED"
        and not str(variables.get("proposal_id") or "")
        and not bool(variables.get("proposal_commit_attempted"))
    )
    variables["closeout_delegation_authorized"] = authorized
    if authorized:
        return None
    return Content(  # noqa: F821
        parts=[
            Part.from_agent_transfer(  # noqa: F821
                agent="Credit Card Support Agent"
            )
        ]
    )
