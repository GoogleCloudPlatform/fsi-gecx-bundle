# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Action-neutral durable lifecycle engine for banking proposals."""

from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.exc import IntegrityError

from models.action_proposal import ActionProposal
from models.identity import User
from services.action_proposal_context import ProposalRuntimeContext, RuntimeContextError
from services.proposal_protocol import (
    ActionRegistry,
    RecoveryClass,
    RuntimeEvidenceValidator,
    ValidatedRuntimeEvidence,
)
from utils.audit import record_audit_event


DEFAULT_PROPOSAL_TTL_SECONDS = 180
ACTIVE_PROPOSAL_STATUSES = ("PROPOSED", "PRESENTED", "CONFIRMED", "COMMITTING")
TERMINAL_STATUSES = {"COMMITTED", "DECLINED", "INVALIDATED", "EXPIRED"}


class ProposalError(ValueError):
    """Base error for proposal contract violations."""

    default_code = "PROPOSAL_REJECTED"
    default_recovery_class = RecoveryClass.CORRECT_REQUEST
    default_customer_message = "The action proposal request was rejected."

    def __init__(
        self,
        operator_message: str,
        *,
        code: str | None = None,
        recovery_class: RecoveryClass | None = None,
        customer_message: str | None = None,
        proposal: ActionProposal | None = None,
    ):
        super().__init__(operator_message)
        self.code = code or self.default_code
        self.recovery_class = recovery_class or self.default_recovery_class
        self.customer_message = customer_message or self.default_customer_message
        self.proposal = proposal

    def safe_result(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "error": self.code,
            "recovery_class": self.recovery_class.value,
            "message": self.customer_message,
        }
        if self.proposal is not None:
            result.update(
                {
                    "proposal_id": str(self.proposal.id),
                    "action_type": self.proposal.action_type,
                    "status": self.proposal.status,
                }
            )
        return result


class ProposalConflictError(ProposalError):
    """The same idempotency key was reused for a different proposal."""

    default_code = "PROPOSAL_CONFLICT"


class ProposalTransitionError(ProposalError):
    """A requested lifecycle transition is not legal."""

    default_code = "PROPOSAL_STATE_INVALID"


class ProposalScopeError(ProposalError):
    """A proposal does not belong to the supplied trusted execution scope."""

    default_code = "PROPOSAL_SCOPE_MISMATCH"
    default_recovery_class = RecoveryClass.REFRESH_SESSION
    default_customer_message = (
        "The action proposal is not available in this customer support session."
    )


class ActiveProposalExistsError(ProposalConflictError):
    """The support session already has an unresolved proposal."""

    default_code = "ACTIVE_PROPOSAL_EXISTS"
    default_recovery_class = RecoveryClass.RESOLVE_ACTIVE_PROPOSAL
    default_customer_message = (
        "Resolve the current action proposal before proposing another action."
    )


class ActionPreconditionError(ProposalTransitionError):
    """The domain state bound to a proposal is no longer executable."""

    def __init__(self, message: str, *, reason: str):
        super().__init__(
            message,
            code="ACTION_PRECONDITION_CHANGED",
            recovery_class=RecoveryClass.CREATE_NEW_PROPOSAL,
            customer_message=(
                "The underlying account state changed. Review current information "
                "before creating a new proposal."
            ),
        )
        self.reason = reason


@dataclass(frozen=True)
class CommitClaim:
    proposal: ActionProposal
    should_execute: bool


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def as_utc(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def canonical_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
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


class ProposalLifecycleEngine:
    """Own lifecycle, locking, idempotency, execution, and reconciliation."""

    def __init__(
        self,
        db,
        *,
        registry: ActionRegistry,
        evidence_validator: RuntimeEvidenceValidator | None = None,
        audit_recorder: Callable[..., None] = record_audit_event,
    ):
        self.db = db
        self.registry = registry
        self.evidence_validator = evidence_validator or RuntimeEvidenceValidator()
        self.audit_recorder = audit_recorder

    def create(self, **values) -> ActionProposal:
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

        specification = self.registry.require(values["action_type"])
        if values["contract_version"] != specification.contract_version:
            raise ProposalError("Action contract version does not match registration.")
        if (
            values["confirmation_policy"]
            != specification.authorization_policy.durable_confirmation_policy
        ):
            raise ProposalError("Confirmation policy does not match registration.")
        try:
            specification.validate_payload(values["action_payload"])
        except ValueError as exc:
            raise ProposalError(str(exc)) from exc
        payload, fingerprint = canonical_payload(values.pop("action_payload"))
        existing = self._find_idempotent_proposal(values)
        if existing:
            return self._validate_idempotent_replay(
                existing,
                values=values,
                fingerprint=fingerprint,
            )

        now = utcnow()
        active = self._lock_and_find_active_proposal(
            customer_id=values["customer_id"],
            support_session_id=values["support_session_id"],
            now=now,
        )
        if active is not None:
            raise ActiveProposalExistsError(
                f"Active proposal {active.id} blocks replacement in this session.",
                proposal=active,
            )
        expires_at = values.pop("expires_at", None) or (
            now + datetime.timedelta(seconds=DEFAULT_PROPOSAL_TTL_SECONDS)
        )
        expires_at = as_utc(expires_at)
        if expires_at <= now:
            raise ProposalError("Proposal expiration must be in the future.")
        proposal = ActionProposal(
            **values,
            status="PROPOSED",
            action_payload=payload,
            payload_fingerprint=fingerprint,
            expires_at=expires_at,
        )
        try:
            with self.db.begin_nested():
                self.db.add(proposal)
                self.db.flush()
        except IntegrityError:
            existing = self._find_idempotent_proposal(values)
            if existing is not None:
                return self._validate_idempotent_replay(
                    existing,
                    values=values,
                    fingerprint=fingerprint,
                )
            active = self._find_active_proposal(
                customer_id=values["customer_id"],
                support_session_id=values["support_session_id"],
            )
            if active is not None:
                raise ActiveProposalExistsError(
                    f"Concurrent active proposal {active.id} won this session scope.",
                    proposal=active,
                )
            raise
        return proposal

    # Temporary compatibility seam for callers characterized in packet one.
    def _create(self, **values) -> ActionProposal:
        return self.create(**values)

    def attest_decision(
        self,
        proposal: ActionProposal,
        *,
        runtime_context: ProposalRuntimeContext,
    ) -> ValidatedRuntimeEvidence:
        evidence = self.validate_decision_evidence(
            proposal,
            runtime_context=runtime_context,
        )
        if proposal.status == "PROPOSED":
            self.mark_presented(
                proposal.id,
                assistant_turn_id=evidence.presentation_turn_id,
            )
        if proposal.status == "PRESENTED":
            self.confirm(
                proposal.id,
                customer_turn_id=evidence.decision_turn_id,
                protected_evidence=evidence.protected_evidence,
            )
        return evidence

    def validate_decision_evidence(
        self,
        proposal: ActionProposal,
        *,
        runtime_context: ProposalRuntimeContext,
    ) -> ValidatedRuntimeEvidence:
        specification = self.registry.require(proposal.action_type)
        try:
            return self.evidence_validator.validate_decision(
                runtime_context,
                specification.authorization_policy,
                presentation_requirement=specification.presentation_requirement,
            )
        except RuntimeContextError as exc:
            raise ProposalTransitionError(
                str(exc),
                code="PRESENTATION_EVIDENCE_REQUIRED",
                recovery_class=RecoveryClass.REPRESENT_AND_RECONFIRM,
                customer_message=(
                    "Present the current proposal again and obtain a later explicit "
                    "customer decision."
                ),
                proposal=proposal,
            ) from exc

    def execute_registered_commit(
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
    ) -> dict[str, Any]:
        """Execute any registered action through one transaction pipeline."""
        proposal = self._get_locked(proposal_id)
        specification = self.registry.require(expected_action_type)
        try:
            claim = self.claim_commit(
                proposal.id,
                customer_id=customer_id,
                support_session_id=support_session_id,
                runtime_name=runtime_name,
                runtime_session_id=runtime_session_id,
                reset_generation=reset_generation,
                expected_action_type=expected_action_type,
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

        handler = specification.handler
        if not claim.should_execute:
            if proposal.status == "COMMITTED":
                return self.proposal_result(proposal, idempotent_replay=True)
            try:
                result = handler.reconcile(proposal)
                if result is not None:
                    specification.validate_result(result)
                    self.mark_committed(proposal.id, result_payload=result, now=now)
                    handler.record_reconciled(proposal, result)
                    self.db.commit()
                    return self.proposal_result(proposal, idempotent_replay=True)
            except Exception:
                self.db.rollback()
                raise
            return {
                "success": False,
                "error": "COMMIT_RESULT_PENDING",
                "recovery_class": RecoveryClass.RETRY_SAME_PROPOSAL.value,
                "proposal_id": str(proposal.id),
                "action_type": proposal.action_type,
                "status": "COMMITTING",
                "idempotent_replay": True,
                "message": handler.commit_pending_message(proposal),
            }

        try:
            handler.validate_current_preconditions(proposal)
        except ActionPreconditionError as exc:
            proposal.status = "INVALIDATED"
            proposal.invalidation_reason = exc.reason
            proposal.completed_at = as_utc(now or utcnow())
            try:
                self._record_disposition_event(proposal)
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
            exc.proposal = proposal
            raise

        try:
            handler.record_commit_started(proposal)
            result = handler.execute(proposal)
            specification.validate_result(result)
            committed = self.mark_committed(
                proposal.id,
                result_payload=result,
                now=now,
            )
            handler.record_committed(committed, result)
            self.db.commit()
            return self.proposal_result(committed, idempotent_replay=False)
        except Exception:
            self.db.rollback()
            raise

    def mark_presented(
        self,
        proposal_id,
        *,
        assistant_turn_id: str,
        now: datetime.datetime | None = None,
    ) -> ActionProposal:
        proposal = self._get_locked(proposal_id)
        now = as_utc(now or utcnow())
        self._expire_if_needed(proposal, now)
        if proposal.status == "PRESENTED":
            if proposal.presented_assistant_turn_id != assistant_turn_id:
                raise ProposalConflictError(
                    "Proposal was already presented on a different assistant turn.",
                    code="PRESENTATION_EVIDENCE_REQUIRED",
                    recovery_class=RecoveryClass.REPRESENT_AND_RECONFIRM,
                    customer_message=(
                        "Present the current proposal again and obtain a later explicit "
                        "customer decision."
                    ),
                    proposal=proposal,
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
        now = as_utc(now or utcnow())
        self._expire_if_needed(proposal, now)
        if proposal.status == "CONFIRMED":
            if proposal.confirmation_customer_turn_id != customer_turn_id:
                raise ProposalConflictError(
                    "Proposal was already confirmed on a different customer turn.",
                    code="PRESENTATION_EVIDENCE_REQUIRED",
                    recovery_class=RecoveryClass.REPRESENT_AND_RECONFIRM,
                    customer_message=(
                        "Present the current proposal again and obtain a later explicit "
                        "customer decision."
                    ),
                    proposal=proposal,
                )
            return proposal
        self._require_status(proposal, "PRESENTED", transition="confirm")
        if not customer_turn_id or customer_turn_id == proposal.originating_customer_turn_id:
            raise ProposalTransitionError(
                "Confirmation must come from a later real customer turn.",
                code="PRESENTATION_EVIDENCE_REQUIRED",
                recovery_class=RecoveryClass.REPRESENT_AND_RECONFIRM,
                customer_message=(
                    "Present the current proposal and obtain a later explicit customer "
                    "decision."
                ),
                proposal=proposal,
            )
        evidence, _ = canonical_payload(protected_evidence)
        if not evidence:
            raise ProposalError(
                "Protected confirmation evidence is required.",
                code="PRESENTATION_EVIDENCE_REQUIRED",
                recovery_class=RecoveryClass.REPRESENT_AND_RECONFIRM,
                customer_message=(
                    "Present the current proposal and obtain a later explicit customer "
                    "decision."
                ),
                proposal=proposal,
            )
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
        now = as_utc(now or utcnow())
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
        proposal.completed_at = as_utc(now or utcnow())
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
        proposal = self._get_locked(proposal_id)
        self._validate_scope(
            proposal,
            customer_id=customer_id,
            support_session_id=support_session_id,
            runtime_name=runtime_name,
            runtime_session_id=runtime_session_id,
            expected_action_type=expected_action_type,
        )
        now = as_utc(now or utcnow())
        if proposal.status in {"COMMITTED", "COMMITTING"}:
            return CommitClaim(proposal=proposal, should_execute=False)
        self._expire_if_needed(proposal, now)
        if proposal.reset_generation != reset_generation:
            if proposal.status not in TERMINAL_STATUSES:
                proposal.status = "INVALIDATED"
                proposal.invalidation_reason = "RESET_GENERATION_CHANGED"
                proposal.completed_at = now
                self.db.flush()
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
        result, _ = canonical_payload(result_payload)
        if proposal.status == "COMMITTED":
            if proposal.result_payload != result:
                raise ProposalConflictError(
                    "Committed proposal already has a different result."
                )
            return proposal
        self._require_status(proposal, "COMMITTING", transition="complete commit")
        proposal.status = "COMMITTED"
        proposal.result_payload = result
        proposal.completed_at = as_utc(now or utcnow())
        self.db.flush()
        return proposal

    def proposal_view(self, proposal: ActionProposal) -> dict[str, Any]:
        specification = self.registry.require(proposal.action_type)
        return {
            "success": True,
            "proposal_id": str(proposal.id),
            "action_type": proposal.action_type,
            "contract_version": proposal.contract_version,
            "status": proposal.status,
            "confirmation_policy": proposal.confirmation_policy,
            "customer_safe_summary": proposal.customer_safe_summary,
            "display_selection": specification.handler.display_selection(proposal),
            "expires_at": as_utc(proposal.expires_at).isoformat(),
        }

    @staticmethod
    def proposal_result(
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

    # Compatibility alias retained for characterized internal callers.
    _proposal_result = proposal_result

    def _find_idempotent_proposal(self, values: dict[str, Any]):
        return (
            self.db.query(ActionProposal)
            .filter(
                ActionProposal.customer_id == values["customer_id"],
                ActionProposal.support_session_id == values["support_session_id"],
                ActionProposal.action_type == values["action_type"],
                ActionProposal.idempotency_key == values["idempotency_key"],
            )
            .first()
        )

    def _lock_and_find_active_proposal(
        self,
        *,
        customer_id,
        support_session_id: str,
        now: datetime.datetime,
    ) -> ActionProposal | None:
        # Lock the durable customer row so concurrent inserts cannot both pass
        # the active-scope check. The partial unique index remains the final
        # cross-process backstop.
        (
            self.db.query(User.id)
            .filter(User.id == customer_id)
            .with_for_update()
            .first()
        )
        proposals = (
            self.db.query(ActionProposal)
            .filter(
                ActionProposal.customer_id == customer_id,
                ActionProposal.support_session_id == support_session_id,
                ActionProposal.status.in_(ACTIVE_PROPOSAL_STATUSES),
            )
            .order_by(ActionProposal.created_at, ActionProposal.id)
            .with_for_update()
            .all()
        )
        active: ActionProposal | None = None
        for proposal in proposals:
            if proposal.status != "COMMITTING" and as_utc(proposal.expires_at) <= now:
                proposal.status = "EXPIRED"
                proposal.invalidation_reason = "PROPOSAL_EXPIRED"
                proposal.completed_at = now
                self._record_disposition_event(proposal)
                continue
            if active is None:
                active = proposal
        self.db.flush()
        return active

    def _find_active_proposal(
        self, *, customer_id, support_session_id: str
    ) -> ActionProposal | None:
        return (
            self.db.query(ActionProposal)
            .filter(
                ActionProposal.customer_id == customer_id,
                ActionProposal.support_session_id == support_session_id,
                ActionProposal.status.in_(ACTIVE_PROPOSAL_STATUSES),
            )
            .order_by(ActionProposal.created_at, ActionProposal.id)
            .first()
        )

    @staticmethod
    def _validate_idempotent_replay(
        existing: ActionProposal,
        *,
        values: dict[str, Any],
        fingerprint: str,
    ) -> ActionProposal:
        immutable_match = (
            existing.payload_fingerprint == fingerprint
            and str(existing.account_id or "") == str(values.get("account_id") or "")
            and existing.contract_version == values["contract_version"]
            and existing.runtime_name == values["runtime_name"]
            and existing.runtime_session_id == values["runtime_session_id"]
            and existing.originating_customer_turn_id
            == values["originating_customer_turn_id"]
            and existing.reset_generation == values["reset_generation"]
            and existing.confirmation_policy == values["confirmation_policy"]
            and existing.customer_safe_summary == values["customer_safe_summary"]
            and existing.catalog_snapshot_id == values.get("catalog_snapshot_id")
        )
        if not immutable_match:
            raise ProposalConflictError(
                "Idempotency key is already bound to a different proposal."
            )
        return existing

    def _record_disposition_event(self, proposal: ActionProposal) -> None:
        self.audit_recorder(
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
            raise ProposalScopeError(
                "Action proposal was not found.",
                code="PROPOSAL_SCOPE_MISMATCH",
                recovery_class=RecoveryClass.REFRESH_SESSION,
                customer_message=(
                    "The action proposal is not available in this customer support "
                    "session."
                ),
            )
        return proposal

    def _expire_if_needed(
        self, proposal: ActionProposal, now: datetime.datetime
    ) -> None:
        if proposal.status not in TERMINAL_STATUSES and as_utc(proposal.expires_at) <= now:
            proposal.status = "EXPIRED"
            proposal.invalidation_reason = "PROPOSAL_EXPIRED"
            proposal.completed_at = now
            self.db.flush()
            raise ProposalTransitionError(
                "Action proposal has expired.",
                code="PROPOSAL_EXPIRED",
                recovery_class=RecoveryClass.CREATE_NEW_PROPOSAL,
                customer_message=(
                    "The action proposal expired. Review current information before "
                    "creating a new proposal."
                ),
                proposal=proposal,
            )

    @staticmethod
    def _require_status(
        proposal: ActionProposal, required: str, *, transition: str
    ) -> None:
        if proposal.status != required:
            raise ProposalTransitionError(
                f"Cannot {transition} proposal in {proposal.status} status; "
                f"expected {required}.",
                proposal=proposal,
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
                "Action proposal does not belong to this customer and runtime session.",
                code="PROPOSAL_SCOPE_MISMATCH",
                recovery_class=RecoveryClass.REFRESH_SESSION,
                customer_message=(
                    "The action proposal is not available in this customer support "
                    "session."
                ),
                proposal=proposal,
            )
