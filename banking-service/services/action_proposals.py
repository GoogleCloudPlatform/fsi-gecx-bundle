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

This module is intentionally not exposed as a generic MCP surface. Domain
services create typed proposals; trusted runtime adapters advance presentation
and confirmation state; domain commit services claim and complete execution.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from sqlalchemy import or_

from models.action_proposal import ActionProposal
from models.fraud import FraudAlert
from models.identity import User
from repositories.credit_card import CreditCardRepository
from repositories.fraud import FraudAlertRepository
from services.action_proposal_context import ProposalRuntimeContext, RuntimeContextError
from services.credit_card import issue_replacement_card, queue_wallet_provisioning
from services.proposal_lifecycle import (
    ActionPreconditionError,
    ProposalConflictError as ProposalConflictError,
    ProposalError,
    ProposalLifecycleEngine,
    ProposalScopeError,
    ProposalTransitionError,
    TERMINAL_STATUSES,
)
from services.proposal_protocol import (
    ActionRegistry,
    ActionSpecification,
    GENERAL_ACKNOWLEDGMENT_POLICY,
)
from utils.audit import record_audit_event
from utils.log_safety import stable_log_reference


TRIAGE_FRAUD_CASE = "TRIAGE_FRAUD_CASE"
FRAUD_TRIAGE_CONTRACT_VERSION = "fraud-triage.v1"
REISSUE_CARD = "REISSUE_CARD"
CARD_REISSUE_CONTRACT_VERSION = "card-reissue.v1"
PROVISION_GOOGLE_WALLET = "PROVISION_GOOGLE_WALLET"
WALLET_PROVISIONING_CONTRACT_VERSION = "wallet-provisioning.v1"
NON_COMMIT_DECISIONS = {"DECLINE", "REVISE", "CANCEL"}
logger = logging.getLogger(__name__)


def _normalized_ids(values: list[str] | None) -> list[str]:
    return sorted(
        {str(value).strip() for value in (values or []) if str(value).strip()}
    )


class _DomainActionHandler:
    """Default hooks shared by the first banking action handlers."""

    def __init__(self, db):
        self.db = db

    def reconcile(self, proposal: ActionProposal) -> dict[str, Any] | None:
        return None

    def commit_pending_message(self, proposal: ActionProposal) -> str:
        return "Action proposal commit is already in progress."

    def validate_current_preconditions(self, proposal: ActionProposal) -> None:
        return None

    def record_commit_started(self, proposal: ActionProposal) -> None:
        return None

    def record_reconciled(
        self, proposal: ActionProposal, result: dict[str, Any]
    ) -> None:
        return None

    def record_committed(
        self, proposal: ActionProposal, result: dict[str, Any]
    ) -> None:
        record_audit_event(
            self.db,
            "ACTION_PROPOSAL_COMMITTED",
            {
                "proposal_id": str(proposal.id),
                "correlation_id": str(proposal.id),
                "action_type": proposal.action_type,
                "contract_version": proposal.contract_version,
                "customer_id": str(proposal.customer_id),
                "account_id": str(proposal.account_id or "") or None,
                "support_session_id": proposal.support_session_id,
                "runtime_name": proposal.runtime_name,
                "result_status": result.get("status"),
            },
        )


class _CardReissueHandler(_DomainActionHandler):
    def display_selection(self, proposal: ActionProposal) -> dict[str, Any]:
        payload = dict(proposal.action_payload or {})
        return {
            "reason": payload.get("reason"),
            "issue_virtual_card": bool(payload.get("issue_virtual_card")),
        }

    def execute(self, proposal: ActionProposal) -> dict[str, Any]:
        payload = dict(proposal.action_payload or {})
        replacement = issue_replacement_card(
            self.db,
            account_id=str(proposal.account_id),
            reason=f"CUSTOMER_REPORTED_{payload.get('reason')}",
            issue_virtual_card=bool(payload.get("issue_virtual_card", True)),
            compromised_card_id=str(payload.get("compromised_card_id") or ""),
            commit_transaction=False,
        )
        return {
            "success": True,
            "message": replacement.get("message"),
            "replacement_card": replacement,
            "card_status": "BLOCKED",
        }


class _WalletProvisioningHandler(_DomainActionHandler):
    def display_selection(self, proposal: ActionProposal) -> dict[str, Any]:
        payload = dict(proposal.action_payload or {})
        return {"wallet_provider": payload.get("wallet_provider")}

    def execute(self, proposal: ActionProposal) -> dict[str, Any]:
        payload = dict(proposal.action_payload or {})
        wallet = queue_wallet_provisioning(
            self.db,
            account_id=str(proposal.account_id),
            card_token=str(payload.get("card_token") or ""),
            wallet_provider="GOOGLE_WALLET",
            initiated_by="CUSTOMER_VOICE_SUPPORT",
            commit_transaction=False,
        )
        return {
            "success": True,
            "message": wallet.get("message"),
            **wallet,
        }


class _FraudTriageHandler(_DomainActionHandler):
    def commit_pending_message(self, proposal: ActionProposal) -> str:
        return "Fraud proposal commit is already in progress."

    def display_selection(self, proposal: ActionProposal) -> dict[str, Any]:
        payload = dict(proposal.action_payload or {})
        return {
            "fraud_alert_id": payload.get("fraud_alert_id"),
            "disputed_authorization_ids": payload.get(
                "disputed_authorization_ids", []
            ),
            "disputed_transaction_ids": payload.get("disputed_transaction_ids", []),
            "issue_replacement": bool(payload.get("issue_replacement")),
            "escalate": bool(payload.get("escalate")),
        }

    def _workflow_key(self, proposal: ActionProposal) -> str:
        return f"proposal:{proposal.id}:{proposal.payload_fingerprint[:48]}"

    def _locked_alert(self, proposal: ActionProposal):
        payload = dict(proposal.action_payload or {})
        return (
            self.db.query(FraudAlert)
            .filter(
                FraudAlert.id == payload.get("fraud_alert_id"),
                FraudAlert.customer_id == proposal.customer_id,
                FraudAlert.credit_account_id == proposal.account_id,
            )
            .with_for_update()
            .first()
        )

    def validate_current_preconditions(self, proposal: ActionProposal) -> None:
        alert = self._locked_alert(proposal)
        if not alert or alert.status != "OPEN":
            raise ActionPreconditionError(
                "Fraud alert is no longer open; create a new proposal from current state.",
                reason="FRAUD_ALERT_NO_LONGER_OPEN",
            )

    def execute(self, proposal: ActionProposal) -> dict[str, Any]:
        from services.fraud_alerts import FraudAlertService

        payload = dict(proposal.action_payload or {})
        alert = self._locked_alert(proposal)
        return FraudAlertService(self.db)._triage_fraud_case_in_transaction(
            auth_provider_uid=alert.auth_provider_uid,
            fraud_alert_id=str(alert.id),
            disputed_authorization_ids=payload.get("disputed_authorization_ids"),
            disputed_transaction_ids=payload.get("disputed_transaction_ids"),
            issue_replacement=bool(payload.get("issue_replacement")),
            escalate=bool(payload.get("escalate")),
            idempotency_key=self._workflow_key(proposal),
        )

    def reconcile(self, proposal: ActionProposal) -> dict[str, Any] | None:
        fraud_alert_id = (proposal.action_payload or {}).get("fraud_alert_id")
        if not fraud_alert_id:
            return None
        action = FraudAlertRepository(self.db).get_case_action_by_idempotency_key(
            fraud_alert_id=fraud_alert_id,
            idempotency_key=self._workflow_key(proposal),
        )
        if not action or action.status != "SUCCEEDED":
            return None
        return dict(action.result_payload or {})

    def record_commit_started(self, proposal: ActionProposal) -> None:
        payload = dict(proposal.action_payload or {})
        record_audit_event(
            self.db,
            "ACTION_PROPOSAL_COMMIT_STARTED",
            {
                "proposal_id": str(proposal.id),
                "correlation_id": str(proposal.id),
                "action_type": proposal.action_type,
                "contract_version": proposal.contract_version,
                "customer_id": str(proposal.customer_id),
                "account_id": str(proposal.account_id),
                "support_session_id": proposal.support_session_id,
                "runtime_name": proposal.runtime_name,
                "fraud_alert_id": str(payload.get("fraud_alert_id")),
                "payload_fingerprint": proposal.payload_fingerprint,
            },
        )

    def record_committed(
        self, proposal: ActionProposal, result: dict[str, Any]
    ) -> None:
        payload = dict(proposal.action_payload or {})
        record_audit_event(
            self.db,
            "ACTION_PROPOSAL_COMMITTED",
            {
                "proposal_id": str(proposal.id),
                "correlation_id": str(proposal.id),
                "action_type": proposal.action_type,
                "contract_version": proposal.contract_version,
                "customer_id": str(proposal.customer_id),
                "account_id": str(proposal.account_id),
                "support_session_id": proposal.support_session_id,
                "runtime_name": proposal.runtime_name,
                "fraud_alert_id": str(payload.get("fraud_alert_id")),
                "outcome": result.get("outcome"),
                "payload_fingerprint": proposal.payload_fingerprint,
            },
        )

    def record_reconciled(
        self, proposal: ActionProposal, result: dict[str, Any]
    ) -> None:
        fraud_alert_id = (proposal.action_payload or {}).get("fraud_alert_id")
        action = FraudAlertRepository(self.db).get_case_action_by_idempotency_key(
            fraud_alert_id=fraud_alert_id,
            idempotency_key=self._workflow_key(proposal),
        )
        record_audit_event(
            self.db,
            "ACTION_PROPOSAL_COMMIT_RECONCILED",
            {
                "proposal_id": str(proposal.id),
                "correlation_id": str(proposal.id),
                "action_type": proposal.action_type,
                "customer_id": str(proposal.customer_id),
                "fraud_alert_id": str(fraud_alert_id),
                "domain_action_id": str(action.id) if action else None,
                "outcome": result.get("outcome"),
            },
        )


def _customer_account_scope(proposal: ActionProposal) -> tuple[str, str | None]:
    return (
        str(proposal.customer_id),
        str(proposal.account_id) if proposal.account_id else None,
    )


def _action_registry(db) -> ActionRegistry:
    """Register the three current actions explicitly at service construction."""
    return ActionRegistry(
        (
            ActionSpecification(
                action_type=TRIAGE_FRAUD_CASE,
                contract_version=FRAUD_TRIAGE_CONTRACT_VERSION,
                payload_schema={
                    "fraud_alert_id": str,
                    "disputed_authorization_ids": list,
                    "disputed_transaction_ids": list,
                    "issue_replacement": bool,
                    "escalate": bool,
                },
                scope_resolver=_customer_account_scope,
                authorization_policy=GENERAL_ACKNOWLEDGMENT_POLICY,
                handler=_FraudTriageHandler(db),
                result_schema={"success": bool},
            ),
            ActionSpecification(
                action_type=REISSUE_CARD,
                contract_version=CARD_REISSUE_CONTRACT_VERSION,
                payload_schema={
                    "account_id": str,
                    "compromised_card_id": str,
                    "reason": str,
                    "issue_virtual_card": bool,
                },
                scope_resolver=_customer_account_scope,
                authorization_policy=GENERAL_ACKNOWLEDGMENT_POLICY,
                handler=_CardReissueHandler(db),
                result_schema={"success": bool},
            ),
            ActionSpecification(
                action_type=PROVISION_GOOGLE_WALLET,
                contract_version=WALLET_PROVISIONING_CONTRACT_VERSION,
                payload_schema={
                    "account_id": str,
                    "card_id": str,
                    "card_token": str,
                    "wallet_provider": str,
                },
                scope_resolver=_customer_account_scope,
                authorization_policy=GENERAL_ACKNOWLEDGMENT_POLICY,
                handler=_WalletProvisioningHandler(db),
                result_schema={"success": bool},
            ),
        )
    )


class ActionProposalService(ProposalLifecycleEngine):
    def __init__(self, db):
        super().__init__(
            db,
            registry=_action_registry(db),
            audit_recorder=record_audit_event,
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
        alert = (
            self.db.query(FraudAlert)
            .filter(
                FraudAlert.id == fraud_alert_id,
                FraudAlert.customer_id == customer_id,
            )
            .first()
        )
        if not alert:
            raise ProposalScopeError("Fraud alert was not found for this customer.")
        if alert.status != "OPEN":
            raise ProposalError("Fraud alert is no longer open.")

        authorization_ids = _normalized_ids(disputed_authorization_ids)
        transaction_ids = _normalized_ids(disputed_transaction_ids)
        allowed_authorization_ids = {
            str(value) for value in (alert.suspicious_authorization_ids or [])
        }
        unexpected_authorizations = sorted(
            set(authorization_ids) - allowed_authorization_ids
        )
        if unexpected_authorizations:
            raise ProposalScopeError(
                "Authorization ids are not part of this fraud alert: "
                + ", ".join(unexpected_authorizations)
            )

        allowed_transaction_ids = {
            str(item.get("transaction_id"))
            for item in (alert.suspicious_transactions or [])
            if item.get("transaction_id")
        }
        unexpected_transactions = sorted(set(transaction_ids) - allowed_transaction_ids)
        if unexpected_transactions:
            raise ProposalScopeError(
                "Transaction ids are not part of this fraud alert: "
                + ", ".join(unexpected_transactions)
            )

        payload = {
            "fraud_alert_id": str(alert.id),
            "disputed_authorization_ids": authorization_ids,
            "disputed_transaction_ids": transaction_ids,
            "issue_replacement": bool(issue_replacement),
            "escalate": bool(escalate),
        }
        return self._create(
            contract_version=FRAUD_TRIAGE_CONTRACT_VERSION,
            action_type=TRIAGE_FRAUD_CASE,
            customer_id=customer_id,
            account_id=alert.credit_account_id,
            support_session_id=support_session_id,
            runtime_name=runtime_name,
            runtime_session_id=runtime_session_id,
            originating_customer_turn_id=originating_customer_turn_id,
            reset_generation=reset_generation,
            confirmation_policy="EXPLICIT_VERBAL",
            action_payload=payload,
            customer_safe_summary=self._fraud_triage_summary(
                alert=alert,
                authorization_ids=authorization_ids,
                transaction_ids=transaction_ids,
                issue_replacement=bool(issue_replacement),
                escalate=bool(escalate),
            ),
            catalog_snapshot_id=catalog_snapshot_id,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )

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
        runtime_context.require_customer_turn()
        customer_id = self._resolve_customer_id(customer_identity)
        account = CreditCardRepository(self.db).get_account_by_customer(
            str(customer_id)
        )
        if not account:
            raise ProposalScopeError("Active credit-card account was not found.")
        cards = CreditCardRepository(self.db).list_cards_by_account(account.id)
        card = next(
            (
                item
                for item in cards
                if item.is_active and item.status == "ACTIVE"
            ),
            None,
        )
        if not card:
            raise ProposalError("No active card is eligible for reissue.")
        normalized_reason = str(reason or "").strip().upper()
        if normalized_reason not in {"LOST", "STOLEN", "DAMAGED"}:
            raise ProposalError("Card reissue reason must be LOST, STOLEN, or DAMAGED.")

        proposal = self._create(
            contract_version=CARD_REISSUE_CONTRACT_VERSION,
            action_type=REISSUE_CARD,
            customer_id=customer_id,
            account_id=account.id,
            support_session_id=runtime_context.support_session_id,
            runtime_name=runtime_context.runtime_name,
            runtime_session_id=runtime_context.runtime_session_id,
            originating_customer_turn_id=runtime_context.customer_turn_id,
            reset_generation=runtime_context.reset_generation,
            confirmation_policy="EXPLICIT_VERBAL",
            action_payload={
                "account_id": str(account.id),
                "compromised_card_id": str(card.id),
                "reason": normalized_reason,
                "issue_virtual_card": True,
            },
            customer_safe_summary=(
                f"Confirm that you want to block the card ending {card.last_four} "
                "and issue a replacement virtual card."
            ),
            catalog_snapshot_id=runtime_context.catalog_snapshot_id,
            idempotency_key=idempotency_key,
        )
        self.db.commit()
        return self.proposal_view(proposal)

    def propose_wallet_provisioning_for_identity(
        self,
        *,
        customer_identity: str,
        runtime_context: ProposalRuntimeContext,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Create a Wallet proposal bound to the customer's active virtual card."""
        runtime_context.require_customer_turn()
        customer_id = self._resolve_customer_id(customer_identity)
        repo = CreditCardRepository(self.db)
        account = repo.get_account_by_customer(str(customer_id))
        if not account:
            raise ProposalScopeError("Active credit-card account was not found.")
        cards = repo.list_cards_by_account(account.id)
        card = next(
            (
                item
                for item in cards
                if item.is_active and item.status == "ACTIVE" and item.is_virtual
            ),
            None,
        )
        if not card:
            raise ProposalError(
                "No active virtual card is eligible for Wallet provisioning."
            )

        proposal = self._create(
            contract_version=WALLET_PROVISIONING_CONTRACT_VERSION,
            action_type=PROVISION_GOOGLE_WALLET,
            customer_id=customer_id,
            account_id=account.id,
            support_session_id=runtime_context.support_session_id,
            runtime_name=runtime_context.runtime_name,
            runtime_session_id=runtime_context.runtime_session_id,
            originating_customer_turn_id=runtime_context.customer_turn_id,
            reset_generation=runtime_context.reset_generation,
            confirmation_policy="EXPLICIT_VERBAL",
            action_payload={
                "account_id": str(account.id),
                "card_id": str(card.id),
                "card_token": card.card_token,
                "wallet_provider": "GOOGLE_WALLET",
            },
            customer_safe_summary=(
                f"Confirm that you want to queue the virtual card ending "
                f"{card.last_four} for Google Wallet."
            ),
            catalog_snapshot_id=runtime_context.catalog_snapshot_id,
            idempotency_key=idempotency_key,
        )
        self.db.commit()
        return self.proposal_view(proposal)

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
            raise ProposalError(
                "Proposal decision must be DECLINE, REVISE, or CANCEL."
            )
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
        specification = self.registry.require(proposal.action_type)
        evidence = self.evidence_validator.validate_decision(
            runtime_context,
            specification.authorization_policy,
        )
        if proposal.reset_generation != runtime_context.reset_generation:
            if proposal.status not in TERMINAL_STATUSES:
                self.invalidate(proposal.id, reason="RESET_GENERATION_CHANGED")
                self._record_disposition_event(proposal)
                self.db.commit()
            raise ProposalScopeError("Proposal was invalidated by a session reset.")
        if proposal.status == "PROPOSED":
            self.mark_presented(
                proposal.id,
                assistant_turn_id=evidence.presentation_turn_id,
            )
        if proposal.presented_assistant_turn_id != evidence.presentation_turn_id:
            raise ProposalScopeError(
                "Proposal presentation does not belong to the protected turn."
            )
        customer_turn_id = evidence.decision_turn_id
        if customer_turn_id == proposal.originating_customer_turn_id:
            raise ProposalTransitionError(
                "A proposal decision must come from a later customer turn."
            )

        if proposal.status in {"DECLINED", "INVALIDATED"}:
            expected_reason = {
                "DECLINE": "CUSTOMER_DECLINED",
                "REVISE": "CUSTOMER_REVISED",
                "CANCEL": "CUSTOMER_CANCELLED",
            }[normalized_decision]
            if (
                proposal.status == ("DECLINED" if normalized_decision == "DECLINE" else "INVALIDATED")
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
        self._record_disposition_event(proposal)
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

    def _commit_for_identity(
        self,
        proposal_id,
        *,
        customer_identity: str,
        runtime_context: ProposalRuntimeContext,
        expected_action_type: str,
    ) -> dict[str, Any]:
        """Attest and execute any action through the registered pipeline."""
        customer_id = self._resolve_customer_id(customer_identity)
        proposal = self._get_locked(proposal_id)
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

    @staticmethod
    def _fraud_triage_summary(
        *,
        alert: FraudAlert,
        authorization_ids: list[str],
        transaction_ids: list[str],
        issue_replacement: bool,
        escalate: bool,
    ) -> str:
        if not authorization_ids and not transaction_ids:
            return (
                f"Confirm that you recognize all reviewed activity on card ending "
                f"{alert.card_last_four}; no fraud dispute or replacement card will be opened."
            )

        selected_authorizations = set(authorization_ids)
        selected_transactions = set(transaction_ids)
        descriptions: list[str] = []
        for item in alert.suspicious_transactions or []:
            if (
                str(item.get("authorization_id")) not in selected_authorizations
                and str(item.get("transaction_id")) not in selected_transactions
            ):
                continue
            merchant = str(item.get("merchant_name") or "unknown merchant")
            amount_cents = int(item.get("amount_cents") or 0)
            descriptions.append(f"${amount_cents / 100:,.2f} at {merchant}")
        selection = ", ".join(descriptions) or (
            f"{len(authorization_ids) + len(transaction_ids)} selected transaction(s)"
        )
        followups = []
        if issue_replacement:
            followups.append("block the current card and issue a replacement")
        if escalate:
            followups.append("request specialist review")
        suffix = f", and {' and '.join(followups)}" if followups else ""
        return (
            f"Confirm that you want to dispute {selection} on card ending "
            f"{alert.card_last_four}{suffix}."
        )
