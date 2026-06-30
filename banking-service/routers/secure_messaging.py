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
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models.authentication import ValidatedToken
from models.secure_messaging import (
    SecureMessageCreateRequest,
    SecureMessageResponse,
    AdminReadRequest,
)
from utils.auth import get_current_user
from utils.database import get_db
from services.messaging import MessagingService, messaging, identity_repo  # noqa: F401

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/secure-messaging", tags=["secure-messaging"], dependencies=[Depends(get_current_user)])


def get_messaging_service(db: Session = Depends(get_db)) -> MessagingService:
    return MessagingService(db)


@router.post("", response_model=SecureMessageResponse)
async def create_message(
        request: SecureMessageCreateRequest,
        token: ValidatedToken = Depends(get_current_user),
        service: MessagingService = Depends(get_messaging_service)
):
    try:
        return service.create_message(request, token)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in create_message: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.get("", response_model=list[SecureMessageResponse])
async def get_messages(
        token: ValidatedToken = Depends(get_current_user),
        service: MessagingService = Depends(get_messaging_service)
):
    try:
        return service.get_messages(token)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in get_messages: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.delete("/messages/{message_id}", response_model=dict)
async def delete_message(
        message_id: str,
        token: ValidatedToken = Depends(get_current_user),
        service: MessagingService = Depends(get_messaging_service)
):
    try:
        return service.delete_message(message_id, token)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in delete_message: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.delete("/threads/{thread_id}", response_model=dict)
async def delete_thread(
        thread_id: str,
        token: ValidatedToken = Depends(get_current_user),
        service: MessagingService = Depends(get_messaging_service)
):
    try:
        return service.delete_thread(thread_id, token)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in delete_thread: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.post("/read", response_model=dict)
async def mark_messages_as_read(
        message_ids: list[str],
        token: ValidatedToken = Depends(get_current_user),
        service: MessagingService = Depends(get_messaging_service)
):
    try:
        return service.mark_messages_as_read(message_ids, token)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in mark_messages_as_read: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.post("/admin/read", response_model=dict)
async def mark_messages_as_agent_read(
        request: AdminReadRequest,
        token: ValidatedToken = Depends(get_current_user),
        service: MessagingService = Depends(get_messaging_service)
):
    try:
        return service.mark_messages_as_agent_read(request, token)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in mark_messages_as_agent_read: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.get("/admin/customer/{user_id}", response_model=list[SecureMessageResponse])
async def admin_get_messages_for_customer(
        user_id: str,
        token: ValidatedToken = Depends(get_current_user),
        service: MessagingService = Depends(get_messaging_service)
):
    try:
        return service.admin_get_messages_for_customer(user_id, token)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in admin_get_messages_for_customer: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.delete("/admin/messages/{message_id}", response_model=dict)
async def admin_delete_message(
        message_id: str,
        user_id: str,
        token: ValidatedToken = Depends(get_current_user),
        service: MessagingService = Depends(get_messaging_service)
):
    try:
        return service.admin_delete_message(message_id, user_id, token)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in admin_delete_message: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.delete("/admin/threads/{thread_id}", response_model=dict)
async def admin_delete_thread(
        thread_id: str,
        user_id: str,
        token: ValidatedToken = Depends(get_current_user),
        service: MessagingService = Depends(get_messaging_service)
):
    try:
        return service.admin_delete_thread(thread_id, user_id, token)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in admin_delete_thread: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")
