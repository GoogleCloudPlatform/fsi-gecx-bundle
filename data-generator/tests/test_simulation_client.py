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

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

import main
from main import app, BANKING_SERVICE_URL

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    res = response.json()
    assert res["status"] == "ok"
    assert res["service"] == "data-generator"
    assert "version" in res
    assert "commit" in res


@respx.mock
def test_get_merchants_prefers_canonical_api_shape(monkeypatch):
    monkeypatch.setattr(main, "merchants_list", [])
    respx.get(f"{BANKING_SERVICE_URL}/api/v1/merchants").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "clean_name": "Canonical Merchant",
                    "raw_descriptor_pattern": "CANONICAL MERCHANT%",
                    "category": "Retail",
                    "mcc": "5311",
                    "country_code": "USA",
                    "is_international": False,
                    "risk_score": 1,
                }
            ],
        )
    )

    merchants = main.get_merchants()

    assert merchants == [
        {
            "merchant": "Canonical Merchant",
            "descriptor": "CANONICAL MERCHANT%",
            "category": "Retail",
            "mcc": "5311",
            "country_code": "USA",
            "is_international": False,
            "risk_score": 1,
        }
    ]


@respx.mock
def test_get_merchants_falls_back_to_legacy_route_shape(monkeypatch):
    monkeypatch.setattr(main, "merchants_list", [])
    respx.get(f"{BANKING_SERVICE_URL}/api/v1/merchants").mock(
        return_value=httpx.Response(404, json={"detail": "Not Found"})
    )
    respx.get(f"{BANKING_SERVICE_URL}/merchants").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "clean_name": "Legacy Merchant",
                    "raw_descriptor": "LEGACY MERCHANT%",
                    "category": "Dining",
                    "default_mcc": "5812",
                    "country_code": "MEX",
                    "is_international": True,
                    "risk_score": 9,
                }
            ],
        )
    )

    merchants = main.get_merchants()

    assert merchants == [
        {
            "merchant": "Legacy Merchant",
            "descriptor": "LEGACY MERCHANT%",
            "category": "Dining",
            "mcc": "5812",
            "country_code": "MEX",
            "is_international": True,
            "risk_score": 9,
        }
    ]

@pytest.mark.asyncio
@respx.mock
async def test_simulate_pulse_success():
    original_plan_builder = main.build_randomized_pulse_plan
    original_randint = main.random.randint
    original_auto_paydown = main.auto_paydown_high_utilization_cards
    main.build_randomized_pulse_plan = lambda total_events, window_seconds=58: [0.0, 0.0, 0.0, 0.0]
    main.random.randint = lambda a, b: 4 if (a, b) == (8, 12) else original_randint(a, b)
    async def noop_auto_paydown(client, cards, trigger_utilization=0.65, target_utilization=0.35):
        return []
    main.auto_paydown_high_utilization_cards = noop_auto_paydown

    # Mock Gateway Endpoints
    auth_route = respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize").mock(
        return_value=httpx.Response(200, json={"action_code": "00", "auth_code": "123456", "status": "PENDING"})
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/settle").mock(
        return_value=httpx.Response(200, json={"status": "SETTLED"})
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/reverse").mock(
        return_value=httpx.Response(200, json={"status": "REVERSED"})
    )
    
    # Trigger simulation pulse
    try:
        response = client.post("/simulate-pulse")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert data["swipes_attempted"] == 4
        assert data["scheduled_events"] == 4
        assert data["distribution_window_seconds"] == 58
    finally:
        main.build_randomized_pulse_plan = original_plan_builder
        main.random.randint = original_randint
        main.auto_paydown_high_utilization_cards = original_auto_paydown
    
    # Assert auth requests were sent with the correct headers
    assert auth_route.called
    for request in auth_route.calls:
        assert request[0].headers.get("X-Card-Network-Token") == main.get_card_network_token()
        payload = request[0].read().decode()
        assert "card_token" in payload
        assert "amount_cents" in payload
        assert "retrieval_reference_number" in payload

@pytest.mark.asyncio
@respx.mock
async def test_simulate_pulse_declined():
    original_plan_builder = main.build_randomized_pulse_plan
    original_randint = main.random.randint
    original_auto_paydown = main.auto_paydown_high_utilization_cards
    main.build_randomized_pulse_plan = lambda total_events, window_seconds=58: [0.0, 0.0, 0.0, 0.0]
    main.random.randint = lambda a, b: 4 if (a, b) == (8, 12) else original_randint(a, b)
    async def noop_auto_paydown(client, cards, trigger_utilization=0.65, target_utilization=0.35):
        return []
    main.auto_paydown_high_utilization_cards = noop_auto_paydown

    # Mock Gateway declines swipes (action_code = 51)
    auth_route = respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize").mock(
        return_value=httpx.Response(200, json={"action_code": "51", "auth_code": "000000", "status": "DECLINED", "decline_reason": "INSUFFICIENT_FUNDS"})
    )
    settle_route = respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/settle").mock(
        return_value=httpx.Response(200, json={"status": "SETTLED"})
    )
    
    try:
        response = client.post("/simulate-pulse")
        assert response.status_code == 200
        assert response.json()["status"] == "NOOP"
        assert response.json()["authorizations_created"] == 0

        # Assert auth was called, but settle was NOT called since it was declined
        assert auth_route.called
        assert not settle_route.called
    finally:
        main.build_randomized_pulse_plan = original_plan_builder
        main.random.randint = original_randint
        main.auto_paydown_high_utilization_cards = original_auto_paydown

@respx.mock
def test_simulate_surge_success():
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize").mock(
        return_value=httpx.Response(200, json={"action_code": "00", "auth_code": "123456", "status": "PENDING"})
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/settle").mock(
        return_value=httpx.Response(200, json={"status": "SETTLED"})
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/reverse").mock(
        return_value=httpx.Response(200, json={"status": "REVERSED"})
    )
    response = client.post("/simulate-surge", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"
    assert response.json()["swipes_attempted"] == 50


def test_simulate_surge_fails_without_spendable_cards():
    response = client.post("/simulate-surge", json={
        "active_cards": [
            {
                "card_token": "tok_dead",
                "cardholder_name": "Declined User",
                "persona": "PRIME",
                "mccs": ["5411"],
                "amount_min": 1500,
                "amount_max": 15000,
                "available_credit_cents": 0,
            }
        ]
    })

    assert response.status_code == 409
    assert "No spendable active cards" in response.json()["detail"]


@respx.mock
def test_generate_fails_without_active_cards_in_deployed_mode(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "data-generator")
    monkeypatch.setenv("CARD_NETWORK_SWITCH_TOKEN", "switch-secret-key-12345")
    respx.get(f"{BANKING_SERVICE_URL}/api/v1/credit-card/active-cards").mock(
        return_value=httpx.Response(503, json={"detail": {"status": "MAINTENANCE"}})
    )

    response = client.post("/generate")

    assert response.status_code == 200
    assert response.json()["status"] == "SKIPPED"
    assert "reset is in progress" in response.json()["message"]


@respx.mock
def test_generate_skips_without_retry_when_active_card_discovery_times_out(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "data-generator")
    monkeypatch.setenv("CARD_NETWORK_SWITCH_TOKEN", "switch-secret-key-12345")
    respx.get(f"{BANKING_SERVICE_URL}/api/v1/credit-card/active-cards").mock(
        side_effect=httpx.ReadTimeout("timed out")
    )

    response = client.post("/generate")

    assert response.status_code == 200
    assert response.json()["status"] == "SKIPPED"
    assert "temporarily unavailable" in response.json()["message"]


@respx.mock
def test_simulate_surge_returns_503_during_maintenance(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "data-generator")
    monkeypatch.setenv("CARD_NETWORK_SWITCH_TOKEN", "switch-secret-key-12345")
    respx.get(f"{BANKING_SERVICE_URL}/api/v1/credit-card/active-cards").mock(
        return_value=httpx.Response(503, json={"detail": {"status": "MAINTENANCE"}})
    )

    response = client.post("/simulate-surge", json={}, headers={"X-Card-Network-Token": main.get_card_network_token()})

    assert response.status_code == 503
    assert "reset is in progress" in response.json()["detail"]


def test_get_spendable_cards_filters_exhausted_cards():
    cards = [
        {"card_token": "tok_1", "available_credit_cents": 0},
        {"card_token": "tok_2", "available_credit_cents": 99},
        {"card_token": "tok_3", "available_credit_cents": 100},
        {"card_token": "tok_4"},
    ]

    spendable = main.get_spendable_cards(cards)

    assert [card["card_token"] for card in spendable] == ["tok_3", "tok_4"]


def test_get_generator_eligible_cards_excludes_presenter_and_vip_cards():
    cards = [
        {"card_token": "tok_presenter", "generator_eligible": False},
        {"card_token": "tok_vip", "generator_eligible": False},
        {"card_token": "tok_mock", "generator_eligible": True},
        {"card_token": "tok_legacy"},
    ]

    eligible = main.get_generator_eligible_cards(cards)

    assert [card["card_token"] for card in eligible] == ["tok_mock", "tok_legacy"]


@pytest.mark.asyncio
@respx.mock
async def test_auto_paydown_high_utilization_cards_calls_internal_endpoint():
    route = respx.post(f"{BANKING_SERVICE_URL}/api/v1/credit-card/internal/auto-paydown").mock(
        return_value=httpx.Response(200, json={"status": "SUCCESS", "paid_amount_cents": 25000})
    )

    async with httpx.AsyncClient() as async_client:
        results = await main.auto_paydown_high_utilization_cards(
            async_client,
            [
                {
                    "customer_id": "cust-1",
                    "credit_account_id": "cred-1",
                    "credit_limit_cents": 100000,
                    "available_credit_cents": 20000,
                },
                {
                    "customer_id": "cust-2",
                    "credit_account_id": "cred-2",
                    "credit_limit_cents": 100000,
                    "available_credit_cents": 50000,
                },
            ],
        )

    assert route.called
    assert route.call_count == 1
    assert results[0]["status"] == "SUCCESS"
    assert results[0]["credit_account_id"] == "cred-1"


@pytest.mark.asyncio
@respx.mock
async def test_auto_paydown_high_utilization_cards_caps_accounts_per_pulse(monkeypatch):
    monkeypatch.setattr(main, "AUTO_PAYDOWN_MAX_ACCOUNTS_PER_PULSE", 2)
    monkeypatch.setattr(main.random, "shuffle", lambda items: None)
    route = respx.post(f"{BANKING_SERVICE_URL}/api/v1/credit-card/internal/auto-paydown").mock(
        return_value=httpx.Response(200, json={"status": "SUCCESS", "paid_amount_cents": 25000})
    )

    cards = [
        {
            "customer_id": f"cust-{idx}",
            "credit_account_id": f"cred-{idx}",
            "credit_limit_cents": 100000,
            "available_credit_cents": 10000,
        }
        for idx in range(4)
    ]

    async with httpx.AsyncClient() as async_client:
        results = await main.auto_paydown_high_utilization_cards(async_client, cards)

    assert route.call_count == 2
    assert len(results) == 2

@pytest.mark.asyncio
@respx.mock
async def test_inject_anomaly_success():
    auth_route = respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize").mock(
        return_value=httpx.Response(200, json={"action_code": "00", "auth_code": "999999", "status": "PENDING"})
    )
    
    response = client.post("/inject-anomaly", json={"card_token": "tok_visa_test"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ANOMALY_INJECTED"
    assert data["injected_swipes_count"] == 4
    assert data["card_token"] == "tok_visa_test"
    assert auth_route.call_count == 4
