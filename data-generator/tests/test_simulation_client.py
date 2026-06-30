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

import asyncio
import pytest
from fastapi.testclient import TestClient
import respx
import httpx

from main import app, BANKING_SERVICE_URL, CARD_NETWORK_TOKEN

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "data-generator"}

@pytest.mark.asyncio
@respx.mock
async def test_simulate_pulse_success():
    # Mock Gateway Endpoints
    auth_route = respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize").mock(
        return_value=httpx.Response(200, json={"action_code": "00", "auth_code": "123456", "status": "PENDING"})
    )
    settle_route = respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/settle").mock(
        return_value=httpx.Response(200, json={"status": "SETTLED"})
    )
    reverse_route = respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/reverse").mock(
        return_value=httpx.Response(200, json={"status": "REVERSED"})
    )
    
    # Trigger simulation pulse
    response = client.post("/simulate-pulse")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert 3 <= data["swipes_attempted"] <= 5
    
    # Assert auth requests were sent with the correct headers
    assert auth_route.called
    for request in auth_route.calls:
        assert request[0].headers.get("X-Card-Network-Token") == CARD_NETWORK_TOKEN
        payload = request[0].read().decode()
        assert "card_token" in payload
        assert "amount_cents" in payload
        assert "retrieval_reference_number" in payload

@pytest.mark.asyncio
@respx.mock
async def test_simulate_pulse_declined():
    # Mock Gateway declines swipes (action_code = 51)
    auth_route = respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize").mock(
        return_value=httpx.Response(200, json={"action_code": "51", "auth_code": "000000", "status": "DECLINED", "decline_reason": "INSUFFICIENT_FUNDS"})
    )
    settle_route = respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/settle").mock(
        return_value=httpx.Response(200, json={"status": "SETTLED"})
    )
    
    response = client.post("/simulate-pulse")
    assert response.status_code == 200
    
    # Assert auth was called, but settle was NOT called since it was declined
    assert auth_route.called
    assert not settle_route.called

def test_simulate_surge_accepted():
    response = client.post("/simulate-surge", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
