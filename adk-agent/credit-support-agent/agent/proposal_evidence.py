# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Minimal ADK projection of banking-owned action-proposal evidence.

This module deliberately does not copy the proposal payload, fingerprint,
expiry, session scope, or durable lifecycle. Banking owns those values. ADK
retains only opaque identity, protected turn ordering, and the checkpoint
needed to retry the same commit after an uncertain transport result.
"""

from __future__ import annotations


AWAITING_PRESENTATION = "AWAITING_PRESENTATION"
AWAITING_DECISION = "AWAITING_DECISION"
DECISION_ATTESTED = "DECISION_ATTESTED"
COMMIT_IN_FLIGHT = "COMMIT_IN_FLIGHT"
COMMIT_RETRY = "COMMIT_RETRY"

UNRESOLVED_EVIDENCE_STATES = frozenset(
    {
        AWAITING_PRESENTATION,
        AWAITING_DECISION,
        DECISION_ATTESTED,
        COMMIT_IN_FLIGHT,
        COMMIT_RETRY,
    }
)


def create_pending_proposal(
    *,
    proposal_id: str,
    action_type: str,
    contract_version: str,
    originating_customer_turn_id: str | None,
) -> dict:
    """Project one successful banking proposal response into ADK state."""
    return {
        "schema_version": 1,
        "proposal_id": str(proposal_id),
        "action_type": str(action_type),
        "contract_version": str(contract_version),
        "evidence_state": AWAITING_PRESENTATION,
        "originating_customer_turn_id": str(originating_customer_turn_id or ""),
        "presentation_turn_id": None,
        "presentation_observed_at_epoch_s": None,
        "confirmation_turn_id": None,
        "recovery_attempt_count": 0,
        "recovery_reason": None,
    }


def mark_proposal_presented(
    projection: dict | None,
    *,
    assistant_turn_id: str,
    observed_at_epoch_s: float,
) -> dict:
    updated = dict(projection or {})
    if updated.get("evidence_state") != AWAITING_PRESENTATION:
        return updated
    updated["evidence_state"] = AWAITING_DECISION
    updated["presentation_turn_id"] = str(assistant_turn_id)
    updated["presentation_observed_at_epoch_s"] = float(observed_at_epoch_s)
    return updated


def attest_model_decision(
    projection: dict | None,
    *,
    proposal_id: str,
    action_type: str,
    customer_turn_id: str,
    customer_observed_at_epoch_s: float,
) -> dict:
    """Bind typed model intent to protected later-turn evidence only."""
    updated = dict(projection or {})
    if updated.get("evidence_state") in {
        DECISION_ATTESTED,
        COMMIT_IN_FLIGHT,
        COMMIT_RETRY,
    }:
        return updated
    if updated.get("evidence_state") != AWAITING_DECISION:
        return updated
    if str(updated.get("proposal_id") or "") != str(proposal_id):
        return updated
    if str(updated.get("action_type") or "") != str(action_type):
        return updated
    customer_turn_id = str(customer_turn_id or "")
    if not customer_turn_id:
        return updated
    if customer_turn_id in {
        str(updated.get("originating_customer_turn_id") or ""),
        str(updated.get("presentation_turn_id") or ""),
    }:
        return updated
    presented_at = float(updated.get("presentation_observed_at_epoch_s") or 0)
    if not presented_at or float(customer_observed_at_epoch_s or 0) <= presented_at:
        return updated
    updated["evidence_state"] = DECISION_ATTESTED
    updated["confirmation_turn_id"] = customer_turn_id
    return updated


def proposal_evidence_error(
    projection: dict | None,
    *,
    proposal_id: str,
    action_type: str,
) -> str | None:
    projection = projection or {}
    if str(projection.get("proposal_id") or "") != str(proposal_id or ""):
        return "The opaque proposal id does not match the current proposal."
    if str(projection.get("action_type") or "") != str(action_type or ""):
        return "The current proposal belongs to a different action."
    if projection.get("evidence_state") not in {
        DECISION_ATTESTED,
        COMMIT_RETRY,
    }:
        return "A protected later customer decision turn is required."
    if not projection.get("presentation_turn_id") or not projection.get(
        "confirmation_turn_id"
    ):
        return "Protected proposal presentation and decision evidence is required."
    return None


def mark_commit_in_flight(projection: dict | None) -> dict:
    updated = dict(projection or {})
    if updated.get("evidence_state") == COMMIT_RETRY:
        updated["recovery_attempt_count"] = (
            int(updated.get("recovery_attempt_count") or 0) + 1
        )
    if updated.get("evidence_state") in {DECISION_ATTESTED, COMMIT_RETRY}:
        updated["evidence_state"] = COMMIT_IN_FLIGHT
        updated["recovery_reason"] = None
    return updated


def mark_commit_retry(projection: dict | None, *, reason: str) -> dict:
    updated = dict(projection or {})
    if updated.get("evidence_state") == COMMIT_IN_FLIGHT:
        updated["evidence_state"] = COMMIT_RETRY
        updated["recovery_reason"] = str(reason)
    return updated


def require_re_presentation(projection: dict | None) -> dict:
    """Retain only the same opaque proposal identity for fresh evidence."""
    updated = dict(projection or {})
    if not updated:
        return updated
    updated["evidence_state"] = AWAITING_PRESENTATION
    updated["presentation_turn_id"] = None
    updated["presentation_observed_at_epoch_s"] = None
    updated["confirmation_turn_id"] = None
    updated["recovery_reason"] = None
    return updated
