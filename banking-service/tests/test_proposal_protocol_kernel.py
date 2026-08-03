# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Contract tests for the internal runtime-neutral proposal kernel."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from services.action_proposal_context import ProposalRuntimeContext, RuntimeContextError
from services.action_proposals import (
    ActionProposalService,
    PROVISION_GOOGLE_WALLET,
    REISSUE_CARD,
    TRIAGE_FRAUD_CASE,
)
from services.proposal_protocol import (
    GENERAL_ACKNOWLEDGMENT_POLICY,
    REQUIRED_RESTATEMENT_POLICY,
    PresentationPolicy,
    RuntimeEvidenceValidator,
)


def _decision_context() -> ProposalRuntimeContext:
    return ProposalRuntimeContext(
        support_session_id="support-kernel",
        runtime_name="CONTRACT_RUNTIME",
        runtime_session_id="runtime-kernel",
        customer_turn_id="customer-decision",
        reset_generation="1:0",
        presentation_turn_id="assistant-presentation",
        confirmation_turn_id="customer-decision",
        confirmation_method="EXPLICIT_VERBAL",
        confirmation_source="MODEL_TOOL_INTENT",
    )


def test_evidence_validator_distinguishes_authorization_profiles() -> None:
    validator = RuntimeEvidenceValidator()
    context = _decision_context()

    general = validator.validate_decision(context, GENERAL_ACKNOWLEDGMENT_POLICY)
    assert general.protected_evidence["source"] == "MODEL_TOOL_INTENT"
    assert (
        GENERAL_ACKNOWLEDGMENT_POLICY.presentation_policy
        is PresentationPolicy.FLEXIBLE_SUMMARY
    )

    with pytest.raises(RuntimeContextError, match="presentation acknowledgment"):
        validator.validate_decision(context, REQUIRED_RESTATEMENT_POLICY)

    strict = validator.validate_decision(
        context,
        REQUIRED_RESTATEMENT_POLICY,
        additional_evidence={
            "presentation_acknowledgment": (
                "DETERMINISTIC_REQUIRED_FACTS_RENDERED"
            )
        },
    )
    assert strict.protected_evidence["presentation_acknowledgment"] == (
        "DETERMINISTIC_REQUIRED_FACTS_RENDERED"
    )
    assert (
        REQUIRED_RESTATEMENT_POLICY.presentation_policy
        is PresentationPolicy.REQUIRED_FACT_RESTATEMENT
    )


def test_current_actions_are_explicitly_registered_on_one_policy() -> None:
    service = ActionProposalService(db=None)

    assert service.registry.action_types == {
        TRIAGE_FRAUD_CASE,
        REISSUE_CARD,
        PROVISION_GOOGLE_WALLET,
    }
    specifications = tuple(
        service.registry.require(action_type)
        for action_type in service.registry.action_types
    )
    assert all(
        item.authorization_policy is GENERAL_ACKNOWLEDGMENT_POLICY
        for item in specifications
    )
    assert len({type(item.handler) for item in specifications}) == 3
    assert all(item.payload_schema for item in specifications)
    assert all(item.result_schema for item in specifications)
    assert all(callable(item.scope_resolver) for item in specifications)


def test_lifecycle_engine_has_no_registered_domain_action_branches() -> None:
    source_path = (
        Path(__file__).parents[1] / "services" / "proposal_lifecycle.py"
    )
    tree = ast.parse(source_path.read_text())
    names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }
    assert names.isdisjoint(
        {"TRIAGE_FRAUD_CASE", "REISSUE_CARD", "PROVISION_GOOGLE_WALLET"}
    )
