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
import re
import uuid
from pathlib import Path


CATALOG_PATH = Path(__file__).resolve().parents[1] / "resources" / "data" / "merchant_catalog.json"
MCC_PATH = Path(__file__).resolve().parents[1] / "resources" / "data" / "merchant_category_codes.json"
MERCHANT_INTELLIGENCE_PATH = Path(__file__).resolve().parents[1] / "resources" / "data" / "merchant_intelligence.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
TRAVEL_CITIES = {"Vancouver", "Toronto", "London", "Paris", "Berlin", "Madrid", "Rome", "Venice"}


def _load_catalog() -> list[dict]:
    return json.loads(CATALOG_PATH.read_text())


def _merchant_by_slug(merchant_slug: str) -> dict:
    catalog = json.loads(CATALOG_PATH.read_text())
    return next(item for item in catalog if item["merchant_id"] == merchant_slug)


def _deterministic_merchant_uuid(merchant_slug: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"merchant-master:{merchant_slug}")


def _store_descriptors(item: dict) -> list[str]:
    stores = item.get("stores") or []
    if stores:
        return [store["raw_descriptor"] for store in stores]
    variations = item.get("store_variations") or []
    if variations:
        return variations
    return [item["clean_name"].upper()]


def test_international_travel_catalog_has_dining_depth_by_city():
    dining = _merchant_by_slug("global_travel_dining")
    stores_by_city = {
        city: [store for store in dining["stores"] if store.get("city") == city]
        for city in TRAVEL_CITIES
    }

    assert set(stores_by_city) == TRAVEL_CITIES
    assert all(len(stores) >= 3 for stores in stores_by_city.values())
    assert all(store["is_international"] for stores in stores_by_city.values() for store in stores)


def test_international_travel_catalog_has_air_and_everyday_merchants():
    everyday = _merchant_by_slug("global_travel_everyday")
    air = _merchant_by_slug("international_air_travel")
    hotels = _merchant_by_slug("international_hotels")

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


def test_demo_travel_mcc_categories_are_not_generic_other():
    mcc_rows = {row["mcc"]: row for row in json.loads(MCC_PATH.read_text())}

    assert mcc_rows["7011"]["primary_category"] == "TRAVEL"
    assert mcc_rows["7011"]["detailed_category"] == "LODGING"
    assert mcc_rows["7011"]["is_travel"] is True
    assert mcc_rows["7298"]["primary_category"] == "HEALTHCARE"
    assert mcc_rows["7298"]["detailed_category"] == "PERSONAL_CARE"


def test_catalog_mcc_taxonomy_uses_specific_categories_for_common_spend():
    mcc_rows = {row["mcc"]: row for row in json.loads(MCC_PATH.read_text())}

    expected = {
        "4121": ("TRAVEL", "GROUND_TRANSPORTATION"),
        "4215": ("SERVICES", "COURIER_DELIVERY"),
        "4814": ("TELECOM", "MOBILE_PHONE_SERVICE"),
        "4899": ("ENTERTAINMENT", "STREAMING_SUBSCRIPTION"),
        "5311": ("MERCHANDISE", "DEPARTMENT_STORE"),
        "5541": ("GAS_AUTOMOTIVE", "FUEL"),
        "5732": ("MERCHANDISE", "ELECTRONICS"),
        "5816": ("DIGITAL_GOODS", "DIGITAL_GOODS"),
        "5912": ("HEALTHCARE", "PHARMACY"),
        "7512": ("TRAVEL", "RENTAL_CAR"),
        "7997": ("FITNESS", "FITNESS_CLUB"),
        "8011": ("HEALTHCARE", "MEDICAL_SERVICES"),
    }

    for mcc, (primary, detailed) in expected.items():
        assert mcc_rows[mcc]["primary_category"] == primary
        assert mcc_rows[mcc]["detailed_category"] == detailed


def test_google_products_are_first_class_catalog_merchants():
    catalog = {item["merchant_id"]: item for item in _load_catalog()}
    intelligence = {item["name"]: item for item in json.loads(MERCHANT_INTELLIGENCE_PATH.read_text())}

    expected_catalog = {
        "google_play_store": "5817",
        "youtube_tv": "4899",
        "google_fi": "4814",
        "google_store": "5732",
    }
    expected_intelligence = {
        "GOOGLE PLAY": "5817",
        "YOUTUBE TV": "4899",
        "GOOGLE FI": "4814",
        "GOOGLE STORE": "5732",
    }

    for merchant_id, mcc in expected_catalog.items():
        assert catalog[merchant_id]["default_mcc"] == mcc
        assert catalog[merchant_id]["stores"]

    for merchant_name, mcc in expected_intelligence.items():
        assert mcc in intelligence[merchant_name]["mccs"]


def test_merchant_catalog_slugs_generate_unique_stable_uuid_relationships():
    catalog = _load_catalog()
    slugs = [item["merchant_id"] for item in catalog]
    merchant_ids = [_deterministic_merchant_uuid(slug) for slug in slugs]
    store_ids = [
        uuid.uuid5(uuid.NAMESPACE_DNS, f"merchant-store:{item['merchant_id']}:{descriptor}")
        for item in catalog
        for descriptor in _store_descriptors(item)
    ]

    assert len(slugs) == len(set(slugs))
    assert len(merchant_ids) == len(set(merchant_ids))
    assert len(store_ids) == len(set(store_ids))
    assert all(isinstance(merchant_id, uuid.UUID) for merchant_id in merchant_ids)


def test_merchant_catalog_default_mccs_are_covered_by_taxonomy_seed():
    catalog_mccs = {item["default_mcc"] for item in _load_catalog()}
    taxonomy = json.loads(MCC_PATH.read_text())
    taxonomy_mccs = {item["mcc"] for item in taxonomy}

    assert catalog_mccs
    assert catalog_mccs.issubset(taxonomy_mccs)


def test_enriched_mcc_taxonomy_has_stable_identity_and_metadata():
    taxonomy = json.loads(MCC_PATH.read_text())
    mccs = [item["mcc"] for item in taxonomy]

    assert len(taxonomy) >= 900
    assert len(mccs) == len(set(mccs))
    assert all(re.fullmatch(r"\d{4}", mcc) for mcc in mccs)
    assert all(uuid.uuid5(uuid.NAMESPACE_DNS, f"merchant-category-code:{mcc}") for mcc in mccs)

    sample = next(item for item in taxonomy if item["mcc"] == "5411")
    assert sample["primary_category"]
    assert sample["detailed_category"]
    assert isinstance(sample["risk_score"], int)
    assert isinstance(sample["metadata"], dict)
    assert "risk_flags" in sample["metadata"]


def test_simulator_mcc_literals_are_covered_by_taxonomy_seed():
    taxonomy = json.loads(MCC_PATH.read_text())
    taxonomy_mccs = {item["mcc"] for item in taxonomy}
    source_paths = [
        REPO_ROOT / "data-generator" / "main.py",
        REPO_ROOT / "data-generator" / "scenarios" / "templates.py",
        REPO_ROOT / "banking-service" / "services" / "simulation.py",
    ]
    emitted_mccs = set()
    for path in source_paths:
        for line in path.read_text().splitlines():
            if "mcc" not in line.lower():
                continue
            emitted_mccs.update(re.findall(r'"([0-9]{4})"', line))

    assert emitted_mccs
    assert emitted_mccs.issubset(taxonomy_mccs)


def test_merchant_intelligence_resource_has_covered_mccs_and_aliases():
    taxonomy_mccs = {item["mcc"] for item in json.loads(MCC_PATH.read_text())}
    intelligence = json.loads(MERCHANT_INTELLIGENCE_PATH.read_text())
    names = [item["name"] for item in intelligence]

    assert len(intelligence) >= 40
    assert len(names) == len(set(names))
    for item in intelligence:
        assert item["name"]
        assert item["aliases"]
        assert item["type"]
        assert isinstance(item["risk"], int)
        assert set(item["mccs"]).issubset(taxonomy_mccs)
