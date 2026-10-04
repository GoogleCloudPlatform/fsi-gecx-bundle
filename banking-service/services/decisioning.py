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
from typing import Callable, Literal, Protocol
import uuid

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)
from models.money import MAX_MINOR, Money
from services.credit_card import CREDIT_LIMIT_POLICY, evaluate_credit_limit

Outcome = Literal["APPROVED", "DECLINED", "NEEDS_INFORMATION", "REFER_FOR_REVIEW"]
Reason = Literal[
    "APPROVED_BY_POLICY",
    "LIMIT_CEILING_EXCEEDED",
    "POLICY_DECLINED",
    "INFORMATION_REQUIRED",
    "REVIEW_REQUIRED",
]
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config/decisioning/demo.v1.json"


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


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_ref: str = Field(pattern=r"^[a-f0-9]{64}$")
    scope_ref: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_ref: str = Field(pattern=r"^[a-f0-9]{64}$")
    requested_limit: Money
    facts: CheckedDecisionFacts


class BankDecision(BaseModel):
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
            "DECLINED": {"POLICY_DECLINED", "LIMIT_CEILING_EXCEEDED"},
            "NEEDS_INFORMATION": {"INFORMATION_REQUIRED"},
            "REFER_FOR_REVIEW": {"REVIEW_REQUIRED"},
        }
        if (self.outcome == "APPROVED") != (self.approved_limit is not None):
            raise ValueError("Approved Money and decision outcome must agree.")
        if not set(self.reason_codes) <= expected[self.outcome]:
            raise ValueError("Decision outcome and reasons must agree.")
        if self.expires_at <= self.evaluated_at:
            raise ValueError("Decision expiry must follow evaluation.")
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


def validate_decision(value, request, policy, now):
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
    if decision.evidence_references != (request.input_ref,):
        raise ValueError("Decision evidence is not bound to the checked inputs.")
    if (
        decision.outcome == "APPROVED"
        and decision.approved_limit != request.requested_limit
    ):
        raise ValueError("Counteroffers require a separate contract.")
    if decision.evaluated_at > now or decision.expires_at <= now:
        raise ValueError("Decision is future-dated or expired.")
    if (
        decision.expires_at - decision.evaluated_at
    ).total_seconds() > policy.approval_ttl_seconds:
        raise ValueError("Decision exceeds its approved freshness contract.")
    return decision


class DemoDecisioningProvider:
    def __init__(self, policy, *, scenario="STANDARD", clock: Callable = utcnow):
        self._policy = policy
        self.scenario = scenario
        self.clock = clock

    @property
    def current_policy(self):
        return self._policy

    def evaluate(self, request):
        reason = evaluate_credit_limit(
            request.facts.model_dump(), request.requested_limit.model_dump()
        )
        if reason not in {None, "DEMO_LIMIT_CEILING_EXCEEDED"}:
            raise ValueError(
                "Execution eligibility must be checked before decisioning."
            )
        scenario = self.scenario
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
        outcome = "DECLINED" if reason else outcomes[scenario]
        evaluated = self.clock()
        return BankDecision(
            decision_id=str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{self.current_policy.digest}:{request.request_ref}",
                )
            ),
            provider_id=self.current_policy.provider_id,
            outcome=outcome,
            approved_limit=request.requested_limit if outcome == "APPROVED" else None,
            reason_codes=("LIMIT_CEILING_EXCEEDED" if reason else reasons[scenario],),
            policy=self.current_policy,
            evaluated_at=evaluated,
            expires_at=evaluated
            + datetime.timedelta(seconds=self.current_policy.approval_ttl_seconds),
            request_ref=request.request_ref,
            scope_ref=request.scope_ref,
            input_ref=request.input_ref,
            evidence_references=(request.input_ref,),
        )


def load_decisioning_provider(
    *, scenario=None, config_path=DEFAULT_CONFIG, clock=utcnow
):
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
            }
        ),
        approval_ttl_seconds=config["approval_ttl_seconds"],
    )
    return DemoDecisioningProvider(policy, scenario=selected, clock=clock)
