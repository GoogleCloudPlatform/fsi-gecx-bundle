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

"""Bank-owned decision contracts and a deterministic in-process demo adapter.

Providers evaluate before execution locks are acquired. Policy identity is local
metadata, never a network call. A future remote adapter must define its receipt
and revocation contract separately; this protocol never implies live revocation.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Annotated, Callable, Literal, Protocol
import uuid

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_serializer,
    model_validator,
)
from models.money import MAX_MINOR, Money
from services.credit_card import CREDIT_LIMIT_POLICY, evaluate_credit_limit

Outcome = Literal[
    "APPROVED", "DECLINED", "NEEDS_INFORMATION", "REFER_FOR_REVIEW", "COUNTEROFFER"
]
Reason = Literal[
    "APPROVED_BY_POLICY",
    "LIMIT_CEILING_EXCEEDED",
    "POLICY_DECLINED",
    "INFORMATION_REQUIRED",
    "REVIEW_REQUIRED",
    # Tiered credit-limit contract (additive; populated by the tiered provider).
    "COUNTEROFFER_AVAILABLE",
    "COOLING_OFF_ACTIVE",
    "ABOVE_PRODUCT_MAXIMUM",
    "INCOME_CONFIRMATION_REQUIRED",
    "INQUIRY_CONSENT_REQUIRED",
    "CREDIT_PROFILE_INELIGIBLE",
    # Tiered provider outcomes (additive).
    "BUREAU_DECLINED",
    "INCOME_CAP_EXCEEDED",
]
# The bank, never the model, selects the inquiry tier for a request.
InquiryType = Literal["NONE", "SOFT", "HARD"]
ConsentedInquiryType = Literal["SOFT", "HARD"]
NextStep = Literal[
    "SPECIALIST_REVIEW",
    "PRODUCT_UPGRADE",
    "PROVIDE_INCOME",
    "RETRY_AFTER_COOLING_OFF",
    "ACCEPT_COUNTEROFFER",
    "ACCEPT_PREAPPROVED_HEADROOM",
    "ACCEPT_SOFT_TIER_CAP",
]
CreditTier = Literal["PRIME_EXCELLENT", "PRIME", "NEAR_PRIME", "SUBPRIME"]
Fingerprint = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
DecisionRef = Annotated[
    str, Field(pattern=r"^[A-Za-z0-9_.-]{1,64}:[A-Za-z0-9_.-]{1,128}$")
]
DisclosureVersion = Annotated[
    str, Field(pattern=r"^(soft|hard)-inquiry-disclosure\.v[1-9][0-9]{0,3}$")
]
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config/decisioning/demo.v1.json"
DEFAULT_TIER_CONFIG = (
    Path(__file__).resolve().parents[1] / "config/decisioning/credit_limit_tiers.v1.json"
)


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class DecisionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    policy_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    version: StrictInt = Field(ge=1)
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    approval_ttl_seconds: StrictInt = Field(ge=1, le=300)


class CheckedDecisionFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    account_id: str = Field(pattern=r"^[A-Fa-f0-9-]{36}$")
    account_status: Literal["ACTIVE"]
    currency_code: Literal["USD"]
    product_code: str = Field(min_length=1, max_length=50)
    current_limit_minor: StrictInt = Field(gt=0, le=MAX_MINOR)
    product_active: Literal[True]
    minimum_limit_minor: StrictInt = Field(gt=0, le=MAX_MINOR)
    maximum_limit_minor: StrictInt = Field(gt=0, le=MAX_MINOR)


def _omit_absent(data, keys):
    """Keep legacy wire bytes: absent additive fields are not serialized."""
    for key in keys:
        if data.get(key) is None:
            data.pop(key, None)
    return data


class InquiryConsent(BaseModel):
    """Consent for exactly one bank-selected inquiry tier.

    SOFT consent never authorizes HARD (and vice versa); the disclosure version
    is namespaced by tier so a soft disclosure cannot back a hard consent.
    ``consent_ref`` is ``proposal_evidence.consent_evidence_ref`` of the
    accepted consent evidence and is bound into the decision evidence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    inquiry_type: ConsentedInquiryType
    disclosure_version: DisclosureVersion
    consent_ref: Fingerprint

    @model_validator(mode="after")
    def disclosure_matches_tier(self):
        if not self.disclosure_version.startswith(f"{self.inquiry_type.lower()}-"):
            raise ValueError("Consent disclosure does not match its inquiry type.")
        return self


class CounterofferOrigin(BaseModel):
    """Link from a new counteroffer proposal's request to its originating decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    origin_request_ref: Fingerprint
    origin_decision_ref: DecisionRef
    origin_requested_limit: Money


class Counteroffer(BaseModel):
    """Echo of the originating request on a COUNTEROFFER decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    origin_request_ref: Fingerprint
    requested_limit: Money


class RefusalFacts(BaseModel):
    """Bounded, data-only facts an agent may relay; no free text beyond the product name.

    All limits are total-limit Money values in the account currency:
    ``current_limit <= max_instantly_approvable <= soft_tier_cap <= product_maximum``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    reason_code: Reason
    retryable: StrictBool
    current_limit: Money
    product_maximum: Money
    max_instantly_approvable: Money
    soft_tier_cap: Money
    product_name: str = Field(
        min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f-\x9f]+$"
    )
    next_steps: tuple[NextStep, ...] = Field(min_length=1, max_length=4)
    retry_after: datetime.date | None = None

    @model_validator(mode="after")
    def coherent_facts(self):
        if self.product_name != self.product_name.strip():
            raise ValueError("Product name must be trimmed printable text.")
        if len(set(self.next_steps)) != len(self.next_steps):
            raise ValueError("Next steps must be unique.")
        cooling = "RETRY_AFTER_COOLING_OFF" in self.next_steps
        if cooling != (self.retry_after is not None) or (cooling and not self.retryable):
            raise ValueError("Cooling-off retry facts must agree.")
        limits = (
            self.current_limit,
            self.max_instantly_approvable,
            self.soft_tier_cap,
            self.product_maximum,
        )
        if len({m.currency_code for m in limits}) != 1:
            raise ValueError("Refusal limits must share one currency.")
        amounts = [m.amount_minor for m in limits]
        if amounts[0] <= 0 or amounts != sorted(amounts):
            raise ValueError("Refusal limits must be positive and ordered.")
        return self


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_ref: str = Field(pattern=r"^[a-f0-9]{64}$")
    scope_ref: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_ref: str = Field(pattern=r"^[a-f0-9]{64}$")
    requested_limit: Money
    facts: CheckedDecisionFacts
    # Additive tiered-contract inputs; omitted from the wire when absent.
    inquiry_consent: InquiryConsent | None = None
    origin: CounterofferOrigin | None = None
    # Fingerprint of the bank-derived customer signals; the signals themselves
    # (income, score, tier) are NPI and are never serialized into requests.
    signals_ref: Fingerprint | None = None

    @model_serializer(mode="wrap")
    def _legacy_wire(self, handler):
        return _omit_absent(
            handler(self), ("inquiry_consent", "origin", "signals_ref")
        )

    @model_validator(mode="after")
    def counteroffer_below_origin(self):
        origin = self.origin
        if origin is not None and (
            origin.origin_requested_limit.currency_code
            != self.requested_limit.currency_code
            or origin.origin_requested_limit.amount_minor
            <= self.requested_limit.amount_minor
        ):
            raise ValueError("A counteroffer must be below its originating request.")
        return self


class BankDecision(BaseModel):
    """Bank-owned receipt for one ``DecisionRequest``.

    Additive tiered fields (``inquiry_type``, ``counteroffer``, ``refusal``) are
    optional and omitted from the wire when absent, so legacy receipts keep
    their exact serialized bytes and payload fingerprints.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    decision_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    provider_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    outcome: Outcome
    approved_limit: Money | None
    reason_codes: tuple[Reason, ...] = Field(min_length=1, max_length=4)
    policy: DecisionPolicy
    evaluated_at: datetime.datetime
    expires_at: datetime.datetime
    request_ref: str = Field(pattern=r"^[a-f0-9]{64}$")
    scope_ref: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_ref: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_references: tuple[str, ...] = Field(min_length=1, max_length=4)
    inquiry_type: InquiryType | None = None
    counteroffer: Counteroffer | None = None
    refusal: RefusalFacts | None = None

    @model_serializer(mode="wrap")
    def _legacy_wire(self, handler):
        return _omit_absent(
            handler(self), ("inquiry_type", "counteroffer", "refusal")
        )

    @field_validator("evaluated_at", "expires_at")
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Decision timestamps must be timezone-aware.")
        return value.astimezone(datetime.timezone.utc)

    @field_validator("evidence_references")
    @classmethod
    def bounded_references(cls, values):
        if any(
            len(v) != 64 or any(c not in "0123456789abcdef" for c in v) for v in values
        ):
            raise ValueError(
                "Decision evidence references must be checked fingerprints."
            )
        return values

    @model_validator(mode="after")
    def coherent_outcome(self):
        expected = {
            "APPROVED": {"APPROVED_BY_POLICY"},
            "DECLINED": {
                "POLICY_DECLINED",
                "LIMIT_CEILING_EXCEEDED",
                "COOLING_OFF_ACTIVE",
                "CREDIT_PROFILE_INELIGIBLE",
                "BUREAU_DECLINED",
                "INCOME_CAP_EXCEEDED",
            },
            "NEEDS_INFORMATION": {
                "INFORMATION_REQUIRED",
                "INCOME_CONFIRMATION_REQUIRED",
                "INQUIRY_CONSENT_REQUIRED",
            },
            "REFER_FOR_REVIEW": {"REVIEW_REQUIRED", "ABOVE_PRODUCT_MAXIMUM"},
            "COUNTEROFFER": {
                "COUNTEROFFER_AVAILABLE",
                "LIMIT_CEILING_EXCEEDED",
                "INCOME_CAP_EXCEEDED",
            },
        }
        offers = self.outcome in {"APPROVED", "COUNTEROFFER"}
        if offers != (self.approved_limit is not None):
            raise ValueError("Approved Money and decision outcome must agree.")
        if not set(self.reason_codes) <= expected[self.outcome]:
            raise ValueError("Decision outcome and reasons must agree.")
        if self.expires_at <= self.evaluated_at:
            raise ValueError("Decision expiry must follow evaluation.")
        if self.outcome == "COUNTEROFFER" and (
            "COUNTEROFFER_AVAILABLE" not in self.reason_codes
            or self.counteroffer is None
            or self.refusal is None
            or self.inquiry_type is None
        ):
            raise ValueError(
                "A counteroffer requires its origin link, refusal facts and inquiry tier."
            )
        if self.outcome != "COUNTEROFFER" and self.counteroffer is not None:
            raise ValueError("Only a counteroffer outcome may carry counteroffer terms.")
        if "INQUIRY_CONSENT_REQUIRED" in self.reason_codes and self.inquiry_type not in {
            "SOFT",
            "HARD",
        }:
            raise ValueError("A consent request must name the SOFT or HARD tier.")
        refusal = self.refusal
        if refusal is not None:
            if self.outcome == "APPROVED":
                raise ValueError("Approved decisions carry no refusal facts.")
            if refusal.reason_code not in self.reason_codes:
                raise ValueError("Refusal reason must be a decision reason.")
            if ("ACCEPT_COUNTEROFFER" in refusal.next_steps) != (
                self.outcome == "COUNTEROFFER"
            ):
                raise ValueError("Only a counteroffer may be accepted.")
        return self

    @property
    def binding_ref(self):
        return f"{self.provider_id}:{self.decision_id}"


class DecisioningProvider(Protocol):
    @property
    def current_policy(self) -> DecisionPolicy:
        """Return locally available identity without I/O or reevaluation."""
        ...

    def evaluate(self, request: DecisionRequest) -> BankDecision:
        """Return an explicit decision; exceptions never authorize fallback approval."""
        ...


def validate_decision(value, request, policy, now, *, tier_config=None):
    """Revalidate an untrusted receipt and bind it to the bank-owned request.

    Error order: shape/coherence, provider identity, request scope, evidence
    binding (inputs plus consent), inquiry consent (tier, then the configured
    disclosure version), amount/counteroffer binding, refusal facts, freshness.
    Every failure raises ``ValueError`` (or a pydantic ``ValidationError``);
    callers must treat any exception as no approval. A request carrying
    consent requires ``tier_config`` (a ``CreditLimitTierConfig``) and fails
    closed without it.
    """
    if isinstance(value, BankDecision):
        if set(value.__dict__) != set(BankDecision.model_fields):
            raise ValueError("Decision contains unknown fields.")
        value = value.model_dump(mode="json")
    decision = BankDecision.model_validate(value)
    if decision.provider_id != policy.provider_id or decision.policy != policy:
        raise ValueError("Decision provider/policy identity does not match.")
    if any(
        getattr(decision, key) != getattr(request, key)
        for key in ("request_ref", "scope_ref", "input_ref")
    ):
        raise ValueError("Decision does not match the bank-owned request scope.")
    consent = request.inquiry_consent
    if decision.evidence_references != (request.input_ref,) + (
        (consent.consent_ref,) if consent else ()
    ):
        raise ValueError("Decision evidence is not bound to the checked inputs.")
    requests_consent = "INQUIRY_CONSENT_REQUIRED" in decision.reason_codes
    if requests_consent:
        # Asking for (further) consent must not claim the consent already held.
        if consent is not None and consent.inquiry_type == decision.inquiry_type:
            raise ValueError("Decision requests consent the customer already gave.")
    elif consent is not None and decision.inquiry_type != consent.inquiry_type:
        raise ValueError("Inquiry consent does not authorize this inquiry type.")
    elif consent is None and decision.inquiry_type in {"SOFT", "HARD"}:
        raise ValueError("A SOFT or HARD inquiry requires matching consent.")
    if consent is not None:
        if tier_config is None:
            raise ValueError("Consent cannot be checked without the tier configuration.")
        disclosures = tier_config.policy_for(request.facts.product_code).disclosures
        if consent.disclosure_version != getattr(disclosures, consent.inquiry_type):
            raise ValueError("Consent does not cite the current disclosure for its tier.")
    asked = request.requested_limit
    if decision.outcome == "APPROVED" and decision.approved_limit != asked:
        raise ValueError("Counteroffers require a separate contract.")
    if decision.outcome == "COUNTEROFFER":
        offer, facts = decision.approved_limit, request.facts
        if request.origin is not None:
            raise ValueError("A counteroffer request cannot itself be countered.")
        if (
            decision.counteroffer.origin_request_ref != request.request_ref
            or decision.counteroffer.requested_limit != asked
        ):
            raise ValueError("Counteroffer is not linked to its originating request.")
        if (
            offer.currency_code != asked.currency_code
            or not facts.current_limit_minor
            < offer.amount_minor
            < asked.amount_minor
            <= facts.maximum_limit_minor
        ):
            raise ValueError("Counteroffer amount is outside the checked bounds.")
    if decision.refusal is not None:
        facts = request.facts
        if decision.refusal.current_limit != Money(
            amount_minor=facts.current_limit_minor, currency_code=facts.currency_code
        ) or decision.refusal.product_maximum != Money(
            amount_minor=facts.maximum_limit_minor, currency_code=facts.currency_code
        ):
            raise ValueError("Refusal facts do not match the checked inputs.")
    if decision.evaluated_at > now or decision.expires_at <= now:
        raise ValueError("Decision is future-dated or expired.")
    if (
        decision.expires_at - decision.evaluated_at
    ).total_seconds() > policy.approval_ttl_seconds:
        raise ValueError("Decision exceeds its approved freshness contract.")
    return decision


class DemoDecisioningProvider:
    """Deterministic in-process bank decision adapter.

    Operator scenarios other than ``STANDARD`` override every request. Under
    ``STANDARD``, a request evaluated with bank-derived ``signals`` runs the
    customer-aware tiered policy (gates, pre-approved headroom, SOFT/HARD
    inquiry tiers, income cap, simulated bureau); without signals it keeps the
    legacy approve-as-requested behaviour used by contract tests.
    """

    def __init__(
        self, policy, *, scenario="STANDARD", clock: Callable = utcnow, tier_config=None
    ):
        self._policy = policy
        self.scenario = scenario
        self.clock = clock
        self.tier_config = tier_config

    @property
    def current_policy(self):
        return self._policy

    def evaluate(self, request, signals=None):
        reason = evaluate_credit_limit(
            request.facts.model_dump(), request.requested_limit.model_dump()
        )
        if reason:
            raise ValueError(
                "Execution eligibility must be checked before decisioning."
            )
        if self.scenario == "STANDARD" and signals is not None:
            return self._evaluate_tiered(request, signals)
        outcomes = {
            "STANDARD": "APPROVED",
            "DECLINE": "DECLINED",
            "NEEDS_INFORMATION": "NEEDS_INFORMATION",
            "REFER_FOR_REVIEW": "REFER_FOR_REVIEW",
        }
        reasons = {
            "STANDARD": "APPROVED_BY_POLICY",
            "DECLINE": "POLICY_DECLINED",
            "NEEDS_INFORMATION": "INFORMATION_REQUIRED",
            "REFER_FOR_REVIEW": "REVIEW_REQUIRED",
        }
        outcome = outcomes[self.scenario]
        return self._decision(
            request,
            outcome=outcome,
            approved=request.requested_limit if outcome == "APPROVED" else None,
            reasons=(reasons[self.scenario],),
        )

    def _decision(
        self, request, *, outcome, approved, reasons, inquiry_type=None,
        counteroffer=None, refusal=None,
    ):
        consent = request.inquiry_consent
        evaluated = self.clock()
        return BankDecision(
            decision_id=str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{self.current_policy.digest}:{request.request_ref}"
                    + (f":{consent.consent_ref}" if consent else ""),
                )
            ),
            provider_id=self.current_policy.provider_id,
            outcome=outcome,
            approved_limit=approved,
            reason_codes=reasons,
            policy=self.current_policy,
            evaluated_at=evaluated,
            expires_at=evaluated
            + datetime.timedelta(seconds=self.current_policy.approval_ttl_seconds),
            request_ref=request.request_ref,
            scope_ref=request.scope_ref,
            input_ref=request.input_ref,
            evidence_references=(request.input_ref,)
            + ((consent.consent_ref,) if consent else ()),
            inquiry_type=inquiry_type,
            counteroffer=counteroffer,
            refusal=refusal,
        )

    def _evaluate_tiered(self, request, signals):
        signals = CreditSignals.model_validate(signals)
        if request.signals_ref != signals.ref:
            raise ValueError("Customer signals are not bound to this request.")
        tier_config = self.tier_config or load_credit_limit_tier_config()
        facts = request.facts
        caps = tier_caps(
            facts, signals, tier_config.policy_for(facts.product_code), self.clock()
        )
        asked = request.requested_limit
        amount = asked.amount_minor

        def money(value):
            return Money(amount_minor=value, currency_code=facts.currency_code)

        def refusal(reason_code, next_steps, *, retryable=False, retry_after=None):
            return RefusalFacts(
                reason_code=reason_code,
                retryable=retryable,
                current_limit=money(caps.current),
                product_maximum=money(caps.product_maximum),
                max_instantly_approvable=money(caps.max_instantly_approvable),
                soft_tier_cap=money(caps.soft_cap),
                product_name=signals.product_name,
                next_steps=next_steps,
                retry_after=retry_after,
            )

        def refuse(outcome, reason_code, next_steps, inquiry_type="NONE", **extra):
            return self._decision(
                request, outcome=outcome, approved=None, reasons=(reason_code,),
                inquiry_type=inquiry_type,
                refusal=refusal(reason_code, next_steps, **extra),
            )

        def counter(offer, reason_codes, next_steps, inquiry_type):
            return self._decision(
                request, outcome="COUNTEROFFER", approved=money(offer),
                reasons=reason_codes, inquiry_type=inquiry_type,
                counteroffer=Counteroffer(
                    origin_request_ref=request.request_ref, requested_limit=asked
                ),
                refusal=refusal(reason_codes[-1], next_steps),
            )

        def approve(inquiry_type):
            return self._decision(
                request, outcome="APPROVED", approved=asked,
                reasons=("APPROVED_BY_POLICY",), inquiry_type=inquiry_type,
            )

        if amount > caps.product_maximum:
            return refuse(
                "REFER_FOR_REVIEW", "ABOVE_PRODUCT_MAXIMUM",
                ("PRODUCT_UPGRADE", "SPECIALIST_REVIEW"),
            )
        if caps.gate == "COOLING_OFF_ACTIVE":
            return refuse(
                "DECLINED", "COOLING_OFF_ACTIVE", ("RETRY_AFTER_COOLING_OFF",),
                retryable=True, retry_after=caps.retry_after,
            )
        if caps.gate == "INCOME_CONFIRMATION_REQUIRED":
            return refuse(
                "NEEDS_INFORMATION", "INCOME_CONFIRMATION_REQUIRED",
                ("PROVIDE_INCOME", "SPECIALIST_REVIEW"),
            )
        if caps.gate == "CREDIT_PROFILE_INELIGIBLE":
            return refuse(
                "DECLINED", "CREDIT_PROFILE_INELIGIBLE", ("SPECIALIST_REVIEW",)
            )
        if request.origin is not None:
            # The caller bound this request to a validated post-inquiry
            # counteroffer (validate_counteroffer_origin); no new inquiry.
            return approve("NONE")
        if amount <= caps.max_instantly_approvable:
            return approve("NONE")
        if amount > caps.hard_cap:
            if caps.hard_cap > caps.current:
                return counter(
                    caps.hard_cap,
                    ("COUNTEROFFER_AVAILABLE", "INCOME_CAP_EXCEEDED"),
                    ("ACCEPT_COUNTEROFFER", "PROVIDE_INCOME", "SPECIALIST_REVIEW"),
                    "NONE",
                )
            return refuse(
                "DECLINED", "LIMIT_CEILING_EXCEEDED",
                ("PROVIDE_INCOME", "SPECIALIST_REVIEW"),
            )
        tier = "SOFT" if amount <= caps.soft_cap else "HARD"
        consent = request.inquiry_consent
        if consent is None or consent.inquiry_type != tier:
            headroom = caps.max_instantly_approvable > caps.current
            if tier == "SOFT":
                steps = ("ACCEPT_PREAPPROVED_HEADROOM",) if headroom else ("SPECIALIST_REVIEW",)
            else:
                steps = (
                    ("ACCEPT_SOFT_TIER_CAP",) if caps.soft_cap > caps.current
                    else ("SPECIALIST_REVIEW",)
                )
            return refuse(
                "NEEDS_INFORMATION", "INQUIRY_CONSENT_REQUIRED", steps,
                inquiry_type=tier,
            )
        score = signals.credit_score
        if tier == "SOFT":
            if score >= SOFT_BUREAU_APPROVE_SCORE:
                return approve("SOFT")
            if caps.max_instantly_approvable > caps.current:
                return counter(
                    caps.max_instantly_approvable, ("COUNTEROFFER_AVAILABLE",),
                    ("ACCEPT_COUNTEROFFER", "SPECIALIST_REVIEW"), "SOFT",
                )
            return refuse(
                "DECLINED", "BUREAU_DECLINED", ("SPECIALIST_REVIEW",),
                inquiry_type="SOFT",
            )
        if score >= HARD_BUREAU_APPROVE_SCORE:
            return approve("HARD")
        if score >= HARD_BUREAU_COUNTER_SCORE and caps.soft_cap > caps.current:
            return counter(
                caps.soft_cap, ("COUNTEROFFER_AVAILABLE",),
                ("ACCEPT_COUNTEROFFER", "SPECIALIST_REVIEW"), "HARD",
            )
        return refuse(
            "DECLINED", "BUREAU_DECLINED", ("SPECIALIST_REVIEW",), inquiry_type="HARD"
        )


def load_decisioning_provider(
    *, scenario=None, config_path=DEFAULT_CONFIG, clock=utcnow,
    tier_config_path=DEFAULT_TIER_CONFIG,
):
    tier_config = load_credit_limit_tier_config(tier_config_path)
    config = json.loads(Path(config_path).read_text())
    if (
        set(config)
        != {
            "schema_version",
            "provider_id",
            "policy_id",
            "policy_version",
            "approval_ttl_seconds",
            "default_scenario",
            "scenarios",
        }
        or type(config["schema_version"]) is not int
        or config["schema_version"] != 1
    ):
        raise ValueError("Unsupported decisioning configuration.")
    allowed = {"STANDARD", "DECLINE", "NEEDS_INFORMATION", "REFER_FOR_REVIEW"}
    if (
        not isinstance(config["scenarios"], list)
        or len(config["scenarios"]) != len(allowed)
        or any(type(v) is not str for v in config["scenarios"])
        or set(config["scenarios"]) != allowed
        or config["default_scenario"] not in allowed
    ):
        raise ValueError("Decisioning scenarios must be the closed operator contract.")
    selected = (
        scenario or os.getenv("BANK_DECISIONING_SCENARIO") or config["default_scenario"]
    )
    if selected not in allowed:
        raise ValueError("Unknown operator decisioning scenario.")
    policy = DecisionPolicy(
        provider_id=config["provider_id"],
        policy_id=config["policy_id"],
        version=config["policy_version"],
        digest=digest(
            {
                "provider_id": config["provider_id"],
                "policy_id": config["policy_id"],
                "version": config["policy_version"],
                "approval_ttl_seconds": config["approval_ttl_seconds"],
                "scenario": selected,
                "execution_policy": CREDIT_LIMIT_POLICY,
                "tier_policy": digest(tier_config.model_dump(mode="json")),
            }
        ),
        approval_ttl_seconds=config["approval_ttl_seconds"],
    )
    return DemoDecisioningProvider(
        policy, scenario=selected, clock=clock, tier_config=tier_config
    )


# --- Tiered credit-limit configuration (shape and defaults only) ------------
# The headroom/tier formula that consumes this config is owner-approved before
# the tiered provider uses it. This file is not part of the demo policy digest.

Bps = Annotated[StrictInt, Field(ge=0, le=10000)]
Days = Annotated[StrictInt, Field(ge=0, le=3650)]


class _ClosedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TierGates(_ClosedConfig):
    cooling_off_days: Days
    income_confirmation_max_age_days: Annotated[StrictInt, Field(ge=1, le=3650)]
    minimum_credit_score: Annotated[StrictInt, Field(ge=300, le=850)]
    minimum_tenure_months: Annotated[StrictInt, Field(ge=0, le=600)]
    max_late_payments_12m: Annotated[StrictInt, Field(ge=0, le=12)]


class CreditTierBps(_ClosedConfig):
    """Instant headroom as a fraction (bps) of the current limit, per credit tier."""

    PRIME_EXCELLENT: Bps
    PRIME: Bps
    NEAR_PRIME: Bps
    SUBPRIME: Bps


class UtilizationBand(_ClosedConfig):
    max_bps: Annotated[StrictInt, Field(ge=0, le=20000)]
    factor_bps: Bps


class TenureBand(_ClosedConfig):
    min_months: Annotated[StrictInt, Field(ge=0, le=600)]
    factor_bps: Bps


class HeadroomInputs(_ClosedConfig):
    tier_bps: CreditTierBps
    # Utilization above the last band's max_bps yields no instant headroom.
    utilization_bands: tuple[UtilizationBand, ...] = Field(min_length=1, max_length=8)
    # Tenure below the first band's min_months yields no instant headroom.
    tenure_bands: tuple[TenureBand, ...] = Field(min_length=1, max_length=8)
    max_limit_to_income_bps: Annotated[StrictInt, Field(ge=1, le=10000)]

    @model_validator(mode="after")
    def ascending_bands(self):
        for bands, key in (
            (self.utilization_bands, "max_bps"),
            (self.tenure_bands, "min_months"),
        ):
            values = [getattr(band, key) for band in bands]
            if any(a >= b for a, b in zip(values, values[1:])):
                raise ValueError("Bands must be strictly ascending.")
        return self


class SoftTier(_ClosedConfig):
    # A soft-tier cap below the current limit would make SOFT meaningless.
    max_multiple_of_current_bps: Annotated[StrictInt, Field(ge=10000, le=100000)]


class InquiryDisclosures(_ClosedConfig):
    SOFT: Annotated[str, Field(pattern=r"^soft-inquiry-disclosure\.v[1-9][0-9]{0,3}$")]
    HARD: Annotated[str, Field(pattern=r"^hard-inquiry-disclosure\.v[1-9][0-9]{0,3}$")]


class TierPolicy(_ClosedConfig):
    rounding_step_minor: Annotated[StrictInt, Field(ge=1, le=MAX_MINOR)]
    gates: TierGates
    headroom: HeadroomInputs
    soft_tier: SoftTier
    disclosures: InquiryDisclosures

    @model_validator(mode="after")
    def tenure_respects_gate(self):
        if self.headroom.tenure_bands[0].min_months < self.gates.minimum_tenure_months:
            raise ValueError("Tenure bands cannot start below the tenure gate.")
        return self


class CreditLimitTierConfig(_ClosedConfig):
    """Closed, versioned thresholds for NONE/SOFT/HARD credit-limit tiers.

    ``product_overrides`` entries fully replace ``default`` for that product;
    there is no partial merge.
    """

    schema_version: Literal[1]
    policy_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")]
    policy_version: Annotated[StrictInt, Field(ge=1)]
    default: TierPolicy
    product_overrides: dict[
        Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,50}$")], TierPolicy
    ]

    def policy_for(self, product_code):
        return self.product_overrides.get(product_code, self.default)


def load_credit_limit_tier_config(path=DEFAULT_TIER_CONFIG):
    return CreditLimitTierConfig.model_validate_json(Path(path).read_text())


# --- Customer signals and deterministic tier caps ---------------------------
# Simulated bureau thresholds (demo only; no real consumer report is pulled).
SOFT_BUREAU_APPROVE_SCORE = 660
HARD_BUREAU_APPROVE_SCORE = 700
HARD_BUREAU_COUNTER_SCORE = 660


def _aware(value):
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


class CreditSignals(BaseModel):
    """Bank-derived customer signals for one decision (NPI; never serialized
    into payloads, refusal facts, results or logs; bound only by ``ref``)."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    credit_score: Annotated[StrictInt, Field(ge=300, le=850)] | None
    credit_tier: Annotated[str, Field(min_length=1, max_length=50)] | None
    annual_income_minor: Annotated[StrictInt, Field(ge=0, le=MAX_MINOR)] | None
    income_confirmed_at: datetime.datetime | None
    opened_at: datetime.datetime | None
    last_limit_increase_at: datetime.datetime | None
    balance_minor: Annotated[StrictInt, Field(ge=-MAX_MINOR, le=MAX_MINOR)]
    late_payment: StrictBool
    product_name: str = Field(
        min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f-\x9f]+$"
    )

    @field_validator("income_confirmed_at", "opened_at", "last_limit_increase_at")
    @classmethod
    def utc(cls, value):
        return _aware(value)

    @property
    def ref(self):
        return digest(self.model_dump(mode="json"))


class TierCaps(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    gate: Reason | None
    retry_after: datetime.date | None
    tenure_months: StrictInt
    current: StrictInt
    product_maximum: StrictInt
    headroom: StrictInt
    max_instantly_approvable: StrictInt
    soft_cap: StrictInt
    hard_cap: StrictInt


def tier_caps(facts, signals, policy, now):
    """Owner-approved deterministic gates and caps (integer minor units, bps).

    Gate order: cooling-off, income confirmation, credit profile/tenure. Any
    gate or a late payment yields zero instant headroom. Guarantees
    ``current <= max_instantly_approvable <= soft_cap <= hard_cap <= product_maximum``.
    """
    now = _aware(now)
    step = policy.rounding_step_minor
    gates = policy.gates

    def floor_step(value):
        return (value // step) * step

    L, P = facts.current_limit_minor, facts.maximum_limit_minor
    opened = signals.opened_at
    tenure = max(0, (now - opened).days // 30) if opened else 0
    gate = retry_after = None
    last = signals.last_limit_increase_at
    if last is not None and now - last < datetime.timedelta(days=gates.cooling_off_days):
        gate = "COOLING_OFF_ACTIVE"
        retry_after = (last + datetime.timedelta(days=gates.cooling_off_days)).date()
    elif (
        signals.credit_score is None
        or not signals.annual_income_minor
        or signals.income_confirmed_at is None
        or now - signals.income_confirmed_at
        > datetime.timedelta(days=gates.income_confirmation_max_age_days)
    ):
        gate = "INCOME_CONFIRMATION_REQUIRED"
    elif (
        signals.credit_score < gates.minimum_credit_score
        or tenure < gates.minimum_tenure_months
    ):
        gate = "CREDIT_PROFILE_INELIGIBLE"
    income = signals.annual_income_minor or 0
    income_cap = max(
        L, min(P, floor_step(income * policy.headroom.max_limit_to_income_bps // 10000))
    )
    utilization = (signals.balance_minor * 10000) // L if L > 0 else 0
    u_factor = next(
        (b.factor_bps for b in policy.headroom.utilization_bands if b.max_bps >= utilization),
        0,
    )
    t_factor = 0
    for band in policy.headroom.tenure_bands:
        if band.min_months <= tenure:
            t_factor = band.factor_bps
    tier_bps = getattr(policy.headroom.tier_bps, signals.credit_tier or "", 0) if (
        signals.credit_tier in CreditTierBps.model_fields
    ) else 0
    raw = floor_step(L * tier_bps * u_factor * t_factor // 10**12)
    headroom = max(0, min(raw, income_cap - L))
    if gate is not None or signals.late_payment:
        headroom = 0
    instant = L + headroom
    soft_cap = max(
        instant,
        min(P, income_cap, floor_step(L * policy.soft_tier.max_multiple_of_current_bps // 10000)),
    )
    hard_cap = max(soft_cap, min(P, income_cap))
    return TierCaps(
        gate=gate, retry_after=retry_after, tenure_months=tenure, current=L,
        product_maximum=P, headroom=headroom, max_instantly_approvable=instant,
        soft_cap=soft_cap, hard_cap=hard_cap,
    )
