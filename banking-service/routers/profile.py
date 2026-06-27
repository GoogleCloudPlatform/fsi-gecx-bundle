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
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from models.authentication import ValidatedToken
from models.profile import CustomerProfileCreateRequest, CustomerProfile, CustomerProfileUpdateRequest, CustomerShortProfile
from utils.auth import get_current_user
from utils.database import get_db
from services.profile import ProfileService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"], dependencies=[Depends(get_current_user)])


def get_profile_service(db: Session = Depends(get_db)) -> ProfileService:
    return ProfileService(db)


@router.get("", response_model=CustomerProfile)
async def get_profile(
        token: ValidatedToken = Depends(get_current_user),
        service: ProfileService = Depends(get_profile_service)
):
    try:
        return service.get_or_provision_profile(token)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in get_profile: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.post("", response_model=dict)
async def create_profile(
        request: CustomerProfileCreateRequest,
        token: ValidatedToken = Depends(get_current_user),
        service: ProfileService = Depends(get_profile_service)
):
    try:
        return service.create_profile(request, token)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in create_profile: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.put("", response_model=dict)
async def update_profile(
        request: CustomerProfileUpdateRequest,
        token: ValidatedToken = Depends(get_current_user),
        service: ProfileService = Depends(get_profile_service)
):
    try:
        return service.update_profile(request, token)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in update_profile: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.get("/customers", response_model=list[CustomerShortProfile])
async def get_all_customers(
        token: ValidatedToken = Depends(get_current_user),
        service: ProfileService = Depends(get_profile_service)
):
    try:
        return service.get_all_customers(token)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in get_all_customers: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")
