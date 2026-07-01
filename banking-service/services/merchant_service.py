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

import os
import json
import random
import logging
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass
from sqlalchemy.orm import Session
from models.merchant import MerchantMaster, Merchant

logger = logging.getLogger("banking_service.merchants")

RESOURCE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources")


@dataclass
class MerchantDTO:
    """Pure Python DTO decoupled from SQLAlchemy ORM session state for robust in-memory caching."""
    id: Any
    merchant_id: str
    clean_name: str
    raw_descriptor_pattern: str
    mcc: str
    category: str
    country_code: str
    logo_url: Optional[str]
    merchant_domain: Optional[str]
    is_subscription: bool
    is_international: bool
    risk_score: int


class MerchantEnrichmentService:
    """
    State-of-the-art Master Merchant Database & Transaction Enrichment Engine.
    Provides microsecond in-memory TTL/regex caching, entity resolution, CDN logo link mapping,
    and algorithmic store variation generation for domestic and international fraud/travel simulations.
    """
    _cache_initialized: bool = False
    _merchants_by_id: Dict[str, MerchantDTO] = {}
    _domestic_merchants: List[MerchantDTO] = []
    _international_merchants: List[MerchantDTO] = []
    _store_variations_map: Dict[str, List[str]] = {}

    @classmethod
    def invalidate_cache(cls) -> None:
        """Clears in-memory merchant catalog cache."""
        cls._cache_initialized = False
        cls._merchants_by_id.clear()
        cls._domestic_merchants.clear()
        cls._international_merchants.clear()
        cls._store_variations_map.clear()

    @classmethod
    def seed_merchant_catalog(cls, db: Session) -> int:
        """
        Seeds the Master Merchant Database (`merchants.merchant_master`) from authoritative JSON resources
        if the catalog is empty. Returns the count of seeded merchant entities.
        """
        if db.query(MerchantMaster).count() > 0:
            cls.load_cache_if_needed(db)
            return 0

        logger.info("Seeding Master Merchant Database (`merchants.merchant_master`) from authoritative catalog...")
        catalog_path = os.path.join(RESOURCE_DIR, "merchant_catalog.json")
        if not os.path.exists(catalog_path):
            logger.warning(f"Merchant catalog resource not found at {catalog_path}.")
            return 0

        with open(catalog_path, "r") as f:
            raw_data = json.load(f)

        new_merchants = []
        for item in raw_data:
            variations = item.pop("store_variations", [])
            m = MerchantMaster(**item)
            new_merchants.append(m)
            cls._store_variations_map[item["merchant_id"]] = variations

        db.add_all(new_merchants)
        db.flush()
        logger.info(f"Seeded {len(new_merchants)} Master Merchant entities into `ref_data.merchant_master`.")
        cls.invalidate_cache()
        return len(new_merchants)

    @classmethod
    def load_cache_if_needed(cls, db: Session) -> None:
        """Loads merchant entities into in-memory dictionary for microsecond lookup performance."""
        if cls._cache_initialized and cls._merchants_by_id:
            return

        all_merchants = db.query(MerchantMaster).all()
        if not all_merchants:
            cls.seed_merchant_catalog(db)
            all_merchants = db.query(MerchantMaster).all()

        detached_merchants = [
            MerchantDTO(
                id=m.id,
                merchant_id=m.merchant_id,
                clean_name=m.clean_name,
                raw_descriptor_pattern=m.raw_descriptor_pattern,
                mcc=m.mcc,
                category=m.category,
                country_code=m.country_code,
                logo_url=m.logo_url,
                merchant_domain=m.merchant_domain,
                is_subscription=m.is_subscription,
                is_international=m.is_international,
                risk_score=m.risk_score,
            )
            for m in all_merchants
        ]

        cls._merchants_by_id = {m.merchant_id: m for m in detached_merchants}
        cls._domestic_merchants = [m for m in detached_merchants if not m.is_international]
        cls._international_merchants = [m for m in detached_merchants if m.is_international]

        # Load store variations from file if map is empty after DB load
        if not cls._store_variations_map:
            catalog_path = os.path.join(RESOURCE_DIR, "merchant_catalog.json")
            if os.path.exists(catalog_path):
                try:
                    with open(catalog_path, "r") as f:
                        raw_data = json.load(f)
                    for item in raw_data:
                        cls._store_variations_map[item["merchant_id"]] = item.get("store_variations", [item["clean_name"]])
                except Exception as e:
                    logger.debug(f"Could not reload store variations map: {e}")

        cls._cache_initialized = True
        logger.debug(f"Merchant cache warmed with {len(all_merchants)} entities ({len(cls._domestic_merchants)} domestic, {len(cls._international_merchants)} international).")

    @classmethod
    def enrich_transaction(cls, db: Session, raw_descriptor: str, mcc: Optional[str] = None, country: str = "USA") -> Dict[str, Any]:
        """
        Simulates a live Tier-1 transaction enrichment API lookup.
        Performs regex/substring matching against in-memory merchant catalog to return clean brand entity JSON,
        CDN logo URL, industry MCC, and international fraud flags.
        """
        cls.load_cache_if_needed(db)
        upper_desc = raw_descriptor.upper()

        matched_merchant: Optional[Merchant] = None
        for m in cls._merchants_by_id.values():
            pat = m.raw_descriptor_pattern.replace("%", "").upper()
            if pat in upper_desc or m.clean_name.upper() in upper_desc:
                matched_merchant = m
                break

        if matched_merchant:
            return {
                "merchant_id": str(matched_merchant.merchant_id),
                "clean_name": matched_merchant.clean_name,
                "merchant_domain": matched_merchant.merchant_domain,
                "logo_url": matched_merchant.logo_url,
                "mcc": matched_merchant.mcc,
                "category": matched_merchant.category,
                "country_code": matched_merchant.country_code,
                "is_subscription": matched_merchant.is_subscription,
                "is_international": matched_merchant.is_international,
                "risk_score": matched_merchant.risk_score,
            }

        # Fallback for unrecognized local merchants
        fallback_mcc = mcc or "0000"
        return {
            "merchant_id": f"MID-GENERIC-{fallback_mcc}",
            "clean_name": raw_descriptor.strip() or "Unrecognized Merchant",
            "merchant_domain": None,
            "logo_url": None,
            "mcc": fallback_mcc,
            "category": "General Merchandise",
            "country_code": country,
            "is_subscription": False,
            "is_international": country != "USA",
            "risk_score": 30 if country != "USA" else 0,
        }

    @classmethod
    def get_random_merchant(cls, db: Session, is_international: bool = False, category: Optional[str] = None) -> Tuple[Union[MerchantMaster, MerchantDTO], str]:
        """
        Returns a random merchant entity and a realistic store variation string.
        Used by algorithmic seeding to generate rich domestic vs. international anomaly distributions.
        """
        cls.load_cache_if_needed(db)

        pool = cls._international_merchants if is_international else cls._domestic_merchants
        if category:
            pool = [m for m in pool if m.category.lower() == category.lower()] or pool
        if not pool:
            pool = list(cls._merchants_by_id.values())

        merchant = random.choice(pool)
        variations = cls._store_variations_map.get(merchant.merchant_id, [merchant.clean_name])
        store_string = random.choice(variations)
        return merchant, store_string

    @classmethod
    def list_merchants(cls, db: Session, category: Optional[str] = None, country: Optional[str] = None, is_international: Optional[bool] = None) -> List[Union[MerchantMaster, MerchantDTO]]:
        """Returns filtered list of merchants from Master Merchant Database."""
        cls.load_cache_if_needed(db)
        results = list(cls._merchants_by_id.values())
        if category:
            results = [m for m in results if m.category.lower() == category.lower()]
        if country:
            results = [m for m in results if m.country_code.upper() == country.upper()]
        if is_international is not None:
            results = [m for m in results if m.is_international == is_international]
        return results
