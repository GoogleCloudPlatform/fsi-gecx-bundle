# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
    AuthorizationPolicy,
    CapabilityRiskTier,
    DecisionPolicy,
    EvidencePolicy,
    GENERAL_ACKNOWLEDGMENT_POLICY,
    PresentationQualityGate,
    PresentationRequirement,
    ProtectedPresentationAcknowledgment,
    REQUIRED_RESTATEMENT_POLICY,
    PresentationPolicy,
    RecoveryPolicy,
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
        validator.validate_decision(
            context,
            REQUIRED_RESTATEMENT_POLICY,
            presentation_requirement=PresentationRequirement(
                required_fact_keys=frozenset({"amount", "destination"}),
                quality_gate=(
                    PresentationQualityGate.DETERMINISTIC_ACKNOWLEDGMENT
                ),
                natural_language_allowed=False,
            ),
        )

    strict = validator.validate_decision(
        context,
        REQUIRED_RESTATEMENT_POLICY,
        presentation_requirement=PresentationRequirement(
            required_fact_keys=frozenset({"amount", "destination"}),
            quality_gate=PresentationQualityGate.DETERMINISTIC_ACKNOWLEDGMENT,
            natural_language_allowed=False,
        ),
        presentation_acknowledgment=ProtectedPresentationAcknowledgment(
            acknowledgment_type="DETERMINISTIC_REQUIRED_FACTS_RENDERED",
            source="TRUSTED_RENDERER",
            acknowledged_fact_keys=frozenset({"amount", "destination"}),
            artifact_id="render-artifact-1",
        ),
    )
    assert strict.protected_evidence["presentation_acknowledgment"] == (
        "DETERMINISTIC_REQUIRED_FACTS_RENDERED"
    )
    assert strict.protected_evidence["acknowledged_fact_keys"] == [
        "amount",
        "destination",
    ]
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
    assert all(
        item.authorization_policy.risk_tier
        is CapabilityRiskTier.BOUNDED_SERVICING
        for item in specifications
    )
    assert all(
        item.presentation_requirement.quality_gate
        is PresentationQualityGate.RELEASE_EVALUATION
        and item.presentation_requirement.natural_language_allowed
        and item.presentation_requirement.required_fact_keys
        for item in specifications
    )
    assert len({type(item.handler) for item in specifications}) == 3
    assert all(item.payload_schema for item in specifications)
    assert all(item.result_schema for item in specifications)
    assert all(callable(item.scope_resolver) for item in specifications)


def test_each_tier_one_action_declares_its_required_banking_facts() -> None:
    service = ActionProposalService(db=None)
    assert service.registry.require(
        TRIAGE_FRAUD_CASE
    ).presentation_requirement.required_fact_keys == {
        "reviewed_activity_selection",
        "card_last_four",
        "proposed_disposition",
        "replacement_and_escalation_consequences",
    }
    assert service.registry.require(
        REISSUE_CARD
    ).presentation_requirement.required_fact_keys == {
        "card_last_four",
        "current_card_blocking",
        "replacement_card_form",
    }
    assert service.registry.require(
        PROVISION_GOOGLE_WALLET
    ).presentation_requirement.required_fact_keys == {
        "card_last_four",
        "wallet_provider",
        "provisioning_is_queued",
    }


@pytest.mark.parametrize(
    (
        "name",
        "presentation",
        "decision",
        "decision_source",
        "presentation_source",
        "risk_tier",
    ),
    (
        (
            "VERBATIM_DISCLOSURE_EXTENSION",
            PresentationPolicy.VERBATIM_DISCLOSURE,
            DecisionPolicy.EXPLICIT_VERBAL,
            "MODEL_TOOL_INTENT",
            "TRUSTED_RENDERER",
            CapabilityRiskTier.ELEVATED_RISK,
        ),
        (
            "EXPLICIT_UI_EXTENSION",
            PresentationPolicy.DETERMINISTIC_UI,
            DecisionPolicy.EXPLICIT_UI,
            "TRUSTED_UI_INTENT",
            "TRUSTED_UI_RENDERER",
            CapabilityRiskTier.ELEVATED_RISK,
        ),
        (
            "STEP_UP_EXTENSION",
            PresentationPolicy.TRUSTED_RENDER_ACKNOWLEDGMENT,
            DecisionPolicy.STEP_UP,
            "TRUSTED_STEP_UP_ASSERTION",
            "TRUSTED_RENDERER",
            CapabilityRiskTier.ELEVATED_RISK,
        ),
        (
            "HUMAN_APPROVAL_EXTENSION",
            PresentationPolicy.TRUSTED_RENDER_ACKNOWLEDGMENT,
            DecisionPolicy.HUMAN_APPROVAL,
            "TRUSTED_HUMAN_APPROVAL",
            "TRUSTED_RENDERER",
            CapabilityRiskTier.HUMAN_OWNED,
        ),
    ),
)
def test_stricter_policy_extension_points_are_typed_but_unregistered(
    name,
    presentation,
    decision,
    decision_source,
    presentation_source,
    risk_tier,
) -> None:
    policy = AuthorizationPolicy(
        name=name,
        risk_tier=risk_tier,
        presentation_policy=presentation,
        decision_policy=decision,
        evidence_policy=EvidencePolicy(
            accepted_sources=frozenset({decision_source}),
            required_presentation_acknowledgment="TRUSTED_PRESENTATION_RENDERED",
            accepted_presentation_acknowledgment_sources=frozenset(
                {presentation_source}
            ),
        ),
        recovery_policy=RecoveryPolicy.REPRESENT_AND_RECONFIRM,
    )
    assert policy.decision_policy is decision
    assert policy.risk_tier is risk_tier
    assert name not in ActionProposalService(db=None).registry.action_types


def test_deterministic_policy_cannot_omit_typed_acknowledgment() -> None:
    with pytest.raises(ValueError, match="typed acknowledgment"):
        AuthorizationPolicy(
            name="UNSAFE_STRICT_POLICY",
            risk_tier=CapabilityRiskTier.ELEVATED_RISK,
            presentation_policy=PresentationPolicy.VERBATIM_DISCLOSURE,
            decision_policy=DecisionPolicy.EXPLICIT_VERBAL,
            evidence_policy=EvidencePolicy(
                accepted_sources=frozenset({"MODEL_TOOL_INTENT"}),
                accepted_presentation_acknowledgment_sources=frozenset(
                    {"TRUSTED_RENDERER"}
                ),
            ),
            recovery_policy=RecoveryPolicy.ESCALATE,
        )


def test_required_restatement_rejects_partial_fact_acknowledgment() -> None:
    with pytest.raises(RuntimeContextError, match="missing required facts"):
        RuntimeEvidenceValidator().validate_decision(
            _decision_context(),
            REQUIRED_RESTATEMENT_POLICY,
            presentation_requirement=PresentationRequirement(
                required_fact_keys=frozenset({"amount", "destination"}),
                quality_gate=(
                    PresentationQualityGate.DETERMINISTIC_ACKNOWLEDGMENT
                ),
                natural_language_allowed=False,
            ),
            presentation_acknowledgment=ProtectedPresentationAcknowledgment(
                acknowledgment_type="DETERMINISTIC_REQUIRED_FACTS_RENDERED",
                source="TRUSTED_RENDERER",
                acknowledged_fact_keys=frozenset({"amount"}),
                artifact_id="render-artifact-2",
            ),
        )


def test_required_restatement_rejects_untrusted_renderer_source() -> None:
    with pytest.raises(RuntimeContextError, match="accepted trusted source"):
        RuntimeEvidenceValidator().validate_decision(
            _decision_context(),
            REQUIRED_RESTATEMENT_POLICY,
            presentation_requirement=PresentationRequirement(
                required_fact_keys=frozenset({"amount", "destination"}),
                quality_gate=(
                    PresentationQualityGate.DETERMINISTIC_ACKNOWLEDGMENT
                ),
                natural_language_allowed=False,
            ),
            presentation_acknowledgment=ProtectedPresentationAcknowledgment(
                acknowledgment_type="DETERMINISTIC_REQUIRED_FACTS_RENDERED",
                source="MODEL_ARGUMENT",
                acknowledged_fact_keys=frozenset({"amount", "destination"}),
                artifact_id="render-artifact-3",
            ),
        )


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
