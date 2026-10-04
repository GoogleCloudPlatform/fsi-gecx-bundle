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

"""Conformance for bank-owned decision receipts and operator-only scenarios."""

import datetime
import json
import uuid

import pytest
from pydantic import ValidationError
from models.money import Money
from services.decisioning import (
    DEFAULT_CONFIG,
    DecisionRequest,
    load_decisioning_provider,
    validate_decision,
)

NOW = datetime.datetime(2026, 10, 2, tzinfo=datetime.timezone.utc)


def request():
    return DecisionRequest(
        request_ref="a" * 64,
        scope_ref="b" * 64,
        input_ref="c" * 64,
        requested_limit=Money(amount_minor=1500000, currency_code="USD"),
        facts={
            "account_id": str(uuid.uuid4()),
            "account_status": "ACTIVE",
            "currency_code": "USD",
            "product_code": "DEMO",
            "current_limit_minor": 1000000,
            "product_active": True,
            "minimum_limit_minor": 100000,
            "maximum_limit_minor": 3000000,
        },
    )


@pytest.mark.parametrize(
    "scenario,outcome",
    [
        ("STANDARD", "APPROVED"),
        ("DECLINE", "DECLINED"),
        ("NEEDS_INFORMATION", "NEEDS_INFORMATION"),
        ("REFER_FOR_REVIEW", "REFER_FOR_REVIEW"),
    ],
)
def test_operator_scenarios_return_explicit_valid_receipts(scenario, outcome):
    provider = load_decisioning_provider(scenario=scenario, clock=lambda: NOW)
    req = request()
    receipt = validate_decision(
        provider.evaluate(req), req, provider.current_policy, NOW
    )
    assert receipt.outcome == outcome
    assert (receipt.approved_limit is not None) == (outcome == "APPROVED")
    assert receipt.binding_ref.startswith("demo-bank:")
    assert receipt.evidence_references == (req.input_ref,)
    assert provider.evaluate(req).decision_id == receipt.decision_id


def test_request_facts_are_copied_and_immutable():
    raw = request().model_dump(mode="json")
    req = DecisionRequest.model_validate(raw)
    raw["facts"]["current_limit_minor"] = 1
    assert req.facts.current_limit_minor == 1000000
    with pytest.raises(ValidationError):
        req.facts.current_limit_minor = 1
    with pytest.raises(ValidationError):
        DecisionRequest.model_validate(
            {**raw, "facts": {**raw["facts"], "secret": "no"}}
        )


@pytest.mark.parametrize(
    "change",
    [
        {"secret": "private"},
        {"approved_limit": {"amount_minor": True, "currency_code": "USD"}},
        {"approved_limit": {"amount_minor": 1600000, "currency_code": "USD"}},
        {
            "approved_limit": {
                "amount_minor": 1500000,
                "currency_code": "USD",
                "secret": "no",
            }
        },
        {"provider_id": "other"},
        {"request_ref": "d" * 64},
        {"scope_ref": "d" * 64},
        {"input_ref": "d" * 64},
        {"evidence_references": ["d" * 64]},
        {"reason_codes": ["invented"]},
        {"outcome": "DECLINED"},
        {"evaluated_at": NOW.replace(tzinfo=None).isoformat()},
        {"evaluated_at": (NOW + datetime.timedelta(seconds=1)).isoformat()},
        {"expires_at": NOW.isoformat()},
        {"expires_at": (NOW + datetime.timedelta(seconds=301)).isoformat()},
    ],
)
def test_inconsistent_or_unbounded_provider_response_fails_closed(change):
    provider = load_decisioning_provider(clock=lambda: NOW)
    req = request()
    raw = provider.evaluate(req).model_dump(mode="json")
    raw.update(change)
    with pytest.raises((ValueError, ValidationError)):
        validate_decision(raw, req, provider.current_policy, NOW)


def test_reused_model_instances_revalidate_nested_money_and_unknown_fields():
    provider = load_decisioning_provider(clock=lambda: NOW)
    req = request()
    receipt = provider.evaluate(req)
    forged = receipt.model_copy(
        update={
            "approved_limit": req.requested_limit.model_copy(
                update={"amount_minor": True}
            )
        }
    )
    with pytest.raises(ValueError):
        validate_decision(forged, req, provider.current_policy, NOW)
    with pytest.raises(ValueError):
        validate_decision(
            receipt.model_copy(update={"secret": "private"}),
            req,
            provider.current_policy,
            NOW,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"secret": "private"},
        {"scenarios": ["STANDARD"]},
        {
            "scenarios": [
                "STANDARD",
                "DECLINE",
                "NEEDS_INFORMATION",
                {"name": "REFER_FOR_REVIEW"},
            ]
        },
        {"approval_ttl_seconds": True},
        {"approval_ttl_seconds": 301},
        {"policy_version": True},
        {"default_scenario": "invented"},
    ],
)
def test_operator_config_is_closed_and_bounded(tmp_path, change):
    config = json.loads(DEFAULT_CONFIG.read_text())
    config.update(change)
    path = tmp_path / "decision.json"
    path.write_text(json.dumps(config))
    with pytest.raises((ValueError, ValidationError)):
        load_decisioning_provider(config_path=path)
