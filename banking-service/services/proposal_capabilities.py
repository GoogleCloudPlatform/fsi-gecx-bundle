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
from services.proposal_protocol import PolicyEvaluationEvidence, RecoveryClass
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


INSTANT_APPROVAL_SEMANTICS = "DEMO_APPROVED_ON_CONFIRMATION"
CONSENT_APPROVAL_SEMANTICS = {
    "SOFT": "SOFT_INQUIRY_CONSENT_ON_CONFIRMATION",
    "HARD": "HARD_INQUIRY_CONSENT_ON_CONFIRMATION",
}
ADVERSE_ACTION_OUTCOMES = {"DECLINED", "COUNTEROFFER"}


def _cleared_balance_minor(account):
    # Legacy column read through its attribute name; exposed only as Money facts.
    value = getattr(account, "cleared_balance" + "_cents")
    return value if type(value) is int else 0


def _late_payment(account, now):
    """Overdue proxy: a past due date with no payment on or after it."""
    from services.decisioning import _aware

    due = _aware(account.payment_due_date)
    if due is None or due >= now:
        return False
    paid = _aware(account.last_payment_date)
    return paid is None or paid < due


def credit_signals(db, customer_id, account, product, now):
    """Bank-derived tier inputs; NPI stays in memory and is bound by ``ref``."""
    from models.kyc import UserCreditProfile
    from services.decisioning import CreditSignals

    profile = (
        db.query(UserCreditProfile)
        .filter(UserCreditProfile.user_id == customer_id)
        .one_or_none()
    )
    return CreditSignals(
        credit_score=profile.credit_score if profile else None,
        credit_tier=profile.credit_tier if profile else None,
        annual_income_minor=max(0, profile.stated_annual_income.amount_minor)
        if profile
        else None,
        income_confirmed_at=profile.income_confirmed_at if profile else None,
        opened_at=account.opened_at,
        last_limit_increase_at=account.last_limit_increase_at,
        balance_minor=_cleared_balance_minor(account),
        late_payment=_late_payment(account, now),
        product_name=product.product_name,
    )


def _provider_evaluate(provider, request, signals):
    import inspect

    try:
        accepts_signals = "signals" in inspect.signature(provider.evaluate).parameters
    except (TypeError, ValueError):
        accepts_signals = False
    if accepts_signals:
        return provider.evaluate(request, signals=signals)
    return provider.evaluate(request)


def _tier_config(provider):
    from services.decisioning import load_credit_limit_tier_config

    return getattr(provider, "tier_config", None) or load_credit_limit_tier_config()


def _clock(provider):
    from services.decisioning import utcnow

    return getattr(provider, "clock", None) or utcnow


def derive_inquiry_consent(proposal, request, inquiry_type, tier_config):
    """Server-side consent from the bank-recorded confirmation of a consent offer.

    Never accepts consent from tool or model input: the tier comes from the
    pinned bank decision, the disclosure from the tier configuration and the
    customer turn from the protected confirmation recorded by the lifecycle.
    """
    from services.decisioning import InquiryConsent
    from services.proposal_evidence import consent_evidence_ref

    if (
        inquiry_type not in CONSENT_APPROVAL_SEMANTICS
        or proposal.action_payload.get("approval_semantics")
        != CONSENT_APPROVAL_SEMANTICS[inquiry_type]
        or not proposal.confirmation_customer_turn_id
        or not proposal.confirmation_evidence
        or proposal.confirmed_at is None
    ):
        raise ValueError("No bank-recorded consent confirmation for this inquiry.")
    disclosure = getattr(
        tier_config.policy_for(request.facts.product_code).disclosures, inquiry_type
    )
    evidence = {
        "runtime_session_id": proposal.runtime_session_id,
        "inquiry_consent": {
            "inquiry_type": inquiry_type,
            "disclosure_version": disclosure,
            "consent_turn_id": proposal.confirmation_customer_turn_id,
        },
    }
    return InquiryConsent(
        inquiry_type=inquiry_type,
        disclosure_version=disclosure,
        consent_ref=consent_evidence_ref(evidence, request.request_ref),
    )


def _with_consent(request, consent):
    from services.decisioning import DecisionRequest

    return DecisionRequest.model_validate(
        {
            **request.model_dump(mode="json"),
            "inquiry_consent": consent.model_dump(mode="json"),
        }
    )


def find_counteroffer_origin(
    db, *, customer_id, account_id, scope, provider, policy, tier_config,
    signals, now, requested=None, origin_request_ref=None, within_ttl=True,
):
    """Re-derive a post-inquiry COUNTEROFFER in the same authenticated scope.

    Looks only at INVALIDATED consent offers of this customer, support session,
    runtime session, reset generation and account. The origin decision is
    recomputed deterministically from the pinned request and the consent
    derived from that row's protected confirmation; nothing is read from input.
    Returns ``(origin_request, origin_decision)`` or ``None``.
    """
    import datetime

    from services.decisioning import BankDecision, DecisionRequest, validate_decision
    from services.proposal_lifecycle import as_utc

    rows = (
        db.query(ActionProposal)
        .filter(
            ActionProposal.customer_id == customer_id,
            ActionProposal.account_id == account_id,
            ActionProposal.support_session_id == scope["support_session_id"],
            ActionProposal.runtime_name == scope["runtime_name"],
            ActionProposal.runtime_session_id == scope["runtime_session_id"],
            ActionProposal.reset_generation == scope["reset_generation"],
            ActionProposal.action_type == "CREDIT_LIMIT_INCREASE",
            ActionProposal.status == "INVALIDATED",
            ActionProposal.invalidation_reason == "COUNTEROFFER_AVAILABLE",
        )
        .order_by(ActionProposal.completed_at.desc())
        .limit(5)
        .all()
    )
    window = datetime.timedelta(seconds=policy.approval_ttl_seconds)
    for row in rows:
        if within_ttl and (
            row.completed_at is None or as_utc(row.completed_at) < now - window
        ):
            continue
        try:
            origin_request = DecisionRequest.model_validate(
                row.action_payload["decision_request"]
            )
            if (
                origin_request_ref is not None
                and origin_request.request_ref != origin_request_ref
            ) or origin_request.signals_ref != signals.ref:
                continue
            pinned = BankDecision.model_validate(row.action_payload["bank_decision"])
            consent = derive_inquiry_consent(
                row, origin_request, pinned.inquiry_type, tier_config
            )
            bureau_request = _with_consent(origin_request, consent)
            decision = validate_decision(
                _provider_evaluate(provider, bureau_request, signals),
                bureau_request, policy, _clock(provider)(), tier_config=tier_config,
            )
        except Exception:
            continue
        if decision.outcome == "COUNTEROFFER" and (
            requested is None or decision.approved_limit == requested
        ):
            return bureau_request, decision
    return None


def _counteroffer_payload(payload):
    keys = (
        "account_id", "current_limit", "proposed_limit", "increase_amount",
        "bank_decision", "decision_request", "approval_semantics",
    )
    return {
        **{key: payload[key] for key in keys},
        "origin": payload["decision_request"]["origin"],
    }


_ADVERSE_REASONS = {
    "ABOVE_PRODUCT_MAXIMUM": "The requested limit exceeds the maximum credit limit for this card product.",
    "LIMIT_CEILING_EXCEEDED": "Income insufficient for the amount of credit requested.",
    "INCOME_CAP_EXCEEDED": "Income insufficient for the amount of credit requested.",
    "CREDIT_PROFILE_INELIGIBLE": "Length of account relationship or credit profile does not meet our requirements.",
    "COOLING_OFF_ACTIVE": "A credit limit increase was granted recently.",
    "BUREAU_DECLINED": "Information obtained in a report from a consumer reporting agency.",
    "COUNTEROFFER_AVAILABLE": "Information obtained in a report from a consumer reporting agency.",
}
_ECOA_NOTICE = (
    "The federal Equal Credit Opportunity Act prohibits creditors from discriminating "
    "against credit applicants on the basis of race, color, religion, national origin, "
    "sex, marital status, age (provided the applicant has the capacity to enter into a "
    "binding contract); because all or part of the applicant's income derives from any "
    "public assistance program; or because the applicant has in good faith exercised any "
    "right under the Consumer Credit Protection Act. The federal agency that administers "
    "compliance with this law concerning this creditor is the Consumer Financial "
    "Protection Bureau."
)
_FCRA_NOTICE = (
    "Our decision was based in whole or in part on information obtained in a report "
    "from a consumer reporting agency (simulated for this demonstration). The agency "
    "did not make this decision and cannot explain why it was made. You have the right "
    "to obtain a free copy of your report from the agency within 60 days and to dispute "
    "the accuracy or completeness of any information in it."
)


def adverse_action_notice(refusal, *, key, outcome, requested, offer=None, inquiry_type=None):
    """ECOA/Reg B and FCRA notice content from bounded facts only (no NPI)."""
    from services.proposal_lifecycle import _usd

    name = refusal.product_name
    reasons = [
        _ADVERSE_REASONS.get(code, "The request does not meet our credit policy.")
        for code in dict.fromkeys(
            [refusal.reason_code]
            + (["COUNTEROFFER_AVAILABLE"] if outcome == "COUNTEROFFER" and inquiry_type in CONSENT_APPROVAL_SEMANTICS else [])
        )
    ]
    if refusal.reason_code == "COOLING_OFF_ACTIVE" and refusal.retry_after:
        reasons.append(
            f"Another increase can be considered on or after {refusal.retry_after.isoformat()}."
        )
    decision = (
        f"We can't approve the amount requested, but we can offer a credit limit of {_usd(offer)}."
        if outcome == "COUNTEROFFER" and offer is not None
        else "We can't approve this request."
    )
    lines = [
        f"We reviewed your request to increase the credit limit on your {name} card "
        f"from {_usd(refusal.current_limit)} to {_usd(requested)}.",
        decision,
        "Principal reason(s): " + " ".join(reasons),
    ]
    if inquiry_type in CONSENT_APPROVAL_SEMANTICS:
        lines.append(_FCRA_NOTICE)
    lines += [_ECOA_NOTICE, "This is a demonstration notice; no real credit report was obtained."]
    return {
        "key": key,
        "subject": f"Credit Limit Request Decision — {name}",
        "body": "\n\n".join(lines),
    }


def _consent_summary(current, proposed, inquiry_type, disclosure, product_name):
    impact = (
        "a soft credit inquiry, which does not affect your credit score"
        if inquiry_type == "SOFT"
        else "a hard credit inquiry, which may affect your credit score"
    )
    return (
        f"Request an increase of your {product_name} credit limit from "
        f"{usd_limit_text(current)} to {usd_limit_text(proposed)}. Confirming "
        f"authorizes {impact} (disclosure {disclosure}). If the bank approves after "
        "the inquiry, the new limit takes effect immediately; otherwise no limit "
        "changes and the bank may offer a different amount."
    )


def prepare_credit_limit(
    db, customer_id, inputs, parameters, *, provider=None, preparation_context=None
):
    if inputs["currency_code"] not in {"USD", "MXN", "JPY", "BHD"}:
        raise ProposalError("Use a supported canonical currency code.")
    # No model-supplied account ID; fail closed on ambiguous owned scope.
    # Closed accounts are terminal and never in scope; frozen or delinquent
    # accounts stay in scope so policy evaluation can refuse them explicitly.
    accounts = (
        db.query(CreditAccount)
        .filter(
            CreditAccount.customer_id == customer_id,
            CreditAccount.status != "CLOSED",
        )
        .all()
    )
    if len(accounts) > 1:
        raise ProposalScopeError(
            "Exactly one owned open credit account is required.",
            code="MULTIPLE_OPEN_CREDIT_ACCOUNTS",
            recovery_class=RecoveryClass.ESCALATE,
            customer_message=(
                "More than one open credit card account is on file, so this "
                "limit change can't be completed here. A specialist can help."
            ),
        )
    if len(accounts) != 1:
        raise ProposalScopeError("Exactly one owned open credit account is required.")
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
    if not reason:
        delta = requested["amount_minor"] - account.credit_limit_cents
        if (
            type(account.available_credit_cents) is not int
            or not -MAX_MINOR <= account.available_credit_cents <= MAX_MINOR
            or not -MAX_MINOR <= account.available_credit_cents + delta <= MAX_MINOR
        ):
            reason = "AVAILABLE_CREDIT_OUT_OF_RANGE"
    from services.decisioning import (
        CheckedDecisionFacts,
        CounterofferOrigin,
        DecisionPolicy,
        load_decisioning_provider,
        DecisionRequest,
        RefusalFacts,
        digest,
        tier_caps,
        validate_decision,
    )

    if reason:
        refusal = notice = None
        if (
            reason == "PRODUCT_LIMIT_OUT_OF_BOUNDS"
            and requested["amount_minor"] > facts["maximum_limit_minor"]
        ):
            try:
                tier_config = _tier_config(provider)
                now = _clock(provider)()
                checked = CheckedDecisionFacts.model_validate(facts)
                caps = tier_caps(
                    checked,
                    credit_signals(db, customer_id, account, product, now),
                    tier_config.policy_for(checked.product_code),
                    now,
                )

                def usd(value):
                    return Money(amount_minor=value, currency_code="USD")

                refusal = RefusalFacts(
                    reason_code="ABOVE_PRODUCT_MAXIMUM",
                    retryable=False,
                    current_limit=usd(caps.current),
                    product_maximum=usd(caps.product_maximum),
                    max_instantly_approvable=usd(caps.max_instantly_approvable),
                    soft_tier_cap=usd(caps.soft_cap),
                    product_name=product.product_name,
                    next_steps=("PRODUCT_UPGRADE", "SPECIALIST_REVIEW"),
                )
                notice = adverse_action_notice(
                    refusal,
                    key=digest({"request": digest(preparation_context), "reason": reason}),
                    outcome="DECLINED",
                    requested=requested,
                )
            except Exception:
                refusal = notice = None
        facts = {**facts, **credit_limit_arithmetic(account, requested)}
        raise ProposalPolicyError(
            PolicyEvaluationEvidence(
                policy=dict(CREDIT_LIMIT_POLICY),
                facts=facts,
                requested_limit=requested,
                reason_code=reason,
            ),
            refusal_facts=refusal,
            adverse_action=notice,
        )

    request = None
    policy = None
    origin = None
    try:
        now = _clock(provider)()
        signals = credit_signals(db, customer_id, account, product, now)
        requested_money = Money.model_validate(requested)

        def decision_request(origin=None):
            return DecisionRequest(
                request_ref=digest(preparation_context),
                scope_ref=origin[0].scope_ref
                if origin
                else digest(
                    {
                        key: value
                        for key, value in preparation_context.items()
                        if key != "input_fingerprint"
                    }
                ),
                input_ref=digest(
                    {
                        "facts": facts,
                        "requested_limit": requested,
                        "signals_ref": signals.ref,
                    }
                ),
                requested_limit=requested_money,
                facts=facts,
                signals_ref=signals.ref,
                origin=CounterofferOrigin(
                    origin_request_ref=origin[0].request_ref,
                    origin_decision_ref=origin[1].binding_ref,
                    origin_requested_limit=origin[0].requested_limit,
                )
                if origin
                else None,
            )

        request = decision_request()
        provider = provider if provider is not None else load_decisioning_provider()
        metadata = provider.current_policy
        policy = DecisionPolicy.model_validate(
            metadata.model_dump(mode="json")
            if isinstance(metadata, DecisionPolicy)
            else metadata
        )
        tier_config = _tier_config(provider)
        origin = find_counteroffer_origin(
            db,
            customer_id=customer_id,
            account_id=account.id,
            scope=preparation_context,
            provider=provider,
            policy=policy,
            tier_config=tier_config,
            signals=signals,
            now=now,
            requested=requested_money,
        )
        if origin:
            request = decision_request(origin)
        returned = _provider_evaluate(provider, request, signals)
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
                decision_request=request.model_dump(mode="json")
                if request is not None
                else None,
            )
        ) from None
    try:
        decision = validate_decision(
            returned, request, policy, _clock(provider)(), tier_config=tier_config
        )
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
    consent_offer = (
        decision.outcome == "NEEDS_INFORMATION"
        and "INQUIRY_CONSENT_REQUIRED" in decision.reason_codes
        and decision.inquiry_type in CONSENT_APPROVAL_SEMANTICS
        and request.origin is None
    )
    if (decision.outcome != "APPROVED" and not consent_offer) or execution_reason:
        notice = None
        if decision.refusal is not None and decision.outcome in ADVERSE_ACTION_OUTCOMES:
            notice = adverse_action_notice(
                decision.refusal,
                key=decision.binding_ref,
                outcome=decision.outcome,
                requested=requested,
                offer=decision.approved_limit,
                inquiry_type=decision.inquiry_type,
            )
        raise ProposalPolicyError(
            PolicyEvaluationEvidence(
                policy=dict(CREDIT_LIMIT_POLICY),
                facts=facts,
                requested_limit=requested,
                reason_code=execution_reason or decision.reason_codes[0],
                bank_decision=decision.model_dump(mode="json"),
                decision_policy=policy.model_dump(mode="json"),
                decision_request=request.model_dump(mode="json"),
            ),
            adverse_action=notice,
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
        "approval_semantics": CONSENT_APPROVAL_SEMANTICS[decision.inquiry_type]
        if consent_offer
        else INSTANT_APPROVAL_SEMANTICS,
    }
    if origin:
        from services.proposal_definitions import validate_counteroffer_origin

        try:
            validate_counteroffer_origin(
                _counteroffer_payload(payload),
                origin[1],
                origin_request=origin[0],
                policy=policy,
                now=_clock(provider)(),
                tier_config=tier_config,
            )
        except Exception:
            raise ProposalPolicyError(
                PolicyEvaluationEvidence(
                    policy=dict(CREDIT_LIMIT_POLICY),
                    facts=facts,
                    requested_limit=requested,
                    reason_code="COUNTEROFFER_ORIGIN_INVALID",
                    decision_failure="INVALID_PROVIDER_RESPONSE",
                    decision_policy=policy.model_dump(mode="json"),
                    decision_request=request.model_dump(mode="json"),
                )
            ) from None
    if consent_offer:
        disclosure = getattr(
            tier_config.policy_for(facts["product_code"]).disclosures,
            decision.inquiry_type,
        )
        summary = _consent_summary(
            current, proposed, decision.inquiry_type, disclosure, product.product_name
        )
    else:
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
    )

    def no_longer_valid():
        return ActionPreconditionError(
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
        )

    try:
        provider = provider if provider is not None else load_decisioning_provider()
        policy = DecisionPolicy.model_validate(
            provider.current_policy.model_dump(mode="json")
        )
        tier_config = _tier_config(provider)
        now = _clock(provider)()
        request = DecisionRequest.model_validate(payload["decision_request"])
        current_account = (
            db.query(CreditAccount)
            .filter(
                CreditAccount.id == proposal.account_id,
                CreditAccount.customer_id == proposal.customer_id,
            )
            .one_or_none()
        )
        current_product = current_account and (
            db.query(CreditProduct)
            .filter_by(product_code=current_account.product_code)
            .one_or_none()
        )
        # A missing account/product is refused by the locked eligibility check
        # below; signals (and any inquiry) then cannot authorize execution.
        signals = (
            credit_signals(
                db, proposal.customer_id, current_account, current_product, now
            )
            if current_account is not None and current_product is not None
            else None
        )
    except Exception:
        raise no_longer_valid() from None
    if signals is not None and request.signals_ref != signals.ref:
        raise ActionPreconditionError(
            "Customer credit signals changed after the offer was prepared.",
            reason="CREDIT_SIGNALS_CHANGED",
            policy_evidence=PolicyEvaluationEvidence(
                policy=dict(CREDIT_LIMIT_POLICY),
                facts=payload["eligibility_facts"],
                requested_limit=payload["proposed_limit"],
                reason_code="CREDIT_SIGNALS_CHANGED",
                bank_decision=payload["bank_decision"],
                decision_failure="APPROVAL_NO_LONGER_VALID",
            ),
        )
    scope = {
        key: getattr(proposal, key)
        for key in ("support_session_id", "runtime_name", "runtime_session_id", "reset_generation")
    }
    try:
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
            scope_ref=request.scope_ref
            if request.origin is not None
            else digest(
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
                    "signals_ref": request.signals_ref,
                }
            ),
            requested_limit=Money.model_validate(payload["proposed_limit"]),
            facts=payload["eligibility_facts"],
            signals_ref=request.signals_ref,
            origin=request.origin,
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
            payload["bank_decision"], request, policy, now, tier_config=tier_config
        )
        semantics = payload["approval_semantics"]
        consent_offer = (
            decision.outcome == "NEEDS_INFORMATION"
            and "INQUIRY_CONSENT_REQUIRED" in decision.reason_codes
            and request.origin is None
            and semantics == CONSENT_APPROVAL_SEMANTICS.get(decision.inquiry_type)
        )
        if (
            not consent_offer
            and (
                decision.outcome != "APPROVED"
                or semantics != INSTANT_APPROVAL_SEMANTICS
                or decision.approved_limit.model_dump() != payload["proposed_limit"]
            )
        ) or (
            decision.binding_ref != proposal.bank_decision_ref
            or request.facts.account_id != str(proposal.account_id)
        ):
            raise ValueError("Approval does not match the proposal binding.")
        if request.signals_ref is None:
            raise ValueError("The offer is not bound to customer signals.")
        if request.origin is not None and signals is not None:
            from services.proposal_definitions import validate_counteroffer_origin

            origin = find_counteroffer_origin(
                db,
                customer_id=proposal.customer_id,
                account_id=proposal.account_id,
                scope=scope,
                provider=provider,
                policy=policy,
                tier_config=tier_config,
                signals=signals,
                now=now,
                requested=Money.model_validate(payload["proposed_limit"]),
                origin_request_ref=request.origin.origin_request_ref,
                within_ttl=False,
            )
            if origin is None:
                raise ValueError("Counteroffer origin is unavailable in this scope.")
            validate_counteroffer_origin(
                _counteroffer_payload(payload),
                origin[1],
                origin_request=origin[0],
                policy=policy,
                now=_clock(provider)(),
                tier_config=tier_config,
            )
        bureau = bureau_request = None
        if consent_offer:
            consent = derive_inquiry_consent(
                proposal, request, decision.inquiry_type, tier_config
            )
            bureau_request = _with_consent(request, consent)
    except Exception:
        raise no_longer_valid() from None
    if consent_offer and signals is not None:
        try:
            bureau = validate_decision(
                _provider_evaluate(provider, bureau_request, signals),
                bureau_request, policy, _clock(provider)(), tier_config=tier_config,
            )
        except Exception:
            raise ActionPreconditionError(
                "The bank decision is unavailable after the credit inquiry consent.",
                reason="BANK_DECISION_UNAVAILABLE",
                policy_evidence=PolicyEvaluationEvidence(
                    policy=dict(CREDIT_LIMIT_POLICY),
                    facts=payload["eligibility_facts"],
                    requested_limit=payload["proposed_limit"],
                    reason_code="BANK_DECISION_UNAVAILABLE",
                    bank_decision=payload["bank_decision"],
                    decision_failure="PROVIDER_UNAVAILABLE",
                    decision_request=bureau_request.model_dump(mode="json"),
                ),
            ) from None
        if not (
            bureau.outcome == "APPROVED"
            and bureau.approved_limit.model_dump() == payload["proposed_limit"]
        ):
            reason = (
                "COUNTEROFFER_AVAILABLE"
                if bureau.outcome == "COUNTEROFFER"
                else bureau.reason_codes[0]
            )
            notice = None
            if bureau.refusal is not None and bureau.outcome in ADVERSE_ACTION_OUTCOMES:
                notice = adverse_action_notice(
                    bureau.refusal,
                    key=bureau.binding_ref,
                    outcome=bureau.outcome,
                    requested=payload["proposed_limit"],
                    offer=bureau.approved_limit,
                    inquiry_type=bureau.inquiry_type,
                )
            raise ActionPreconditionError(
                "The bank decision after the credit inquiry did not approve this amount.",
                reason=reason,
                policy_evidence=PolicyEvaluationEvidence(
                    policy=dict(CREDIT_LIMIT_POLICY),
                    facts=payload["eligibility_facts"],
                    requested_limit=payload["proposed_limit"],
                    reason_code=reason,
                    bank_decision=bureau.model_dump(mode="json"),
                    decision_request=bureau_request.model_dump(mode="json"),
                ),
                refusal_facts=bureau.refusal,
                inquiry_type=bureau.inquiry_type,
                counteroffer=bureau.counteroffer,
                adverse_action=notice,
            )
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
            policy,
            _clock(provider)(),
            tier_config=tier_config,
        )
        if bureau is not None:
            validate_decision(
                bureau, bureau_request, policy, _clock(provider)(),
                tier_config=tier_config,
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
    if (consent_offer and bureau is None) or (
        request.origin is not None and signals is None
    ):
        # Never execute an inquiry offer or counteroffer without its bank decision.
        raise no_longer_valid()


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
