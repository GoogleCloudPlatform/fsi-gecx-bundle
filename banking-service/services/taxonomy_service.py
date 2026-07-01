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

import threading
from typing import Dict
from cachetools import TTLCache
from models.fdx import PersonalFinanceCategory

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
    """Thread-safe cached taxonomy lookup service mapping MCCs to FDX PersonalFinanceCategory objects."""
    _cache: TTLCache = TTLCache(maxsize=1, ttl=3600)
    _lock: threading.Lock = threading.Lock()

    @classmethod
    def get_taxonomy_map(cls) -> Dict[str, Dict[str, str]]:
        if "map" in cls._cache:
            return cls._cache["map"]
        with cls._lock:
            if "map" in cls._cache:
                return cls._cache["map"]
            cls._cache["map"] = DEFAULT_TAXONOMY_MAP
            return cls._cache["map"]

    @classmethod
    def get_category(cls, mcc: str) -> PersonalFinanceCategory:
        mapping = cls.get_taxonomy_map()
        cat_data = mapping.get(str(mcc), {"primary": "MERCHANDISE", "detailed": "MERCHANDISE_OTHER"})
        return PersonalFinanceCategory(
            primary=cat_data["primary"],
            detailed=cat_data["detailed"],
            confidence_level="VERY_HIGH"
        )
