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

import logging
import threading
from typing import Dict, Optional
from cachetools import TTLCache
from models.fdx import PersonalFinanceCategory
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

DEFAULT_TAXONOMY_MAP: Dict[str, Dict[str, str]] = {
    "5311": {"primary": "MERCHANDISE", "detailed": "MERCHANDISE_DEPARTMENT_STORES"},
    "5411": {"primary": "GROCERY", "detailed": "GROCERY_SUPERMARKETS"},
    "5814": {"primary": "DINING", "detailed": "DINING_FAST_FOOD"},
    "5812": {"primary": "DINING", "detailed": "DINING_RESTAURANTS"},
    "4511": {"primary": "OTHER_TRAVEL", "detailed": "OTHER_TRAVEL_FLIGHTS"},
    "7011": {"primary": "OTHER_TRAVEL", "detailed": "OTHER_TRAVEL_LODGING"},
    "4121": {"primary": "OTHER_TRAVEL", "detailed": "OTHER_TRAVEL_TAXI"},
    "8011": {"primary": "HEALTHCARE", "detailed": "HEALTHCARE_MEDICAL"},
    "5541": {"primary": "GAS_AUTOMOTIVE", "detailed": "GAS_AUTOMOTIVE_FUEL"},
    "4814": {"primary": "OTHER", "detailed": "OTHER_TELECOMMUNICATIONS"},
    "4899": {"primary": "OTHER", "detailed": "OTHER_ENTERTAINMENT"},
    "FEE": {"primary": "FEES", "detailed": "FEES_LATE"},
}


class TaxonomyService:
    """Thread-safe cached taxonomy lookup service mapping MCCs to FDX PersonalFinanceCategory objects backed by ref_data."""
    _cache: TTLCache = TTLCache(maxsize=1, ttl=3600)
    _lock: threading.Lock = threading.Lock()

    @classmethod
    def invalidate_cache(cls) -> None:
        with cls._lock:
            cls._cache.clear()

    @classmethod
    def get_taxonomy_map(cls, db: Optional[Session] = None) -> Dict[str, Dict[str, str]]:
        if "map" in cls._cache:
            return cls._cache["map"]
        with cls._lock:
            if "map" in cls._cache:
                return cls._cache["map"]
            
            close_db = False
            if db is None:
                try:
                    from utils.database import SessionLocal
                    db = SessionLocal()
                    close_db = True
                except Exception as e:
                    logger.warning(f"Could not connect to DB for taxonomy lookup: {e}")
                    cls._cache["map"] = DEFAULT_TAXONOMY_MAP
                    return cls._cache["map"]
            
            try:
                from models.reference import MerchantCategoryCode
                records = db.query(MerchantCategoryCode).all()
                if records:
                    mapping = {
                        r.mcc: {"primary": r.primary_category, "detailed": r.detailed_category}
                        for r in records
                    }
                    cls._cache["map"] = mapping
                    return mapping
                else:
                    cls._cache["map"] = DEFAULT_TAXONOMY_MAP
                    return cls._cache["map"]
            except Exception as e:
                logger.warning(f"Could not load taxonomy from ref_data database: {e}. Falling back to default map.")
                return DEFAULT_TAXONOMY_MAP
            finally:
                if close_db and db:
                    db.close()

    @classmethod
    def get_category(cls, mcc: str, db: Optional[Session] = None) -> PersonalFinanceCategory:
        mapping = cls.get_taxonomy_map(db=db)
        cat_data = mapping.get(str(mcc), {"primary": "MERCHANDISE", "detailed": "MERCHANDISE_OTHER"})
        return PersonalFinanceCategory(
            primary=cat_data["primary"],
            detailed=cat_data["detailed"],
            confidence_level="VERY_HIGH"
        )
