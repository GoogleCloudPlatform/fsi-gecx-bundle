"""Lifecycle primitives for banking-owned consequential-action proposals.

This module is intentionally not exposed as a generic MCP surface. Domain
services create typed proposals; trusted runtime adapters advance presentation
and confirmation state; domain commit services claim and complete execution.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from models.action_proposal import ActionProposal
from models.fraud import FraudAlert


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
