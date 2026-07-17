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
import json
import pytest
import respx
from uuid import UUID
from fastapi.testclient import TestClient

import main
from main import app, BANKING_SERVICE_URL

client = TestClient(app)


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.raise_on_set = False

    def ping(self):
        return True

    def set(self, key, value, nx=False, ex=None):
        del ex
        if self.raise_on_set:
            raise RuntimeError("redis unavailable")
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    res = response.json()
    assert res["status"] == "ok"
    assert res["service"] == "data-generator"
    assert "build_version" in res
    assert "build_commit_id" in res


@respx.mock
def test_get_merchants_prefers_canonical_api_shape(monkeypatch):
    monkeypatch.setattr(main, "merchants_list", [])
    respx.get(f"{BANKING_SERVICE_URL}/api/v1/merchants").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "merchant_id": "36d183e2-a902-53e0-a761-1ea6d078da9f",
                    "merchant_slug": "canonical_merchant",
                    "merchant_store_id": "81c84671-7dec-5e79-a141-9c02f774b6bf",
                    "clean_name": "Canonical Merchant",
                    "raw_descriptor_pattern": "CANONICAL MERCHANT%",
                    "category": "Retail",
                    "mcc": "5311",
                    "country_code": "USA",
                    "city": "San Francisco",
                    "region": "CA",
                    "postal_code": "94103",
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "card_present_capable": True,
                    "ecommerce_capable": False,
                    "high_risk_flags": ["ELECTRONICS"],
                    "is_international": False,
                    "risk_score": 1,
                }
            ],
        )
    )

    merchants = main.get_merchants()

    assert merchants == [
        {
            "merchant_id": "36d183e2-a902-53e0-a761-1ea6d078da9f",
            "merchant_slug": "canonical_merchant",
            "merchant_store_id": "81c84671-7dec-5e79-a141-9c02f774b6bf",
            "merchant": "Canonical Merchant",
            "descriptor": "CANONICAL MERCHANT%",
            "category": "Retail",
            "mcc": "5311",
            "country_code": "USA",
            "city": "San Francisco",
            "region": "CA",
            "postal_code": "94103",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "card_present_capable": True,
            "ecommerce_capable": False,
            "high_risk_flags": ["ELECTRONICS"],
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
                    "city": "Cancun",
                    "region": "QR",
                    "postal_code": "77500",
                    "latitude": 21.1619,
                    "longitude": -86.8515,
                    "card_present_capable": True,
                    "ecommerce_capable": False,
                    "high_risk_flags": [],
                    "is_international": True,
                    "risk_score": 9,
                }
            ],
        )
    )

    merchants = main.get_merchants()

    assert merchants == [
        {
            "merchant_id": None,
            "merchant_slug": None,
            "merchant_store_id": None,
            "merchant": "Legacy Merchant",
            "descriptor": "LEGACY MERCHANT%",
            "category": "Dining",
            "mcc": "5812",
            "country_code": "MEX",
            "city": "Cancun",
            "region": "QR",
            "postal_code": "77500",
            "latitude": 21.1619,
            "longitude": -86.8515,
            "card_present_capable": True,
            "ecommerce_capable": False,
            "high_risk_flags": [],
            "is_international": True,
            "risk_score": 9,
        }
    ]


def test_build_persona_profile_and_behavior_policy_shapes_card_usage():
    ypro = main.build_persona_profile(
        {"persona": "YPRO", "cardholder_name": "Ava Taylor"}
    )
    ypro_policy = main.build_behavior_policy(
        {"persona": "YPRO", "amount_min": 400, "amount_max": 3500}, ypro
    )
    hnw = main.build_persona_profile(
        {"persona": "HNW", "cardholder_name": "Executive Traveler"}
    )

    assert ypro.persona_id == "young_professional_digital"
    assert ypro.digital_commerce_propensity > ypro.travel_propensity
    assert "4899" in ypro_policy.preferred_mccs
    assert ypro_policy.ecommerce_context
    assert hnw.persona_id == "hnw_travel"
    assert hnw.travel_propensity > ypro.travel_propensity


def test_ambient_profile_control_surface_updates_runtime_knobs():
    client.post("/ambient/profile/reset")

    response = client.put(
        "/ambient/profile",
        json={
            "profile_name": "agent-travel-warmup",
            "pulse_min_events": 3,
            "pulse_max_events": 3,
            "pulse_window_seconds": 12,
            "workflow_concurrency": 2,
            "persona_weights": {"YPRO": 1, "HNW": 4},
            "travel_multiplier": 2.5,
            "ecommerce_multiplier": 0.5,
            "fraud_pattern_enabled": True,
            "fraud_pattern_rate": 0.25,
            "fraud_pattern_max_per_pulse": 2,
            "auto_paydown_max_accounts_per_pulse": 1,
            "updated_by": "agentic-test",
        },
    )

    assert response.status_code == 200
    profile = response.json()
    assert profile["profile_name"] == "agent-travel-warmup"
    assert profile["pulse_min_events"] == 3
    assert profile["persona_weights"] == {"YPRO": 1.0, "HNW": 4.0}

    status_response = client.get("/simulation/status")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["pulse"]["min_events"] == 3
    assert status_body["fraud_patterns"]["enabled"] is True
    assert "/ambient/profile" in status_body["supported_routes"]
    assert status_body["ambient_profile"]["updated_by"] == "agentic-test"

    client.post("/ambient/profile/reset")


def test_select_ambient_card_uses_persona_weights(monkeypatch):
    cards = [
        {"card_token": "tok_prime", "persona": "PRIME"},
        {"card_token": "tok_ypro", "persona": "YPRO"},
    ]
    profile = main.AmbientLoadProfile(persona_weights={"PRIME": 1, "YPRO": 9})

    def fake_choices(population, weights=None, k=1):
        assert population == cards
        assert weights == [1.0, 9.0]
        assert k == 1
        return [cards[1]]

    monkeypatch.setattr(main.random, "choices", fake_choices)

    assert main.select_ambient_card(cards, profile)["card_token"] == "tok_ypro"


@pytest.mark.asyncio
@respx.mock
async def test_simulate_swipe_event_uses_persona_ecommerce_context(monkeypatch):
    monkeypatch.setattr(
        main,
        "get_merchants",
        lambda: [
            {
                "merchant_id": "36d183e2-a902-53e0-a761-1ea6d078da9f",
                "merchant_slug": "streaming_merchant",
                "merchant_store_id": "81c84671-7dec-5e79-a141-9c02f774b6bf",
                "merchant": "Streaming Merchant",
                "descriptor": "STREAMING MERCHANT*ONLINE",
                "category": "Streaming & Entertainment",
                "mcc": "4899",
                "country_code": "USA",
                "city": None,
                "region": None,
                "postal_code": None,
                "latitude": None,
                "longitude": None,
                "card_present_capable": False,
                "ecommerce_capable": True,
                "high_risk_flags": [],
                "is_international": False,
                "risk_score": 0,
            },
            {
                "merchant_id": "acbce33d-2eee-5473-9631-0882b0631098",
                "merchant_slug": "coffee_shop",
                "merchant_store_id": "8701f624-d5fb-5e11-a3fd-8a57c7b0bb7f",
                "merchant": "Coffee Shop",
                "descriptor": "COFFEE SHOP",
                "category": "Coffee",
                "mcc": "5814",
                "country_code": "USA",
                "city": "Mountain View",
                "region": "CA",
                "postal_code": "94043",
                "latitude": 37.4,
                "longitude": -122.1,
                "card_present_capable": True,
                "ecommerce_capable": False,
                "high_risk_flags": [],
                "is_international": False,
                "risk_score": 0,
            },
        ],
    )
    random_values = iter([0.5, 0.0])
    monkeypatch.setattr(main.random, "random", lambda: next(random_values, 0.5))
    monkeypatch.setattr(main.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(
        main.random, "choices", lambda population, weights=None, k=1: ["PENDING"]
    )

    auth_route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize"
    ).mock(
        return_value=httpx.Response(
            200, json={"action_code": "00", "auth_code": "123456", "status": "PENDING"}
        )
    )

    async with httpx.AsyncClient() as async_client:
        result = await main.simulate_swipe_event(
            async_client,
            {
                "card_token": "tok_ypro",
                "cardholder_name": "Ava Taylor",
                "persona": "YPRO",
                "mccs": ["4899", "5814"],
                "amount_min": 400,
                "amount_max": 3500,
                "available_credit_cents": 100000,
            },
        )

    assert result["authorized"] is True
    payload = json.loads(auth_route.calls[0].request.content.decode())
    assert UUID(payload["merchant_id"])
    assert UUID(payload["merchant_store_id"])
    assert payload["merchant_slug"] == "streaming_merchant"
    assert payload["merchant_category_code"] == "4899"
    assert payload["transaction_channel"] == "ECOMMERCE"
    assert payload["entry_mode"] == "ECOMMERCE"


@pytest.mark.asyncio
@respx.mock
async def test_simulate_pulse_success():
    original_plan_builder = main.build_randomized_pulse_plan
    original_randint = main.random.randint
    original_auto_paydown = main.auto_paydown_high_utilization_cards
    main.build_randomized_pulse_plan = lambda total_events, window_seconds=58: [
        0.0,
        0.0,
        0.0,
        0.0,
    ]
    main.random.randint = lambda a, b: (
        4 if (a, b) == (8, 12) else original_randint(a, b)
    )

    async def noop_auto_paydown(
        client, cards, trigger_utilization=0.65, target_utilization=0.35, **kwargs
    ):
        return []

    main.auto_paydown_high_utilization_cards = noop_auto_paydown

    # Mock Gateway Endpoints
    auth_route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize"
    ).mock(
        return_value=httpx.Response(
            200, json={"action_code": "00", "auth_code": "123456", "status": "PENDING"}
        )
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
        assert (
            request[0].headers.get("X-Card-Network-Token")
            == main.get_card_network_token()
        )
        payload = request[0].read().decode()
        parsed = json.loads(payload)
        assert "card_token" in parsed
        assert "amount_cents" in parsed
        assert "retrieval_reference_number" in parsed
        assert parsed["transaction_channel"] in {"CARD_PRESENT", "WALLET", "ECOMMERCE"}
        assert parsed["entry_mode"] in {
            "CHIP",
            "CONTACTLESS",
            "MAG_STRIPE",
            "ECOMMERCE",
        }
        assert parsed["merchant_country_code"] == "USA"


@pytest.mark.asyncio
@respx.mock
async def test_simulate_pulse_uses_runtime_ambient_profile(monkeypatch):
    client.post("/ambient/profile/reset")
    client.put(
        "/ambient/profile",
        json={
            "profile_name": "agent-quiet",
            "pulse_min_events": 2,
            "pulse_max_events": 2,
            "pulse_window_seconds": 9,
            "workflow_concurrency": 1,
            "fraud_pattern_enabled": False,
            "auto_paydown_max_accounts_per_pulse": 0,
        },
    )
    original_plan_builder = main.build_randomized_pulse_plan
    observed = {}

    def fake_plan(total_events, window_seconds=58):
        observed["total_events"] = total_events
        observed["window_seconds"] = window_seconds
        return [0.0, 0.0]

    async def noop_auto_paydown(*args, **kwargs):
        return []

    monkeypatch.setattr(main, "build_randomized_pulse_plan", fake_plan)
    monkeypatch.setattr(main, "auto_paydown_high_utilization_cards", noop_auto_paydown)

    auth_route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize"
    ).mock(
        return_value=httpx.Response(
            200, json={"action_code": "00", "auth_code": "123456", "status": "PENDING"}
        )
    )

    try:
        response = client.post("/simulate-pulse")
        assert response.status_code == 200
        body = response.json()
        assert body["scheduled_events"] == 2
        assert body["distribution_window_seconds"] == 9
        assert body["ambient_profile"]["profile_name"] == "agent-quiet"
        assert observed == {"total_events": 2, "window_seconds": 9}
        assert auth_route.call_count == 2
    finally:
        main.build_randomized_pulse_plan = original_plan_builder
        client.post("/ambient/profile/reset")


@pytest.mark.asyncio
@respx.mock
async def test_simulate_pulse_declined():
    original_plan_builder = main.build_randomized_pulse_plan
    original_randint = main.random.randint
    original_auto_paydown = main.auto_paydown_high_utilization_cards
    main.build_randomized_pulse_plan = lambda total_events, window_seconds=58: [
        0.0,
        0.0,
        0.0,
        0.0,
    ]
    main.random.randint = lambda a, b: (
        4 if (a, b) == (8, 12) else original_randint(a, b)
    )

    async def noop_auto_paydown(
        client, cards, trigger_utilization=0.65, target_utilization=0.35, **kwargs
    ):
        return []

    main.auto_paydown_high_utilization_cards = noop_auto_paydown

    # Mock Gateway declines swipes (action_code = 51)
    auth_route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "action_code": "51",
                "auth_code": "000000",
                "status": "DECLINED",
                "decline_reason": "INSUFFICIENT_FUNDS",
            },
        )
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
def test_vip_mexico_top_off_generates_varied_settled_basket():
    auth_route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "action_code": "00",
                "authorization_id": "8e7cf8ba-a9fc-44b3-80b3-f24d86bf4f98",
                "auth_code": "123456",
                "retrieval_reference_number": "VIPTOP000001",
                "status": "PENDING",
            },
        )
    )
    settle_route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/card-network/settle"
    ).mock(return_value=httpx.Response(200, json={"success": True, "status": "SETTLED"}))

    response = client.post(
        "/ensure-vip-mexico-leaders",
        json={
            "seed": 1841,
            "targets": [
                {
                    "customer_id": "vip-1",
                    "customer_name": "VIP Customer",
                    "card_token": "tok_vip_1",
                    "target_cents": 900000,
                    "top_off_cents": 250000,
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["customers_topped_off"] == 1
    assert response.json()["transactions_created"] == 4
    assert response.json()["total_added_cents"] == 250000
    assert auth_route.call_count == 4
    assert settle_route.call_count == 4
    payloads = [json.loads(call.request.content.decode()) for call in auth_route.calls]
    assert sum(payload["amount_cents"] for payload in payloads) == 250000
    assert {payload["merchant_country_code"] for payload in payloads} == {"MEX"}
    assert len({payload["merchant_name"] for payload in payloads}) == 4


@respx.mock
def test_simulate_surge_success():
    auth_route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize"
    ).mock(
        return_value=httpx.Response(
            200, json={"action_code": "00", "auth_code": "123456", "status": "PENDING"}
        )
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/settle").mock(
        return_value=httpx.Response(200, json={"status": "SETTLED"})
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/reverse").mock(
        return_value=httpx.Response(200, json={"status": "REVERSED"})
    )
    response = client.post("/simulate-surge", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["swipes_attempted"] == 50
    assert body["planned_event_count"] == 50
    assert body["scenario_id"].startswith("lakehouse_spend_velocity_surge-")
    assert (
        body["settlements_created"]
        + body["reversals_created"]
        + body["pending_holds_created"]
        == 50
    )
    assert body["validation_hints"]
    first_payload = json.loads(auth_route.calls[0].request.content.decode())
    assert first_payload["synthetic_scenario_id"] == body["scenario_id"]
    assert first_payload["synthetic_event_id"].startswith("surge-event-")


def test_simulate_surge_fails_without_spendable_cards():
    response = client.post(
        "/simulate-surge",
        json={
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
        },
    )

    assert response.status_code == 409
    assert "No spendable active cards" in response.json()["detail"]


@respx.mock
def test_generate_fails_without_active_cards_in_deployed_mode(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "data-generator")
    monkeypatch.setenv("CARD_NETWORK_SWITCH_TOKEN", "switch-secret-key-12345")
    monkeypatch.setattr(main, "PULSE_ADMISSION_REDIS_REQUIRED", False)
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
    monkeypatch.setattr(main, "PULSE_ADMISSION_REDIS_REQUIRED", False)
    respx.get(f"{BANKING_SERVICE_URL}/api/v1/credit-card/active-cards").mock(
        side_effect=httpx.ReadTimeout("timed out")
    )

    response = client.post("/generate")

    assert response.status_code == 200
    assert response.json()["status"] == "SKIPPED"
    assert "temporarily unavailable" in response.json()["message"]


def test_generate_skips_duplicate_cloudevent_without_generating(monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(main, "get_pulse_redis_client", lambda: fake_redis)

    async def fake_execute_simulation_pulse(event_id=None):
        return {
            "status": "SUCCESS",
            "message": "Simulation pulse completed.",
            "swipes_attempted": 1,
            "event_id": event_id,
        }

    monkeypatch.setattr(main, "execute_simulation_pulse", fake_execute_simulation_pulse)

    first = client.post("/generate", headers={"ce-id": "event-123"})
    second = client.post("/generate", headers={"ce-id": "event-123"})

    assert first.status_code == 200
    assert first.json()["status"] == "SUCCESS"
    assert first.json()["event_id"] == "event-123"
    assert second.status_code == 200
    assert second.json()["status"] == "SKIPPED_DUPLICATE_EVENT"
    assert second.json()["event_id"] == "event-123"


def test_generate_skips_active_distributed_pulse_without_generating(monkeypatch):
    fake_redis = FakeRedis()
    fake_redis.store["data-generator:pulse:active"] = "existing-token"
    monkeypatch.setattr(main, "get_pulse_redis_client", lambda: fake_redis)

    async def fail_if_called(event_id=None):
        raise AssertionError(f"pulse should not execute for {event_id}")

    monkeypatch.setattr(main, "execute_simulation_pulse", fail_if_called)

    response = client.post("/generate", headers={"ce-id": "event-active"})

    assert response.status_code == 200
    assert response.json()["status"] == "SKIPPED_ACTIVE_PULSE"
    assert response.json()["event_id"] == "event-active"


def test_generate_skips_when_admission_control_unavailable_in_deployed_mode(
    monkeypatch,
):
    monkeypatch.setenv("K_SERVICE", "data-generator")
    monkeypatch.setattr(main, "PULSE_ADMISSION_REDIS_REQUIRED", True)
    monkeypatch.setattr(main, "get_pulse_redis_client", lambda: None)

    async def fail_if_called(event_id=None):
        raise AssertionError(f"pulse should not execute for {event_id}")

    monkeypatch.setattr(main, "execute_simulation_pulse", fail_if_called)

    response = client.post("/generate", headers={"ce-id": "event-no-redis"})

    assert response.status_code == 200
    assert response.json()["status"] == "SKIPPED_ADMISSION_UNAVAILABLE"
    assert response.json()["event_id"] == "event-no-redis"


@respx.mock
def test_simulate_surge_returns_503_during_maintenance(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "data-generator")
    monkeypatch.setenv("CARD_NETWORK_SWITCH_TOKEN", "switch-secret-key-12345")
    respx.get(f"{BANKING_SERVICE_URL}/api/v1/credit-card/active-cards").mock(
        return_value=httpx.Response(503, json={"detail": {"status": "MAINTENANCE"}})
    )

    response = client.post(
        "/simulate-surge",
        json={},
        headers={"X-Card-Network-Token": main.get_card_network_token()},
    )

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


def test_build_fraud_pattern_payloads_labels_without_score_override():
    payloads = main.build_fraud_pattern_payloads(
        {"card_token": "tok_pattern", "available_credit_cents": 200000},
        "cnp_gift_card_burst",
    )

    assert len(payloads) == 3
    first = payloads[0]
    assert first["card_token"] == "tok_pattern"
    assert first["synthetic_fraud_label"] == "FRAUD_PATTERN"
    assert first["fraud_pattern_label"] == "cnp_gift_card_burst"
    assert first["transaction_channel"] == "ECOMMERCE"
    assert first["entry_mode"] == "ECOMMERCE"
    assert first["is_digital_goods"] is True
    assert "risk_score" not in first
    assert "is_fraud_simulation" not in first


def test_build_fraud_pattern_payloads_supports_impossible_travel_sequence():
    payloads = main.build_fraud_pattern_payloads(
        {"card_token": "tok_travel", "available_credit_cents": 200000},
        "impossible_travel_card_present",
    )

    assert len(payloads) == 2
    assert payloads[0]["merchant_city"] == "San Francisco"
    assert payloads[1]["merchant_city"] == "New York"
    assert all(payload["transaction_channel"] == "CARD_PRESENT" for payload in payloads)


@pytest.mark.asyncio
@respx.mock
async def test_auto_paydown_high_utilization_cards_calls_internal_endpoint():
    route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/credit-card/internal/auto-paydown"
    ).mock(
        return_value=httpx.Response(
            200, json={"status": "SUCCESS", "paid_amount_cents": 25000}
        )
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
    route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/credit-card/internal/auto-paydown"
    ).mock(
        return_value=httpx.Response(
            200, json={"status": "SUCCESS", "paid_amount_cents": 25000}
        )
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
    auth_route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize"
    ).mock(
        return_value=httpx.Response(
            200, json={"action_code": "00", "auth_code": "999999", "status": "PENDING"}
        )
    )

    response = client.post("/inject-anomaly", json={"card_token": "tok_visa_test"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ANOMALY_INJECTED"
    assert data["injected_swipes_count"] == 5
    assert data["card_token"] == "tok_visa_test"
    assert auth_route.call_count == 5


@pytest.mark.asyncio
@respx.mock
async def test_simulate_fraud_patterns_dispatches_labeled_payloads_without_overrides():
    auth_route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize"
    ).mock(
        return_value=httpx.Response(
            200, json={"action_code": "00", "auth_code": "999999", "status": "FLAGGED"}
        )
    )

    response = client.post(
        "/simulate-fraud-patterns",
        json={
            "card_token": "tok_visa_pattern",
            "pattern": "cnp_gift_card_burst",
            "count": 1,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "FRAUD_PATTERNS_SIMULATED"
    assert data["patterns_attempted"] == 1
    assert data["authorizations_created"] == 3
    assert auth_route.call_count == 3
    for call in auth_route.calls:
        payload = json.loads(call.request.read().decode())
        assert payload["synthetic_fraud_label"] == "FRAUD_PATTERN"
        assert payload["fraud_pattern_label"] == "cnp_gift_card_burst"
        assert payload["transaction_channel"] == "ECOMMERCE"
        assert "risk_score" not in payload
        assert "is_fraud_simulation" not in payload
