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
from models.credit_card import CreditAccount, CreditProduct
from models.money import MAX_MINOR, Money
from services.money_presentation import project_money
from services.proposal_protocol import PolicyEvaluationEvidence
from models.fraud import FraudAlert
from repositories.credit_card import CreditCardRepository
from repositories.fraud import FraudAlertRepository
from services.credit_card import (
    CREDIT_LIMIT_POLICY,
    evaluate_credit_limit,
    apply_limit_increase,
    issue_replacement_card,
    queue_wallet_provisioning,
)
from services.fraud_money import fraud_money_facts
from services.fraud_presentation import fraud_proposal_summary
from services.proposal_lifecycle import (
    ActionPreconditionError,
    ProposalScopeError,
    ProposalError,
    ProposalPolicyError,
)


def default_reconcile(db, proposal: ActionProposal) -> dict[str, Any] | None:
    return None


def default_commit_pending_message(db, proposal: ActionProposal) -> str:
    return "Action proposal commit is already in progress."


def default_validate_current_preconditions(
    db, proposal: ActionProposal, *, provider=None
) -> None:
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
    # Proposal audit is emitted uniformly by the lifecycle engine.
    return None


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


def fraud_validate_current_preconditions(
    db, proposal: ActionProposal, *, provider=None
) -> None:
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


def normalized_ids(values):
    return sorted(
        {str(value).strip() for value in (values or []) if str(value).strip()}
    )


def prepare_fraud(
    db, customer_id, inputs, parameters, *, provider=None, preparation_context=None
):
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


def prepare_card(
    db, customer_id, inputs, parameters, *, provider=None, preparation_context=None
):
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
        if not isinstance(inputs[key], expected) or (
            expected is int and type(inputs[key]) is not int
        ):
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


def business_inputs_unchanged(inputs):
    return inputs


def fraud_business_inputs(inputs):
    return {
        **inputs,
        **{
            key: normalized_ids(inputs.get(key))
            for key in ("disputed_authorization_ids", "disputed_transaction_ids")
        },
    }


def usd_limit_text(money):
    return "$" + project_money(money)["display_text"].removeprefix("USD ")


def credit_limit_facts(account, product):
    return {
        "account_id": str(account.id),
        "account_status": account.status,
        "currency_code": account.currency,
        "product_code": account.product_code,
        "current_limit_minor": account.credit_limit_cents,
        "product_active": product.is_active if product else None,
        "minimum_limit_minor": product.min_credit_limit_cents if product else None,
        "maximum_limit_minor": product.max_credit_limit_cents if product else None,
    }


def credit_limit_arithmetic(account, requested):
    available = account.available_credit_cents
    current = account.credit_limit_cents
    amount = requested["amount_minor"]
    projected = (
        available + amount - current
        if all(type(v) is int for v in (available, current, amount))
        else None
    )
    return {
        "available_credit_minor": available if type(available) is int else None,
        "projected_available_credit_minor": projected,
    }


def prepare_credit_limit(
    db, customer_id, inputs, parameters, *, provider=None, preparation_context=None
):
    if inputs["currency_code"] not in {"USD", "MXN", "JPY", "BHD"}:
        raise ProposalError("Use a supported canonical currency code.")
    # No model-supplied account ID; fail closed on ambiguous owned scope.
    accounts = (
        db.query(CreditAccount)
        .filter(
            CreditAccount.customer_id == customer_id,
        )
        .all()
    )
    if len(accounts) != 1:
        raise ProposalScopeError("Exactly one owned active credit account is required.")
    account = accounts[0]
    product = (
        db.query(CreditProduct).filter_by(product_code=account.product_code).first()
    )
    facts = credit_limit_facts(account, product)
    requested = {
        "amount_minor": inputs["requested_limit_minor"],
        "currency_code": inputs["currency_code"],
    }
    reason = evaluate_credit_limit(facts, requested)
    # The provider owns the demo credit decision; execution guards remain local.
    if reason == "DEMO_LIMIT_CEILING_EXCEEDED":
        reason = None
    if not reason:
        delta = requested["amount_minor"] - account.credit_limit_cents
        if (
            type(account.available_credit_cents) is not int
            or not -MAX_MINOR <= account.available_credit_cents <= MAX_MINOR
            or not -MAX_MINOR <= account.available_credit_cents + delta <= MAX_MINOR
        ):
            reason = "AVAILABLE_CREDIT_OUT_OF_RANGE"
    if reason:
        facts = {**facts, **credit_limit_arithmetic(account, requested)}
        raise ProposalPolicyError(
            PolicyEvaluationEvidence(
                policy=dict(CREDIT_LIMIT_POLICY),
                facts=facts,
                requested_limit=requested,
                reason_code=reason,
            )
        )
    from services.decisioning import (
        DecisionPolicy,
        load_decisioning_provider,
        DecisionRequest,
        digest,
        validate_decision,
        utcnow,
    )

    request = DecisionRequest(
        request_ref=digest(preparation_context),
        scope_ref=digest(
            {
                key: value
                for key, value in preparation_context.items()
                if key != "input_fingerprint"
            }
        ),
        input_ref=digest({"facts": facts, "requested_limit": requested}),
        requested_limit=Money.model_validate(requested),
        facts=facts,
    )
    policy = None
    try:
        provider = provider if provider is not None else load_decisioning_provider()
        metadata = provider.current_policy
        policy = DecisionPolicy.model_validate(
            metadata.model_dump(mode="json")
            if isinstance(metadata, DecisionPolicy)
            else metadata
        )
        returned = provider.evaluate(request)
    except Exception:
        raise ProposalPolicyError(
            PolicyEvaluationEvidence(
                policy=dict(CREDIT_LIMIT_POLICY),
                facts=facts,
                requested_limit=requested,
                reason_code="BANK_DECISION_UNAVAILABLE",
                decision_failure="PROVIDER_UNAVAILABLE",
                decision_policy=policy.model_dump(mode="json")
                if policy is not None
                else None,
                decision_request=request.model_dump(mode="json"),
            )
        ) from None
    try:
        decision = validate_decision(returned, request, policy, utcnow())
    except Exception:
        raise ProposalPolicyError(
            PolicyEvaluationEvidence(
                policy=dict(CREDIT_LIMIT_POLICY),
                facts=facts,
                requested_limit=requested,
                reason_code="BANK_DECISION_INVALID",
                decision_failure="INVALID_PROVIDER_RESPONSE",
                decision_policy=policy.model_dump(mode="json"),
                decision_request=request.model_dump(mode="json"),
            )
        ) from None
    execution_reason = evaluate_credit_limit(facts, requested)
    if decision.outcome != "APPROVED" or execution_reason:
        raise ProposalPolicyError(
            PolicyEvaluationEvidence(
                policy=dict(CREDIT_LIMIT_POLICY),
                facts=facts,
                requested_limit=requested,
                reason_code=execution_reason or decision.reason_codes[0],
                bank_decision=decision.model_dump(mode="json"),
                decision_policy=policy.model_dump(mode="json"),
                decision_request=request.model_dump(mode="json"),
            )
        )
    current = Money(amount_minor=facts["current_limit_minor"], currency_code="USD")
    proposed = Money.model_validate(requested)
    increase = Money(
        amount_minor=proposed.amount_minor - current.amount_minor, currency_code="USD"
    )
    payload = {
        "account_id": str(account.id),
        "current_limit": current.model_dump(),
        "proposed_limit": proposed.model_dump(),
        "increase_amount": increase.model_dump(),
        "credit_limit_policy": dict(CREDIT_LIMIT_POLICY),
        "eligibility_facts": facts,
        "prepared_arithmetic": credit_limit_arithmetic(account, requested),
        "bank_decision": decision.model_dump(mode="json"),
        "decision_request": request.model_dump(mode="json"),
        "approval_semantics": "DEMO_APPROVED_ON_CONFIRMATION",
    }
    summary = (
        f"Increase your credit limit from {usd_limit_text(current)} "
        f"to {usd_limit_text(proposed)}, an increase of "
        f"{usd_limit_text(increase)}. This eligible demo increase "
        "takes effect after you confirm; it is not a submission for underwriting review."
    )
    return account.id, payload, summary


def validate_credit_limit(db, proposal, *, provider=None):
    payload = proposal.action_payload
    from services.decisioning import (
        DecisionPolicy,
        load_decisioning_provider,
        DecisionRequest,
        digest,
        validate_decision,
        utcnow,
    )

    try:
        provider = provider if provider is not None else load_decisioning_provider()
        request = DecisionRequest.model_validate(payload["decision_request"])
        context = {
            "customer_id": str(proposal.customer_id),
            "definition_digest": proposal.definition_digest,
            **{
                key: getattr(proposal, key)
                for key in (
                    "support_session_id",
                    "runtime_name",
                    "runtime_session_id",
                    "originating_customer_turn_id",
                    "reset_generation",
                    "idempotency_key",
                )
            },
            "input_fingerprint": payload["_business_input_fingerprint"],
        }
        expected = DecisionRequest(
            request_ref=digest(context),
            scope_ref=digest(
                {
                    key: value
                    for key, value in context.items()
                    if key != "input_fingerprint"
                }
            ),
            input_ref=digest(
                {
                    "facts": payload["eligibility_facts"],
                    "requested_limit": payload["proposed_limit"],
                }
            ),
            requested_limit=Money.model_validate(payload["proposed_limit"]),
            facts=payload["eligibility_facts"],
        )
        from services.proposal_lifecycle import canonical_payload

        if (
            request != expected
            or canonical_payload(payload)[1] != proposal.payload_fingerprint
        ):
            raise ValueError(
                "The checked approval request no longer matches its proposal."
            )
        decision = validate_decision(
            payload["bank_decision"],
            request,
            DecisionPolicy.model_validate(
                provider.current_policy.model_dump(mode="json")
            ),
            utcnow(),
        )
        if (
            decision.outcome != "APPROVED"
            or decision.approved_limit.model_dump() != payload["proposed_limit"]
            or decision.binding_ref != proposal.bank_decision_ref
            or request.facts.account_id != str(proposal.account_id)
        ):
            raise ValueError("Approval does not match the proposal binding.")
    except Exception:
        raise ActionPreconditionError(
            "The bank approval is no longer applicable; prepare a new offer.",
            reason="BANK_DECISION_NO_LONGER_VALID",
            policy_evidence=PolicyEvaluationEvidence(
                policy=dict(CREDIT_LIMIT_POLICY),
                facts=payload["eligibility_facts"],
                requested_limit=payload["proposed_limit"],
                reason_code="BANK_DECISION_NO_LONGER_VALID",
                bank_decision=payload["bank_decision"],
                decision_failure="APPROVAL_NO_LONGER_VALID",
            ),
        ) from None
    account = (
        db.query(CreditAccount)
        .filter(
            CreditAccount.id == proposal.account_id,
            CreditAccount.customer_id == proposal.customer_id,
        )
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if account is None:
        raise ActionPreconditionError(
            "Owned account is unavailable.", reason="ACCOUNT_UNAVAILABLE"
        )
    product = (
        db.query(CreditProduct)
        .filter_by(product_code=account.product_code)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    observed = credit_limit_facts(account, product)
    # A lock wait may cross the approval deadline. Validate after both locks,
    # without invoking the provider's decision operation in this transaction.
    try:
        validate_decision(
            payload["bank_decision"],
            request,
            DecisionPolicy.model_validate(
                provider.current_policy.model_dump(mode="json")
            ),
            utcnow(),
        )
    except Exception:
        raise ActionPreconditionError(
            "The bank approval expired or changed while awaiting execution.",
            reason="BANK_DECISION_NO_LONGER_VALID",
            policy_evidence=PolicyEvaluationEvidence(
                policy=dict(CREDIT_LIMIT_POLICY),
                facts=observed,
                approved_facts=payload["eligibility_facts"],
                requested_limit=payload["proposed_limit"],
                reason_code="BANK_DECISION_NO_LONGER_VALID",
                bank_decision=payload["bank_decision"],
                decision_failure="APPROVAL_NO_LONGER_VALID",
                decision_request=payload["decision_request"],
            ),
        ) from None
    reason = evaluate_credit_limit(observed, payload["proposed_limit"])
    if (
        payload["credit_limit_policy"] != CREDIT_LIMIT_POLICY
        or observed != payload["eligibility_facts"]
    ):
        reason = reason or "CREDIT_LIMIT_POLICY_CHANGED"
    delta = payload["proposed_limit"]["amount_minor"] - account.credit_limit_cents
    if (
        type(account.available_credit_cents) is not int
        or not -MAX_MINOR <= account.available_credit_cents <= MAX_MINOR
        or not -MAX_MINOR <= account.available_credit_cents + delta <= MAX_MINOR
    ):
        reason = "AVAILABLE_CREDIT_OUT_OF_RANGE"
    if reason:
        raise ActionPreconditionError(
            "Credit-limit eligibility changed; prepare a new offer.",
            reason=reason,
            policy_evidence=PolicyEvaluationEvidence(
                policy=dict(CREDIT_LIMIT_POLICY),
                facts={
                    **observed,
                    **credit_limit_arithmetic(account, payload["proposed_limit"]),
                },
                approved_facts=payload["eligibility_facts"],
                requested_limit=payload["proposed_limit"],
                reason_code=reason,
            ),
        )


def execute_credit_limit(db, proposal):
    payload = proposal.action_payload
    result = apply_limit_increase(
        db,
        account_id=proposal.account_id,
        requested_limit_cents=payload["proposed_limit"]["amount_minor"],
        commit_transaction=False,
    )
    return {
        "success": True,
        "message": f"Your credit limit is now {usd_limit_text(Money.model_validate(payload['proposed_limit']))}.",
        "account_id": str(proposal.account_id),
        "approval_semantics": payload["approval_semantics"],
        "previous_credit_limit": payload["current_limit"],
        "credit_limit": payload["proposed_limit"],
        "increase_amount": payload["increase_amount"],
        "available_credit": Money(
            amount_minor=result["available_credit_cents"], currency_code="USD"
        ).model_dump(),
    }


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
    normalize_business_inputs: Callable = business_inputs_unchanged
    validate: Callable = default_validate_current_preconditions
    reconcile: Callable = default_reconcile
    started: Callable = default_record_commit_started
    committed: Callable = default_record_committed
    reconciled: Callable = default_record_reconciled
    pending: Callable = default_commit_pending_message


OPERATIONS = {
    "credit.adjust_limit.v1": Operation(
        execute=execute_credit_limit,
        prepare=prepare_credit_limit,
        input_schema={"requested_limit_minor": int, "currency_code": str},
        parameters={},
        literal_bindings={},
        template_fields=frozenset(),
        payload_schema={
            "account_id": str,
            "current_limit": dict,
            "proposed_limit": dict,
            "increase_amount": dict,
            "credit_limit_policy": dict,
            "eligibility_facts": dict,
            "prepared_arithmetic": dict,
            "bank_decision": dict,
            "decision_request": dict,
            "approval_semantics": str,
        },
        public_fields=frozenset(
            {"current_limit", "proposed_limit", "increase_amount", "approval_semantics"}
        ),
        required_facts=frozenset(
            {"current_limit", "proposed_limit", "increase_amount", "approval_semantics"}
        ),
        validate=validate_credit_limit,
    ),
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
        normalize_business_inputs=fraud_business_inputs,
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
