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

from enum import Enum
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.bq import find_nearest_locations, search_locations_by_text
from utils.gemini import geocode_address

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/locator", tags=["locator"])


class LocationType(str, Enum):
    ALL = "ALL"
    BRANCH = "BRANCH"
    ATM = "ATM"


class LocationItem(BaseModel):
    id: str
    type: LocationType
    name: str
    address: str
    latitude: float
    longitude: float
    hours: Optional[str] = None
    phone_number: Optional[str] = None
    distance_miles: Optional[float] = None


class LocatorResponse(BaseModel):
    results: List[LocationItem]


def _format_location_item(row: dict, include_distance: bool = True) -> LocationItem:
    dist_meters = row.get("distance_meters") if include_distance else None
    dist_miles = round(dist_meters * 0.000621371, 2) if dist_meters is not None else None
    return LocationItem(
        id=row["id"],
        type=row["type"],
        name=row["name"],
        address=row["address"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        hours=row["hours"],
        phone_number=row["phone_number"],
        distance_miles=dist_miles
    )


@router.get("", response_model=LocatorResponse)
async def get_locations(
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    address: Optional[str] = None,
    type: LocationType = LocationType.ALL
):
    try:
        results = []
        if lat is not None and lng is not None:
            # Query by proximity
            rows = find_nearest_locations(lat, lng, type.value)
            for r in rows:
                results.append(_format_location_item(r, include_distance=True))
        elif address:
            # Try geocoding address
            coords = await geocode_address(address)
            if coords:
                alat, alng = coords
                rows = find_nearest_locations(alat, alng, type.value)
                for r in rows:
                    results.append(_format_location_item(r, include_distance=True))
            else:
                # Fallback to text search
                rows = search_locations_by_text(address, type.value)
                for r in rows:
                    results.append(_format_location_item(r, include_distance=False))
        else:
            # No parameters, return an empty list
            pass
        return LocatorResponse(results=results)
    except Exception as e:
        logger.error(f"Error in locator endpoint: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve locations")
