# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""CES closeout checkpoints, intentionally separate from proposal evidence."""

import hashlib


def _customer_input_fingerprint(callback_context) -> str:
    """Return an opaque identity for the callback-owned customer input."""
    digest = hashlib.sha256()
    part_count = 0
    for part in callback_context.get_last_user_input() or []:
        value = str(part.text_or_transcript() or "")
        if not value:
            continue
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        part_count += 1
    return digest.hexdigest() if part_count else ""


def _clear_closeout_checkpoint(callback_context) -> None:
    callback_context.variables["closeout_checkpoint_state"] = ""
    callback_context.variables["closeout_originating_turn_id"] = ""
    callback_context.variables["closeout_originating_input_fingerprint"] = ""
    callback_context.variables["closeout_delegation_authorized"] = False


def _later_customer_turn_is_present(callback_context) -> bool:
    """Validate turn ordering while the parent still owns customer input."""
    variables = callback_context.variables
    if str(variables.get("closeout_checkpoint_state") or "") != "OFFERED":
        return False
    originating_turn = str(variables.get("closeout_originating_turn_id") or "")
    originating_input = str(
        variables.get("closeout_originating_input_fingerprint") or ""
    )
    invocation_id = str(callback_context.invocation_id or "")
    current_input = _customer_input_fingerprint(callback_context)
    if not current_input:
        return False
    return bool(
        (invocation_id and originating_turn and invocation_id != originating_turn)
        or (originating_input and current_input != originating_input)
        or not originating_input
    )


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
        input_fingerprint = _customer_input_fingerprint(callback_context)
        originating_turn = str(
            callback_context.variables.get("customer_turn_id") or invocation_id
        )
        # The MCP transport projects this protected variable into the required
        # x-customer-turn-id header. Non-proposal servicing paths do not set it
        # elsewhere, so bind it at the closeout-offer boundary.
        callback_context.variables["customer_turn_id"] = invocation_id
        callback_context.variables["closeout_checkpoint_state"] = "OFFERED"
        callback_context.variables["closeout_originating_turn_id"] = originating_turn
        callback_context.variables["closeout_originating_input_fingerprint"] = (
            input_fingerprint
        )
        callback_context.variables["closeout_delegation_authorized"] = False
        return None
    if (
        tool_name.endswith("transfer_to_agent")
        and str(input.get("agent_name") or "") == "Session Closeout Agent"
    ):
        # The after-model callback emits the second, structural transfer after
        # this callback has authorized the handoff. Allow that transfer through
        # without revalidating customer input that the continuation no longer
        # owns.
        if (
            bool(callback_context.variables.get("closeout_delegation_authorized"))
            and str(
                callback_context.variables.get("closeout_checkpoint_state") or ""
            )
            == "OFFERED"
            and not str(callback_context.variables.get("proposal_id") or "")
            and not bool(callback_context.variables.get("proposal_commit_attempted"))
        ):
            return None
        if (
            str(callback_context.variables.get("proposal_id") or "")
            or bool(callback_context.variables.get("proposal_commit_attempted"))
            or not _later_customer_turn_is_present(callback_context)
        ):
            callback_context.variables["closeout_delegation_authorized"] = False
            return {
                "success": False,
                "error": "CLOSEOUT_HANDOFF_NOT_READY",
                "message": "Offer final assistance and wait for a later customer turn.",
            }
        # This is the last callback boundary that reliably owns the later
        # customer input. The child trusts the persisted typed checkpoint
        # because CES does not expose that input to its before-agent callback.
        callback_context.variables["closeout_delegation_authorized"] = True
        # Consume the model's first transfer as a local authorization result.
        # The resulting model continuation is replaced with a native transfer
        # by the after-model callback, activating the child in this same turn.
        return {
            "success": True,
            "status": "CLOSEOUT_HANDOFF_AUTHORIZED",
        }
    if not tool_name.endswith("end_session"):
        _clear_closeout_checkpoint(callback_context)
        return None
    checkpoint_state = str(
        callback_context.variables.get("closeout_checkpoint_state") or ""
    )
    originating_turn = str(
        callback_context.variables.get("closeout_originating_turn_id") or ""
    )
    originating_input = str(
        callback_context.variables.get("closeout_originating_input_fingerprint") or ""
    )
    current_input = _customer_input_fingerprint(callback_context)
    distinct_callback_turn = bool(
        invocation_id and originating_turn and invocation_id != originating_turn
    )
    distinct_customer_input = bool(
        current_input and originating_input and current_input != originating_input
    )
    customer_input_arrived_after_offer = bool(current_input and not originating_input)
    if (
        checkpoint_state != "OFFERED"
        or not current_input
        or not (
            distinct_callback_turn
            or distinct_customer_input
            or customer_input_arrived_after_offer
        )
    ):
        return {
            "success": False,
            "error": "CLOSEOUT_CHECKPOINT_REQUIRED",
            "message": "Offer final assistance and wait for a later customer turn.",
        }
    callback_context.variables["closeout_checkpoint_state"] = "ENDING"
    return None
