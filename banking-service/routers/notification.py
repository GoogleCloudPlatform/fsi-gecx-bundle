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
from models.notification import RegisterDevice, SendNotificationRequest
from utils.auth import get_current_user
from utils.database import get_db
from services.messaging import MessagingService, messaging, identity_repo  # noqa: F401

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notification", tags=["notification"], dependencies=[Depends(get_current_user)])


def get_messaging_service(db: Session = Depends(get_db)) -> MessagingService:
    return MessagingService(db)


@router.post("/device", response_model=dict)
async def register_device(
        request: RegisterDevice,
        token: ValidatedToken = Depends(get_current_user),
        service: MessagingService = Depends(get_messaging_service)
):
    try:
        return service.register_device(request, token)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in register_device: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.delete("/device", response_model=dict)
async def unregister_device(
        device_token: str,
        token: ValidatedToken = Depends(get_current_user),
        service: MessagingService = Depends(get_messaging_service)
):
    try:
        return service.unregister_device(device_token, token)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in unregister_device: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.post("/send", response_model=dict)
async def send_notification(
        request: SendNotificationRequest,
        token: ValidatedToken = Depends(get_current_user),
        service: MessagingService = Depends(get_messaging_service)
):
    try:
        return service.send_notification(request, token)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in send_notification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to send notification")
