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

import pytest
from fastapi import Header, HTTPException
from httpx import AsyncClient, ASGITransport

from main import app
from models.authentication import ValidatedToken
from routers.ccai_authentication import get_current_user


@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def override_auth():
    def mock_get_current_user(x_goog_iap_jwt_assertion: str = Header(None)):
        if x_goog_iap_jwt_assertion == "mock_token":
            return ValidatedToken(claims={"sub": "USER_123", "email": "john.doe@example.com"})
        raise HTTPException(status_code=401, detail="Missing or invalid mock token")

    app.dependency_overrides[get_current_user] = mock_get_current_user
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_auth_token_success(async_client):
    # Pass the mock IAP header
    response = await async_client.post(
        "/ccai/auth/token",
        headers={"x-goog-iap-jwt-assertion": "mock_token"}
    )
    assert response.status_code == 200
    resp_json = response.json()
    assert "token" in resp_json
    assert isinstance(resp_json["token"], str)


@pytest.mark.asyncio
async def test_chat_auth_token_with_user_info(async_client):
    # This test previously passed a JSON body, but the endpoint now ignores it
    # and uses IAP headers. We still pass the mock header to make it pass.
    response = await async_client.post(
        "/ccai/auth/token",
        headers={"x-goog-iap-jwt-assertion": "mock_token"}
    )
    assert response.status_code == 200
    resp_json = response.json()
    assert "token" in resp_json
    assert isinstance(resp_json["token"], str)
