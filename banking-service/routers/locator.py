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
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from utils.database import get_db
from services.locator import LocatorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/locator", tags=["locator"])


def get_locator_service(db: Session = Depends(get_db)) -> LocatorService:
    return LocatorService(db)


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


@router.get("", response_model=LocatorResponse)
async def get_locations(
    lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    lng: Optional[float] = Query(None, ge=-180.0, le=180.0),
    address: Optional[str] = Query(None, max_length=200),
    type: LocationType = LocationType.ALL,
    service: LocatorService = Depends(get_locator_service)
):
    try:
        results = await service.get_locations(lat=lat, lng=lng, address=address, loc_type=type.value)
        return LocatorResponse(results=results)
    except Exception as e:
        logger.error(f"Error in locator endpoint: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve locations")
