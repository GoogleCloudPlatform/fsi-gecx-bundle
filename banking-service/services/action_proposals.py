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

"""Lifecycle primitives for banking-owned consequential-action proposals.

Catalog-backed and typed entry points create proposals; trusted runtime adapters
advance presentation and confirmation state. Registered banking capabilities
execute under the shared lifecycle and authorization protocol.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from models.action_proposal import ActionProposal
from models.identity import User
from services.action_proposal_context import ProposalRuntimeContext, RuntimeContextError
from services.proposal_definitions import action_contract, load_action_registry
from dataclasses import replace
from services.proposal_evidence import definition_snapshot
from services.proposal_lifecycle import (
    ActiveProposalExistsError as ActiveProposalExistsError,
    ProposalConflictError as ProposalConflictError,
    ProposalError,
    ProposalPolicyError,
    ProposalLifecycleEngine,
    ProposalScopeError,
    ProposalTransitionError,
    TERMINAL_STATUSES,
)
from services.proposal_protocol import (
    PolicyEvaluationEvidence,
    RecoveryClass,
)
from utils.audit import record_audit_event
from services.proposal_audit import audited_request, record_rejection
from services.proposal_lifecycle import as_utc, utcnow
from utils.log_safety import stable_log_reference


TRIAGE_FRAUD_CASE, FRAUD_TRIAGE_CONTRACT_VERSION = action_contract("fraud-triage")
REISSUE_CARD, CARD_REISSUE_CONTRACT_VERSION = action_contract("card-reissue")
PROVISION_GOOGLE_WALLET, WALLET_PROVISIONING_CONTRACT_VERSION = action_contract(
    "google-wallet-provisioning"
)
NON_COMMIT_DECISIONS = {"DECLINE", "REVISE", "CANCEL"}
logger = logging.getLogger(__name__)


class ActionProposalService(ProposalLifecycleEngine):
    def __init__(self, db, *, decisioning_provider=None):
        super().__init__(
            db,
            registry=load_action_registry(db, decisioning_provider=decisioning_provider),
            audit_recorder=record_audit_event,
        )

    def _require_current_publication(self, specification):
        """Serialize fresh preparation with publication; pinned retries bypass this."""
        from services.playbook_repository import SqlPlaybookRepository, RepositoryError

        try:
            current = SqlPlaybookRepository(self.db).lock_published(
                specification.definition_id
            )
        except RepositoryError as exc:
            raise ProposalError(
                "The published playbook is unavailable; discover again."
            ) from exc
        expected = (
            specification.definition_revision,
            specification.definition_digest,
        )
        if current != expected:
            raise ProposalError("The published playbook changed; discover again.")

    def record_request_rejection(self, identity, context, operation, exc, request):
        try:
            customer_id = self._resolve_customer_id(identity)
        except ProposalScopeError:
            customer_id = None
        # Retain a real expiry only within the authenticated matching scope.
        # The failed transaction has already been rolled back; this cleanup and
        # its rejection record commit together without any banking mutation.
        if (
            customer_id
            and getattr(exc, "code", None) == "PROPOSAL_EXPIRED"
            and request.get("proposal_id")
        ):
            proposal = self.db.query(ActionProposal).filter(
                ActionProposal.id == request["proposal_id"],
                ActionProposal.customer_id == customer_id,
                ActionProposal.support_session_id == context.support_session_id,
                ActionProposal.runtime_name == context.runtime_name,
                ActionProposal.runtime_session_id == context.runtime_session_id,
            ).with_for_update().first()
            if (
                proposal
                and proposal.status not in TERMINAL_STATUSES
                and proposal.status != "COMMITTING"
                and as_utc(proposal.expires_at) <= utcnow()
            ):
                proposal.status = "EXPIRED"
                proposal.invalidation_reason = "PROPOSAL_EXPIRED"
                proposal.completed_at = utcnow()
                self._record_disposition_event(proposal)
        record_rejection(self.db, identity, context, operation, exc, request, customer_id=customer_id)

    @audited_request("PREPARE")
    def prepare_playbook_for_identity(
        self,
        *,
        playbook_id,
        revision,
        digest,
        inputs,
        customer_identity,
        runtime_context,
        idempotency_key,
    ):
        from services.proposal_capabilities import validate_inputs

        runtime_context.require_customer_turn()
        customer_id = self._resolve_customer_id(customer_identity)
        try:
            specification = self.registry.resolve(playbook_id, revision, digest)
        except ValueError as exc:
            raise ProposalError(
                "The discovered playbook revision is unavailable; discover again."
            ) from exc
        context = dict(
            customer_id=customer_id,
            action_type=specification.action_type,
            support_session_id=runtime_context.support_session_id,
            runtime_name=runtime_context.runtime_name,
            runtime_session_id=runtime_context.runtime_session_id,
            originating_customer_turn_id=runtime_context.customer_turn_id,
            reset_generation=runtime_context.reset_generation,
            catalog_snapshot_id=runtime_context.catalog_snapshot_id,
            idempotency_key=idempotency_key,
        )
        existing = self._find_idempotent_proposal(context)
        if existing:
            pinned = self.registry.for_proposal(existing)
            if pinned.definition_digest != digest:
                raise ProposalError("Retry the original proposal revision.")
        else:
            self._require_current_publication(specification)
        operation = specification.handler.operation
        validate_inputs(inputs, operation.public_input_schema or operation.input_schema)
        normalized = operation.normalize_public_inputs(
            self.db, customer_identity, inputs
        )
        proposal = self.propose_action(
            **context,
            inputs=normalized,
            specification=specification,
        )
        self.db.commit()
        return self.proposal_view(proposal)

    def commit_action_for_identity(
        self, proposal_id, *, customer_identity, runtime_context
    ):
        return self._commit_for_identity(
            proposal_id,
            customer_identity=customer_identity,
            runtime_context=runtime_context,
        )

    def propose_fraud_triage(
        self,
        *,
        customer_id,
        fraud_alert_id,
        disputed_authorization_ids: list[str] | None,
        disputed_transaction_ids: list[str] | None,
        issue_replacement: bool,
        escalate: bool,
        support_session_id: str,
        runtime_name: str,
        runtime_session_id: str,
        originating_customer_turn_id: str,
        reset_generation: str,
        idempotency_key: str,
        catalog_snapshot_id: str | None = None,
        expires_at: datetime.datetime | None = None,
    ) -> ActionProposal:
        """Create an immutable proposal for an existing active fraud alert."""
        return self.propose_action(
            action_type=TRIAGE_FRAUD_CASE,
            customer_id=customer_id,
            inputs=dict(
                fraud_alert_id=str(fraud_alert_id),
                disputed_authorization_ids=disputed_authorization_ids,
                disputed_transaction_ids=disputed_transaction_ids,
                issue_replacement=issue_replacement,
                escalate=escalate,
            ),
            support_session_id=support_session_id,
            runtime_name=runtime_name,
            runtime_session_id=runtime_session_id,
            originating_customer_turn_id=originating_customer_turn_id,
            reset_generation=reset_generation,
            idempotency_key=idempotency_key,
            catalog_snapshot_id=catalog_snapshot_id,
            expires_at=expires_at,
        )

    @audited_request("PREPARE")
    def propose_fraud_triage_for_identity(
        self,
        *,
        customer_identity: str,
        fraud_alert_id,
        disputed_authorization_ids: list[str] | None,
        disputed_transaction_ids: list[str] | None,
        issue_replacement: bool,
        escalate: bool,
        runtime_context: ProposalRuntimeContext,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Create a typed proposal using authenticated transport identity/context."""
        runtime_context.require_customer_turn()
        customer_id = self._resolve_customer_id(customer_identity)
        proposal = self.propose_fraud_triage(
            customer_id=customer_id,
            fraud_alert_id=fraud_alert_id,
            disputed_authorization_ids=disputed_authorization_ids,
            disputed_transaction_ids=disputed_transaction_ids,
            issue_replacement=issue_replacement,
            escalate=escalate,
            support_session_id=runtime_context.support_session_id,
            runtime_name=runtime_context.runtime_name,
            runtime_session_id=runtime_context.runtime_session_id,
            originating_customer_turn_id=runtime_context.customer_turn_id,
            reset_generation=runtime_context.reset_generation,
            catalog_snapshot_id=runtime_context.catalog_snapshot_id,
            idempotency_key=idempotency_key,
        )
        self.db.commit()
        return self.proposal_view(proposal)

    def propose_card_reissue_for_identity(
        self,
        *,
        customer_identity: str,
        runtime_context: ProposalRuntimeContext,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Create a card-reissue proposal without exposing mutable card details."""
        return self._propose_for_identity(
            REISSUE_CARD,
            customer_identity,
            runtime_context,
            {"reason": reason},
            idempotency_key,
        )

    def propose_wallet_provisioning_for_identity(
        self,
        *,
        customer_identity: str,
        runtime_context: ProposalRuntimeContext,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Create a Wallet proposal bound to the customer's active virtual card."""
        return self._propose_for_identity(
            PROVISION_GOOGLE_WALLET,
            customer_identity,
            runtime_context,
            {},
            idempotency_key,
        )

    def commit_card_reissue_for_identity(
        self,
        proposal_id,
        *,
        customer_identity: str,
        runtime_context: ProposalRuntimeContext,
    ) -> dict[str, Any]:
        return self._commit_for_identity(
            proposal_id,
            customer_identity=customer_identity,
            runtime_context=runtime_context,
            expected_action_type=REISSUE_CARD,
        )

    def commit_wallet_provisioning_for_identity(
        self,
        proposal_id,
        *,
        customer_identity: str,
        runtime_context: ProposalRuntimeContext,
    ) -> dict[str, Any]:
        return self._commit_for_identity(
            proposal_id,
            customer_identity=customer_identity,
            runtime_context=runtime_context,
            expected_action_type=PROVISION_GOOGLE_WALLET,
        )

    @audited_request("DECIDE")
    def decide_for_identity(
        self,
        proposal_id,
        *,
        decision: str,
        customer_identity: str,
        runtime_context: ProposalRuntimeContext,
    ) -> dict[str, Any]:
        """Apply a typed non-commit customer decision to one current proposal."""
        normalized_decision = str(decision or "").strip().upper()
        if normalized_decision not in NON_COMMIT_DECISIONS:
            raise ProposalError("Proposal decision must be DECLINE, REVISE, or CANCEL.")
        customer_id = self._resolve_customer_id(customer_identity)
        proposal = self._get_locked(proposal_id)
        self._validate_scope(
            proposal,
            customer_id=customer_id,
            support_session_id=runtime_context.support_session_id,
            runtime_name=runtime_context.runtime_name,
            runtime_session_id=runtime_context.runtime_session_id,
            expected_action_type=proposal.action_type,
        )
        evidence = self.validate_decision_evidence(
            proposal,
            runtime_context=runtime_context,
        )
        if proposal.reset_generation != runtime_context.reset_generation:
            if proposal.status not in TERMINAL_STATUSES:
                self.invalidate(proposal.id, reason="RESET_GENERATION_CHANGED")
                self.db.commit()
            raise ProposalScopeError(
                "Proposal was invalidated by a session reset.",
                code="RESET_GENERATION_CHANGED",
                recovery_class=RecoveryClass.CREATE_NEW_PROPOSAL,
                customer_message=(
                    "The support session was reset. Review current information before "
                    "creating a new proposal."
                ),
                proposal=proposal,
            )
        if proposal.status == "PROPOSED":
            self.mark_presented(
                proposal.id,
                assistant_turn_id=evidence.presentation_turn_id,
            )
        if proposal.presented_assistant_turn_id != evidence.presentation_turn_id:
            raise ProposalScopeError(
                "Proposal presentation does not belong to the protected turn.",
                code="PRESENTATION_EVIDENCE_REQUIRED",
                recovery_class=RecoveryClass.REPRESENT_AND_RECONFIRM,
                customer_message=(
                    "Present the current proposal again and obtain a later explicit "
                    "customer decision."
                ),
                proposal=proposal,
            )
        customer_turn_id = evidence.decision_turn_id
        if customer_turn_id == proposal.originating_customer_turn_id:
            raise ProposalTransitionError(
                "A proposal decision must come from a later customer turn.",
                code="PRESENTATION_EVIDENCE_REQUIRED",
                recovery_class=RecoveryClass.REPRESENT_AND_RECONFIRM,
                customer_message=(
                    "Present the current proposal and obtain a later explicit customer "
                    "decision."
                ),
                proposal=proposal,
            )

        if proposal.status in {"DECLINED", "INVALIDATED"}:
            expected_reason = {
                "DECLINE": "CUSTOMER_DECLINED",
                "REVISE": "CUSTOMER_REVISED",
                "CANCEL": "CUSTOMER_CANCELLED",
            }[normalized_decision]
            if (
                proposal.status
                == ("DECLINED" if normalized_decision == "DECLINE" else "INVALIDATED")
                and proposal.invalidation_reason == expected_reason
            ):
                return {
                    **self.proposal_view(proposal),
                    "decision": normalized_decision,
                    "idempotent_replay": True,
                }
            raise ProposalTransitionError(
                f"Proposal is already terminal in {proposal.status} state."
            )

        proposal.confirmation_evidence = evidence.protected_evidence
        proposal.confirmation_customer_turn_id = customer_turn_id
        if normalized_decision == "DECLINE":
            self.decline(
                proposal.id,
                customer_turn_id=customer_turn_id,
            )
        else:
            self.invalidate(
                proposal.id,
                reason=(
                    "CUSTOMER_REVISED"
                    if normalized_decision == "REVISE"
                    else "CUSTOMER_CANCELLED"
                ),
            )
            proposal.confirmation_customer_turn_id = customer_turn_id
        self.db.commit()
        return {
            **self.proposal_view(proposal),
            "decision": normalized_decision,
            "idempotent_replay": False,
        }

    def commit_fraud_triage(
        self,
        proposal_id,
        *,
        customer_id,
        support_session_id: str,
        runtime_name: str,
        runtime_session_id: str,
        reset_generation: str,
        now: datetime.datetime | None = None,
    ) -> dict[str, Any]:
        """Execute fraud through the same registered pipeline as other actions."""
        return self.execute_registered_commit(
            proposal_id,
            customer_id=customer_id,
            support_session_id=support_session_id,
            runtime_name=runtime_name,
            runtime_session_id=runtime_session_id,
            reset_generation=reset_generation,
            expected_action_type=TRIAGE_FRAUD_CASE,
            now=now,
        )

    @audited_request("COMMIT")
    def commit_fraud_triage_for_identity(
        self,
        proposal_id,
        *,
        customer_identity: str,
        runtime_context: ProposalRuntimeContext,
    ) -> dict[str, Any]:
        """Attest protected later-turn evidence and commit an opaque proposal id."""
        stage = "validate_evidence"
        try:
            stage = "resolve_customer"
            customer_id = self._resolve_customer_id(customer_identity)
            stage = "load_proposal"
            proposal = self._get_locked(proposal_id)
            stage = "validate_scope"
            self._validate_scope(
                proposal,
                customer_id=customer_id,
                support_session_id=runtime_context.support_session_id,
                runtime_name=runtime_context.runtime_name,
                runtime_session_id=runtime_context.runtime_session_id,
                expected_action_type=TRIAGE_FRAUD_CASE,
            )
            stage = "attest_decision"
            self.attest_decision(proposal, runtime_context=runtime_context)
            stage = "execute_commit"
            return self.commit_fraud_triage(
                proposal.id,
                customer_id=customer_id,
                support_session_id=runtime_context.support_session_id,
                runtime_name=runtime_context.runtime_name,
                runtime_session_id=runtime_context.runtime_session_id,
                reset_generation=runtime_context.reset_generation,
            )
        except (ProposalError, RuntimeContextError) as exc:
            logger.warning(
                "Fraud proposal identity commit rejected proposal_ref=%s "
                "stage=%s error_type=%s reason_ref=%s",
                stable_log_reference(proposal_id, "proposal"),
                stage,
                type(exc).__name__,
                stable_log_reference(str(exc), "reason"),
            )
            raise

    def proposal_disposition_for_identity(
        self,
        proposal_id,
        *,
        customer_identity: str,
        runtime_context: ProposalRuntimeContext,
    ) -> dict[str, Any]:
        """Return a compact terminal/checkpoint disposition within trusted scope."""
        customer_id = self._resolve_customer_id(customer_identity)
        proposal = self._get_locked(proposal_id)
        self._validate_scope(
            proposal,
            customer_id=customer_id,
            support_session_id=runtime_context.support_session_id,
            runtime_name=runtime_context.runtime_name,
            runtime_session_id=runtime_context.runtime_session_id,
            expected_action_type=TRIAGE_FRAUD_CASE,
        )
        return {
            "proposal_id": str(proposal.id),
            "action_type": proposal.action_type,
            "contract_version": proposal.contract_version,
            "status": proposal.status,
            "invalidation_reason": proposal.invalidation_reason,
        }

    @audited_request("COMMIT")
    def _commit_for_identity(
        self,
        proposal_id,
        *,
        customer_identity: str,
        runtime_context: ProposalRuntimeContext,
        expected_action_type: str | None = None,
    ) -> dict[str, Any]:
        """Attest and execute any action through the registered pipeline."""
        customer_id = self._resolve_customer_id(customer_identity)
        proposal = self._get_locked(proposal_id)
        expected_action_type = expected_action_type or proposal.action_type
        self._validate_scope(
            proposal,
            customer_id=customer_id,
            support_session_id=runtime_context.support_session_id,
            runtime_name=runtime_context.runtime_name,
            runtime_session_id=runtime_context.runtime_session_id,
            expected_action_type=expected_action_type,
        )
        self.attest_decision(proposal, runtime_context=runtime_context)
        return self.execute_registered_commit(
            proposal.id,
            customer_id=customer_id,
            support_session_id=runtime_context.support_session_id,
            runtime_name=runtime_context.runtime_name,
            runtime_session_id=runtime_context.runtime_session_id,
            reset_generation=runtime_context.reset_generation,
            expected_action_type=expected_action_type,
        )

    def proposal_trace_for_identity(
        self,
        *,
        customer_identity: str,
        support_session_id: str,
    ) -> list[dict[str, Any]]:
        """Return a presenter-safe lifecycle view for one support session."""
        customer_id = self._resolve_customer_id(customer_identity)
        proposals = (
            self.db.query(ActionProposal)
            .filter(
                ActionProposal.customer_id == customer_id,
                ActionProposal.support_session_id == str(support_session_id),
            )
            .order_by(ActionProposal.created_at.asc(), ActionProposal.id.asc())
            .all()
        )
        return [self._proposal_trace_view(proposal) for proposal in proposals]

    @staticmethod
    def _proposal_trace_view(proposal: ActionProposal) -> dict[str, Any]:
        """Serialize only customer-safe and correlation-safe proposal fields."""
        return {
            "proposal_ref": stable_log_reference(str(proposal.id), "proposal"),
            "action_type": proposal.action_type,
            "contract_version": proposal.contract_version,
            "status": proposal.status,
            "customer_safe_summary": proposal.customer_safe_summary,
            "catalog_snapshot_ref": (
                stable_log_reference(proposal.catalog_snapshot_id, "catalog-snapshot")
                if proposal.catalog_snapshot_id
                else None
            ),
            "presentation_verified": bool(proposal.presented_assistant_turn_id),
            "confirmation_verified": bool(proposal.confirmation_customer_turn_id),
            "commit_started": bool(proposal.commit_started_at),
            "created_at": proposal.created_at.isoformat()
            if proposal.created_at
            else None,
            "completed_at": proposal.completed_at.isoformat()
            if proposal.completed_at
            else None,
            "invalidation_reason": proposal.invalidation_reason,
        }

    def _resolve_customer_id(self, customer_identity: str):
        identity = str(customer_identity or "").strip()
        identity_filters = [
            User.auth_provider_uid == identity,
            User.email == identity,
        ]
        try:
            identity_filters.append(User.id == uuid.UUID(identity))
        except (TypeError, ValueError):
            pass
        user = self.db.query(User).filter(or_(*identity_filters)).first()
        if not user:
            raise ProposalScopeError(
                "Authenticated customer identity does not resolve to a banking customer."
            )
        return user.id

    @audited_request("PREPARE")
    def _propose_for_identity(self, action_type, identity, context, inputs, key):
        context.require_customer_turn()
        proposal = self.propose_action(
            action_type=action_type,
            customer_id=self._resolve_customer_id(identity),
            inputs=inputs,
            support_session_id=context.support_session_id,
            runtime_name=context.runtime_name,
            runtime_session_id=context.runtime_session_id,
            originating_customer_turn_id=context.customer_turn_id,
            reset_generation=context.reset_generation,
            catalog_snapshot_id=context.catalog_snapshot_id,
            idempotency_key=key,
        )
        self.db.commit()
        return self.proposal_view(proposal)

    def propose_action(
        self, *, action_type, customer_id, inputs, specification=None, **context
    ):
        existing = self._find_idempotent_proposal(
            dict(action_type=action_type, customer_id=customer_id, **context)
        )
        specification = (
            self.registry.for_proposal(existing)
            if existing
            else specification or self.registry.require(action_type)
        )
        from services.proposal_lifecycle import canonical_payload
        from services.proposal_definitions import validate_inputs
        validate_inputs(inputs, specification.handler.operation.input_schema)
        inputs = specification.handler.operation.normalize_business_inputs(inputs)
        _, input_fingerprint = canonical_payload(inputs)
        if existing:
            fields = ("support_session_id", "runtime_name", "runtime_session_id", "originating_customer_turn_id", "reset_generation", "catalog_snapshot_id")
            if (any(getattr(existing, key) != context.get(key) for key in fields)
                or existing.action_payload.get("_business_input_fingerprint") != input_fingerprint):
                raise ProposalConflictError("Retry inputs or trusted scope changed for a different proposal.")
            return existing
        self._require_current_publication(specification)
        preparation_context = {
            "customer_id": str(customer_id), "definition_digest": specification.definition_digest,
            **{key: context.get(key) for key in ("support_session_id", "runtime_name", "runtime_session_id", "originating_customer_turn_id", "reset_generation", "idempotency_key")},
            "input_fingerprint": input_fingerprint,
        }
        try:
            account_id, payload, summary = specification.handler.prepare(
                customer_id, inputs, preparation_context=preparation_context
            )
        except ProposalPolicyError as exc:
            exc.policy_evidence = replace(
                exc.policy_evidence, definition=definition_snapshot(specification)
            )
            raise
        payload["_business_input_fingerprint"] = input_fingerprint
        bank_decision_ref = None
        if "bank_decision" in payload:
            from services.decisioning import BankDecision
            bank_decision_ref = BankDecision.model_validate(payload["bank_decision"]).binding_ref
        try:
            return self._create(
                bank_decision_ref=bank_decision_ref,
                action_type=action_type,
            contract_version=specification.contract_version,
            definition_id=specification.definition_id,
            definition_revision=specification.definition_revision,
            definition_digest=specification.definition_digest,
            customer_id=customer_id,
            account_id=account_id,
            confirmation_policy=specification.authorization_policy.durable_confirmation_policy,
            action_payload=payload,
            customer_safe_summary=summary,
            **context,
            )
        except IntegrityError as exc:
            diagnostic = getattr(exc.orig, "diag", None)
            binding_violation = getattr(diagnostic, "constraint_name", None) == "uq_action_proposals_bank_decision_ref"
            if getattr(exc.orig, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_UNIQUE":
                binding_violation = str(exc.orig).endswith("action_proposals.bank_decision_ref")
            if bank_decision_ref and binding_violation:
                raise ProposalPolicyError(PolicyEvaluationEvidence(
                    policy=payload["credit_limit_policy"], facts=payload["eligibility_facts"],
                    requested_limit=payload["proposed_limit"], reason_code="BANK_DECISION_ALREADY_BOUND",
                    bank_decision=payload["bank_decision"], decision_failure="APPROVAL_ALREADY_BOUND",
                    definition=definition_snapshot(specification),
                )) from None
            raise

    def proposal_view(self, proposal):
        view = super().proposal_view(proposal)
        handler = self.registry.for_proposal(proposal).handler
        view.update(handler.public_projection(proposal))
        return view
