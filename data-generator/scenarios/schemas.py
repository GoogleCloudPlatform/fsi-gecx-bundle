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

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ScenarioMode(StrEnum):
    DRY_RUN = "dry_run"
    EXECUTE = "execute"
    REPLAY = "replay"


class ScenarioType(StrEnum):
    FRAUD_TRAVEL_STORY = "fraud_travel_story"
    PREMIUM_TRAVEL_OFFER_FUEL = "premium_travel_offer_fuel"
    NORMAL_BASELINE_ACTIVITY = "normal_baseline_activity"
    LAKEHOUSE_SPEND_VELOCITY_SURGE = "lakehouse_spend_velocity_surge"
    UNKNOWN_REQUEST = "unknown_request"


class ScenarioIntensity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlannedEventType(StrEnum):
    AUTHORIZATION = "authorization"
    SETTLEMENT = "settlement"
    REVERSAL = "reversal"
    PENDING_HOLD = "pending_hold"
    CUSTOMER_ACTION = "customer_action"
    VALIDATION = "validation"


class OutcomeLabel(StrEnum):
    EXPECTED_FRAUD = "expected_fraud"
    CONFIRMED_FRAUD = "confirmed_fraud"
    FALSE_POSITIVE = "false_positive"
    CONFIRMED_LEGITIMATE = "confirmed_legitimate"
    CUSTOMER_DISPUTED = "customer_disputed"
    UNRESOLVED = "unresolved"
    NOT_APPLICABLE = "not_applicable"


class ExecutionLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_customers: int = Field(1, ge=0, le=5000)
    max_cards: int = Field(1, ge=0, le=5000)
    max_authorizations: int = Field(10, ge=0, le=1000)
    max_settlements: int = Field(10, ge=0, le=1000)
    max_duration_seconds: int = Field(120, ge=1, le=3600)
    max_fraud_events: int = Field(0, ge=0, le=1000)


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(..., min_length=1, max_length=1000)
    scenario_type: ScenarioType | None = None
    mode: ScenarioMode = ScenarioMode.DRY_RUN
    intensity: ScenarioIntensity = ScenarioIntensity.MEDIUM
    seed: int = Field(1841, ge=0)
    target_customer_id: str | None = None
    target_card_token: str | None = None
    target_cohort_size: int | None = Field(None, ge=0, le=5000)
    time_window_minutes: int = Field(120, ge=1, le=10080)
    max_customers: int | None = Field(None, ge=0, le=5000)
    max_events: int | None = Field(None, ge=0, le=1000)
    excluded_account_tags: list[str] = Field(default_factory=list)
    allow_vip_targets: bool = False
    allow_presenter_targets: bool = False
    safety_constraints: dict[str, Any] = Field(default_factory=dict)

    @field_validator("goal")
    @classmethod
    def normalize_goal(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @model_validator(mode="after")
    def execution_requires_intent(self) -> "ScenarioRequest":
        if self.mode == ScenarioMode.EXECUTE and self.scenario_type is None:
            # Keep v1 conservative: free-text requests can plan, but execution should
            # use an explicit template until agentic planning is hardened.
            self.safety_constraints.setdefault(
                "execution_warning",
                "Free-text execute requests require explicit scenario_type before execution.",
            )
        return self


class PersonaProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persona_id: str
    role: str
    home_metro: str | None = None
    home_country_code: str = "USA"
    card_profile: str | None = None
    typical_mccs: list[str] = Field(default_factory=list)
    travel_propensity: float = Field(0.0, ge=0.0, le=1.0)
    digital_commerce_propensity: float = Field(0.0, ge=0.0, le=1.0)
    card_present_propensity: float = Field(0.8, ge=0.0, le=1.0)
    protected_account_policy: Literal["exclude", "explicit_opt_in", "allow"] = "exclude"
    notes: list[str] = Field(default_factory=list)


class BehaviorPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: str
    preferred_mccs: list[str] = Field(default_factory=list)
    spend_min_cents: int = Field(100, ge=1)
    spend_max_cents: int = Field(10_000, ge=1)
    settlement_probability: float = Field(0.8, ge=0.0, le=1.0)
    reversal_probability: float = Field(0.1, ge=0.0, le=1.0)
    pending_probability: float = Field(0.1, ge=0.0, le=1.0)
    utilization_trigger: float | None = Field(None, ge=0.0, le=1.0)
    target_utilization: float | None = Field(None, ge=0.0, le=1.0)
    travel_context: str | None = None
    ecommerce_context: str | None = None

    @model_validator(mode="after")
    def probabilities_sum_to_oneish(self) -> "BehaviorPolicy":
        total = self.settlement_probability + self.reversal_probability + self.pending_probability
        if abs(total - 1.0) > 0.001:
            raise ValueError("settlement, reversal, and pending probabilities must sum to 1.0")
        if self.target_utilization is not None and self.utilization_trigger is not None:
            if self.target_utilization >= self.utilization_trigger:
                raise ValueError("target_utilization must be lower than utilization_trigger")
        return self


class MerchantContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    mcc: str = Field(..., min_length=3, max_length=4)
    merchant_name_hint: str | None = None
    country_code: str = Field("USA", min_length=2, max_length=3)
    city: str | None = None
    region: str | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    transaction_channel: str = "CARD_PRESENT"
    entry_mode: str = "CHIP"
    ip_country_code: str | None = None
    shipping_country_code: str | None = None
    is_digital_goods: bool = False
    high_risk_flags: list[str] = Field(default_factory=list)


class PlannedCardEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    offset_minutes: int = Field(0, ge=0)
    event_type: PlannedEventType
    persona_id: str
    amount_cents: int | None = Field(None, ge=1)
    merchant_context: MerchantContext | None = None
    expected_score_band: str | None = None
    expected_reason_codes: list[str] = Field(default_factory=list)
    outcome_label: OutcomeLabel = OutcomeLabel.NOT_APPLICABLE
    description: str


class ExpectedValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validation_id: str
    surface: str
    expectation: str
    query_hint: str | None = None
    metric_name: str | None = None
    expected_minimum: int | None = Field(None, ge=0)


class ScenarioPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    scenario_type: ScenarioType
    mode: ScenarioMode = ScenarioMode.DRY_RUN
    seed: int = Field(..., ge=0)
    template_version: str
    planner_version: str
    goal: str
    personas: list[PersonaProfile]
    behavior_policies: list[BehaviorPolicy]
    timeline: list[PlannedCardEvent]
    expected_validations: list[ExpectedValidation] = Field(default_factory=list)
    limits: ExecutionLimits
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def timeline_within_limits(self) -> "ScenarioPlan":
        auth_events = [event for event in self.timeline if event.event_type == PlannedEventType.AUTHORIZATION]
        if len(auth_events) > self.limits.max_authorizations:
            raise ValueError("timeline exceeds max_authorizations")
        if len(self.personas) > self.limits.max_customers:
            raise ValueError("persona count exceeds max_customers")
        return self
