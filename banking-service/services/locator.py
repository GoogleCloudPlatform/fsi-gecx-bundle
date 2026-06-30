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
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from repositories import identity as identity_repo
from utils.gemini import geocode_address

logger = logging.getLogger(__name__)


class LocatorService:
    """Service layer encapsulating retail branch and ATM location retrieval."""

    def __init__(self, db: Session):
        self.db = db

    def _format_location_item(self, row: dict, include_distance: bool = True) -> Dict[str, Any]:
        dist_miles = row.get("distance_miles") if include_distance else None
        if dist_miles is None and include_distance and row.get("distance_meters") is not None:
            dist_miles = round(row["distance_meters"] * 0.000621371, 2)
        return {
            "id": row["id"],
            "type": row["type"],
            "name": row["name"],
            "address": row["address"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "hours": row.get("hours"),
            "phone_number": row.get("phone_number"),
            "distance_miles": dist_miles
        }

    async def get_locations(
        self,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        address: Optional[str] = None,
        loc_type: str = "ALL"
    ) -> List[Dict[str, Any]]:
        results = []
        if lat is not None and lng is not None:
            rows = identity_repo.find_nearest_locations(self.db, lat, lng, loc_type)
            for r in rows:
                results.append(self._format_location_item(r, include_distance=True))
        elif address:
            coords = await geocode_address(address)
            if coords:
                alat, alng = coords
                rows = identity_repo.find_nearest_locations(self.db, alat, alng, loc_type)
                for r in rows:
                    results.append(self._format_location_item(r, include_distance=True))
            else:
                rows = identity_repo.search_locations_by_text(self.db, address, loc_type)
                for r in rows:
                    results.append(self._format_location_item(r, include_distance=False))
        return results
