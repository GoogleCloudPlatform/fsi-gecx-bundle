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
from typing import Dict, Any
from cachetools import TTLCache
from models.fdx import PersonalFinanceCategory

DEFAULT_TAXONOMY_MAP: Dict[str, Dict[str, str]] = {
    "5411": {"primary": "GENERAL_MERCHANDISE", "detailed": "GENERAL_MERCHANDISE_SUPERSTORES"},
    "5814": {"primary": "FOOD_AND_DRINK", "detailed": "FOOD_AND_DRINK_FAST_FOOD"},
    "5812": {"primary": "FOOD_AND_DRINK", "detailed": "FOOD_AND_DRINK_RESTAURANTS"},
    "4511": {"primary": "TRAVEL", "detailed": "TRAVEL_FLIGHTS"},
    "7011": {"primary": "TRAVEL", "detailed": "TRAVEL_LODGING"},
    "4814": {"primary": "GENERAL_SERVICES", "detailed": "GENERAL_SERVICES_TELECOMMUNICATIONS"},
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
        cat_data = mapping.get(str(mcc), {"primary": "GENERAL_MERCHANDISE", "detailed": "GENERAL_MERCHANDISE_OTHER"})
        return PersonalFinanceCategory(
            primary=cat_data["primary"],
            detailed=cat_data["detailed"],
            confidence_level="VERY_HIGH"
        )
