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

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_merchants_routes_are_available_on_all_supported_prefixes():
    payload = [
        {
            "merchant_id": "MID-TEST-001",
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
