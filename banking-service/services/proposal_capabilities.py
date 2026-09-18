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

"""Code-owned banking capabilities used by declarative service actions."""

from dataclasses import dataclass
from typing import Callable, Any
from models.action_proposal import ActionProposal
from models.fraud import FraudAlert
from repositories.credit_card import CreditCardRepository
from repositories.fraud import FraudAlertRepository
from services.credit_card import issue_replacement_card, queue_wallet_provisioning
from services.fraud_money import fraud_money_facts
from services.fraud_presentation import fraud_proposal_summary
from services.proposal_lifecycle import (
    ActionPreconditionError,
    ProposalScopeError,
    ProposalError,
)
from utils.audit import record_audit_event


def default_reconcile(db, proposal: ActionProposal) -> dict[str, Any] | None:
    return None


def default_commit_pending_message(db, proposal: ActionProposal) -> str:
    return "Action proposal commit is already in progress."


def default_validate_current_preconditions(db, proposal: ActionProposal) -> None:
    return None


def default_record_commit_started(db, proposal: ActionProposal) -> None:
    return None


def default_record_reconciled(
    db, proposal: ActionProposal, result: dict[str, Any]
) -> None:
    return None


def default_record_committed(
    db, proposal: ActionProposal, result: dict[str, Any]
) -> None:
    record_audit_event(
        db,
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


def card_execute(db, proposal: ActionProposal) -> dict[str, Any]:
    payload = dict(proposal.action_payload or {})
    replacement = issue_replacement_card(
        db,
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


def wallet_execute(db, proposal: ActionProposal) -> dict[str, Any]:
    payload = dict(proposal.action_payload or {})
    wallet = queue_wallet_provisioning(
        db,
        account_id=str(proposal.account_id),
        card_token=str(payload.get("card_token") or ""),
        wallet_provider=payload["wallet_provider"],
        initiated_by="CUSTOMER_VOICE_SUPPORT",
        commit_transaction=False,
    )
    return {
        "success": True,
        "message": wallet.get("message"),
        **wallet,
    }


def fraud_commit_pending_message(db, proposal: ActionProposal) -> str:
    return "Fraud proposal commit is already in progress."


def fraud_workflow_key(db, proposal: ActionProposal) -> str:
    return f"proposal:{proposal.id}:{proposal.payload_fingerprint[:48]}"


def fraud_locked_alert(db, proposal: ActionProposal):
    payload = dict(proposal.action_payload or {})
    return (
        db.query(FraudAlert)
        .filter(
            FraudAlert.id == payload.get("fraud_alert_id"),
            FraudAlert.customer_id == proposal.customer_id,
            FraudAlert.credit_account_id == proposal.account_id,
        )
        .with_for_update()
        .first()
    )


def fraud_validate_current_preconditions(db, proposal: ActionProposal) -> None:
    alert = fraud_locked_alert(db, proposal)
    if not alert or alert.status != "OPEN":
        raise ActionPreconditionError(
            "Fraud alert is no longer open; create a new proposal from current state.",
            reason="FRAUD_ALERT_NO_LONGER_OPEN",
        )


def fraud_execute(db, proposal: ActionProposal) -> dict[str, Any]:
    from services.fraud_alerts import FraudAlertService

    payload = dict(proposal.action_payload or {})
    alert = fraud_locked_alert(db, proposal)
    return FraudAlertService(db)._triage_fraud_case_in_transaction(
        auth_provider_uid=alert.auth_provider_uid,
        fraud_alert_id=str(alert.id),
        disputed_authorization_ids=payload.get("disputed_authorization_ids"),
        disputed_transaction_ids=payload.get("disputed_transaction_ids"),
        issue_replacement=bool(payload.get("issue_replacement")),
        escalate=bool(payload.get("escalate")),
        idempotency_key=fraud_workflow_key(db, proposal),
    )


def fraud_reconcile(db, proposal: ActionProposal) -> dict[str, Any] | None:
    fraud_alert_id = (proposal.action_payload or {}).get("fraud_alert_id")
    if not fraud_alert_id:
        return None
    action = FraudAlertRepository(db).get_case_action_by_idempotency_key(
        fraud_alert_id=fraud_alert_id,
        idempotency_key=fraud_workflow_key(db, proposal),
    )
    if not action or action.status != "SUCCEEDED":
        return None
    return dict(action.result_payload or {})


def fraud_record_commit_started(db, proposal: ActionProposal) -> None:
    payload = dict(proposal.action_payload or {})
    record_audit_event(
        db,
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


def fraud_record_committed(
    db, proposal: ActionProposal, result: dict[str, Any]
) -> None:
    payload = dict(proposal.action_payload or {})
    record_audit_event(
        db,
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


def fraud_record_reconciled(
    db, proposal: ActionProposal, result: dict[str, Any]
) -> None:
    fraud_alert_id = (proposal.action_payload or {}).get("fraud_alert_id")
    action = FraudAlertRepository(db).get_case_action_by_idempotency_key(
        fraud_alert_id=fraud_alert_id,
        idempotency_key=fraud_workflow_key(db, proposal),
    )
    record_audit_event(
        db,
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


def normalized_ids(values):
    return sorted(
        {str(value).strip() for value in (values or []) if str(value).strip()}
    )


def prepare_fraud(db, customer_id, inputs, parameters):
    fraud_alert_id = inputs["fraud_alert_id"]
    disputed_authorization_ids = inputs.get("disputed_authorization_ids")
    disputed_transaction_ids = inputs.get("disputed_transaction_ids")
    issue_replacement = inputs["issue_replacement"]
    escalate = inputs["escalate"]
    alert = (
        db.query(FraudAlert)
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

    authorization_ids = normalized_ids(disputed_authorization_ids)
    transaction_ids = normalized_ids(disputed_transaction_ids)
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

    facts = [
        fact
        for fact in fraud_money_facts(CreditCardRepository(db), alert)
        if str(fact.get("authorization_id")) in set(authorization_ids)
        or str(fact.get("transaction_id")) in set(transaction_ids)
    ]
    summary = fraud_proposal_summary(
        card_last_four=alert.card_last_four,
        facts=facts,
        issue_replacement=bool(issue_replacement),
        escalate=bool(escalate),
    )
    payload = {
        "money_facts": facts,
        "card_last_four": alert.card_last_four,
        "fraud_alert_id": str(alert.id),
        "disputed_authorization_ids": authorization_ids,
        "disputed_transaction_ids": transaction_ids,
        "issue_replacement": bool(issue_replacement),
        "escalate": bool(escalate),
    }
    return alert.credit_account_id, payload, summary


def prepare_card(db, customer_id, inputs, parameters):
    repo = CreditCardRepository(db)
    account = repo.get_account_by_customer(str(customer_id))
    if not account:
        raise ProposalScopeError("Active credit-card account was not found.")
    card = next(
        (
            item
            for item in repo.list_cards_by_account(account.id)
            if item.is_active
            and item.status == "ACTIVE"
            and (not parameters["require_virtual"] or item.is_virtual)
        ),
        None,
    )
    if not card:
        raise ProposalError("No active card is eligible for the requested action.")
    facts = {
        "account_id": str(account.id),
        "card_id": str(card.id),
        "compromised_card_id": str(card.id),
        "card_token": card.card_token,
        "card_last_four": card.last_four,
    }
    if "reason" in inputs:
        reason = str(inputs["reason"] or "").strip().upper()
        if reason not in {"LOST", "STOLEN", "DAMAGED"}:
            raise ProposalError("Card reissue reason must be LOST, STOLEN, or DAMAGED.")
        facts["reason"] = reason
    return account.id, facts, None


def validate_inputs(inputs, schema):
    if not isinstance(inputs, dict) or set(inputs) != set(schema):
        raise ProposalError("Business inputs do not match the operation contract.")
    for key, expected in schema.items():
        if not isinstance(inputs[key], expected):
            raise ProposalError(f"Invalid business input: {key}.")
        if isinstance(inputs[key], list) and any(
            not isinstance(v, str) for v in inputs[key]
        ):
            raise ProposalError("Selection IDs must be lists of strings.")


def public_fraud_inputs(db, identity, inputs):
    from services.fraud_alerts import FraudAlertService

    review_keys = (
        "fraud_alert_id",
        "selection_status",
        "disputed_authorization_ids",
        "disputed_transaction_ids",
        "recognized_authorization_ids",
        "recognized_transaction_ids",
    )
    review = FraudAlertService(db).review_open_alert_selection(
        auth_provider_uid=identity, **{key: inputs[key] for key in review_keys}
    )
    if review.get("success") is not True or review.get("ready_to_propose") is not True:
        raise ProposalError(
            review.get("message") or "Complete the fraud selection first."
        )
    return {
        key: value
        for key, value in inputs.items()
        if key
        not in {
            "selection_status",
            "recognized_authorization_ids",
            "recognized_transaction_ids",
        }
    }


def public_inputs_unchanged(db, identity, inputs):
    return inputs


@dataclass(frozen=True)
class Operation:
    execute: Callable
    prepare: Callable
    payload_schema: dict
    input_schema: dict
    parameters: dict
    literal_bindings: dict
    template_fields: frozenset
    public_fields: frozenset
    required_facts: frozenset
    public_input_schema: dict | None = None
    normalize_public_inputs: Callable = public_inputs_unchanged
    validate: Callable = default_validate_current_preconditions
    reconcile: Callable = default_reconcile
    started: Callable = default_record_commit_started
    committed: Callable = default_record_committed
    reconciled: Callable = default_record_reconciled
    pending: Callable = default_commit_pending_message


OPERATIONS = {
    "fraud.triage.v1": Operation(
        execute=fraud_execute,
        prepare=prepare_fraud,
        public_input_schema={
            "fraud_alert_id": str,
            "selection_status": str,
            "disputed_authorization_ids": list,
            "disputed_transaction_ids": list,
            "recognized_authorization_ids": list,
            "recognized_transaction_ids": list,
            "issue_replacement": bool,
            "escalate": bool,
        },
        normalize_public_inputs=public_fraud_inputs,
        input_schema={
            "fraud_alert_id": str,
            "issue_replacement": bool,
            "escalate": bool,
            "disputed_authorization_ids": (list, type(None)),
            "disputed_transaction_ids": (list, type(None)),
        },
        parameters={},
        literal_bindings={},
        template_fields=frozenset(),
        payload_schema={
            "fraud_alert_id": str,
            "disputed_authorization_ids": list,
            "disputed_transaction_ids": list,
            "issue_replacement": bool,
            "escalate": bool,
            "money_facts": list,
            "card_last_four": str,
        },
        public_fields=frozenset(
            [
                "fraud_alert_id",
                "disputed_authorization_ids",
                "disputed_transaction_ids",
                "issue_replacement",
                "escalate",
                "money_facts",
                "card_last_four",
                "issue_replacement",
                "escalate",
            ]
        ),
        required_facts=frozenset(
            [
                "card_last_four",
                "proposed_disposition",
                "replacement_and_escalation_consequences",
                "reviewed_activity_selection",
            ]
        ),
        validate=fraud_validate_current_preconditions,
        reconcile=fraud_reconcile,
        started=fraud_record_commit_started,
        committed=fraud_record_committed,
        reconciled=fraud_record_reconciled,
        pending=fraud_commit_pending_message,
    ),
    "cards.issue_replacement.v1": Operation(
        execute=card_execute,
        prepare=prepare_card,
        input_schema={"reason": str},
        parameters={"require_virtual": False},
        literal_bindings={"issue_virtual_card": True},
        template_fields=frozenset({"card_last_four"}),
        payload_schema={
            "account_id": str,
            "compromised_card_id": str,
            "reason": str,
            "issue_virtual_card": bool,
        },
        public_fields=frozenset(["reason", "issue_virtual_card"]),
        required_facts=frozenset(
            ["card_last_four", "current_card_blocking", "replacement_card_form"]
        ),
    ),
    "cards.queue_wallet.v1": Operation(
        execute=wallet_execute,
        prepare=prepare_card,
        input_schema={},
        parameters={"require_virtual": True},
        literal_bindings={"wallet_provider": "GOOGLE_WALLET"},
        template_fields=frozenset({"card_last_four"}),
        payload_schema={
            "account_id": str,
            "card_id": str,
            "card_token": str,
            "wallet_provider": str,
        },
        public_fields=frozenset(["wallet_provider"]),
        required_facts=frozenset(
            ["card_last_four", "provisioning_is_queued", "wallet_provider"]
        ),
    ),
}
