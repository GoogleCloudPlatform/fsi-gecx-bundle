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
from decimal import Decimal
from sqlalchemy.orm import Session
from models.merchant import MerchantMaster, MerchantStore

logger = logging.getLogger("banking_service.merchants")

RESOURCE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources")

KNOWN_STORE_GEO: Dict[str, Dict[str, Any]] = {
    "MOUNTAIN VIEW CA": {"city": "Mountain View", "region": "CA", "postal_code": "94043", "latitude": 37.3861, "longitude": -122.0839},
    "SAN FRANCISCO CA": {"city": "San Francisco", "region": "CA", "postal_code": "94103", "latitude": 37.7749, "longitude": -122.4194},
    "NEW YORK NY": {"city": "New York", "region": "NY", "postal_code": "10001", "latitude": 40.7128, "longitude": -74.0060},
    "CHICAGO IL": {"city": "Chicago", "region": "IL", "postal_code": "60601", "latitude": 41.8781, "longitude": -87.6298},
    "SEATTLE WA": {"city": "Seattle", "region": "WA", "postal_code": "98101", "latitude": 47.6062, "longitude": -122.3321},
    "DALLAS TX": {"city": "Dallas", "region": "TX", "postal_code": "75201", "latitude": 32.7767, "longitude": -96.7970},
    "LOS ANGELES CA": {"city": "Los Angeles", "region": "CA", "postal_code": "90012", "latitude": 34.0522, "longitude": -118.2437},
    "CANCUN MX": {"city": "Cancun", "region": "QR", "postal_code": "77500", "latitude": 21.1619, "longitude": -86.8515},
    "CDMX": {"city": "Mexico City", "region": "CMX", "postal_code": "06000", "latitude": 19.4326, "longitude": -99.1332},
    "MEXICO CITY": {"city": "Mexico City", "region": "CMX", "postal_code": "06000", "latitude": 19.4326, "longitude": -99.1332},
}

HIGH_RISK_FLAG_KEYWORDS: Dict[str, str] = {
    "GIFT": "GIFT_CARD",
    "RAZER": "DIGITAL_GOODS",
    "GAME": "GAMING",
    "CRYPTO": "CRYPTO_LIKE",
    "ELECTRONIC": "ELECTRONICS",
    "BEST BUY": "ELECTRONICS",
    "APPLE": "ELECTRONICS",
}


def _infer_store_geo(location_name: str, raw_descriptor: str, country_code: str) -> Dict[str, Any]:
    haystack = f"{location_name} {raw_descriptor}".upper()
    for marker, geo in KNOWN_STORE_GEO.items():
        if marker in haystack:
            return geo
    if country_code.upper() != "USA":
        return {"city": None, "region": None, "postal_code": None, "latitude": None, "longitude": None}
    return {"city": None, "region": None, "postal_code": None, "latitude": None, "longitude": None}


def _is_ecommerce_descriptor(raw_descriptor: str) -> bool:
    upper_desc = raw_descriptor.upper()
    return any(token in upper_desc for token in ["ONLINE", ".COM", "MKTPLACE", "STREAMING", "SUBSCRIPTION", "PRIME", "ORDER", "DIGITAL"])


def _infer_high_risk_flags(clean_name: str, raw_descriptor: str) -> list[str]:
    haystack = f"{clean_name} {raw_descriptor}".upper()
    return sorted({flag for keyword, flag in HIGH_RISK_FLAG_KEYWORDS.items() if keyword in haystack})


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


@dataclass
class MerchantDTO:
    """Pure Python DTO decoupled from SQLAlchemy ORM session state for robust in-memory caching."""
    id: Any
    merchant_id: str
    clean_name: str
    location_name: str
    raw_descriptor_pattern: str
    mcc: str
    category: str
    country_code: str
    city: Optional[str]
    region: Optional[str]
    postal_code: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    card_present_capable: bool
    ecommerce_capable: bool
    high_risk_flags: list[str]
    logo_url: Optional[str]
    merchant_domain: Optional[str]
    is_subscription: bool
    is_international: bool
    risk_score: int


class MerchantEnrichmentService:
    """
    State-of-the-art Master Merchant Database & Transaction Enrichment Engine (3NF Normalized Architecture).
    Provides microsecond in-memory TTL/regex caching, entity resolution, CDN logo link mapping,
    and algorithmic store variation generation for domestic and international fraud/travel simulations.
    """
    _cache_initialized: bool = False
    _merchants_by_id: Dict[str, MerchantDTO] = {}
    _stores_list: List[MerchantDTO] = []
    _domestic_merchants: List[MerchantDTO] = []
    _international_merchants: List[MerchantDTO] = []

    @staticmethod
    def _build_generic_merchant(
        mcc: str = "5311",
        country_code: str = "USA",
        is_international: bool = False,
    ) -> MerchantDTO:
        return MerchantDTO(
            id="generic-merchant",
            merchant_id=f"generic-{mcc.lower()}",
            clean_name="Generic Merchant",
            location_name="Generic Merchant",
            raw_descriptor_pattern="GENERIC MERCHANT",
            mcc=mcc,
            category="MERCHANDISE",
            country_code=country_code,
            city=None,
            region=None,
            postal_code=None,
            latitude=None,
            longitude=None,
            card_present_capable=not is_international,
            ecommerce_capable=False,
            high_risk_flags=[],
            logo_url=None,
            merchant_domain=None,
            is_subscription=False,
            is_international=is_international,
            risk_score=30 if is_international else 0,
        )

    @classmethod
    def invalidate_cache(cls) -> None:
        """Clears in-memory merchant catalog cache."""
        cls._cache_initialized = False
        cls._merchants_by_id.clear()
        cls._stores_list.clear()
        cls._domestic_merchants.clear()
        cls._international_merchants.clear()

    @classmethod
    def seed_merchant_catalog(cls, db: Session) -> int:
        """
        Seeds the Normalized Master Merchant Database (`merchants.merchant_master` and `merchants.merchant_stores`)
        from authoritative JSON resources if empty. Returns count of seeded parent brands.
        """
        if db.query(MerchantMaster).count() > 0:
            cls.load_cache_if_needed(db)
            return 0

        logger.info("Seeding Normalized Master Merchant Database (`merchants.merchant_master` and `stores`) from JSON...")
        catalog_path = os.path.join(RESOURCE_DIR, "data", "merchant_catalog.json")
        if not os.path.exists(catalog_path):
            logger.warning(f"Merchant catalog resource not found at {catalog_path}.")
            return 0

        with open(catalog_path, "r") as f:
            raw_data = json.load(f)

        seeded_count = 0
        for item in raw_data:
            stores = item.pop("stores", [])
            legacy_vars = item.pop("store_variations", [])
            mcc_val = item.pop("default_mcc", item.pop("mcc", "0000"))
            
            m = MerchantMaster(
                merchant_id=item["merchant_id"],
                clean_name=item["clean_name"],
                default_mcc=mcc_val,
                merchant_domain=item.get("merchant_domain"),
                logo_url=item.get("logo_url"),
                is_subscription=item.get("is_subscription", False)
            )
            db.add(m)
            db.flush()
            seeded_count += 1

            if stores:
                for s_dict in stores:
                    geo = _infer_store_geo(s_dict["location_name"], s_dict["raw_descriptor"], s_dict.get("country_code", "USA"))
                    ecommerce_capable = s_dict.get("ecommerce_capable", _is_ecommerce_descriptor(s_dict["raw_descriptor"]))
                    s = MerchantStore(
                        merchant_id=m.merchant_id,
                        location_name=s_dict["location_name"],
                        raw_descriptor=s_dict["raw_descriptor"],
                        country_code=s_dict.get("country_code", "USA"),
                        city=s_dict.get("city", geo["city"]),
                        region=s_dict.get("region", geo["region"]),
                        postal_code=s_dict.get("postal_code", geo["postal_code"]),
                        latitude=_decimal_or_none(s_dict.get("latitude", geo["latitude"])),
                        longitude=_decimal_or_none(s_dict.get("longitude", geo["longitude"])),
                        card_present_capable=s_dict.get("card_present_capable", not ecommerce_capable),
                        ecommerce_capable=ecommerce_capable,
                        high_risk_flags=",".join(s_dict.get("high_risk_flags", _infer_high_risk_flags(m.clean_name, s_dict["raw_descriptor"]))),
                        is_international=s_dict.get("is_international", False),
                        risk_score=s_dict.get("risk_score", 0)
                    )
                    db.add(s)
            elif legacy_vars:
                for idx, v in enumerate(legacy_vars):
                    geo = _infer_store_geo(f"{m.clean_name} #{idx+1}", v, "USA")
                    ecommerce_capable = _is_ecommerce_descriptor(v)
                    s = MerchantStore(
                        merchant_id=m.merchant_id,
                        location_name=f"{m.clean_name} #{idx+1}",
                        raw_descriptor=v,
                        country_code="USA",
                        city=geo["city"],
                        region=geo["region"],
                        postal_code=geo["postal_code"],
                        latitude=_decimal_or_none(geo["latitude"]),
                        longitude=_decimal_or_none(geo["longitude"]),
                        card_present_capable=not ecommerce_capable,
                        ecommerce_capable=ecommerce_capable,
                        high_risk_flags=",".join(_infer_high_risk_flags(m.clean_name, v)),
                        is_international=False,
                        risk_score=0
                    )
                    db.add(s)
            else:
                ecommerce_capable = _is_ecommerce_descriptor(m.clean_name)
                s = MerchantStore(
                    merchant_id=m.merchant_id,
                    location_name=m.clean_name,
                    raw_descriptor=m.clean_name.upper(),
                    country_code="USA",
                    card_present_capable=not ecommerce_capable,
                    ecommerce_capable=ecommerce_capable,
                    high_risk_flags=",".join(_infer_high_risk_flags(m.clean_name, m.clean_name)),
                    is_international=False,
                    risk_score=0
                )
                db.add(s)

        db.flush()
        logger.info(f"Seeded {seeded_count} parent brands and store locations into normalized `merchants` schema.")
        cls.invalidate_cache()
        return seeded_count

    @classmethod
    def load_cache_if_needed(cls, db: Session) -> None:
        """Loads normalized stores and parent brands into in-memory DTO dictionary for microsecond lookup performance."""
        if cls._cache_initialized and cls._stores_list:
            return

        all_stores = db.query(MerchantStore).all()
        if not all_stores:
            cls.seed_merchant_catalog(db)
            all_stores = db.query(MerchantStore).all()

        from services.taxonomy_service import TaxonomyService
        tax_map = TaxonomyService.get_taxonomy_map(db=db)

        detached_stores = []
        merchants_map = {}
        for s in all_stores:
            m = s.merchant
            mcc_val = m.default_mcc if m else "0000"
            cat_data = tax_map.get(str(mcc_val), {"primary": "MERCHANDISE", "detailed": "MERCHANDISE_OTHER"})
            inferred_geo = _infer_store_geo(s.location_name, s.raw_descriptor, s.country_code)
            inferred_ecommerce = _is_ecommerce_descriptor(s.raw_descriptor)
            inferred_flags = _infer_high_risk_flags(m.clean_name if m else s.location_name, s.raw_descriptor)
            
            dto = MerchantDTO(
                id=s.id,
                merchant_id=s.merchant_id,
                clean_name=m.clean_name if m else s.location_name,
                location_name=s.location_name,
                raw_descriptor_pattern=s.raw_descriptor,
                mcc=mcc_val,
                category=cat_data["primary"],
                country_code=s.country_code,
                city=s.city or inferred_geo["city"],
                region=s.region or inferred_geo["region"],
                postal_code=s.postal_code or inferred_geo["postal_code"],
                latitude=float(s.latitude) if s.latitude is not None else inferred_geo["latitude"],
                longitude=float(s.longitude) if s.longitude is not None else inferred_geo["longitude"],
                card_present_capable=s.card_present_capable and not inferred_ecommerce,
                ecommerce_capable=s.ecommerce_capable or inferred_ecommerce,
                high_risk_flags=[flag for flag in (s.high_risk_flags or "").split(",") if flag] or inferred_flags,
                logo_url=m.logo_url if m else None,
                merchant_domain=m.merchant_domain if m else None,
                is_subscription=m.is_subscription if m else False,
                is_international=s.is_international,
                risk_score=s.risk_score,
            )
            detached_stores.append(dto)
            if s.merchant_id not in merchants_map:
                merchants_map[s.merchant_id] = dto

        cls._stores_list = detached_stores
        cls._merchants_by_id = merchants_map
        cls._domestic_merchants = [dto for dto in detached_stores if not dto.is_international]
        cls._international_merchants = [dto for dto in detached_stores if dto.is_international]

        cls._cache_initialized = True
        logger.debug(f"Merchant cache warmed with {len(merchants_map)} parent brands and {len(detached_stores)} store locations.")

    @classmethod
    def enrich_transaction(cls, db: Session, raw_descriptor: str, mcc: Optional[str] = None, country: str = "USA") -> Dict[str, Any]:
        """
        Simulates a live Tier-1 transaction enrichment API lookup against normalized 3NF database.
        Performs substring matching against store descriptors and returns clean brand entity JSON.
        """
        cls.load_cache_if_needed(db)
        upper_desc = raw_descriptor.upper()

        matched_dto: Optional[MerchantDTO] = None
        for dto in cls._stores_list:
            pat = dto.raw_descriptor_pattern.replace("%", "").upper()
            if pat in upper_desc or dto.clean_name.upper() in upper_desc or dto.location_name.upper() in upper_desc:
                matched_dto = dto
                break

        if matched_dto:
            return {
                "merchant_id": str(matched_dto.merchant_id),
                "clean_name": matched_dto.clean_name,
                "merchant_domain": matched_dto.merchant_domain,
                "logo_url": matched_dto.logo_url,
                "mcc": matched_dto.mcc,
                "category": matched_dto.category,
                "country_code": matched_dto.country_code,
                "city": matched_dto.city,
                "region": matched_dto.region,
                "postal_code": matched_dto.postal_code,
                "latitude": matched_dto.latitude,
                "longitude": matched_dto.longitude,
                "card_present_capable": matched_dto.card_present_capable,
                "ecommerce_capable": matched_dto.ecommerce_capable,
                "high_risk_flags": list(matched_dto.high_risk_flags),
                "is_subscription": matched_dto.is_subscription,
                "is_international": matched_dto.is_international,
                "risk_score": matched_dto.risk_score,
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
            "city": None,
            "region": None,
            "postal_code": None,
            "latitude": None,
            "longitude": None,
            "card_present_capable": country == "USA",
            "ecommerce_capable": _is_ecommerce_descriptor(raw_descriptor),
            "high_risk_flags": _infer_high_risk_flags(raw_descriptor, raw_descriptor),
            "is_subscription": False,
            "is_international": country != "USA",
            "risk_score": 30 if country != "USA" else 0,
        }

    @classmethod
    def get_random_merchant(
        cls,
        db: Session,
        is_international: bool = False,
        category: Optional[str] = None,
        country: Optional[str] = None,
        home_metro: Optional[str] = None,
    ) -> Tuple[Union[MerchantMaster, MerchantDTO], str]:
        """
        Returns a random store location DTO and a realistic store variation string.
        Enforces geographic boundedness by filtering physical store locations to the customer's home metro area
        or consistent travel destination country, preventing random multi-city teleports on the same day.
        """
        cls.load_cache_if_needed(db)

        pool = cls._international_merchants if is_international else cls._domestic_merchants
        if country:
            pool = [dto for dto in pool if dto.country_code.upper() == country.upper()] or pool
        if category:
            pool = [dto for dto in pool if dto.category.lower() == category.lower()] or pool

        if not is_international and home_metro:
            # Keep online/digital/subscription billing stores OR physical stores matching the customer's home metro
            metro_pool = []
            for dto in pool:
                desc = dto.raw_descriptor_pattern.upper()
                is_digital = dto.is_subscription or any(k in desc for k in ["ONLINE", "STREAMING", "SUBSCRIPTION", "BILL", ".COM", "MKTPLACE", "PRIME", "ORDER", "/"])
                if is_digital:
                    metro_pool.append(dto)
                elif home_metro.upper() in desc or any(w in desc for w in home_metro.upper().split() if len(w) > 2):
                    metro_pool.append(dto)
            if metro_pool:
                pool = metro_pool

        if not pool:
            pool = cls._stores_list or list(cls._merchants_by_id.values())
        if not pool:
            generic_country = country.upper() if country else ("MEX" if is_international else "USA")
            generic_mcc = "7011" if is_international else "5311"
            generic = cls._build_generic_merchant(
                mcc=generic_mcc,
                country_code=generic_country,
                is_international=is_international,
            )
            return generic, generic.raw_descriptor_pattern

        dto = random.choice(pool)
        return dto, dto.raw_descriptor_pattern

    @classmethod
    def list_merchants(cls, db: Session, category: Optional[str] = None, country: Optional[str] = None, is_international: Optional[bool] = None) -> List[Union[MerchantMaster, MerchantDTO]]:
        """Returns filtered list of canonical parent brands from Normalized Master Merchant Database."""
        cls.load_cache_if_needed(db)
        results = list(cls._merchants_by_id.values())
        if category:
            results = [dto for dto in results if dto.category.lower() == category.lower()]
        if country:
            results = [dto for dto in results if dto.country_code.upper() == country.upper()]
        if is_international is not None:
            results = [dto for dto in results if dto.is_international == is_international]
        return results
