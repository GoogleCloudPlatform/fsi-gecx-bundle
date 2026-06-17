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

import base64
import json

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from models.authentication import ValidatedToken, ForwardedUserContextType
from utils.auth import get_current_user, PROJECT_ID, is_route_allowed


class MockURL:
    def __init__(self, path: str):
        self.path = path


class MockRequest:
    def __init__(self, method: str, path: str):
        self.method = method
        self.url = MockURL(path)


def _get_mock_firebase_jwt(token: str) -> str:
    payload = {"iss": f"https://securetoken.google.com/{PROJECT_ID}", "sub": token}
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode('utf-8')).decode('utf-8').rstrip('=')
    return f"header.{payload_b64}.signature"


@pytest.mark.asyncio
async def test_get_current_user_firebase_auth_header(monkeypatch):
    token_str = _get_mock_firebase_jwt("user123")

    def mock_validate_firebase_token(token):
        return ValidatedToken(claims={"sub": f"FIREBASE_{token}", "email": f"{token}@example.com"})

    monkeypatch.setattr("utils.auth.validate_firebase_token", mock_validate_firebase_token)

    req = MockRequest("GET", "/profile")
    user = await get_current_user(request=req,
                                  auth=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token_str))
    assert user.claims == {"sub": f"FIREBASE_{token_str}", "email": f"{token_str}@example.com"}


@pytest.mark.asyncio
async def test_get_current_user_cxas_forwarded_header(monkeypatch):
    # Forwarded context is CXAS token
    forwarded_token = _get_mock_firebase_jwt("user456")

    # Standard auth must be a valid Google ID Token
    google_payload = {"iss": "https://accounts.google.com", "email": "agent@gcp-sa-ces.iam.gserviceaccount.com"}
    google_payload_b64 = base64.urlsafe_b64encode(json.dumps(google_payload).encode('utf-8')).decode('utf-8').rstrip(
        '=')
    google_id_token_jwt = f"header.{google_payload_b64}.signature"

    def mock_validate_cxas_token(token):
        return ValidatedToken(claims={"sub": f"CXAS_{token}", "email": f"{token}@example.com",
                                      "type": ForwardedUserContextType.CXAS_AGENT.value})

    def mock_validate_google_id_token(token):
        return ValidatedToken(claims={"sub": "SERVICE_AGENT", "email": "agent@gcp-sa-ces.iam.gserviceaccount.com"})

    monkeypatch.setattr("utils.auth.validate_cxas_token", mock_validate_cxas_token)
    monkeypatch.setattr("utils.auth.validate_google_id_token", mock_validate_google_id_token)

    req = MockRequest("POST", "/profile")
    user = await get_current_user(
        request=req,
        auth=HTTPAuthorizationCredentials(scheme="Bearer", credentials=google_id_token_jwt),
        forwarded_auth=HTTPAuthorizationCredentials(scheme="Bearer", credentials=forwarded_token)
    )
    assert user.claims == {"sub": f"CXAS_{forwarded_token}", "email": f"{forwarded_token}@example.com",
                           "type": ForwardedUserContextType.CXAS_AGENT.value}


@pytest.mark.asyncio
async def test_get_current_user_cxas_forwarded_header_forbidden(monkeypatch):
    # Forwarded context is CXAS token
    forwarded_token = _get_mock_firebase_jwt("user456")

    # Standard auth must be a valid Google ID Token
    google_payload = {"iss": "https://accounts.google.com", "email": "agent@gcp-sa-ces.iam.gserviceaccount.com"}
    google_payload_b64 = base64.urlsafe_b64encode(json.dumps(google_payload).encode('utf-8')).decode('utf-8').rstrip(
        '=')
    google_id_token_jwt = f"header.{google_payload_b64}.signature"

    def mock_validate_cxas_token(token):
        return ValidatedToken(claims={"sub": f"CXAS_{token}", "email": f"{token}@example.com",
                                      "type": ForwardedUserContextType.CXAS_AGENT.value})

    def mock_validate_google_id_token(token):
        return ValidatedToken(claims={"sub": "SERVICE_AGENT", "email": "agent@gcp-sa-ces.iam.gserviceaccount.com"})

    monkeypatch.setattr("utils.auth.validate_cxas_token", mock_validate_cxas_token)
    monkeypatch.setattr("utils.auth.validate_google_id_token", mock_validate_google_id_token)

    # Calling a forbidden endpoint (/secure-messaging) with forwarded auth
    req = MockRequest("GET", "/secure-messaging")
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(
            request=req,
            auth=HTTPAuthorizationCredentials(scheme="Bearer", credentials=google_id_token_jwt),
            forwarded_auth=HTTPAuthorizationCredentials(scheme="Bearer", credentials=forwarded_token)
        )
    assert exc_info.value.status_code == 403
    assert "Forbidden" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_returns_forwarded_auth_when_google_auth_is_valid(monkeypatch):
    forwarded_token = _get_mock_firebase_jwt("fallback_user")


    # Standard auth must be a valid Google ID Token
    google_payload = {"iss": "https://accounts.google.com", "email": "agent@gcp-sa-ces.iam.gserviceaccount.com"}
    google_payload_b64 = base64.urlsafe_b64encode(json.dumps(google_payload).encode('utf-8')).decode('utf-8').rstrip(
        '=')
    google_id_token_jwt = f"header.{google_payload_b64}.signature"

    def mock_validate_cxas_token(token):
        return ValidatedToken(claims={"sub": f"CXAS_{token}", "email": f"{token}@example.com",
                                      "type": ForwardedUserContextType.CXAS_AGENT.value})

    def mock_validate_google_id_token(token):
        return ValidatedToken(claims={"sub": "SERVICE_AGENT", "email": "agent@gcp-sa-ces.iam.gserviceaccount.com"})

    monkeypatch.setattr("utils.auth.validate_cxas_token", mock_validate_cxas_token)
    monkeypatch.setattr("utils.auth.validate_google_id_token", mock_validate_google_id_token)

    req = MockRequest("POST", "/applications")
    user = await get_current_user(
        request=req,
        auth=HTTPAuthorizationCredentials(scheme="Bearer", credentials=google_id_token_jwt),
        forwarded_auth=HTTPAuthorizationCredentials(scheme="Bearer", credentials=forwarded_token)
    )
    # Returns forwarded_auth claims because standard auth (google_id_token) is valid
    assert user.claims == {"sub": f"CXAS_{forwarded_token}", "email": f"{forwarded_token}@example.com",
                           "type": ForwardedUserContextType.CXAS_AGENT.value}


@pytest.mark.asyncio
async def test_get_current_user_cxas_forwarded_header_invalid_type(monkeypatch):
    forwarded_token = _get_mock_firebase_jwt("user456")
    google_payload = {"iss": "https://accounts.google.com", "email": "agent@gcp-sa-ces.iam.gserviceaccount.com"}
    google_payload_b64 = base64.urlsafe_b64encode(json.dumps(google_payload).encode('utf-8')).decode('utf-8').rstrip(
        '=')
    google_id_token_jwt = f"header.{google_payload_b64}.signature"

    # Mocks token claims to have an invalid type "unrecognized-agent"
    def mock_validate_cxas_token(token):
        return ValidatedToken(
            claims={"sub": f"CXAS_{token}", "email": f"{token}@example.com", "type": "unrecognized-agent"})

    def mock_validate_google_id_token(token):
        return ValidatedToken(claims={"sub": "SERVICE_AGENT", "email": "agent@gcp-sa-ces.iam.gserviceaccount.com"})

    monkeypatch.setattr("utils.auth.validate_cxas_token", mock_validate_cxas_token)
    monkeypatch.setattr("utils.auth.validate_google_id_token", mock_validate_google_id_token)

    # Calling an otherwise allowed route (/profile) but with invalid type context
    req = MockRequest("GET", "/profile")
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(
            request=req,
            auth=HTTPAuthorizationCredentials(scheme="Bearer", credentials=google_id_token_jwt),
            forwarded_auth=HTTPAuthorizationCredentials(scheme="Bearer", credentials=forwarded_token)
        )
    assert exc_info.value.status_code == 403
    assert "Forbidden" in exc_info.value.detail


def test_is_route_allowed_patch_application():
    """Verify that is_route_allowed permits PATCH to /applications/2 under CXAS_AGENT context."""
    assert is_route_allowed(
        method="PATCH",
        path="/applications/2",
        context_type=ForwardedUserContextType.CXAS_AGENT.value
    ) is True

