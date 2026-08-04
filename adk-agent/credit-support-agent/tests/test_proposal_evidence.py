# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

from agent.proposal_evidence import (
    AWAITING_DECISION,
    COMMIT_IN_FLIGHT,
    COMMIT_RETRY,
    DECISION_ATTESTED,
    attest_model_decision,
    create_pending_proposal,
    mark_commit_in_flight,
    mark_commit_retry,
    mark_proposal_presented,
    proposal_evidence_error,
)


def test_projection_contains_no_banking_payload_lifecycle_or_expiry() -> None:
    proposal = create_pending_proposal(
        proposal_id="proposal-1",
        action_type="REISSUE_CARD",
        contract_version="card-reissue.v1",
        originating_customer_turn_id="customer-1",
    )
    assert set(proposal).isdisjoint(
        {
            "payload",
            "payload_fingerprint",
            "expires_at",
            "expires_at_epoch_s",
            "session_id",
            "status",
        }
    )


def test_later_turn_evidence_and_same_opaque_id_retry_are_preserved() -> None:
    proposal = create_pending_proposal(
        proposal_id="proposal-1",
        action_type="REISSUE_CARD",
        contract_version="card-reissue.v1",
        originating_customer_turn_id="customer-1",
    )
    proposal = mark_proposal_presented(
        proposal,
        assistant_turn_id="assistant-2",
        observed_at_epoch_s=2,
    )
    assert proposal["evidence_state"] == AWAITING_DECISION
    proposal = attest_model_decision(
        proposal,
        proposal_id="proposal-1",
        action_type="REISSUE_CARD",
        customer_turn_id="customer-3",
        customer_observed_at_epoch_s=3,
    )
    assert proposal["evidence_state"] == DECISION_ATTESTED
    assert (
        proposal_evidence_error(
            proposal,
            proposal_id="proposal-1",
            action_type="REISSUE_CARD",
        )
        is None
    )

    in_flight = mark_commit_in_flight(proposal)
    assert in_flight["evidence_state"] == COMMIT_IN_FLIGHT
    retry = mark_commit_retry(in_flight, reason="COMMIT_RESULT_PENDING")
    assert retry["evidence_state"] == COMMIT_RETRY
    assert retry["presentation_turn_id"] == "assistant-2"
    assert retry["confirmation_turn_id"] == "customer-3"


def test_wrong_opaque_id_or_non_later_turn_fails_closed() -> None:
    proposal = create_pending_proposal(
        proposal_id="proposal-1",
        action_type="REISSUE_CARD",
        contract_version="card-reissue.v1",
        originating_customer_turn_id="customer-1",
    )
    proposal = mark_proposal_presented(
        proposal,
        assistant_turn_id="assistant-2",
        observed_at_epoch_s=2,
    )
    unchanged = attest_model_decision(
        proposal,
        proposal_id="proposal-other",
        action_type="REISSUE_CARD",
        customer_turn_id="customer-3",
        customer_observed_at_epoch_s=3,
    )
    assert unchanged["evidence_state"] == AWAITING_DECISION
    assert proposal_evidence_error(
        unchanged,
        proposal_id="proposal-other",
        action_type="REISSUE_CARD",
    )
