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
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from main import app
from utils.database import SessionLocal
from models.origination import ApplicationArtifact

test_data_dir = Path(__file__).parent / "data"


@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def _mock_storage_client(signed_url: str | None = None):
    mock_blob = MagicMock()
    if signed_url is not None:
        mock_blob.generate_signed_url.return_value = signed_url

    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    mock_storage_client = MagicMock()
    mock_storage_client.bucket.return_value = mock_bucket
    return mock_storage_client, mock_bucket, mock_blob


@pytest.mark.asyncio
async def test_openapi_schema_generation(async_client):
    response = await async_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "paths" in schema


@pytest.mark.asyncio
async def test_health_endpoint(async_client):
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_should_run_startup_seeding_disabled_on_cloud_run_by_default(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "banking-service")
    monkeypatch.delenv("ENABLE_STARTUP_DB_SEEDING", raising=False)

    assert app.router.lifespan_context is not None
    import main as main_module
    assert main_module.should_run_startup_seeding() is False


@pytest.mark.asyncio
async def test_upload_artifact_success(async_client):
    # Create a valid application first
    app_data = {
        "product_category": "LOAN",
        "product_type": "RESIDENTIAL_MORTGAGE",
        "requested_amount": 50000.0
    }
    app_response = await async_client.post("/applications", json=app_data)
    assert app_response.status_code == 200
    app_json = app_response.json()
    valid_app_id = app_json["application_id"]

    file_content = b"This is a test artifact content."
    base64_content = base64.b64encode(file_content).decode("utf-8")

    json_payload = {
        "application_id": valid_app_id,
        "artifact_type": "W2",
        "base64_content": base64_content,
        "content_type": "text/plain"
    }

    mock_storage_client, mock_bucket, mock_blob = _mock_storage_client()

    with patch("services.origination.storage_client", mock_storage_client):
        response = await async_client.post("/artifacts", json=json_payload)

    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json["message"] == "File uploaded successfully and logged to database"
    assert "gcs_uri" in resp_json

    gcs_uri = resp_json["gcs_uri"]

    # The server generates a new UUID for the filename, so we must extract it from the response URI
    # gcs_uri format: gs://bucket_name/filename
    actual_filename = gcs_uri.split("/")[-1]

    mock_storage_client.bucket.assert_called_once()
    mock_bucket.blob.assert_called_once_with(actual_filename)
    mock_blob.upload_from_string.assert_called_once_with(file_content, content_type="text/plain")

    # Verify in SQLAlchemy database
    db = SessionLocal()
    art = db.query(ApplicationArtifact).filter(ApplicationArtifact.gcs_uri == gcs_uri).first()
    assert art is not None
    assert art.claimed_artifact_type == "W2"
    db.close()

    # We leave the BigQuery row as DML deletes can be slow and quota-limited in BQ.
    # Using unique prefixes prevents this from interfering with other operations.


@pytest.mark.asyncio
async def test_upload_artifact_missing_application_id(async_client):
    file_content = b"This is a test artifact content."

    base64_content = base64.b64encode(file_content).decode("utf-8")

    # Missing application_id
    json_payload = {
        "artifact_type": "W2",
        "base64_content": base64_content,
        "content_type": "text/plain"
    }

    response = await async_client.post("/artifacts", json=json_payload)

    # FastAPI returns 422 Unprocessable Entity for missing required fields
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_artifact_invalid_type(async_client):
    file_content = b"This is a test artifact content."

    base64_content = base64.b64encode(file_content).decode("utf-8")

    json_payload = {
        "application_id": "APP_TEST_456",
        "artifact_type": "INVALID_TYPE",
        "base64_content": base64_content,
        "content_type": "text/plain"
    }

    response = await async_client.post("/artifacts", json=json_payload)

    # FastAPI returns 422 Unprocessable Entity for invalid enum values
    assert response.status_code == 422


@pytest.mark.asyncio
@patch("services.origination.extract_data")
async def test_extract_success(mock_extract, async_client):
    mock_extract.return_value = {"application_id": "87345978"}
    """Test that the /extract endpoint successfully extracts data using Gemini."""
    # Create a valid application first
    app_data = {
        "product_category": "LOAN",
        "product_type": "RESIDENTIAL_MORTGAGE",
        "requested_amount": 50000.0
    }
    app_response = await async_client.post("/applications", json=app_data)
    assert app_response.status_code == 200
    app_json = app_response.json()
    valid_app_id = app_json["application_id"]

    file_content = b"This is a test artifact content for extraction. The application id is 87345978"
    base64_content = base64.b64encode(file_content).decode("utf-8")

    json_payload = {
        "application_id": valid_app_id,
        "artifact_type": "W2",
        "base64_content": base64_content,
        "content_type": "text/plain"
    }

    mock_storage_client, _, _ = _mock_storage_client()
    with patch("services.origination.storage_client", mock_storage_client):
        upload_response = await async_client.post("/artifacts", json=json_payload)
        assert upload_response.status_code == 200
        upload_json = upload_response.json()
        artifact_id = upload_json["artifact_id"]

        # 2. Now call the extract endpoint
        fields = ["application_id"]
        extract_response = await async_client.post(f"/artifacts/{artifact_id}/extractions", json=fields)

    assert extract_response.status_code == 200
    extract_json = extract_response.json()
    assert "application_id" in extract_json
    assert extract_json.get("application_id") == "87345978"


@pytest.mark.asyncio
async def test_get_user_mock(async_client):
    response = await async_client.get("/user")
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json == {"claims": {"sub": "mock_user_sub", "email": "mockuser@example.com"}}


@pytest.mark.asyncio
async def test_create_application_success(async_client):
    data = {
        "product_category": "LOAN",
        "product_type": "RESIDENTIAL_MORTGAGE",
        "requested_amount": 10000.0
    }

    response = await async_client.post("/applications", json=data)

    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json["message"] == "Application created successfully"
    assert "application_id" in resp_json


@pytest.mark.asyncio
async def test_create_credit_card_application_success(async_client):
    data = {
        "product_category": "CARD",
        "product_type": "AURA_ELITE_RESERVE",
        "requested_amount": 5000.0
    }

    response = await async_client.post("/applications", json=data)

    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json["message"] == "Application created successfully"
    assert "application_id" in resp_json



@pytest.mark.asyncio
async def test_create_application_missing_fields(async_client):
    # Missing product_category
    data = {
        "product_type": "RESIDENTIAL_MORTGAGE",
        "requested_amount": 10000.0
    }

    response = await async_client.post("/applications", json=data)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_application_invalid_category(async_client):
    data = {
        "product_category": "INVALID_CATEGORY",
        "product_type": "RESIDENTIAL_MORTGAGE",
        "requested_amount": 10000.0
    }

    response = await async_client.post("/applications", json=data)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_application_invalid_amount(async_client):
    data = {
        "product_category": "Loan",
        "product_type": "ResidentialMortgage",
        "requested_amount": 0.0
    }

    response = await async_client.post("/applications", json=data)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_application_success(async_client):
    # First create an application
    data = {
        "product_category": "LOAN",
        "product_type": "RESIDENTIAL_MORTGAGE",
        "requested_amount": 10000.0
    }
    response = await async_client.post("/applications", json=data)
    assert response.status_code == 200
    app_id = response.json()["application_id"]

    # Now update the application
    update_data = {
        "requested_amount": 250000.0,
        "application_status": "PENDING"
    }
    update_response = await async_client.patch(f"/applications/{app_id}", json=update_data)
    assert update_response.status_code == 200
    assert update_response.json()["message"] == "Application updated successfully"
    assert update_response.json()["application_id"] == app_id


@pytest.mark.asyncio
async def test_create_profile_success(async_client):
    unique_id = f"CUST_{uuid.uuid4()}"
    headers = {"Authorization": f"Bearer {unique_id}"}

    data = {
        "first_name": "Test",
        "last_name": "User"
    }
    response = await async_client.post("/profile", json=data, headers=headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Customer profile created successfully"
    assert response.json()["user_id"] == unique_id

    # Test GET the created customer profile
    get_response = await async_client.get("/profile", headers=headers)
    assert get_response.status_code == 200
    profile_data = get_response.json()
    assert profile_data["user_id"] == unique_id
    assert profile_data["first_name"] == "Test"
    assert profile_data["last_name"] == "User"
    assert profile_data["email"] == f"{unique_id}@example.com"


@pytest.mark.asyncio
@patch("services.origination.extract_data")
async def test_get_profile_not_found(mock_extract, async_client):
    mock_extract.return_value = {"status": "success"}
    unique_id = f"CUST_MISSING_{uuid.uuid4()}"
    headers = {"Authorization": f"Bearer {unique_id}"}

    response = await async_client.get("/profile", headers=headers)
    assert response.status_code == 200
    profile_data = response.json()
    assert profile_data["user_id"] == unique_id
    assert profile_data["email"] == f"{unique_id}@example.com"
    assert profile_data["first_name"] == ""
    assert profile_data["last_name"] == ""

    pdf_path = test_data_dir / "Sample-W2.pdf"

    with open(pdf_path, "rb") as f:
        file_content = f.read()

    # Create a valid application first
    app_data = {
        "product_category": "LOAN",
        "product_type": "RESIDENTIAL_MORTGAGE",
        "requested_amount": 50000.0
    }
    app_response = await async_client.post("/applications", json=app_data)
    assert app_response.status_code == 200
    app_json = app_response.json()
    valid_app_id = app_json["application_id"]

    base64_content = base64.b64encode(file_content).decode("utf-8")

    json_payload = {
        "application_id": valid_app_id,
        "artifact_type": "W2",
        "base64_content": base64_content,
        "content_type": "application/pdf"
    }

    mock_storage_client, _, _ = _mock_storage_client()
    with patch("services.origination.storage_client", mock_storage_client):
        response = await async_client.post("/artifacts/upload-and-validate", json=json_payload)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_generate_signed_url_success(async_client):
    # Create a valid application first
    app_data = {
        "product_category": "LOAN",
        "product_type": "RESIDENTIAL_MORTGAGE",
        "requested_amount": 50000.0
    }
    app_response = await async_client.post("/applications", json=app_data)
    assert app_response.status_code == 200
    app_json = app_response.json()
    valid_app_id = app_json["application_id"]

    json_payload = {
        "application_id": valid_app_id,
        "artifact_type": "W2",
        "content_type": "application/pdf"
    }

    mock_storage_client, _, mock_blob = _mock_storage_client(signed_url="http://mock-signed-url")
    with patch("services.origination.storage_client", mock_storage_client), \
         patch("services.origination.default", return_value=(MagicMock(), "local-test-project")), \
         patch("services.origination.ImpersonatedCredentials", return_value=MagicMock()):
        response = await async_client.post("/artifacts/signed-url", json=json_payload)

    assert response.status_code == 200
    resp_json = response.json()
    assert "signed_url" in resp_json
    assert resp_json["signed_url"] == "http://mock-signed-url"
    assert "artifact_id" in resp_json
    assert "gcs_uri" in resp_json
    mock_blob.generate_signed_url.assert_called_once()


@pytest.mark.asyncio
async def test_update_profile_success(async_client):
    unique_id = f"CUST_{uuid.uuid4()}"
    headers = {"Authorization": f"Bearer {unique_id}"}

    # 1. Create Profile First
    create_data = {
        "first_name": "Test",
        "last_name": "User"
    }
    create_response = await async_client.post("/profile", json=create_data, headers=headers)
    assert create_response.status_code == 200

    # 2. Update Profile
    update_data = {
        "first_name": "UpdatedFirst",
        "last_name": "UpdatedLast",
        "phone_number": "123-456-7890"
    }
    update_response = await async_client.put("/profile", json=update_data, headers=headers)
    assert update_response.status_code == 200
    assert update_response.json()["message"] == "Customer profile updated successfully"
    assert update_response.json()["user_id"] == unique_id

    # 3. Verify changes via GET
    get_response = await async_client.get("/profile", headers=headers)
    assert get_response.status_code == 200
    profile_data = get_response.json()
    assert profile_data["user_id"] == unique_id
    assert profile_data["first_name"] == "UpdatedFirst"
    assert profile_data["last_name"] == "UpdatedLast"
    assert profile_data["phone_number"] == "123-456-7890"
    assert profile_data["email"] == f"{unique_id}@example.com"


@pytest.mark.asyncio
async def test_get_all_customers_success(async_client):
    unique_id = f"CUST_LIST_{uuid.uuid4()}"
    headers = {"Authorization": f"Bearer {unique_id}"}

    response = await async_client.get("/profile/customers", headers=headers)
    assert response.status_code == 200
    customers_list = response.json()
    assert isinstance(customers_list, list)
    assert len(customers_list) > 0
    assert "user_id" in customers_list[0]
    assert "first_name" in customers_list[0]
    assert "last_name" in customers_list[0]
