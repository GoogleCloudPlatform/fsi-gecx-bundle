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
    DEFAULT_TIER_CONFIG,
    BankDecision,
    DecisionRequest,
    InquiryConsent,
    load_credit_limit_tier_config,
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


# --- Tiered contract: consent, counteroffer, refusal facts -------------------

LEGACY_DECISION_KEYS = {
    "decision_id", "provider_id", "outcome", "approved_limit", "reason_codes",
    "policy", "evaluated_at", "expires_at", "request_ref", "scope_ref",
    "input_ref", "evidence_references",
}
CONSENT_REF = "e" * 64
TIERS = load_credit_limit_tier_config()


def usd(amount):
    return {"amount_minor": amount, "currency_code": "USD"}


def consent(inquiry_type="SOFT", disclosure=None):
    return {
        "inquiry_type": inquiry_type,
        "disclosure_version": disclosure
        or f"{inquiry_type.lower()}-inquiry-disclosure.v1",
        "consent_ref": CONSENT_REF,
    }


def with_request(req, **changes):
    return DecisionRequest.model_validate({**req.model_dump(mode="json"), **changes})


def receipt(req, **changes):
    provider = load_decisioning_provider(clock=lambda: NOW)
    raw = provider.evaluate(req).model_dump(mode="json")
    raw.update(changes)
    return provider, raw


def refusal(**changes):
    return {
        "reason_code": "COUNTEROFFER_AVAILABLE",
        "retryable": False,
        "current_limit": usd(1000000),
        "product_maximum": usd(3000000),
        "max_instantly_approvable": usd(1200000),
        "soft_tier_cap": usd(1500000),
        "product_name": "Cash Rewards 2%",
        "next_steps": ["ACCEPT_COUNTEROFFER", "SPECIALIST_REVIEW"],
        **changes,
    }


def counteroffer_receipt(req, **changes):
    terms = {
        "outcome": "COUNTEROFFER",
        "approved_limit": usd(1200000),
        "reason_codes": ["COUNTEROFFER_AVAILABLE"],
        "inquiry_type": "NONE",
        "counteroffer": {
            "origin_request_ref": req.request_ref,
            "requested_limit": req.requested_limit.model_dump(),
        },
        "refusal": refusal(),
    }
    return receipt(req, **{**terms, **changes})


def test_soft_consent_never_authorizes_a_hard_inquiry():
    req = with_request(request(), inquiry_consent=consent("SOFT"))
    provider, raw = receipt(
        req, inquiry_type="HARD", evidence_references=[req.input_ref, CONSENT_REF]
    )
    with pytest.raises(ValueError, match="does not authorize"):
        validate_decision(raw, req, provider.current_policy, NOW, tier_config=TIERS)
    raw["inquiry_type"] = "SOFT"
    assert validate_decision(raw, req, provider.current_policy, NOW, tier_config=TIERS).inquiry_type == "SOFT"


@pytest.mark.parametrize(
    "consent_doc,changes",
    [
        (None, {"inquiry_type": "HARD"}),
        (None, {"inquiry_type": "SOFT"}),
        (consent("HARD"), {"inquiry_type": "HARD"}),  # consent_ref not in evidence
        (consent("SOFT"), {"inquiry_type": "NONE", "evidence_references": None}),
    ],
)
def test_inquiry_requires_exact_bound_consent(consent_doc, changes):
    req = with_request(request(), inquiry_consent=consent_doc)
    if changes.get("evidence_references", "") is None:
        changes["evidence_references"] = [req.input_ref, CONSENT_REF]
    provider, raw = receipt(req, **changes)
    with pytest.raises(ValueError):
        validate_decision(raw, req, provider.current_policy, NOW, tier_config=TIERS)


@pytest.mark.parametrize(
    "inquiry_type,disclosure",
    [("HARD", "soft-inquiry-disclosure.v1"), ("SOFT", "hard-inquiry-disclosure.v1")],
)
def test_consent_disclosure_is_bound_to_its_tier(inquiry_type, disclosure):
    with pytest.raises(ValidationError):
        InquiryConsent.model_validate(consent(inquiry_type, disclosure))


@pytest.mark.parametrize(
    "inquiry_type,disclosure",
    [("HARD", "hard-inquiry-disclosure.v999"), ("SOFT", "soft-inquiry-disclosure.v2")],
)
def test_consent_must_cite_the_configured_disclosure_version(inquiry_type, disclosure):
    req = with_request(request(), inquiry_consent=consent(inquiry_type, disclosure))
    provider, raw = receipt(
        req, inquiry_type=inquiry_type, evidence_references=[req.input_ref, CONSENT_REF]
    )
    with pytest.raises(ValueError, match="current disclosure"):
        validate_decision(raw, req, provider.current_policy, NOW, tier_config=TIERS)


def test_consent_fails_closed_without_the_tier_configuration():
    req = with_request(request(), inquiry_consent=consent("SOFT"))
    provider, raw = receipt(
        req, inquiry_type="SOFT", evidence_references=[req.input_ref, CONSENT_REF]
    )
    with pytest.raises(ValueError, match="tier configuration"):
        validate_decision(raw, req, provider.current_policy, NOW)


def test_consent_request_names_a_tier_the_customer_has_not_consented_to():
    req = with_request(request(), inquiry_consent=consent("SOFT"))
    provider, raw = receipt(
        req,
        outcome="NEEDS_INFORMATION",
        approved_limit=None,
        reason_codes=["INQUIRY_CONSENT_REQUIRED"],
        inquiry_type="HARD",
        evidence_references=[req.input_ref, CONSENT_REF],
    )
    assert validate_decision(raw, req, provider.current_policy, NOW, tier_config=TIERS).inquiry_type == "HARD"
    raw["inquiry_type"] = "SOFT"
    with pytest.raises(ValueError, match="already gave"):
        validate_decision(raw, req, provider.current_policy, NOW, tier_config=TIERS)
    raw["inquiry_type"] = None
    with pytest.raises(ValidationError):
        validate_decision(raw, req, provider.current_policy, NOW, tier_config=TIERS)


@pytest.mark.parametrize(
    "change",
    [
        {"counteroffer": None},
        {"refusal": None},
        {"inquiry_type": None},
        {"reason_codes": ["LIMIT_CEILING_EXCEEDED"]},
        {"counteroffer": {"origin_request_ref": "d" * 64, "requested_limit": usd(1500000)}},
        {"counteroffer": {"origin_request_ref": "a" * 64, "requested_limit": usd(1400000)}},
        {
            "counteroffer": {
                "origin_request_ref": "a" * 64,
                "requested_limit": usd(1500000),
                "secret": "no",
            }
        },
        {"approved_limit": usd(1500000)},
        {"approved_limit": usd(1000000)},
        {"approved_limit": {"amount_minor": 1200000, "currency_code": "MXN"}},
    ],
)
def test_counteroffer_without_valid_origin_link_or_bounds_is_rejected(change):
    req = request()
    provider, raw = counteroffer_receipt(req)
    raw.update(change)
    with pytest.raises((ValueError, ValidationError)):
        validate_decision(raw, req, provider.current_policy, NOW, tier_config=TIERS)


def test_counteroffer_validates_only_through_the_counteroffer_contract():
    req = request()
    provider, raw = counteroffer_receipt(req)
    decision = validate_decision(raw, req, provider.current_policy, NOW, tier_config=TIERS)
    assert decision.approved_limit.amount_minor == 1200000
    assert decision.counteroffer.origin_request_ref == req.request_ref
    with pytest.raises(ValueError, match="separate contract"):
        validate_decision(
            {**raw, "outcome": "APPROVED", "reason_codes": ["APPROVED_BY_POLICY"],
             "counteroffer": None, "refusal": None},
            req, provider.current_policy, NOW, tier_config=TIERS,
        )


def test_counteroffer_above_product_maximum_is_rejected():
    base = request()
    # The demo provider refuses over-maximum requests; reuse its receipt shape.
    req = with_request(base, requested_limit=usd(3500000))
    provider, raw = counteroffer_receipt(
        base,
        approved_limit=usd(3200000),
        counteroffer={"origin_request_ref": req.request_ref, "requested_limit": usd(3500000)},
        refusal=refusal(soft_tier_cap=usd(3000000)),
    )
    with pytest.raises(ValueError, match="checked bounds"):
        validate_decision(raw, req, provider.current_policy, NOW, tier_config=TIERS)


def test_counteroffer_requires_the_request_within_the_product_maximum():
    base = request()
    req = with_request(base, requested_limit=usd(3500000))
    # Offer at the product maximum for an over-maximum request stays rejected;
    # whether to allow it is a deferred owner decision for the tiered provider.
    provider, raw = counteroffer_receipt(
        base,
        approved_limit=usd(3000000),
        counteroffer={"origin_request_ref": req.request_ref, "requested_limit": usd(3500000)},
        refusal=refusal(soft_tier_cap=usd(3000000)),
    )
    with pytest.raises(ValueError, match="checked bounds"):
        validate_decision(raw, req, provider.current_policy, NOW, tier_config=TIERS)


def test_counteroffer_proposal_request_cannot_be_countered_again():
    origin = {
        "origin_request_ref": "f" * 64,
        "origin_decision_ref": "demo-bank:decision-1",
        "origin_requested_limit": usd(2000000),
    }
    req = with_request(request(), origin=origin)
    provider, raw = counteroffer_receipt(req)
    with pytest.raises(ValueError, match="cannot itself be countered"):
        validate_decision(raw, req, provider.current_policy, NOW, tier_config=TIERS)
    with pytest.raises(ValidationError):
        with_request(request(), origin={**origin, "origin_requested_limit": usd(1500000)})
    with pytest.raises(ValidationError):
        with_request(request(), origin={**origin, "origin_decision_ref": None})


@pytest.mark.parametrize(
    "decision_change,refusal_change",
    [
        ({}, {"reason_code": "POLICY_DECLINED"}),
        ({}, {"current_limit": usd(900000)}),
        ({}, {"product_maximum": usd(2900000)}),
        ({}, {"product_name": "Cash\nRewards"}),
        ({}, {"product_name": " padded"}),
        ({}, {"secret": "private"}),
        ({}, {"next_steps": ["CALL_ME"]}),
        ({}, {"next_steps": ["SPECIALIST_REVIEW"]}),
        ({}, {"next_steps": ["ACCEPT_COUNTEROFFER", "ACCEPT_COUNTEROFFER"]}),
        ({}, {"max_instantly_approvable": usd(1600000)}),
        ({}, {"soft_tier_cap": usd(3100000)}),
        ({}, {"retryable": "yes"}),
        (
            {},
            {
                "next_steps": ["ACCEPT_COUNTEROFFER", "RETRY_AFTER_COOLING_OFF"],
                "retryable": True,
            },
        ),
    ],
)
def test_refusal_facts_are_bounded_and_bound_to_checked_inputs(
    decision_change, refusal_change
):
    req = request()
    provider, raw = counteroffer_receipt(req, refusal=refusal(**refusal_change))
    raw.update(decision_change)
    with pytest.raises((ValueError, ValidationError)):
        validate_decision(raw, req, provider.current_policy, NOW, tier_config=TIERS)


def test_refusal_facts_are_forbidden_on_approval_and_require_coherent_decline():
    req = request()
    provider, raw = receipt(req, refusal=refusal(reason_code="APPROVED_BY_POLICY",
                                                 next_steps=["SPECIALIST_REVIEW"]))
    with pytest.raises(ValidationError, match="no refusal facts"):
        validate_decision(raw, req, provider.current_policy, NOW, tier_config=TIERS)
    declined = refusal(
        reason_code="COOLING_OFF_ACTIVE",
        retryable=True,
        max_instantly_approvable=usd(1000000),
        next_steps=["RETRY_AFTER_COOLING_OFF"],
        retry_after="2027-04-01",
    )
    provider, raw = receipt(
        req, outcome="DECLINED", approved_limit=None,
        reason_codes=["COOLING_OFF_ACTIVE"], inquiry_type="NONE", refusal=declined,
    )
    decision = validate_decision(raw, req, provider.current_policy, NOW, tier_config=TIERS)
    assert decision.refusal.retry_after == datetime.date(2027, 4, 1)
    assert decision.model_dump(mode="json")["refusal"]["product_name"] == "Cash Rewards 2%"


def test_legacy_receipts_keep_their_exact_wire_shape():
    req = request()
    for scenario in ("STANDARD", "DECLINE", "NEEDS_INFORMATION", "REFER_FOR_REVIEW"):
        provider = load_decisioning_provider(scenario=scenario, clock=lambda: NOW)
        decision = provider.evaluate(req)
        assert set(decision.model_dump(mode="json")) == LEGACY_DECISION_KEYS
        assert BankDecision.model_validate(
            decision.model_dump(mode="json")
        ) == decision
    assert set(req.model_dump(mode="json")) == {
        "request_ref", "scope_ref", "input_ref", "requested_limit", "facts",
    }


# --- Tier configuration (shape and defaults only) ---------------------------


def test_default_tier_config_loads_with_closed_tiers():
    config = load_credit_limit_tier_config()
    policy = config.policy_for("ANY_PRODUCT")
    assert policy is config.default
    assert policy.soft_tier.max_multiple_of_current_bps >= 10000
    assert policy.disclosures.HARD.startswith("hard-")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.update(secret="private"),
        lambda c: c["default"].update(secret="private"),
        lambda c: c["default"]["soft_tier"].update(max_multiple_of_current_bps=9999),
        lambda c: c["default"]["gates"].update(cooling_off_days=180.0),
        lambda c: c["default"]["gates"].update(minimum_credit_score=True),
        lambda c: c["default"]["headroom"]["tier_bps"].pop("SUBPRIME"),
        lambda c: c["default"]["headroom"]["tier_bps"].update(PRIME=10001),
        lambda c: c["default"]["headroom"]["utilization_bands"].reverse(),
        lambda c: c["default"]["headroom"]["tenure_bands"][0].update(min_months=3),
        lambda c: c["default"]["disclosures"].update(HARD="soft-inquiry-disclosure.v1"),
        lambda c: c["product_overrides"].update(lowercase=c["default"]),
        lambda c: c["product_overrides"].update(
            PLATINUM={k: v for k, v in c["default"].items() if k != "gates"}
        ),
        lambda c: c.update(schema_version=2),
    ],
)
def test_tier_config_is_closed_and_bounded(tmp_path, mutate):
    config = json.loads(DEFAULT_TIER_CONFIG.read_text())
    mutate(config)
    path = tmp_path / "tiers.json"
    path.write_text(json.dumps(config))
    with pytest.raises(ValidationError):
        load_credit_limit_tier_config(path)
