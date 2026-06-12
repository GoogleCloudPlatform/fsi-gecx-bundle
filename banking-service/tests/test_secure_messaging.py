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
from unittest.mock import patch, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from main import app
from models.secure_messaging import (
    SUPPORT_MESSAGE_TYPE,
    USER_MESSAGE_TYPE,
    SECURE_MESSAGES_TOPIC,
    SENDER_TYPE_USER,
    SENDER_TYPE_BANK
)
from routers.artifact import bq_client
from utils.gcp import get_project_id


@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_secure_messaging_flow(async_client):
    unique_user_id = f"CUST_MSG_{uuid.uuid4()}"
    headers = {"Authorization": f"Bearer {unique_user_id}"}

    # 1. Create a new thread message
    payload_new = {
        "category": "Billing",
        "message": "I have a question about my last statement."
    }
    response_new = await async_client.post("/secure-messaging", json=payload_new, headers=headers)
    assert response_new.status_code == 200
    msg_new = response_new.json()
    assert msg_new["user_id"] == unique_user_id
    assert msg_new["category"] == "Billing"
    assert msg_new["message"] == "I have a question about my last statement."
    assert msg_new["sender"] == SENDER_TYPE_USER
    assert msg_new["deleted"] is False
    assert msg_new["is_user_read"] is True
    assert msg_new["is_agent_read"] is False
    assert "thread_id" in msg_new
    assert "message_id" in msg_new

    thread_id = msg_new["thread_id"]
    message_id_1 = msg_new["message_id"]

    # 2. Create a reply in the same thread
    payload_reply = {
        "category": "Billing",
        "message": "Also, can I pay it online?",
        "thread_id": thread_id
    }
    response_reply = await async_client.post("/secure-messaging", json=payload_reply, headers=headers)
    assert response_reply.status_code == 200
    msg_reply = response_reply.json()
    assert msg_reply["user_id"] == unique_user_id
    assert msg_reply["thread_id"] == thread_id
    assert msg_reply["message"] == "Also, can I pay it online?"
    assert msg_reply["is_user_read"] is True
    assert msg_reply["is_agent_read"] is False
    message_id_2 = msg_reply["message_id"]

    # Verify directly in BigQuery that 2 rows exist
    project_id = get_project_id()
    query = f"""
        SELECT *
        FROM `{project_id}.banking.user_secure_message`

        WHERE user_id = '{unique_user_id}' AND deleted = FALSE
    """
    query_job = bq_client.query(query)
    results = list(query_job.result())
    assert len(results) == 2

    # 3. Get all messages for the customer
    response_get = await async_client.get("/secure-messaging", headers=headers)
    assert response_get.status_code == 200
    messages_list = response_get.json()
    assert len(messages_list) == 2
    assert messages_list[0]["message_id"] == message_id_1
    assert messages_list[1]["message_id"] == message_id_2

    # 3b. Create an unread message from the bank, verify is_user_read is False, and mark it as read
    payload_bank = {
        "category": "Billing",
        "message": "We have updated your invoice.",
        "sender": SENDER_TYPE_BANK,
        "user_id": unique_user_id,
        "thread_id": thread_id
    }
    response_bank = await async_client.post("/secure-messaging", json=payload_bank, headers=headers)
    assert response_bank.status_code == 200
    msg_bank = response_bank.json()
    assert msg_bank["is_user_read"] is False
    assert msg_bank["is_agent_read"] is True
    message_id_bank = msg_bank["message_id"]

    # Fetch to check list contains it as unread
    response_get_2 = await async_client.get("/secure-messaging", headers=headers)
    assert response_get_2.status_code == 200
    messages_list_2 = response_get_2.json()
    assert len(messages_list_2) == 3
    bank_msg_fetched = next(m for m in messages_list_2 if m["message_id"] == message_id_bank)
    assert bank_msg_fetched["is_user_read"] is False
    assert bank_msg_fetched["is_agent_read"] is True

    # Mark as read
    response_read = await async_client.post("/secure-messaging/read", json=[message_id_bank], headers=headers)
    assert response_read.status_code == 200
    assert response_read.json()["status"] == "success"

    # Fetch again to verify it is now read
    response_get_3 = await async_client.get("/secure-messaging", headers=headers)
    assert response_get_3.status_code == 200
    messages_list_3 = response_get_3.json()
    bank_msg_fetched_3 = next(m for m in messages_list_3 if m["message_id"] == message_id_bank)
    assert bank_msg_fetched_3["is_user_read"] is True
    assert bank_msg_fetched_3["is_agent_read"] is True

    # 4. Soft delete one message
    response_del_msg = await async_client.delete(f"/secure-messaging/messages/{message_id_1}", headers=headers)
    assert response_del_msg.status_code == 200
    assert response_del_msg.json()["status"] == "success"

    # Verify that GET now returns only the remaining message
    response_get_after = await async_client.get("/secure-messaging", headers=headers)
    assert response_get_after.status_code == 200
    messages_list_after = response_get_after.json()
    assert len(messages_list_after) == 2
    assert messages_list_after[0]["message_id"] == message_id_2
    assert messages_list_after[1]["message_id"] == message_id_bank

    # Verify in BQ directly that deleted = True for first, False for second and third
    query_bq_del = f"""
        SELECT message_id, deleted
        FROM `{project_id}.banking.user_secure_message`

        WHERE user_id = '{unique_user_id}'
    """
    results_del = list(bq_client.query(query_bq_del).result())
    assert len(results_del) == 3
    for r in results_del:
        if r.message_id == message_id_1:
            assert r.deleted is True
        else:
            assert r.deleted is False

    # 5. Soft delete the entire thread
    response_del_thread = await async_client.delete(f"/secure-messaging/threads/{thread_id}", headers=headers)
    assert response_del_thread.status_code == 200
    assert response_del_thread.json()["status"] == "success"

    # Verify GET returns nothing
    response_get_thread_after = await async_client.get("/secure-messaging", headers=headers)
    assert response_get_thread_after.status_code == 200
    assert len(response_get_thread_after.json()) == 0

    # Verify in BQ directly that all messages are deleted
    results_thread_del = list(bq_client.query(query_bq_del).result())
    for r in results_thread_del:
        assert r.deleted is True


@pytest.mark.asyncio
async def test_secure_messaging_unauthorized(async_client):
    # Access without credentials should fail with 401 if running on Cloud Run, 
    # but since tests run in local development mode (is_running_locally() is True),
    # get_current_user automatically falls back to get_mock_token().
    # Let's verify that the endpoint works with default mock token.
    payload = {
        "category": "General",
        "message": "Hello from mock user"
    }
    # No headers passed
    response = await async_client.post("/secure-messaging", json=payload)
    assert response.status_code == 200
    msg = response.json()
    assert msg["user_id"] == "mock_user_sub"


@pytest.mark.asyncio
@patch("routers.secure_messaging.get_device_tokens_for_customer")
@patch("routers.secure_messaging.messaging.send_each_for_multicast")
@patch("routers.secure_messaging.messaging.send")
async def test_secure_messaging_push_notification(mock_send, mock_send_multicast, mock_get_tokens, async_client):
    mock_get_tokens.return_value = ["device_token_xyz"]
    mock_multicast_response = MagicMock()
    mock_multicast_response.success_count = 1
    mock_multicast_response.failure_count = 0
    mock_send_multicast.return_value = mock_multicast_response
    mock_send.return_value = "fake_topic_msg_id_123"

    user_id = f"CUST_NOTIF_{uuid.uuid4()}"
    headers = {"Authorization": f"Bearer {user_id}"}

    # 1. Send as 'user' -> should NOT trigger push notification, but SHOULD trigger topic notification
    payload_user = {
        "category": "Loans",
        "message": "Hi, I need help with my loan.",
        "sender": SENDER_TYPE_USER
    }
    response_user = await async_client.post("/secure-messaging", json=payload_user, headers=headers)
    assert response_user.status_code == 200
    mock_send_multicast.assert_not_called()
    mock_get_tokens.assert_not_called()

    mock_send.assert_called_once()
    sent_msg_topic = mock_send.call_args[0][0]
    assert sent_msg_topic.topic == SECURE_MESSAGES_TOPIC
    assert sent_msg_topic.data == {
        "user_id": user_id,
        "type": USER_MESSAGE_TYPE,
        "thread_id": response_user.json()["thread_id"],
        "category": "Loans"
    }

    # Reset mocks
    mock_send_multicast.reset_mock()
    mock_get_tokens.reset_mock()
    mock_send.reset_mock()

    # 2. Send as 'bank' -> should trigger push notification to customer, NOT topic notification
    payload_bank = {
        "category": "Loans",
        "message": "Sure, how can we help you today?",
        "sender": SENDER_TYPE_BANK,
        "user_id": user_id,
        "thread_id": response_user.json()["thread_id"]
    }
    response_bank = await async_client.post("/secure-messaging", json=payload_bank, headers=headers)
    assert response_bank.status_code == 200

    mock_get_tokens.assert_called_once_with(user_id)
    mock_send_multicast.assert_called_once()

    mock_send.assert_called_once()
    sent_msg_topic_bank = mock_send.call_args[0][0]
    assert sent_msg_topic_bank.topic == SECURE_MESSAGES_TOPIC
    assert sent_msg_topic_bank.data == {
        "user_id": user_id,
        "type": SUPPORT_MESSAGE_TYPE,
        "thread_id": response_user.json()["thread_id"],
        "category": "Loans"
    }

    sent_message = mock_send_multicast.call_args[0][0]
    assert sent_message.notification is None
    assert sent_message.tokens == ["device_token_xyz"]
    assert sent_message.data == {
        "title": "New Support Message (Loans)",
        "body": "Sure, how can we help you today?",
        "thread_id": response_user.json()["thread_id"],
        "type": SUPPORT_MESSAGE_TYPE,
        "category": "Loans",
        "user_id": user_id
    }


@pytest.mark.asyncio
async def test_admin_secure_messaging_flow(async_client):
    user_id = f"CUST_ADMIN_TEST_{uuid.uuid4()}"
    headers_customer = {"Authorization": f"Bearer {user_id}"}

    payload_user = {
        "category": "Security",
        "message": "Is this email phishing?"
    }
    response_user = await async_client.post("/secure-messaging", json=payload_user, headers=headers_customer)
    assert response_user.status_code == 200
    msg_user = response_user.json()
    thread_id = msg_user["thread_id"]
    message_id_1 = msg_user["message_id"]

    admin_id = f"ADMIN_SUPPORT_{uuid.uuid4()}"
    headers_admin = {"Authorization": f"Bearer {admin_id}"}

    # Admin GETs messages for this customer
    response_admin_get = await async_client.get(f"/secure-messaging/admin/customer/{user_id}",
                                                headers=headers_admin)
    assert response_admin_get.status_code == 200
    messages_list = response_admin_get.json()
    assert len(messages_list) == 1
    assert messages_list[0]["message_id"] == message_id_1

    # Admin sends reply (POST /secure-messaging with sender='bank')
    payload_reply = {
        "category": "Security",
        "message": "Yes, please delete it.",
        "sender": SENDER_TYPE_BANK,
        "user_id": user_id,
        "thread_id": thread_id
    }
    response_reply = await async_client.post("/secure-messaging", json=payload_reply, headers=headers_admin)
    assert response_reply.status_code == 200
    msg_reply = response_reply.json()
    message_id_2 = msg_reply["message_id"]

    # Verify that the message sent by user is unread for the agent
    assert messages_list[0]["is_agent_read"] is False

    # Mark as agent read
    payload_read = {
        "message_ids": [message_id_1],
        "user_id": user_id
    }
    response_admin_read = await async_client.post("/secure-messaging/admin/read", json=payload_read,
                                                  headers=headers_admin)
    assert response_admin_read.status_code == 200
    assert response_admin_read.json()["status"] == "success"

    # Fetch to verify both messages are listed under customer messages for admin and updated to read
    response_admin_get_2 = await async_client.get(f"/secure-messaging/admin/customer/{user_id}",
                                                  headers=headers_admin)
    assert len(response_admin_get_2.json()) == 2
    assert response_admin_get_2.json()[0]["is_agent_read"] is True

    # Admin deletes one message
    response_del_msg = await async_client.delete(
        f"/secure-messaging/admin/messages/{message_id_1}?user_id={user_id}", headers=headers_admin)
    assert response_del_msg.status_code == 200
    assert response_del_msg.json()["status"] == "success"

    # Fetch to verify only second message remains
    response_admin_get_3 = await async_client.get(f"/secure-messaging/admin/customer/{user_id}",
                                                  headers=headers_admin)
    assert len(response_admin_get_3.json()) == 1
    assert response_admin_get_3.json()[0]["message_id"] == message_id_2

    # Admin deletes the thread
    response_del_thread = await async_client.delete(
        f"/secure-messaging/admin/threads/{thread_id}?user_id={user_id}", headers=headers_admin)
    assert response_del_thread.status_code == 200
    assert response_del_thread.json()["status"] == "success"

    # Fetch to verify no messages are returned
    response_admin_get_4 = await async_client.get(f"/secure-messaging/admin/customer/{user_id}",
                                                  headers=headers_admin)
    assert len(response_admin_get_4.json()) == 0
