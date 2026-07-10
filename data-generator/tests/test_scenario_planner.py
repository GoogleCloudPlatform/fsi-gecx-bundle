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

import pytest
from pydantic import ValidationError

from scenarios import ScenarioRequest, plan_scenario
from scenarios.schemas import ScenarioType
from main import app
from fastapi.testclient import TestClient


client = TestClient(app)


@pytest.mark.parametrize(
    ("goal", "scenario_type"),
    [
        ("Create a fraud story for a traveling executive.", ScenarioType.FRAUD_TRAVEL_STORY),
        ("Create a gift card campaign.", ScenarioType.CNP_GIFT_CARD_CAMPAIGN),
        ("Create a digital card testing campaign.", ScenarioType.DIGITAL_CARD_TESTING_CAMPAIGN),
        ("Create an impossible travel campaign.", ScenarioType.IMPOSSIBLE_TRAVEL_CAMPAIGN),
        ("Create a false positive travel story.", ScenarioType.TRAVEL_FALSE_POSITIVE_STORY),
        ("Generate Mexico travel trend fuel for premium card offer analytics.", ScenarioType.PREMIUM_TRAVEL_OFFER_FUEL),
        ("Create normal weekday baseline card activity.", ScenarioType.NORMAL_BASELINE_ACTIVITY),
        ("Run a lakehouse spend velocity surge for the replication monitor.", ScenarioType.LAKEHOUSE_SPEND_VELOCITY_SURGE),
    ],
)
def test_canned_templates_produce_valid_plans(goal, scenario_type):
    plan = plan_scenario(ScenarioRequest(goal=goal, scenario_type=scenario_type, seed=1841))

    assert plan.scenario_type == scenario_type
    assert plan.scenario_id.startswith(f"{scenario_type.value}-1841-")
    assert plan.mode == "dry_run"
    assert plan.personas
    assert plan.behavior_policies
    assert plan.template_version
    assert plan.planner_version
    assert plan.model_dump(mode="json")["scenario_id"] == plan.scenario_id


def test_fraud_travel_story_contains_fraud_labels_and_expected_reasons():
    plan = plan_scenario(ScenarioRequest(goal="Create a fraud story for a traveling executive.", seed=1841))

    assert plan.scenario_type == ScenarioType.FRAUD_TRAVEL_STORY
    reason_codes = {reason for event in plan.timeline for reason in event.expected_reason_codes}
    outcome_labels = {event.outcome_label for event in plan.timeline}

    assert "CARD_NOT_PRESENT_DESCRIPTOR" in reason_codes
    assert "GIFT_CARD_OR_DIGITAL_GOODS" in reason_codes
    assert "customer_disputed" in outcome_labels
    assert plan.limits.max_fraud_events == 2


@pytest.mark.parametrize(
    ("goal", "scenario_type", "expected_reason"),
    [
        ("Create a gift card campaign.", ScenarioType.CNP_GIFT_CARD_CAMPAIGN, "GIFT_CARD_OR_DIGITAL_GOODS"),
        ("Create a digital card testing campaign.", ScenarioType.DIGITAL_CARD_TESTING_CAMPAIGN, "VELOCITY_SPIKE_10M"),
        ("Create an impossible travel campaign.", ScenarioType.IMPOSSIBLE_TRAVEL_CAMPAIGN, "IMPOSSIBLE_TRAVEL"),
    ],
)
def test_coordinated_fraud_campaign_templates(goal, scenario_type, expected_reason):
    plan = plan_scenario(ScenarioRequest(goal=goal, seed=1841))

    assert plan.scenario_type == scenario_type
    assert plan.labels["demo_surface"] == "fraud_campaign"
    assert plan.labels["fraud_language"] == "true"
    assert plan.limits.max_fraud_events >= 2
    assert any(event.outcome_label == "expected_fraud" for event in plan.timeline)
    assert any(expected_reason in event.expected_reason_codes for event in plan.timeline)


def test_impossible_travel_campaign_includes_card_present_geography():
    plan = plan_scenario(ScenarioRequest(goal="Create impossible travel fraud sequence.", seed=1841))

    countries = {event.merchant_context.country_code for event in plan.timeline if event.merchant_context}
    assert {"USA", "GBR"}.issubset(countries)
    assert all(event.merchant_context.transaction_channel == "CARD_PRESENT" for event in plan.timeline if event.merchant_context)
    assert any(event.merchant_context.latitude is not None for event in plan.timeline if event.merchant_context)


def test_travel_false_positive_story_uses_mexico_geography_without_fraud_language():
    plan = plan_scenario(ScenarioRequest(goal="Create a false positive travel story.", seed=1841))

    assert plan.scenario_type == ScenarioType.TRAVEL_FALSE_POSITIVE_STORY
    assert plan.labels["fraud_language"] == "false"
    assert plan.limits.max_fraud_events == 0
    auth_events = [event for event in plan.timeline if event.merchant_context]
    assert auth_events
    assert {event.merchant_context.country_code for event in auth_events} == {"MEX"}
    assert any(event.outcome_label == "false_positive" for event in plan.timeline)
    assert any(event.outcome_label == "confirmed_legitimate" for event in plan.timeline)
    assert all(event.merchant_context.latitude is not None for event in auth_events)


def test_premium_travel_offer_plan_is_growth_oriented():
    plan = plan_scenario(ScenarioRequest(goal="Build Mexico travel offer audience data.", seed=1841))

    assert plan.scenario_type == ScenarioType.PREMIUM_TRAVEL_OFFER_FUEL
    assert plan.labels["fraud_language"] == "false"
    assert any(event.merchant_context.country_code == "MEX" for event in plan.timeline)
    assert all(event.outcome_label == "confirmed_legitimate" for event in plan.timeline)


def test_lakehouse_spend_velocity_surge_is_bounded_non_fraud_activity():
    plan = plan_scenario(
        ScenarioRequest(
            goal="Run the Active Lakehouse spend velocity surge.",
            seed=1841,
            max_events=12,
            target_cohort_size=6,
        )
    )

    assert plan.scenario_type == ScenarioType.LAKEHOUSE_SPEND_VELOCITY_SURGE
    assert plan.limits.max_authorizations == 12
    assert plan.limits.max_customers == 6
    assert len(plan.timeline) == 12
    assert plan.labels["fraud_language"] == "false"
    assert {event.expected_score_band for event in plan.timeline} == {"low"}


def test_same_prompt_seed_and_template_are_stable():
    request = ScenarioRequest(goal="Create normal baseline card activity.", seed=1234, max_events=7)

    first = plan_scenario(request)
    second = plan_scenario(request)

    assert first.scenario_id == second.scenario_id
    assert [event.event_id for event in first.timeline] == [event.event_id for event in second.timeline]
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_unknown_prompt_returns_safe_warning_plan():
    plan = plan_scenario(ScenarioRequest(goal="Make something interesting happen.", seed=1841))

    assert plan.scenario_type == ScenarioType.UNKNOWN_REQUEST
    assert plan.timeline == []
    assert plan.limits.max_authorizations == 0
    assert plan.warnings


def test_protected_targeting_requires_explicit_opt_in():
    plan = plan_scenario(ScenarioRequest(goal="Target the VIP presenter account with a fraud story.", seed=1841))

    assert plan.scenario_type == ScenarioType.UNKNOWN_REQUEST
    assert any("Presenter/VIP" in warning for warning in plan.warnings)
    assert plan.timeline == []


def test_unbounded_request_rejected_by_schema():
    with pytest.raises(ValidationError):
        ScenarioRequest(goal="Generate a huge unbounded surge.", max_events=500_000)


def test_plan_endpoint_returns_valid_dry_run_plan():
    response = client.post(
        "/scenarios/plan",
        json={
            "goal": "Run the Active Lakehouse spend velocity surge.",
            "seed": 1841,
            "max_events": 6,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["scenario_type"] == "lakehouse_spend_velocity_surge"
    assert body["mode"] == "dry_run"
    assert len(body["timeline"]) == 6
