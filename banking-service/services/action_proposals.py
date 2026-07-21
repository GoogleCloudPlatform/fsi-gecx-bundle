"""Lifecycle primitives for banking-owned consequential-action proposals.

This module is intentionally not exposed as a generic MCP surface. Domain
services create typed proposals; trusted runtime adapters advance presentation
and confirmation state; domain commit services claim and complete execution.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_

from models.action_proposal import ActionProposal
from models.fraud import FraudAlert
from models.identity import User
from repositories.fraud import FraudAlertRepository
from services.action_proposal_context import ProposalRuntimeContext
from utils.audit import record_audit_event


TRIAGE_FRAUD_CASE = "TRIAGE_FRAUD_CASE"
FRAUD_TRIAGE_CONTRACT_VERSION = "fraud-triage.v1"
DEFAULT_PROPOSAL_TTL_SECONDS = 180

TERMINAL_STATUSES = {"COMMITTED", "DECLINED", "INVALIDATED", "EXPIRED"}


class ProposalError(ValueError):
    """Base error for proposal contract violations."""


class ProposalConflictError(ProposalError):
    """The same idempotency key was reused for a different proposal."""


class ProposalTransitionError(ProposalError):
    """A requested lifecycle transition is not legal."""


class ProposalScopeError(ProposalError):
    """A proposal does not belong to the supplied trusted execution scope."""


@dataclass(frozen=True)
class CommitClaim:
    proposal: ActionProposal
    should_execute: bool


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _as_utc(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def _canonical_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if not isinstance(payload, dict):
        raise ProposalError("Action proposal payload must be an object.")
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProposalError(
            "Action proposal payload must be JSON serializable."
        ) from exc
    canonical = json.loads(encoded)
    return canonical, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalized_ids(values: list[str] | None) -> list[str]:
    return sorted(
        {str(value).strip() for value in (values or []) if str(value).strip()}
    )


class ActionProposalService:
    def __init__(self, db):
        self.db = db

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

    def mark_presented(
        self,
        proposal_id,
        *,
        assistant_turn_id: str,
        now: datetime.datetime | None = None,
    ) -> ActionProposal:
        proposal = self._get_locked(proposal_id)
        now = _as_utc(now or _utcnow())
        self._expire_if_needed(proposal, now)
        if proposal.status == "PRESENTED":
            if proposal.presented_assistant_turn_id != assistant_turn_id:
                raise ProposalConflictError(
                    "Proposal was already presented on a different assistant turn."
                )
            return proposal
        self._require_status(proposal, "PROPOSED", transition="present")
        proposal.status = "PRESENTED"
        proposal.presented_assistant_turn_id = assistant_turn_id
        proposal.presented_at = now
        self.db.flush()
        return proposal

    def confirm(
        self,
        proposal_id,
        *,
        customer_turn_id: str,
        protected_evidence: dict[str, Any],
        now: datetime.datetime | None = None,
    ) -> ActionProposal:
        proposal = self._get_locked(proposal_id)
        now = _as_utc(now or _utcnow())
        self._expire_if_needed(proposal, now)
        if proposal.status == "CONFIRMED":
            if proposal.confirmation_customer_turn_id != customer_turn_id:
                raise ProposalConflictError(
                    "Proposal was already confirmed on a different customer turn."
                )
            return proposal
        self._require_status(proposal, "PRESENTED", transition="confirm")
        if (
            not customer_turn_id
            or customer_turn_id == proposal.originating_customer_turn_id
        ):
            raise ProposalTransitionError(
                "Confirmation must come from a later real customer turn."
            )
        evidence, _ = _canonical_payload(protected_evidence)
        if not evidence:
            raise ProposalError("Protected confirmation evidence is required.")
        proposal.status = "CONFIRMED"
        proposal.confirmation_customer_turn_id = customer_turn_id
        proposal.confirmation_evidence = evidence
        proposal.confirmed_at = now
        self.db.flush()
        return proposal

    def decline(
        self,
        proposal_id,
        *,
        customer_turn_id: str,
        now: datetime.datetime | None = None,
    ) -> ActionProposal:
        proposal = self._get_locked(proposal_id)
        now = _as_utc(now or _utcnow())
        self._expire_if_needed(proposal, now)
        if proposal.status == "DECLINED":
            return proposal
        self._require_status(proposal, "PRESENTED", transition="decline")
        proposal.status = "DECLINED"
        proposal.confirmation_customer_turn_id = customer_turn_id
        proposal.invalidation_reason = "CUSTOMER_DECLINED"
        proposal.completed_at = now
        self.db.flush()
        return proposal

    def invalidate(
        self,
        proposal_id,
        *,
        reason: str,
        now: datetime.datetime | None = None,
    ) -> ActionProposal:
        proposal = self._get_locked(proposal_id)
        if proposal.status == "INVALIDATED":
            return proposal
        if proposal.status in TERMINAL_STATUSES or proposal.status == "COMMITTING":
            raise ProposalTransitionError(
                f"Cannot invalidate proposal in {proposal.status} status."
            )
        proposal.status = "INVALIDATED"
        proposal.invalidation_reason = reason
        proposal.completed_at = _as_utc(now or _utcnow())
        self.db.flush()
        return proposal

    def claim_commit(
        self,
        proposal_id,
        *,
        customer_id,
        support_session_id: str,
        runtime_name: str,
        runtime_session_id: str,
        reset_generation: str,
        expected_action_type: str,
        now: datetime.datetime | None = None,
    ) -> CommitClaim:
        """Atomically claim execution after validating trusted proposal scope."""
        proposal = self._get_locked(proposal_id)
        self._validate_scope(
            proposal,
            customer_id=customer_id,
            support_session_id=support_session_id,
            runtime_name=runtime_name,
            runtime_session_id=runtime_session_id,
            expected_action_type=expected_action_type,
        )
        now = _as_utc(now or _utcnow())
        if proposal.status == "COMMITTED":
            return CommitClaim(proposal=proposal, should_execute=False)
        if proposal.status == "COMMITTING":
            return CommitClaim(proposal=proposal, should_execute=False)
        self._expire_if_needed(proposal, now)
        if proposal.reset_generation != reset_generation:
            if proposal.status not in TERMINAL_STATUSES:
                proposal.status = "INVALIDATED"
                proposal.invalidation_reason = "RESET_GENERATION_CHANGED"
                proposal.completed_at = now
                self.db.flush()
            raise ProposalScopeError("Proposal was invalidated by a session reset.")
        self._require_status(proposal, "CONFIRMED", transition="commit")
        proposal.status = "COMMITTING"
        proposal.commit_started_at = now
        self.db.flush()
        return CommitClaim(proposal=proposal, should_execute=True)

    def mark_committed(
        self,
        proposal_id,
        *,
        result_payload: dict[str, Any],
        now: datetime.datetime | None = None,
    ) -> ActionProposal:
        proposal = self._get_locked(proposal_id)
        result, _ = _canonical_payload(result_payload)
        if proposal.status == "COMMITTED":
            if proposal.result_payload != result:
                raise ProposalConflictError(
                    "Committed proposal already has a different result."
                )
            return proposal
        self._require_status(proposal, "COMMITTING", transition="complete commit")
        proposal.status = "COMMITTED"
        proposal.result_payload = result
        proposal.completed_at = _as_utc(now or _utcnow())
        self.db.flush()
        return proposal

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
        """Execute a confirmed fraud proposal in one caller-owned transaction."""
        proposal = self._get_locked(proposal_id)
        try:
            claim = self.claim_commit(
                proposal.id,
                customer_id=customer_id,
                support_session_id=support_session_id,
                runtime_name=runtime_name,
                runtime_session_id=runtime_session_id,
                reset_generation=reset_generation,
                expected_action_type=TRIAGE_FRAUD_CASE,
                now=now,
            )
        except (ProposalScopeError, ProposalTransitionError):
            if proposal.status in {"INVALIDATED", "EXPIRED"}:
                try:
                    self._record_disposition_event(proposal)
                    self.db.commit()
                except Exception:
                    self.db.rollback()
                    raise
            else:
                self.db.rollback()
            raise

        workflow_key = self._fraud_workflow_idempotency_key(proposal)
        if not claim.should_execute:
            if proposal.status == "COMMITTED":
                return self._proposal_result(proposal, idempotent_replay=True)
            try:
                reconciled = self._reconcile_committing_fraud_proposal(
                    proposal, workflow_key=workflow_key, now=now
                )
            except Exception:
                self.db.rollback()
                raise
            if reconciled:
                self.db.commit()
                return self._proposal_result(proposal, idempotent_replay=True)
            return {
                "success": False,
                "proposal_id": str(proposal.id),
                "action_type": proposal.action_type,
                "status": "COMMITTING",
                "idempotent_replay": True,
                "message": "Fraud proposal commit is already in progress.",
            }

        payload = dict(proposal.action_payload or {})
        alert = (
            self.db.query(FraudAlert)
            .filter(
                FraudAlert.id == payload.get("fraud_alert_id"),
                FraudAlert.customer_id == proposal.customer_id,
                FraudAlert.credit_account_id == proposal.account_id,
            )
            .with_for_update()
            .first()
        )
        if not alert or alert.status != "OPEN":
            proposal.status = "INVALIDATED"
            proposal.invalidation_reason = "FRAUD_ALERT_NO_LONGER_OPEN"
            proposal.completed_at = _as_utc(now or _utcnow())
            try:
                self._record_disposition_event(proposal)
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
            raise ProposalTransitionError(
                "Fraud alert is no longer open; create a new proposal from current state."
            )

        try:
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
                    "fraud_alert_id": str(alert.id),
                    "payload_fingerprint": proposal.payload_fingerprint,
                },
            )
            from services.fraud_alerts import FraudAlertService

            result = FraudAlertService(self.db)._triage_fraud_case_in_transaction(
                auth_provider_uid=alert.auth_provider_uid,
                fraud_alert_id=str(alert.id),
                disputed_authorization_ids=payload.get("disputed_authorization_ids"),
                disputed_transaction_ids=payload.get("disputed_transaction_ids"),
                issue_replacement=bool(payload.get("issue_replacement")),
                escalate=bool(payload.get("escalate")),
                idempotency_key=workflow_key,
            )
            committed = self.mark_committed(
                proposal.id,
                result_payload=result,
                now=now,
            )
            record_audit_event(
                self.db,
                "ACTION_PROPOSAL_COMMITTED",
                {
                    "proposal_id": str(committed.id),
                    "correlation_id": str(committed.id),
                    "action_type": committed.action_type,
                    "contract_version": committed.contract_version,
                    "customer_id": str(committed.customer_id),
                    "account_id": str(committed.account_id),
                    "support_session_id": committed.support_session_id,
                    "runtime_name": committed.runtime_name,
                    "fraud_alert_id": str(alert.id),
                    "outcome": result.get("outcome"),
                    "payload_fingerprint": committed.payload_fingerprint,
                },
            )
            self.db.commit()
            return self._proposal_result(committed, idempotent_replay=False)
        except Exception:
            self.db.rollback()
            raise

    def commit_fraud_triage_for_identity(
        self,
        proposal_id,
        *,
        customer_identity: str,
        runtime_context: ProposalRuntimeContext,
    ) -> dict[str, Any]:
        """Attest protected later-turn evidence and commit an opaque proposal id."""
        runtime_context.require_confirmation()
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
        if proposal.status == "PROPOSED":
            self.mark_presented(
                proposal.id,
                assistant_turn_id=str(runtime_context.presentation_turn_id),
            )
        if proposal.status == "PRESENTED":
            self.confirm(
                proposal.id,
                customer_turn_id=str(runtime_context.confirmation_turn_id),
                protected_evidence={
                    "method": runtime_context.confirmation_method,
                    "classification": runtime_context.confirmation_classification,
                    "runtime_name": runtime_context.runtime_name,
                    "runtime_session_id": runtime_context.runtime_session_id,
                    "presentation_turn_id": runtime_context.presentation_turn_id,
                    "confirmation_turn_id": runtime_context.confirmation_turn_id,
                },
            )
        return self.commit_fraud_triage(
            proposal.id,
            customer_id=customer_id,
            support_session_id=runtime_context.support_session_id,
            runtime_name=runtime_context.runtime_name,
            runtime_session_id=runtime_context.runtime_session_id,
            reset_generation=runtime_context.reset_generation,
        )

    @staticmethod
    def proposal_view(proposal: ActionProposal) -> dict[str, Any]:
        payload = dict(proposal.action_payload or {})
        return {
            "success": True,
            "proposal_id": str(proposal.id),
            "action_type": proposal.action_type,
            "contract_version": proposal.contract_version,
            "status": proposal.status,
            "confirmation_policy": proposal.confirmation_policy,
            "customer_safe_summary": proposal.customer_safe_summary,
            "display_selection": {
                "fraud_alert_id": payload.get("fraud_alert_id"),
                "disputed_authorization_ids": payload.get(
                    "disputed_authorization_ids", []
                ),
                "disputed_transaction_ids": payload.get("disputed_transaction_ids", []),
                "issue_replacement": bool(payload.get("issue_replacement")),
                "escalate": bool(payload.get("escalate")),
            },
            "expires_at": _as_utc(proposal.expires_at).isoformat(),
        }

    def _create(self, **values) -> ActionProposal:
        required_strings = (
            "contract_version",
            "action_type",
            "support_session_id",
            "runtime_name",
            "runtime_session_id",
            "originating_customer_turn_id",
            "reset_generation",
            "confirmation_policy",
            "customer_safe_summary",
            "idempotency_key",
        )
        for field in required_strings:
            if not str(values.get(field) or "").strip():
                raise ProposalError(f"{field} is required.")

        payload, fingerprint = _canonical_payload(values.pop("action_payload"))
        existing = (
            self.db.query(ActionProposal)
            .filter(
                ActionProposal.customer_id == values["customer_id"],
                ActionProposal.support_session_id == values["support_session_id"],
                ActionProposal.action_type == values["action_type"],
                ActionProposal.idempotency_key == values["idempotency_key"],
            )
            .first()
        )
        if existing:
            immutable_match = (
                existing.payload_fingerprint == fingerprint
                and str(existing.account_id or "")
                == str(values.get("account_id") or "")
                and existing.runtime_name == values["runtime_name"]
                and existing.runtime_session_id == values["runtime_session_id"]
                and existing.originating_customer_turn_id
                == values["originating_customer_turn_id"]
                and existing.reset_generation == values["reset_generation"]
                and existing.catalog_snapshot_id == values.get("catalog_snapshot_id")
            )
            if not immutable_match:
                raise ProposalConflictError(
                    "Idempotency key is already bound to a different proposal."
                )
            return existing

        now = _utcnow()
        expires_at = values.pop("expires_at", None) or (
            now + datetime.timedelta(seconds=DEFAULT_PROPOSAL_TTL_SECONDS)
        )
        expires_at = _as_utc(expires_at)
        if expires_at <= now:
            raise ProposalError("Proposal expiration must be in the future.")
        proposal = ActionProposal(
            **values,
            status="PROPOSED",
            action_payload=payload,
            payload_fingerprint=fingerprint,
            expires_at=expires_at,
        )
        self.db.add(proposal)
        self.db.flush()
        return proposal

    def _reconcile_committing_fraud_proposal(
        self,
        proposal: ActionProposal,
        *,
        workflow_key: str,
        now: datetime.datetime | None,
    ) -> bool:
        """Finish proposal state when its durable domain result already exists."""
        fraud_alert_id = (proposal.action_payload or {}).get("fraud_alert_id")
        if not fraud_alert_id:
            return False
        action = FraudAlertRepository(self.db).get_case_action_by_idempotency_key(
            fraud_alert_id=fraud_alert_id,
            idempotency_key=workflow_key,
        )
        if not action or action.status != "SUCCEEDED":
            return False
        result = dict(action.result_payload or {})
        self.mark_committed(proposal.id, result_payload=result, now=now)
        record_audit_event(
            self.db,
            "ACTION_PROPOSAL_COMMIT_RECONCILED",
            {
                "proposal_id": str(proposal.id),
                "correlation_id": str(proposal.id),
                "action_type": proposal.action_type,
                "customer_id": str(proposal.customer_id),
                "fraud_alert_id": str(fraud_alert_id),
                "domain_action_id": str(action.id),
                "outcome": result.get("outcome"),
            },
        )
        return True

    @staticmethod
    def _fraud_workflow_idempotency_key(proposal: ActionProposal) -> str:
        return f"proposal:{proposal.id}:{proposal.payload_fingerprint[:48]}"

    @staticmethod
    def _proposal_result(
        proposal: ActionProposal, *, idempotent_replay: bool
    ) -> dict[str, Any]:
        result = dict(proposal.result_payload or {})
        result.update(
            {
                "proposal_id": str(proposal.id),
                "action_type": proposal.action_type,
                "contract_version": proposal.contract_version,
                "status": proposal.status,
                "idempotent_replay": idempotent_replay,
            }
        )
        return result

    def _record_disposition_event(self, proposal: ActionProposal) -> None:
        record_audit_event(
            self.db,
            f"ACTION_PROPOSAL_{proposal.status}",
            {
                "proposal_id": str(proposal.id),
                "correlation_id": str(proposal.id),
                "action_type": proposal.action_type,
                "contract_version": proposal.contract_version,
                "customer_id": str(proposal.customer_id),
                "account_id": str(proposal.account_id or "") or None,
                "support_session_id": proposal.support_session_id,
                "runtime_name": proposal.runtime_name,
                "reason": proposal.invalidation_reason,
            },
        )

    def _get_locked(self, proposal_id) -> ActionProposal:
        proposal = (
            self.db.query(ActionProposal)
            .filter(ActionProposal.id == proposal_id)
            .with_for_update()
            .first()
        )
        if not proposal:
            raise ProposalError("Action proposal was not found.")
        return proposal

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

    def _expire_if_needed(
        self, proposal: ActionProposal, now: datetime.datetime
    ) -> None:
        if (
            proposal.status not in TERMINAL_STATUSES
            and _as_utc(proposal.expires_at) <= now
        ):
            proposal.status = "EXPIRED"
            proposal.invalidation_reason = "PROPOSAL_EXPIRED"
            proposal.completed_at = now
            self.db.flush()
            raise ProposalTransitionError("Action proposal has expired.")

    @staticmethod
    def _require_status(
        proposal: ActionProposal, required: str, *, transition: str
    ) -> None:
        if proposal.status != required:
            raise ProposalTransitionError(
                f"Cannot {transition} proposal in {proposal.status} status; "
                f"expected {required}."
            )

    @staticmethod
    def _validate_scope(
        proposal: ActionProposal,
        *,
        customer_id,
        support_session_id: str,
        runtime_name: str,
        runtime_session_id: str,
        expected_action_type: str,
    ) -> None:
        expected = (
            str(customer_id),
            support_session_id,
            runtime_name,
            runtime_session_id,
            expected_action_type,
        )
        actual = (
            str(proposal.customer_id),
            proposal.support_session_id,
            proposal.runtime_name,
            proposal.runtime_session_id,
            proposal.action_type,
        )
        if actual != expected:
            raise ProposalScopeError(
                "Action proposal does not belong to this customer and runtime session."
            )

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
