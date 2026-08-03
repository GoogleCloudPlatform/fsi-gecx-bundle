# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Internal contracts for the banking-owned action proposal protocol.

The types in this module describe policy and domain-handler seams. They are
internal Banking Service contracts, not a cross-service SDK or MCP surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Mapping, Protocol

from models.action_proposal import ActionProposal
from services.action_proposal_context import ProposalRuntimeContext, RuntimeContextError


class PresentationPolicy(StrEnum):
    FLEXIBLE_SUMMARY = "FLEXIBLE_SUMMARY"
    REQUIRED_FACT_RESTATEMENT = "REQUIRED_FACT_RESTATEMENT"
    VERBATIM_DISCLOSURE = "VERBATIM_DISCLOSURE"
    DETERMINISTIC_UI = "DETERMINISTIC_UI"
    TRUSTED_RENDER_ACKNOWLEDGMENT = "TRUSTED_RENDER_ACKNOWLEDGMENT"


class DecisionPolicy(StrEnum):
    NONE = "NONE"
    EXPLICIT_VERBAL = "EXPLICIT_VERBAL"
    EXPLICIT_UI = "EXPLICIT_UI"
    STEP_UP = "STEP_UP"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"


class RecoveryPolicy(StrEnum):
    RETRY_SAME_PROPOSAL = "RETRY_SAME_PROPOSAL"
    REPRESENT_AND_RECONFIRM = "REPRESENT_AND_RECONFIRM"
    REPLACE_AFTER_DISPOSITION = "REPLACE_AFTER_DISPOSITION"
    ESCALATE = "ESCALATE"


class RecoveryClass(StrEnum):
    """Stable model-safe recovery actions returned by the protocol boundary."""

    CORRECT_REQUEST = "CORRECT_REQUEST"
    RETRY_SAME_PROPOSAL = "RETRY_SAME_PROPOSAL"
    RESOLVE_ACTIVE_PROPOSAL = "RESOLVE_ACTIVE_PROPOSAL"
    REPRESENT_AND_RECONFIRM = "REPRESENT_AND_RECONFIRM"
    CREATE_NEW_PROPOSAL = "CREATE_NEW_PROPOSAL"
    REFRESH_SESSION = "REFRESH_SESSION"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class EvidencePolicy:
    accepted_sources: frozenset[str]
    require_later_customer_turn: bool = True
    required_presentation_acknowledgment: str | None = None


@dataclass(frozen=True)
class AuthorizationPolicy:
    name: str
    presentation_policy: PresentationPolicy
    decision_policy: DecisionPolicy
    evidence_policy: EvidencePolicy
    recovery_policy: RecoveryPolicy

    @property
    def durable_confirmation_policy(self) -> str:
        """Return the existing database value without changing the schema."""
        return self.decision_policy.value


GENERAL_ACKNOWLEDGMENT_POLICY = AuthorizationPolicy(
    name="GENERAL_ACKNOWLEDGMENT",
    presentation_policy=PresentationPolicy.FLEXIBLE_SUMMARY,
    decision_policy=DecisionPolicy.EXPLICIT_VERBAL,
    evidence_policy=EvidencePolicy(
        accepted_sources=frozenset({"MODEL_TOOL_INTENT"}),
    ),
    recovery_policy=RecoveryPolicy.RETRY_SAME_PROPOSAL,
)


REQUIRED_RESTATEMENT_POLICY = AuthorizationPolicy(
    name="REQUIRED_RESTATEMENT",
    presentation_policy=PresentationPolicy.REQUIRED_FACT_RESTATEMENT,
    decision_policy=DecisionPolicy.EXPLICIT_VERBAL,
    evidence_policy=EvidencePolicy(
        accepted_sources=frozenset({"MODEL_TOOL_INTENT"}),
        required_presentation_acknowledgment="DETERMINISTIC_REQUIRED_FACTS_RENDERED",
    ),
    recovery_policy=RecoveryPolicy.REPRESENT_AND_RECONFIRM,
)


@dataclass(frozen=True)
class ValidatedRuntimeEvidence:
    customer_turn_id: str
    presentation_turn_id: str
    decision_turn_id: str
    protected_evidence: dict[str, Any]


class RuntimeEvidenceValidator:
    """Validate authenticated runtime evidence without inspecting prose."""

    def parse_headers(self, headers: Mapping[str, str]) -> ProposalRuntimeContext:
        """Parse the protected wire contract through its compatibility type."""
        return ProposalRuntimeContext.from_headers(headers)

    def validate_decision(
        self,
        context: ProposalRuntimeContext,
        policy: AuthorizationPolicy,
        *,
        additional_evidence: Mapping[str, Any] | None = None,
    ) -> ValidatedRuntimeEvidence:
        context.require_customer_turn()
        if not context.presentation_turn_id or not context.confirmation_turn_id:
            raise RuntimeContextError(
                "Protected presentation and confirmation turn evidence is required."
            )
        if context.confirmation_turn_id == context.presentation_turn_id:
            raise RuntimeContextError(
                "Confirmation must come from a later customer turn."
            )
        if context.customer_turn_id != context.confirmation_turn_id:
            raise RuntimeContextError(
                "Current customer turn does not match the protected confirmation turn."
            )
        if context.confirmation_method != policy.decision_policy.value:
            if policy.decision_policy is DecisionPolicy.EXPLICIT_VERBAL:
                raise RuntimeContextError("Explicit verbal confirmation is required.")
            raise RuntimeContextError(
                f"{policy.decision_policy.value.replace('_', ' ').title()} is required."
            )
        if context.confirmation_source not in policy.evidence_policy.accepted_sources:
            if policy.evidence_policy.accepted_sources == {"MODEL_TOOL_INTENT"}:
                raise RuntimeContextError(
                    "The customer decision must be bound to the model's typed tool choice."
                )
            raise RuntimeContextError(
                "The customer decision is not bound to an accepted protected source."
            )

        evidence = {
            "method": context.confirmation_method,
            "source": context.confirmation_source,
            "runtime_name": context.runtime_name,
            "runtime_session_id": context.runtime_session_id,
            "presentation_turn_id": context.presentation_turn_id,
            "confirmation_turn_id": context.confirmation_turn_id,
            **dict(additional_evidence or {}),
        }
        required_ack = policy.evidence_policy.required_presentation_acknowledgment
        if required_ack and evidence.get("presentation_acknowledgment") != required_ack:
            raise RuntimeContextError(
                "Deterministic presentation acknowledgment is required by policy."
            )
        return ValidatedRuntimeEvidence(
            customer_turn_id=context.customer_turn_id,
            presentation_turn_id=context.presentation_turn_id,
            decision_turn_id=context.confirmation_turn_id,
            protected_evidence=evidence,
        )


class TypedActionHandler(Protocol):
    """A transaction-participating handler for one registered action."""

    def display_selection(self, proposal: ActionProposal) -> dict[str, Any]: ...

    def commit_pending_message(self, proposal: ActionProposal) -> str: ...

    def reconcile(self, proposal: ActionProposal) -> dict[str, Any] | None: ...

    def validate_current_preconditions(self, proposal: ActionProposal) -> None: ...

    def execute(self, proposal: ActionProposal) -> dict[str, Any]: ...

    def record_commit_started(self, proposal: ActionProposal) -> None: ...

    def record_committed(
        self, proposal: ActionProposal, result: dict[str, Any]
    ) -> None: ...

    def record_reconciled(
        self, proposal: ActionProposal, result: dict[str, Any]
    ) -> None: ...


@dataclass(frozen=True)
class ActionSpecification:
    action_type: str
    contract_version: str
    payload_schema: Mapping[str, type | tuple[type, ...]]
    scope_resolver: Callable[[ActionProposal], tuple[str, str | None]]
    authorization_policy: AuthorizationPolicy
    handler: TypedActionHandler
    result_schema: Mapping[str, type | tuple[type, ...]] = field(default_factory=dict)

    def validate_payload(self, payload: Mapping[str, Any]) -> None:
        missing = set(self.payload_schema) - set(payload)
        if missing:
            raise ValueError(
                f"{self.action_type} payload is missing: {', '.join(sorted(missing))}."
            )
        for name, expected_type in self.payload_schema.items():
            if not isinstance(payload[name], expected_type):
                raise ValueError(f"{self.action_type} payload field {name} is invalid.")

    def validate_result(self, result: Mapping[str, Any]) -> None:
        missing = set(self.result_schema) - set(result)
        if missing:
            raise ValueError(
                f"{self.action_type} result is missing: {', '.join(sorted(missing))}."
            )
        for name, expected_type in self.result_schema.items():
            if not isinstance(result[name], expected_type):
                raise ValueError(f"{self.action_type} result field {name} is invalid.")


class ActionRegistry:
    """Explicit process-local registry for banking action specifications."""

    def __init__(self, specifications: tuple[ActionSpecification, ...]):
        self._specifications = {item.action_type: item for item in specifications}
        if len(self._specifications) != len(specifications):
            raise ValueError("Action types must be registered exactly once.")

    def require(self, action_type: str) -> ActionSpecification:
        try:
            return self._specifications[action_type]
        except KeyError as exc:
            raise ValueError(f"Action type is not registered: {action_type}.") from exc

    @property
    def action_types(self) -> frozenset[str]:
        return frozenset(self._specifications)
