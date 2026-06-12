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

import datetime
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from firebase_admin import messaging

from models.authentication import ValidatedToken
from models.secure_messaging import (
    SecureMessageCreateRequest,
    SecureMessageResponse,
    AdminReadRequest,
    SUPPORT_MESSAGE_TYPE,
    USER_MESSAGE_TYPE,
    SECURE_MESSAGES_TOPIC,
    SENDER_TYPE_USER
)
from utils.auth import get_current_user
from utils.bq import (
    create_message_in_bigquery,
    get_messages_for_customer,
    soft_delete_message_in_bigquery,
    soft_delete_thread_in_bigquery,
    get_user_id_for_thread,
    get_device_tokens_for_customer,
    mark_messages_as_user_read_in_bigquery,
    mark_messages_as_agent_read_in_bigquery
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/secure-messaging", tags=["secure-messaging"], dependencies=[Depends(get_current_user)])


@router.post("", response_model=SecureMessageResponse)
async def create_message(
        request: SecureMessageCreateRequest,
        token: ValidatedToken = Depends(get_current_user)
):
    try:
        sender = request.sender or SENDER_TYPE_USER

        if sender == SENDER_TYPE_USER:
            user_id = token.user_id
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid user ID in token")
        else:
            user_id = request.user_id
            if not user_id and request.thread_id:
                user_id = get_user_id_for_thread(request.thread_id)
            if not user_id:
                raise HTTPException(status_code=400, detail="user_id is required when sender is not 'user'")

        message_id = str(uuid.uuid4())
        thread_id = request.thread_id or str(uuid.uuid4())
        created_at = datetime.datetime.now(datetime.timezone.utc)

        create_message_in_bigquery(
            message_id=message_id,
            user_id=user_id,
            sender=sender,
            category=request.category,
            message=request.message,
            created_at=created_at,
            thread_id=thread_id
        )

        # 1. Trigger personal push notification to the customer if sent by bank
        if sender != SENDER_TYPE_USER:
            try:
                tokens = get_device_tokens_for_customer(user_id)
                if tokens:
                    msg_body = request.message
                    if len(msg_body) > 100:
                        msg_body = msg_body[:97] + "..."
                    message = messaging.MulticastMessage(
                        data={
                            "title": f"New Support Message ({request.category})",
                            "body": msg_body,
                            "thread_id": str(thread_id),
                            "type": SUPPORT_MESSAGE_TYPE,
                            "category": str(request.category),
                            "user_id": str(user_id)
                        },
                        tokens=tokens,
                    )
                    batch_response = messaging.send_each_for_multicast(message)
                    logger.info(
                        f"Multicast notification sent to customer {user_id}. "
                        f"Success: {batch_response.success_count}, failure: {batch_response.failure_count}"
                    )
            except Exception as fcm_err:
                logger.error(f"Failed to send multicast Firebase notification: {fcm_err}", exc_info=True)

        # 2. Trigger topic notification to 'all_secure_messages' for all support agents
        try:
            msg_body = request.message
            if len(msg_body) > 100:
                msg_body = msg_body[:97] + "..."

            notif_type = USER_MESSAGE_TYPE if sender == SENDER_TYPE_USER else SUPPORT_MESSAGE_TYPE

            # Send as data-only (silent) message to prevent browser from showing default visual popups
            message = messaging.Message(
                data={
                    "user_id": str(user_id),
                    "type": notif_type,
                    "thread_id": str(thread_id),
                    "category": str(request.category)
                },
                topic=SECURE_MESSAGES_TOPIC
            )
            response = messaging.send(message)
            logger.info(
                f"FCM Notification sent to topic '{SECURE_MESSAGES_TOPIC}' (sender={sender}). "
                f"Message ID: {response}"
            )
        except Exception as fcm_err:
            logger.error(f"Failed to send Firebase notification to {SECURE_MESSAGES_TOPIC} topic: {fcm_err}",
                         exc_info=True)

        return SecureMessageResponse(
            message_id=message_id,
            user_id=user_id,
            sender=sender,
            category=request.category,
            message=request.message,
            created_at=created_at,
            deleted=False,
            thread_id=thread_id,
            is_user_read=True if sender == SENDER_TYPE_USER else False,
            is_agent_read=False if sender == SENDER_TYPE_USER else True
        )
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in create_message: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.get("", response_model=list[SecureMessageResponse])
async def get_messages(
        token: ValidatedToken = Depends(get_current_user)
):
    try:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        messages = get_messages_for_customer(user_id)
        return messages
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in get_messages: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.delete("/messages/{message_id}", response_model=dict)
async def delete_message(
        message_id: str,
        token: ValidatedToken = Depends(get_current_user)
):
    try:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        soft_delete_message_in_bigquery(message_id, user_id)
        return {"status": "success", "message": f"Message {message_id} soft deleted"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in delete_message: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.delete("/threads/{thread_id}", response_model=dict)
async def delete_thread(
        thread_id: str,
        token: ValidatedToken = Depends(get_current_user)
):
    try:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        soft_delete_thread_in_bigquery(thread_id, user_id)
        return {"status": "success", "message": f"Thread {thread_id} soft deleted"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in delete_thread: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.post("/read", response_model=dict)
async def mark_messages_as_read(
        message_ids: list[str],
        token: ValidatedToken = Depends(get_current_user)
):
    try:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        mark_messages_as_user_read_in_bigquery(message_ids, user_id)
        return {"status": "success", "message": f"{len(message_ids)} messages marked as read"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in mark_messages_as_read: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.post("/admin/read", response_model=dict)
async def mark_messages_as_agent_read(
        request: AdminReadRequest,
        token: ValidatedToken = Depends(get_current_user)
):
    try:
        if not token.user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        mark_messages_as_agent_read_in_bigquery(request.message_ids, request.user_id)
        return {"status": "success", "message": f"{len(request.message_ids)} messages marked as agent read"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in mark_messages_as_agent_read: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.get("/admin/customer/{user_id}", response_model=list[SecureMessageResponse])
async def admin_get_messages_for_customer(
        user_id: str,
        token: ValidatedToken = Depends(get_current_user)
):
    try:
        if not token.user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        messages = get_messages_for_customer(user_id)
        return messages
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in admin_get_messages_for_customer: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.delete("/admin/messages/{message_id}", response_model=dict)
async def admin_delete_message(
        message_id: str,
        user_id: str,
        token: ValidatedToken = Depends(get_current_user)
):
    try:
        if not token.user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        soft_delete_message_in_bigquery(message_id, user_id)
        return {"status": "success", "message": f"Message {message_id} soft deleted by admin"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in admin_delete_message: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.delete("/admin/threads/{thread_id}", response_model=dict)
async def admin_delete_thread(
        thread_id: str,
        user_id: str,
        token: ValidatedToken = Depends(get_current_user)
):
    try:
        if not token.user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        soft_delete_thread_in_bigquery(thread_id, user_id)
        return {"status": "success", "message": f"Thread {thread_id} soft deleted by admin"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in admin_delete_thread: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")
