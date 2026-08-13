# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Advance callback-owned closeout state without inspecting generated text."""


def after_model_callback(callback_context, llm_response):
    """Complete an action-response checkpoint or an authorized handoff."""
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
        str(variables.get("closeout_checkpoint_state") or "")
        == "OFFER_PENDING"
        and not str(variables.get("proposal_id") or "")
        and not bool(variables.get("proposal_commit_attempted"))
    ):
        # The successful tool callback opened the checkpoint. Reaching the
        # follow-on model response is the structural evidence that the action
        # result/final-assistance turn was generated. Its wording is not read.
        variables["closeout_checkpoint_state"] = "OFFERED"
    return None
