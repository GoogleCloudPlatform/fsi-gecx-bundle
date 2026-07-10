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

from .schemas import ScenarioRequest, ScenarioType
from .templates import TEMPLATE_BUILDERS, unknown_request_plan

UNSAFE_TARGET_TERMS = ("vip", "presenter", "demo script", "demo-script", "googler")
REAL_DATA_TERMS = ("real customer", "production customer", "actual cardholder", "real cardholder")
APP_LOCATION_TERMS = ("installed app location", "always-on location", "continuous location", "gps tracking")


def infer_scenario_type(goal: str) -> ScenarioType | None:
    normalized = goal.lower()
    if any(term in normalized for term in ("spend surge", "velocity surge", "lakehouse surge", "replication monitor")):
        return ScenarioType.LAKEHOUSE_SPEND_VELOCITY_SURGE
    if any(term in normalized for term in ("premium travel", "offer", "mexico travel trend", "travel offer")):
        return ScenarioType.PREMIUM_TRAVEL_OFFER_FUEL
    if any(term in normalized for term in ("baseline", "normal activity", "ambient", "heartbeat")):
        return ScenarioType.NORMAL_BASELINE_ACTIVITY
    if any(term in normalized for term in ("fraud", "suspicious", "dispute", "traveling executive", "gift card")):
        return ScenarioType.FRAUD_TRAVEL_STORY
    return None


def collect_safety_warnings(request: ScenarioRequest) -> list[str]:
    goal = request.goal.lower()
    warnings = []
    if any(term in goal for term in REAL_DATA_TERMS):
        warnings.append("Request references real customer data; only synthetic demo data is supported.")
    if any(term in goal for term in APP_LOCATION_TERMS):
        warnings.append("Request implies continuous app-location tracking; use merchant/store geography or coarse ecommerce context instead.")
    if any(term in goal for term in UNSAFE_TARGET_TERMS):
        if not (request.allow_presenter_targets or request.allow_vip_targets):
            warnings.append("Presenter/VIP/demo-script targeting requires explicit opt-in.")
    if request.max_events is not None and request.max_events > 1000:
        warnings.append("Requested event count exceeds scenario safety cap and will be rejected by schema validation.")
    return warnings


def plan_scenario(request: ScenarioRequest) -> object:
    warnings = collect_safety_warnings(request)
    if warnings:
        return unknown_request_plan(request, warnings=warnings)

    scenario_type = request.scenario_type or infer_scenario_type(request.goal)
    if scenario_type in TEMPLATE_BUILDERS:
        return TEMPLATE_BUILDERS[scenario_type](request)

    return unknown_request_plan(request)
