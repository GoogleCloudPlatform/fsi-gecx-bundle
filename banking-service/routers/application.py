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

from models.application import ApplicationCreateRequest, ApplicationUpdateRequest
from models.authentication import ValidatedToken
from utils.auth import get_current_user
from utils.bq import log_application_to_bigquery, update_application_in_bigquery

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/applications", tags=["application"], dependencies=[Depends(get_current_user)])


@router.post("")
async def create_application(
        request: ApplicationCreateRequest,
        user_data: ValidatedToken = Depends(get_current_user)
):
    try:
        application_id = log_application_to_bigquery(
            user_data.user_id,
            request.product_category,
            request.product_type,
            request.requested_amount
        )
    except Exception as e:
        logger.error(f"Error in create_application: {e}")
        raise e

    return {
        "message": "Application created successfully",
        "application_id": application_id
    }


@router.patch("/{application_id}")
async def update_application(
        application_id: str,
        request: ApplicationUpdateRequest,
        user_data: ValidatedToken = Depends(get_current_user)
):
    try:
        update_application_in_bigquery(
            application_id=application_id,
            user_id=user_data.user_id,
            requested_amount=request.requested_amount,
            application_status=request.application_status
        )
    except Exception as e:
        logger.error(f"Error in update_application: {e}")
        raise e

    return {
        "message": "Application updated successfully",
        "application_id": application_id
    }

