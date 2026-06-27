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
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from models.application import ApplicationCreateRequest, ApplicationUpdateRequest
from models.authentication import ValidatedToken
from utils.auth import get_current_user
from utils.database import get_db
from services.origination import OriginationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/applications", tags=["application"], dependencies=[Depends(get_current_user)])


def get_origination_service(db: Session = Depends(get_db)) -> OriginationService:
    return OriginationService(db)


@router.post("")
async def create_application(
        request: ApplicationCreateRequest,
        user_data: ValidatedToken = Depends(get_current_user),
        service: OriginationService = Depends(get_origination_service)
):
    try:
        return service.create_application(request, user_data)
    except Exception as e:
        logger.error(f"Error in create_application: {e}")
        raise e


@router.patch("/{application_id}")
async def update_application(
        application_id: str,
        request: ApplicationUpdateRequest,
        user_data: ValidatedToken = Depends(get_current_user),
        service: OriginationService = Depends(get_origination_service)
):
    try:
        return service.update_application(application_id, request, user_data)
    except Exception as e:
        logger.error(f"Error in update_application: {e}")
        raise e
