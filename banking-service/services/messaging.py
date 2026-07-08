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
from typing import Dict, Any, List
from fastapi import HTTPException
from firebase_admin import messaging
from sqlalchemy.orm import Session

from models.authentication import ValidatedToken
from models.notification import RegisterDevice, SendNotificationRequest
from models.secure_messaging import (
    SecureMessageCreateRequest,
    SecureMessageResponse,
    AdminReadRequest,
    SUPPORT_MESSAGE_TYPE,
    USER_MESSAGE_TYPE,
    SECURE_MESSAGES_TOPIC,
    SENDER_TYPE_USER
)
from repositories import identity as identity_repo

logger = logging.getLogger(__name__)


class MessagingService:
    """Service layer encapsulating push notifications and secure customer messaging."""

    def __init__(self, db: Session):
        self.db = db

    def register_device(self, request: RegisterDevice, token: ValidatedToken) -> Dict[str, Any]:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        identity_repo.save_device_token(self.db, user_id, request.device_token)

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

    def unregister_device(self, device_token: str, token: ValidatedToken) -> Dict[str, Any]:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        identity_repo.delete_device_token(self.db, user_id, device_token)

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

    def send_notification(self, request: SendNotificationRequest, token: ValidatedToken) -> Dict[str, Any]:
        if not token.user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        if request.user_id:
            tokens = identity_repo.get_device_tokens_for_customer(self.db, request.user_id)
            if not tokens:
                logger.info(f"No registered devices found for customer {request.user_id}")
                return {
                    "status": "success",
                    "message": f"No registered devices found for customer {request.user_id}",
                    "recipient_type": "customer",
                    "sent_count": 0
                }

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

    def create_message(self, request: SecureMessageCreateRequest, token: ValidatedToken) -> SecureMessageResponse:
        sender = request.sender or SENDER_TYPE_USER

        if sender == SENDER_TYPE_USER:
            user_id = token.user_id
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid user ID in token")
        else:
            user_id = request.user_id
            if not user_id and request.thread_id:
                user_id = identity_repo.get_user_id_for_thread(self.db, request.thread_id)
            if not user_id:
                raise HTTPException(status_code=400, detail="user_id is required when sender is not 'user'")

        message_id = str(uuid.uuid4())
        thread_id = request.thread_id or str(uuid.uuid4())
        created_at = datetime.datetime.now(datetime.timezone.utc)

        identity_repo.create_message(
            db=self.db,
            auth_provider_uid=user_id,
            message_id=message_id,
            sender=sender,
            message=request.message,
            category=request.category,
            thread_id=thread_id
        )

        if sender != SENDER_TYPE_USER:
            try:
                tokens = identity_repo.get_device_tokens_for_customer(self.db, user_id)
                if tokens:
                    msg_body = request.message
                    if len(msg_body) > 100:
                        msg_body = msg_body[:97] + "..."
                    is_fraud_alert = (request.category or "").lower() == "fraud alert"
                    message = messaging.MulticastMessage(
                        data={
                            "title": "Fraud alert: review recent card activity" if is_fraud_alert else f"New Support Message ({request.category})",
                            "body": msg_body,
                            "thread_id": str(thread_id),
                            "type": SUPPORT_MESSAGE_TYPE,
                            "category": str(request.category),
                            "user_id": str(user_id),
                            "deep_link": "/secure-messaging",
                            "entry": "fraud-alert" if is_fraud_alert else "secure-message",
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

        try:
            notif_type = USER_MESSAGE_TYPE if sender == SENDER_TYPE_USER else SUPPORT_MESSAGE_TYPE

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

    def get_messages(self, token: ValidatedToken) -> List[Dict[str, Any]]:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")
        return identity_repo.get_messages_for_customer(self.db, user_id)

    def delete_message(self, message_id: str, token: ValidatedToken) -> Dict[str, Any]:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")
        identity_repo.soft_delete_message(self.db, user_id, message_id)
        return {"status": "success", "message": f"Message {message_id} soft deleted"}

    def delete_thread(self, thread_id: str, token: ValidatedToken) -> Dict[str, Any]:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")
        identity_repo.soft_delete_thread(self.db, user_id, thread_id)
        return {"status": "success", "message": f"Thread {thread_id} soft deleted"}

    def mark_messages_as_read(self, message_ids: List[str], token: ValidatedToken) -> Dict[str, Any]:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")
        identity_repo.mark_messages_as_user_read_by_ids(self.db, user_id, message_ids)
        return {"status": "success", "message": f"{len(message_ids)} messages marked as read"}

    def mark_messages_as_agent_read(self, request: AdminReadRequest, token: ValidatedToken) -> Dict[str, Any]:
        if not token.user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")
        identity_repo.mark_messages_as_agent_read_by_ids(self.db, request.message_ids)
        return {"status": "success", "message": f"{len(request.message_ids)} messages marked as agent read"}

    def admin_get_messages_for_customer(self, user_id: str, token: ValidatedToken) -> List[Dict[str, Any]]:
        if not token.user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")
        return identity_repo.get_messages_for_customer(self.db, user_id)

    def admin_delete_message(self, message_id: str, user_id: str, token: ValidatedToken) -> Dict[str, Any]:
        if not token.user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")
        identity_repo.soft_delete_message(self.db, user_id, message_id)
        return {"status": "success", "message": f"Message {message_id} soft deleted by admin"}

    def admin_delete_thread(self, thread_id: str, user_id: str, token: ValidatedToken) -> Dict[str, Any]:
        if not token.user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")
        identity_repo.soft_delete_thread(self.db, user_id, thread_id)
        return {"status": "success", "message": f"Thread {thread_id} soft deleted by admin"}
