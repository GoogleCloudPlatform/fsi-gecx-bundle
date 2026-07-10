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

import hashlib
from collections.abc import Callable

from .schemas import (
    BehaviorPolicy,
    ExecutionLimits,
    ExpectedValidation,
    MerchantContext,
    OutcomeLabel,
    PersonaProfile,
    PlannedCardEvent,
    PlannedEventType,
    ScenarioIntensity,
    ScenarioPlan,
    ScenarioRequest,
    ScenarioType,
)

PLANNER_VERSION = "local-template-planner-v1"
TEMPLATE_VERSION = "scenario-template-v1"


def stable_scenario_id(request: ScenarioRequest, scenario_type: ScenarioType) -> str:
    normalized = "|".join(
        [
            scenario_type.value,
            str(request.seed),
            request.intensity.value,
            request.goal.lower(),
            TEMPLATE_VERSION,
        ]
    )
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]
    return f"{scenario_type.value}-{request.seed}-{digest}"


def _limits(
    request: ScenarioRequest,
    *,
    customers: int,
    cards: int,
    authorizations: int,
    settlements: int | None = None,
    duration_seconds: int = 120,
    fraud_events: int = 0,
) -> ExecutionLimits:
    return ExecutionLimits(
        max_customers=min(request.max_customers or customers, customers),
        max_cards=cards,
        max_authorizations=min(request.max_events or authorizations, authorizations),
        max_settlements=settlements if settlements is not None else authorizations,
        max_duration_seconds=duration_seconds,
        max_fraud_events=fraud_events,
    )


def _base_plan(
    request: ScenarioRequest,
    scenario_type: ScenarioType,
    *,
    personas: list[PersonaProfile],
    behavior_policies: list[BehaviorPolicy],
    timeline: list[PlannedCardEvent],
    expected_validations: list[ExpectedValidation],
    limits: ExecutionLimits,
    warnings: list[str] | None = None,
    assumptions: list[str] | None = None,
    labels: dict[str, str] | None = None,
) -> ScenarioPlan:
    return ScenarioPlan(
        scenario_id=stable_scenario_id(request, scenario_type),
        scenario_type=scenario_type,
        mode=request.mode,
        seed=request.seed,
        template_version=TEMPLATE_VERSION,
        planner_version=PLANNER_VERSION,
        goal=request.goal,
        personas=personas,
        behavior_policies=behavior_policies,
        timeline=timeline,
        expected_validations=expected_validations,
        limits=limits,
        warnings=warnings or [],
        assumptions=assumptions or [],
        labels=labels or {},
    )


def fraud_travel_story(request: ScenarioRequest) -> ScenarioPlan:
    persona = PersonaProfile(
        persona_id="traveling_executive",
        role="traveling executive",
        home_metro="Mountain View, CA",
        card_profile="premium_travel_card",
        typical_mccs=["4511", "7011", "5812", "4121"],
        travel_propensity=0.85,
        digital_commerce_propensity=0.45,
        card_present_propensity=0.7,
        protected_account_policy="explicit_opt_in",
        notes=["Synthetic executive persona used for fraud/travel rehearsal."],
    )
    policy = BehaviorPolicy(
        policy_id="executive_travel_policy",
        preferred_mccs=["4511", "7011", "5812", "4121", "5947", "5311"],
        spend_min_cents=1_200,
        spend_max_cents=95_000,
        settlement_probability=0.75,
        reversal_probability=0.05,
        pending_probability=0.20,
        utilization_trigger=0.70,
        target_utilization=0.35,
        travel_context="Mexico business travel with normal card-present purchases.",
        ecommerce_context="Occasional ecommerce; suspicious burst uses gift-card and electronics descriptors.",
    )
    timeline = [
        PlannedCardEvent(
            event_id="baseline-coffee-001",
            offset_minutes=0,
            event_type=PlannedEventType.AUTHORIZATION,
            persona_id=persona.persona_id,
            amount_cents=875,
            merchant_context=MerchantContext(category="Coffee", mcc="5814", merchant_name_hint="BLUE BOTTLE COFFEE", city="Mountain View", region="CA"),
            expected_score_band="low",
            description="Normal home-market coffee purchase to establish baseline.",
        ),
        PlannedCardEvent(
            event_id="travel-airline-001",
            offset_minutes=20,
            event_type=PlannedEventType.AUTHORIZATION,
            persona_id=persona.persona_id,
            amount_cents=62_000,
            merchant_context=MerchantContext(category="Airline", mcc="4511", merchant_name_hint="AEROMEXICO", country_code="MEX", city="Mexico City", region="CDMX"),
            expected_score_band="low_to_moderate",
            description="Legitimate airline purchase in the travel corridor.",
        ),
        PlannedCardEvent(
            event_id="travel-hotel-001",
            offset_minutes=45,
            event_type=PlannedEventType.AUTHORIZATION,
            persona_id=persona.persona_id,
            amount_cents=84_000,
            merchant_context=MerchantContext(category="Hotel", mcc="7011", merchant_name_hint="CANCUN RESORT POS", country_code="MEX", city="Cancun", region="QR", latitude=21.1619, longitude=-86.8515),
            expected_score_band="moderate",
            description="Legitimate card-present hotel hold during travel.",
        ),
        PlannedCardEvent(
            event_id="fraud-gift-card-001",
            offset_minutes=65,
            event_type=PlannedEventType.AUTHORIZATION,
            persona_id=persona.persona_id,
            amount_cents=48_500,
            merchant_context=MerchantContext(category="Gift Cards", mcc="5947", merchant_name_hint="RAZER GOLD GIFT CARD ONLINE", transaction_channel="ECOMMERCE", entry_mode="ECOMMERCE", is_digital_goods=True, high_risk_flags=["DIGITAL_GOODS", "GIFT_CARD"]),
            expected_score_band="elevated",
            expected_reason_codes=["CARD_NOT_PRESENT_DESCRIPTOR", "GIFT_CARD_OR_DIGITAL_GOODS"],
            outcome_label=OutcomeLabel.EXPECTED_FRAUD,
            description="Suspicious card-not-present gift-card purchase while travel is in progress.",
        ),
        PlannedCardEvent(
            event_id="fraud-electronics-001",
            offset_minutes=72,
            event_type=PlannedEventType.AUTHORIZATION,
            persona_id=persona.persona_id,
            amount_cents=73_000,
            merchant_context=MerchantContext(category="Electronics", mcc="5311", merchant_name_hint="BEST BUY*MKTPLACE", transaction_channel="ECOMMERCE", entry_mode="ECOMMERCE", high_risk_flags=["ELECTRONICS"]),
            expected_score_band="high",
            expected_reason_codes=["VELOCITY_SPIKE_1H", "RECENT_FLAGGED_ACTIVITY"],
            outcome_label=OutcomeLabel.CUSTOMER_DISPUTED,
            description="Second suspicious online purchase creates a cluster for model and alert workflows.",
        ),
        PlannedCardEvent(
            event_id="customer-dispute-001",
            offset_minutes=90,
            event_type=PlannedEventType.CUSTOMER_ACTION,
            persona_id=persona.persona_id,
            outcome_label=OutcomeLabel.CUSTOMER_DISPUTED,
            description="Synthetic customer disputes the suspicious online purchases.",
        ),
    ]
    validations = [
        ExpectedValidation(validation_id="risk-dashboard-elevated", surface="admin_risk_dashboard", expectation="Risk condition becomes elevated after the suspicious cluster."),
        ExpectedValidation(validation_id="model-decisions-visible", surface="bigquery", expectation="Fraud model decisions exist for generated suspicious authorizations.", query_hint="operations.fraud_model_decisions"),
        ExpectedValidation(validation_id="support-flow-ready", surface="secure_messaging", expectation="One fraud alert or customer action path is available for remediation."),
    ]
    return _base_plan(
        request,
        ScenarioType.FRAUD_TRAVEL_STORY,
        personas=[persona],
        behavior_policies=[policy],
        timeline=timeline,
        expected_validations=validations,
        limits=_limits(request, customers=1, cards=1, authorizations=5, settlements=3, duration_seconds=180, fraud_events=2),
        assumptions=["Travel purchases are synthetic and do not represent real customer behavior."],
        labels={"demo_surface": "fraud", "fraud_language": "true"},
    )


def premium_travel_offer_fuel(request: ScenarioRequest) -> ScenarioPlan:
    cohort_size = request.target_cohort_size or {"low": 8, "medium": 15, "high": 30}[request.intensity.value]
    persona = PersonaProfile(
        persona_id="bay_area_travel_cohort",
        role="premium travel offer candidate cohort",
        home_metro="Mountain View / San Francisco, CA",
        card_profile="prime_or_premium_rewards",
        typical_mccs=["4511", "7011", "5812", "7298"],
        travel_propensity=0.75,
        digital_commerce_propensity=0.35,
        card_present_propensity=0.8,
        notes=["Growth-oriented cohort for Mexico travel offer analytics."],
    )
    policy = BehaviorPolicy(
        policy_id="mexico_travel_offer_policy",
        preferred_mccs=["4511", "7011", "5812", "7298", "4121"],
        spend_min_cents=1_500,
        spend_max_cents=85_000,
        settlement_probability=0.85,
        reversal_probability=0.03,
        pending_probability=0.12,
        travel_context="Mexico airline, resort lodging, dining, wellness, and rideshare activity.",
    )
    categories = [
        ("offer-airline", "Airline", "4511", "AEROMEXICO", 58_000, "Mexico City", "CDMX"),
        ("offer-hotel", "Hotel", "7011", "CANCUN RESORT POS", 72_000, "Cancun", "QR"),
        ("offer-dining", "Dining", "5812", "POLANCO DINING", 9_200, "Mexico City", "CDMX"),
        ("offer-wellness", "Wellness", "7298", "TULUM WELLNESS SPA", 18_500, "Tulum", "QR"),
    ]
    timeline = [
        PlannedCardEvent(
            event_id=f"{event_id}-{idx:03d}",
            offset_minutes=idx * 8,
            event_type=PlannedEventType.AUTHORIZATION,
            persona_id=persona.persona_id,
            amount_cents=amount,
            merchant_context=MerchantContext(category=category, mcc=mcc, merchant_name_hint=name, country_code="MEX", city=city, region=region),
            expected_score_band="low",
            outcome_label=OutcomeLabel.CONFIRMED_LEGITIMATE,
            description=f"Legitimate Mexico travel {category.lower()} spend for premium offer analytics.",
        )
        for idx, (event_id, category, mcc, name, amount, city, region) in enumerate(categories, start=1)
    ]
    validations = [
        ExpectedValidation(validation_id="premium-offer-candidates", surface="bigquery", expectation="Curated premium travel offer candidate view has enough Mexico travel rows.", expected_minimum=min(cohort_size, 15)),
        ExpectedValidation(validation_id="no-fraud-language", surface="admin_or_docs", expectation="Scenario labels remain growth-oriented and do not imply fraud."),
    ]
    return _base_plan(
        request,
        ScenarioType.PREMIUM_TRAVEL_OFFER_FUEL,
        personas=[persona],
        behavior_policies=[policy],
        timeline=timeline,
        expected_validations=validations,
        limits=_limits(request, customers=cohort_size, cards=cohort_size, authorizations=max(4, min(request.max_events or 60, 120)), settlements=max(4, min(request.max_events or 60, 120)), duration_seconds=600),
        assumptions=["Generated travel activity is synthetic campaign analytics fuel."],
        labels={"demo_surface": "growth_analytics", "fraud_language": "false"},
    )


def normal_baseline_activity(request: ScenarioRequest) -> ScenarioPlan:
    cohort_size = request.target_cohort_size or {"low": 25, "medium": 100, "high": 250}[request.intensity.value]
    persona = PersonaProfile(
        persona_id="ambient_everyday_cohort",
        role="everyday cardholder cohort",
        home_metro="Distributed US metros",
        card_profile="mixed_prime_ypro",
        typical_mccs=["5411", "5814", "5541", "4121", "4899"],
        travel_propensity=0.10,
        digital_commerce_propensity=0.45,
        card_present_propensity=0.85,
        notes=["Scheduled heartbeat-compatible persona for normal activity."],
    )
    policy = BehaviorPolicy(
        policy_id="ambient_everyday_policy",
        preferred_mccs=["5411", "5814", "5541", "4121", "4899"],
        spend_min_cents=400,
        spend_max_cents=15_000,
        settlement_probability=0.80,
        reversal_probability=0.10,
        pending_probability=0.10,
        utilization_trigger=0.65,
        target_utilization=0.35,
        ecommerce_context="Normal subscription and marketplace traffic.",
    )
    events = [
        ("baseline-grocery", "Groceries", "5411", "SAFEWAY - HOME METRO", 6_400),
        ("baseline-coffee", "Coffee", "5814", "LOCAL COFFEE", 875),
        ("baseline-gas", "Fuel", "5541", "CHEVRON - HOME METRO", 5_600),
        ("baseline-rideshare", "Rideshare", "4121", "RIDESHARE TRIP", 2_300),
        ("baseline-streaming", "Streaming", "4899", "SPOTIFY*SUBSCRIPTION", 1_699),
    ]
    timeline = [
        PlannedCardEvent(
            event_id=f"{event_id}-{idx:03d}",
            offset_minutes=idx * 6,
            event_type=PlannedEventType.AUTHORIZATION,
            persona_id=persona.persona_id,
            amount_cents=amount,
            merchant_context=MerchantContext(
                category=category,
                mcc=mcc,
                merchant_name_hint=name,
                transaction_channel="ECOMMERCE" if "SUBSCRIPTION" in name else "CARD_PRESENT",
                entry_mode="ECOMMERCE" if "SUBSCRIPTION" in name else "CONTACTLESS",
            ),
            expected_score_band="low",
            outcome_label=OutcomeLabel.CONFIRMED_LEGITIMATE,
            description=f"Normal baseline {category.lower()} activity.",
        )
        for idx, (event_id, category, mcc, name, amount) in enumerate(events, start=1)
    ]
    validations = [
        ExpectedValidation(validation_id="baseline-low-risk", surface="fraud_dashboard", expectation="Baseline activity keeps risk condition normal."),
        ExpectedValidation(validation_id="live-stream-active", surface="admin_stream", expectation="Live stream shows a healthy mix of auth, posted, and pending events."),
    ]
    return _base_plan(
        request,
        ScenarioType.NORMAL_BASELINE_ACTIVITY,
        personas=[persona],
        behavior_policies=[policy],
        timeline=timeline,
        expected_validations=validations,
        limits=_limits(request, customers=cohort_size, cards=cohort_size, authorizations=min(request.max_events or 50, 250), settlements=min(request.max_events or 40, 250), duration_seconds=600),
        assumptions=["Designed to improve ambient baseline behavior without LLM calls."],
        labels={"demo_surface": "baseline", "fraud_language": "false"},
    )


def lakehouse_spend_velocity_surge(request: ScenarioRequest) -> ScenarioPlan:
    event_count = request.max_events or {"low": 20, "medium": 50, "high": 100}[request.intensity.value]
    cohort_size = request.target_cohort_size or max(5, min(event_count // 3, 50))
    persona = PersonaProfile(
        persona_id="lakehouse_velocity_cohort",
        role="active lakehouse spend velocity cohort",
        home_metro="Mixed US metros",
        card_profile="mixed_active_cards",
        typical_mccs=["5411", "5812", "5814", "5541", "4121", "5311"],
        travel_propensity=0.15,
        digital_commerce_propensity=0.35,
        card_present_propensity=0.82,
        notes=["Non-fraud activity burst for live stream and CDC validation."],
    )
    policy = BehaviorPolicy(
        policy_id="lakehouse_velocity_policy",
        preferred_mccs=["5411", "5812", "5814", "5541", "4121", "5311"],
        spend_min_cents=500,
        spend_max_cents=25_000,
        settlement_probability=0.80,
        reversal_probability=0.10,
        pending_probability=0.10,
    )
    timeline = [
        PlannedCardEvent(
            event_id=f"surge-event-{idx:03d}",
            offset_minutes=idx // 5,
            event_type=PlannedEventType.AUTHORIZATION,
            persona_id=persona.persona_id,
            amount_cents=1_000 + (idx % 12) * 750,
            merchant_context=MerchantContext(
                category=["Groceries", "Dining", "Coffee", "Fuel", "Rideshare", "Retail"][idx % 6],
                mcc=["5411", "5812", "5814", "5541", "4121", "5311"][idx % 6],
                merchant_name_hint=f"LAKEHOUSE SURGE MERCHANT {idx:03d}",
                city=["Mountain View", "San Francisco", "Chicago", "Seattle"][idx % 4],
                region=["CA", "CA", "IL", "WA"][idx % 4],
                transaction_channel="CARD_PRESENT",
                entry_mode=["CHIP", "CONTACTLESS", "MAG_STRIPE"][idx % 3],
            ),
            expected_score_band="low",
            outcome_label=OutcomeLabel.CONFIRMED_LEGITIMATE,
            description="Bounded non-fraud spend velocity event for lakehouse replication demo.",
        )
        for idx in range(1, min(event_count, 1000) + 1)
    ]
    validations = [
        ExpectedValidation(validation_id="stream-throughput", surface="admin_stream", expectation="Live event throughput increases immediately after execution.", metric_name="events_per_minute", expected_minimum=min(event_count, 50)),
        ExpectedValidation(validation_id="cdc-freshness", surface="cdc_monitor", expectation="Datastream freshness remains healthy during the burst."),
        ExpectedValidation(validation_id="curated-views", surface="bigquery", expectation="Curated analytics views can consume replicated activity after CDC lands."),
    ]
    return _base_plan(
        request,
        ScenarioType.LAKEHOUSE_SPEND_VELOCITY_SURGE,
        personas=[persona],
        behavior_policies=[policy],
        timeline=timeline,
        expected_validations=validations,
        limits=_limits(request, customers=cohort_size, cards=cohort_size, authorizations=event_count, settlements=int(event_count * 0.8), duration_seconds=300),
        assumptions=["Fraud-like events are excluded by default for this lakehouse activity scenario."],
        labels={"demo_surface": "active_lakehouse", "fraud_language": "false"},
    )


def unknown_request_plan(request: ScenarioRequest, warnings: list[str] | None = None) -> ScenarioPlan:
    persona = PersonaProfile(
        persona_id="unknown_request",
        role="unresolved planning request",
        protected_account_policy="exclude",
        notes=["No execution should occur for this plan."],
    )
    policy = BehaviorPolicy(
        policy_id="no_write_policy",
        preferred_mccs=[],
        spend_min_cents=100,
        spend_max_cents=100,
        settlement_probability=1.0,
        reversal_probability=0.0,
        pending_probability=0.0,
    )
    return _base_plan(
        request,
        ScenarioType.UNKNOWN_REQUEST,
        personas=[persona],
        behavior_policies=[policy],
        timeline=[],
        expected_validations=[],
        limits=ExecutionLimits(max_customers=1, max_cards=0, max_authorizations=0, max_settlements=0, max_duration_seconds=1),
        warnings=warnings or ["No known scenario template matched the request."],
        assumptions=["Dry-run only. Provide a supported scenario_type or a clearer scenario goal."],
        labels={"demo_surface": "unknown", "fraud_language": "false"},
    )


TEMPLATE_BUILDERS: dict[ScenarioType, Callable[[ScenarioRequest], ScenarioPlan]] = {
    ScenarioType.FRAUD_TRAVEL_STORY: fraud_travel_story,
    ScenarioType.PREMIUM_TRAVEL_OFFER_FUEL: premium_travel_offer_fuel,
    ScenarioType.NORMAL_BASELINE_ACTIVITY: normal_baseline_activity,
    ScenarioType.LAKEHOUSE_SPEND_VELOCITY_SURGE: lakehouse_spend_velocity_surge,
}
