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

from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_merchants_routes_are_available_on_all_supported_prefixes():
    merchant_id = str(uuid4())
    merchant_store_id = str(uuid4())
    payload = [
        {
            "merchant_id": merchant_id,
            "merchant_slug": "test_merchant",
            "merchant_store_id": merchant_store_id,
            "clean_name": "Test Merchant",
            "raw_descriptor_pattern": "TEST MERCHANT%",
            "mcc": "5311",
            "category": "Retail",
            "country_code": "USA",
            "city": "Mountain View",
            "region": "CA",
            "postal_code": "94043",
            "latitude": 37.3861,
            "longitude": -122.0839,
            "card_present_capable": True,
            "ecommerce_capable": False,
            "high_risk_flags": [],
            "logo_url": None,
            "merchant_domain": None,
            "is_subscription": False,
            "is_international": False,
            "risk_score": 0,
        }
    ]

    with patch("routers.merchants.MerchantEnrichmentService.list_merchants", return_value=payload):
        for path in ("/api/v1/merchants", "/v1/merchants", "/merchants"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.json() == payload


def test_merchant_detail_routes_split_uuid_and_slug_lookup():
    merchant_id = str(uuid4())
    merchant_store_id = str(uuid4())
    payload = {
        "merchant_id": merchant_id,
        "merchant_slug": "test_merchant",
        "merchant_store_id": merchant_store_id,
        "clean_name": "Test Merchant",
        "raw_descriptor_pattern": "TEST MERCHANT%",
        "mcc": "5311",
        "category": "Retail",
        "country_code": "USA",
        "city": "Mountain View",
        "region": "CA",
        "postal_code": "94043",
        "latitude": 37.3861,
        "longitude": -122.0839,
        "card_present_capable": True,
        "ecommerce_capable": False,
        "high_risk_flags": [],
        "logo_url": None,
        "merchant_domain": None,
        "is_subscription": False,
        "is_international": False,
        "risk_score": 0,
    }

    with (
        patch("routers.merchants.MerchantEnrichmentService.get_by_id", return_value=payload) as get_by_id,
        patch("routers.merchants.MerchantEnrichmentService.get_by_slug", return_value=payload) as get_by_slug,
    ):
        by_id_response = client.get(f"/api/v1/merchants/{merchant_id}")
        by_slug_response = client.get("/api/v1/merchants/by-slug/test_merchant")

    assert by_id_response.status_code == 200
    assert by_id_response.json() == payload
    assert by_slug_response.status_code == 200
    assert by_slug_response.json() == payload
    get_by_id.assert_called_once()
    get_by_slug.assert_called_once()
