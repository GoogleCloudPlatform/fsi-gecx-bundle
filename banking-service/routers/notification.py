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
from firebase_admin import messaging

from models.authentication import ValidatedToken
from models.notification import RegisterDevice, SendNotificationRequest
from models.secure_messaging import SECURE_MESSAGES_TOPIC
from utils.auth import get_current_user
from utils.bq import save_device_token_in_bigquery, delete_device_token_from_bigquery, get_device_tokens_for_customer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notification", tags=["notification"], dependencies=[Depends(get_current_user)])


@router.post("/device", response_model=dict)
async def register_device(
        request: RegisterDevice,
        token: ValidatedToken = Depends(get_current_user)
):
    try:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        save_device_token_in_bigquery(user_id, request.device_token)

        # Subscribe the token to 'all' and SECURE_MESSAGES_TOPIC topics
        for topic in ["all", SECURE_MESSAGES_TOPIC]:
            try:
                response = messaging.subscribe_to_topic([request.device_token], topic)
                logger.info(
                    f"Subscribed device token to '{topic}' topic. "
                    f"Success count: {response.success_count}, failure count: {response.failure_count}"
                )
                if response.failure_count > 0:
                    for error in response.errors:
                        logger.error(f"FCM topic subscription error for topic '{topic}': {error.reason}")
            except Exception as fcm_exc:
                logger.error(f"Failed to subscribe device token to '{topic}' topic: {fcm_exc}", exc_info=True)

        return {
            "status": "success",
            "message": "Device token registered successfully",
            "user_id": user_id
        }
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in register_device: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.delete("/device", response_model=dict)
async def unregister_device(
        device_token: str,
        token: ValidatedToken = Depends(get_current_user)
):
    try:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        delete_device_token_from_bigquery(user_id, device_token)

        # Unsubscribe the token from 'all' and SECURE_MESSAGES_TOPIC topics
        for topic in ["all", SECURE_MESSAGES_TOPIC]:
            try:
                response = messaging.unsubscribe_from_topic([device_token], topic)
                logger.info(
                    f"Unsubscribed device token from '{topic}' topic. "
                    f"Success count: {response.success_count}, failure count: {response.failure_count}"
                )
                if response.failure_count > 0:
                    for error in response.errors:
                        logger.error(f"FCM topic unsubscription error for topic '{topic}': {error.reason}")
            except Exception as fcm_exc:
                logger.error(f"Failed to unsubscribe device token from '{topic}' topic: {fcm_exc}", exc_info=True)

        return {
            "status": "success",
            "message": "Device token unregistered successfully",
            "user_id": user_id
        }
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in unregister_device: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.post("/send", response_model=dict)
async def send_notification(
        request: SendNotificationRequest,
        token: ValidatedToken = Depends(get_current_user)
):
    try:
        # Require authentication to send notifications
        if not token.user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        if request.user_id:
            # Send to a specific customer's registered devices
            tokens = get_device_tokens_for_customer(request.user_id)
            if not tokens:
                logger.info(f"No registered devices found for customer {request.user_id}")
                return {
                    "status": "success",
                    "message": f"No registered devices found for customer {request.user_id}",
                    "recipient_type": "customer",
                    "sent_count": 0
                }

            # Send multicast message to all tokens
            message = messaging.MulticastMessage(
                data=request.data,
                tokens=tokens,
            )
            batch_response = messaging.send_each_for_multicast(message)

            logger.info(
                f"Multicast notification sent to customer {request.user_id}. "
                f"Success: {batch_response.success_count}, failure: {batch_response.failure_count}"
            )

            if batch_response.failure_count > 0:
                for idx, resp in enumerate(batch_response.responses):
                    if not resp.success:
                        logger.warning(f"Failed to send to token index {idx}: {resp.exception}")

            return {
                "status": "success",
                "message": "Notifications sent successfully",
                "recipient_type": "customer",
                "sent_count": batch_response.success_count,
                "failure_count": batch_response.failure_count
            }

        else:
            topic = request.topic or "all"
            message = messaging.Message(
                data=request.data,
                topic=topic,
            )
            message_id = messaging.send(message)
            logger.info(f"Topic notification sent to '{topic}'. Message ID: {message_id}")

            return {
                "status": "success",
                "message": "Notification sent successfully",
                "recipient_type": "topic",
                "topic": topic,
                "message_id": message_id
            }

    except Exception as e:
        logger.error(f"Error in send_notification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to send notification")
