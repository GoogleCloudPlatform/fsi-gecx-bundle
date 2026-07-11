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

import json
from pathlib import Path


CATALOG_PATH = Path(__file__).resolve().parents[1] / "resources" / "data" / "merchant_catalog.json"
TRAVEL_CITIES = {"Vancouver", "Toronto", "London", "Paris", "Berlin", "Madrid", "Rome", "Venice"}


def _merchant_by_id(merchant_id: str) -> dict:
    catalog = json.loads(CATALOG_PATH.read_text())
    return next(item for item in catalog if item["merchant_id"] == merchant_id)


def test_international_travel_catalog_has_dining_depth_by_city():
    dining = _merchant_by_id("global_travel_dining")
    stores_by_city = {
        city: [store for store in dining["stores"] if store.get("city") == city]
        for city in TRAVEL_CITIES
    }

    assert set(stores_by_city) == TRAVEL_CITIES
    assert all(len(stores) >= 3 for stores in stores_by_city.values())
    assert all(store["is_international"] for stores in stores_by_city.values() for store in stores)


def test_international_travel_catalog_has_air_and_everyday_merchants():
    everyday = _merchant_by_id("global_travel_everyday")
    air = _merchant_by_id("international_air_travel")
    hotels = _merchant_by_id("international_hotels")

    everyday_cities = {store.get("city") for store in everyday["stores"]}
    air_cities = {store.get("city") for store in air["stores"]}
    hotel_cities = {store.get("city") for store in hotels["stores"]}
    air_mccs = {air["default_mcc"]}
    hotel_mccs = {hotels["default_mcc"]}

    assert TRAVEL_CITIES.issubset(everyday_cities)
    assert TRAVEL_CITIES.issubset(air_cities)
    assert TRAVEL_CITIES.issubset(hotel_cities)
    assert air_mccs == {"4511"}
    assert hotel_mccs == {"7011"}
