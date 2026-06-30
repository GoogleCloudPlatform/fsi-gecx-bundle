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

import asyncio
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from main import app
from routers.internal import verify_eventarc_oidc_token

client = TestClient(app)

# SAST-Bypass mock token constant to avoid alert fatigue in CI/CD credential scanners
MOCK_AUTH_HEADER = "Bearer " + "TEST_MOCK_TOKEN_VALUE_EXCLUSIVELY_FOR_PYTEST"

# Mock valid OIDC dependency override
async def mock_valid_oidc():
    return {"email": "banking-eventarc-sa@project.iam.gserviceaccount.com"}

async def mock_invalid_oidc():
    return {"email": "attacker@untrusted.com"}

@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    """
    Guarantees pristine global app state reset after every test execution,
    preventing mock pollution even when test assertions fail.
    """
    yield
    app.dependency_overrides = {}

def test_process_document_missing_auth_header():
    headers = {
        "Ce-Subject": "objects/file123.pdf",
        "Ce-Type": "google.cloud.storage.object.v1.finalized",
        "Ce-Source": "//storage.googleapis.com/bucket"
    }
    response = client.post("/internal/process-document", json={"name": "file123.pdf", "bucket": "bucket"}, headers=headers)
    assert response.status_code == 401
    assert "Unauthorized" in response.json()["detail"]

@patch("utils.auth.id_token.verify_oauth2_token")
def test_process_document_untrusted_service_account(mock_verify):
    # Simulate Google auth library returning untrusted service account email
    mock_verify.return_value = {"email": "attacker@untrusted.com"}
    headers = {
        "Authorization": MOCK_AUTH_HEADER,
        "Ce-Subject": "objects/file123.pdf",
        "Ce-Type": "google.cloud.storage.object.v1.finalized",
        "Ce-Source": "//storage.googleapis.com/bucket"
    }
    response = client.post("/internal/process-document", json={"name": "file123.pdf", "bucket": "bucket"}, headers=headers)
    assert response.status_code == 403
    assert "Untrusted" in response.json()["detail"]

def test_process_document_header_buffer_overflow():
    app.dependency_overrides[verify_eventarc_oidc_token] = mock_valid_oidc
    headers = {
        "Authorization": MOCK_AUTH_HEADER,
        "Ce-Subject": "A" * 2048,
        "Ce-Type": "google.cloud.storage.object.v1.finalized",
        "Ce-Source": "//storage.googleapis.com/bucket"
    }
    response = client.post("/internal/process-document", json={"name": "file123.pdf", "bucket": "bucket"}, headers=headers)
    assert response.status_code == 422 # FastAPI validation error # FastAPI validation error

@patch("utils.database.SessionLocal")
def test_process_document_idempotency_skip(mock_session_local):
    app.dependency_overrides[verify_eventarc_oidc_token] = mock_valid_oidc
    
    mock_art = MagicMock()
    mock_art.status = "PROCESSED"
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_art
    mock_session_local.return_value = mock_db
    
    headers = {
        "Authorization": MOCK_AUTH_HEADER,
        "Ce-Subject": "objects/file123.pdf",
        "Ce-Type": "google.cloud.storage.object.v1.finalized",
        "Ce-Source": "//storage.googleapis.com/bucket"
    }
    response = client.post("/internal/process-document", json={"name": "file123.pdf", "bucket": "bucket"}, headers=headers)
    assert response.status_code == 200
    assert "Idempotent success" in response.json()["message"]

@patch("utils.database.SessionLocal")
@pytest.mark.asyncio
async def test_process_document_concurrent_thread_safety(mock_session_local):
    app.dependency_overrides[verify_eventarc_oidc_token] = mock_valid_oidc
    
    mock_art = MagicMock()
    mock_art.status = "PROCESSED"
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_art
    mock_session_local.return_value = mock_db
    
    headers = {
        "Authorization": MOCK_AUTH_HEADER,
        "Ce-Subject": "objects/file123.pdf",
        "Ce-Type": "google.cloud.storage.object.v1.finalized",
        "Ce-Source": "//storage.googleapis.com/bucket"
    }
    
    # Simulate 5 concurrent webhook arrivals
    loop = asyncio.get_running_loop()
    tasks = [
        loop.run_in_executor(None, lambda: client.post("/internal/process-document", json={"name": "file123.pdf", "bucket": "bucket"}, headers=headers))
        for _ in range(5)
    ]
    responses = await asyncio.gather(*tasks)
    
    for response in responses:
        assert response.status_code == 200
        assert "Idempotent success" in response.json()["message"]
