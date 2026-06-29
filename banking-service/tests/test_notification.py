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

import uuid
from unittest.mock import patch, MagicMock, ANY

import pytest
from httpx import AsyncClient, ASGITransport

from main import app
from models.secure_messaging import SECURE_MESSAGES_TOPIC
from utils.database import SessionLocal
from models.identity import User, UserDevice


@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
@patch("routers.notification.messaging.subscribe_to_topic")
async def test_register_device_success(mock_subscribe, async_client):
    mock_sub_response = MagicMock()
    mock_sub_response.success_count = 1
    mock_sub_response.failure_count = 0
    mock_sub_response.errors = []
    mock_subscribe.return_value = mock_sub_response

    unique_id = f"CUST_DEV_{uuid.uuid4()}"
    headers = {"Authorization": f"Bearer {unique_id}"}

    device_token = f"fake_token_{uuid.uuid4()}"
    payload = {
        "device_token": device_token
    }

    # Register Device
    response = await async_client.post("/notification/device", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["message"] == "Device token registered successfully"
    assert response.json()["user_id"] == unique_id

    assert mock_subscribe.call_count == 2
    mock_subscribe.assert_any_call([device_token], "all")
    mock_subscribe.assert_any_call([device_token], SECURE_MESSAGES_TOPIC)

    # Verify in SQLAlchemy database
    db = SessionLocal()
    user = db.query(User).filter(User.auth_provider_uid == unique_id).first()
    assert user is not None
    devices = db.query(UserDevice).filter(UserDevice.user_id == user.id, UserDevice.device_token == device_token).all()
    assert len(devices) == 1
    assert devices[0].device_token == device_token
    db.close()


@pytest.mark.asyncio
@patch("routers.notification.messaging.subscribe_to_topic")
@patch("routers.notification.messaging.unsubscribe_from_topic")
async def test_unregister_device_success(mock_unsubscribe, mock_subscribe, async_client):
    mock_sub_response = MagicMock()
    mock_sub_response.success_count = 1
    mock_sub_response.failure_count = 0
    mock_sub_response.errors = []
    mock_subscribe.return_value = mock_sub_response

    mock_unsub_response = MagicMock()
    mock_unsub_response.success_count = 1
    mock_unsub_response.failure_count = 0
    mock_unsub_response.errors = []
    mock_unsubscribe.return_value = mock_unsub_response

    unique_id = f"CUST_DEV_{uuid.uuid4()}"
    headers = {"Authorization": f"Bearer {unique_id}"}

    device_token = f"fake_token_{uuid.uuid4()}"
    payload = {
        "device_token": device_token
    }

    # First register the device
    reg_response = await async_client.post("/notification/device", json=payload, headers=headers)
    assert reg_response.status_code == 200

    # Unregister Device
    response = await async_client.delete(f"/notification/device?device_token={device_token}", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["message"] == "Device token unregistered successfully"
    assert response.json()["user_id"] == unique_id

    assert mock_unsubscribe.call_count == 2
    mock_unsubscribe.assert_any_call([device_token], "all")
    mock_unsubscribe.assert_any_call([device_token], SECURE_MESSAGES_TOPIC)

    # Verify deleted in SQLAlchemy database
    db = SessionLocal()
    user = db.query(User).filter(User.auth_provider_uid == unique_id).first()
    if user:
        devices = db.query(UserDevice).filter(UserDevice.user_id == user.id, UserDevice.device_token == device_token).all()
        assert len(devices) == 0
    db.close()


@pytest.mark.asyncio
@patch("routers.notification.messaging.send")
async def test_send_notification_topic_success(mock_send, async_client):
    mock_send.return_value = "fake_message_id_123"

    unique_id = f"CUST_DEV_{uuid.uuid4()}"
    headers = {"Authorization": f"Bearer {unique_id}"}

    payload = {
        "topic": "all",
        "data": {
            "title": "Topic Alert",
            "body": "This is a broadcast message."
        }
    }

    response = await async_client.post("/notification/send", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["recipient_type"] == "topic"
    assert response.json()["topic"] == "all"
    assert response.json()["message_id"] == "fake_message_id_123"

    mock_send.assert_called_once()
    message_arg = mock_send.call_args[0][0]
    assert message_arg.notification is None
    assert message_arg.data == {
        "title": "Topic Alert",
        "body": "This is a broadcast message."
    }
    assert message_arg.topic == "all"


@pytest.mark.asyncio
@patch("routers.notification.identity_repo.get_device_tokens_for_customer")
@patch("routers.notification.messaging.send_each_for_multicast")
async def test_send_notification_customer_success(mock_send_multicast, mock_get_tokens, async_client):
    mock_get_tokens.return_value = ["token_abc", "token_xyz"]

    mock_batch_response = MagicMock()
    mock_batch_response.success_count = 2
    mock_batch_response.failure_count = 0
    mock_batch_response.responses = [MagicMock(success=True), MagicMock(success=True)]
    mock_send_multicast.return_value = mock_batch_response

    unique_id = f"CUST_DEV_{uuid.uuid4()}"
    target_user_id = "CUST_TARGET_123"
    headers = {"Authorization": f"Bearer {unique_id}"}

    payload = {
        "user_id": target_user_id,
        "data": {
            "title": "Personal Alert",
            "body": "Hello Customer!"
        }
    }

    response = await async_client.post("/notification/send", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["recipient_type"] == "customer"
    assert response.json()["sent_count"] == 2
    assert response.json()["failure_count"] == 0

    mock_get_tokens.assert_called_once_with(ANY, target_user_id)
    mock_send_multicast.assert_called_once()
    multicast_arg = mock_send_multicast.call_args[0][0]
    assert multicast_arg.notification is None
    assert multicast_arg.data == {
        "title": "Personal Alert",
        "body": "Hello Customer!"
    }
    assert multicast_arg.tokens == ["token_abc", "token_xyz"]


@pytest.mark.asyncio
@patch("routers.notification.identity_repo.get_device_tokens_for_customer")
async def test_send_notification_customer_no_devices(mock_get_tokens, async_client):
    mock_get_tokens.return_value = []

    unique_id = f"CUST_DEV_{uuid.uuid4()}"
    target_user_id = "CUST_NO_DEVICES"
    headers = {"Authorization": f"Bearer {unique_id}"}

    payload = {
        "user_id": target_user_id,
        "data": {
            "title": "Silent Alert",
            "body": "No device to see this."
        }
    }

    response = await async_client.post("/notification/send", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["recipient_type"] == "customer"
    assert response.json()["sent_count"] == 0
    assert "No registered devices found" in response.json()["message"]

    mock_get_tokens.assert_called_once_with(ANY, target_user_id)
