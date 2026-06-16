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
from httpx import AsyncClient, ASGITransport

from main import app

@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_locator_by_coordinates(async_client, monkeypatch):
    mock_locations = [
        {
            "id": "loc-1",
            "type": "BRANCH",
            "name": "Main Branch",
            "address": "123 Main St, New York, NY 10001",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "hours": "Mon-Fri 9am-5pm",
            "phone_number": "212-555-0199",
            "distance_meters": 1609.34,  # Exactly 1 mile
        }
    ]

    monkeypatch.setattr(
        "routers.locator.find_nearest_locations",
        lambda lat, lng, location_type: mock_locations
    )

    response = await async_client.get("/locator?lat=40.7128&lng=-74.0060&type=ALL")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert len(data["results"]) == 1
    assert data["results"][0]["id"] == "loc-1"
    assert data["results"][0]["distance_miles"] == 1.0  # converted from 1609.34 meters


@pytest.mark.asyncio
async def test_locator_by_address_geocoded(async_client, monkeypatch):
    mock_locations = [
        {
            "id": "loc-2",
            "type": "ATM",
            "name": "Times Square ATM",
            "address": "701 7th Ave, New York, NY 10036",
            "latitude": 40.7580,
            "longitude": -73.9855,
            "hours": "24/7",
            "phone_number": None,
            "distance_meters": 804.67,  # 0.5 miles
        }
    ]

    # Mock geocode_address to return coordinates
    async def mock_geocode(address):
        return 40.7580, -73.9855

    monkeypatch.setattr("routers.locator.geocode_address", mock_geocode)
    monkeypatch.setattr(
        "routers.locator.find_nearest_locations",
        lambda lat, lng, location_type: mock_locations
    )

    response = await async_client.get("/locator?address=Times%20Square&type=ATM")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert len(data["results"]) == 1
    assert data["results"][0]["id"] == "loc-2"
    assert data["results"][0]["distance_miles"] == 0.5


@pytest.mark.asyncio
async def test_locator_by_address_fallback(async_client, monkeypatch):
    mock_locations = [
        {
            "id": "loc-3",
            "type": "BRANCH",
            "name": "San Francisco Downtown",
            "address": "456 Market St, San Francisco, CA 94105",
            "latitude": 37.7894,
            "longitude": -122.4014,
            "hours": "Mon-Fri 9am-4pm",
            "phone_number": "415-555-0188",
            "distance_meters": None,
        }
    ]

    # Mock geocode_address to fail
    async def mock_geocode(address):
        return None

    monkeypatch.setattr("routers.locator.geocode_address", mock_geocode)
    monkeypatch.setattr(
        "routers.locator.search_locations_by_text",
        lambda text, location_type: mock_locations
    )

    response = await async_client.get("/locator?address=Market%20St&type=BRANCH")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert len(data["results"]) == 1
    assert data["results"][0]["id"] == "loc-3"
    assert data["results"][0]["distance_miles"] is None
