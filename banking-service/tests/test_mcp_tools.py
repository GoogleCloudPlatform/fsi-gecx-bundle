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
from unittest.mock import MagicMock, patch
from routers.mcp import (
    get_loan_application_documents,
    generate_upload_session_url,
    _extract_customer_identity,
    _mask_ssn,
    _mask_ein
)

@pytest.fixture
def mock_bq_client():
    """Mock BigQuery Client fixture."""
    with patch("routers.mcp.loan.bq_client") as mock_bq:
        yield mock_bq

def test_mcp_extract_customer_identity_iap_header():
    """Verify dynamic extraction of customer email/identity from GCP IAP headers."""
    mock_ctx = MagicMock()
    mock_ctx.request_context.headers = [
        (b"x-goog-authenticated-user-email", b"accounts.google.com:borrower@argolis.solutions")
    ]
    
    customer_id = _extract_customer_identity(mock_ctx)
    assert customer_id == "borrower@argolis.solutions"

def test_mcp_extract_customer_identity_dev_auth_header(monkeypatch):
    """Verify fallback extraction of customer identity from custom Dev auth header context."""
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "true")
    mock_ctx = MagicMock()
    mock_ctx.request_context.headers = [
        (b"authorization", b"Bearer developer@sandbox.horizon")
    ]
    
    customer_id = _extract_customer_identity(mock_ctx)
    assert customer_id == "developer@sandbox.horizon"

def test_mcp_extract_customer_identity_dev_auth_header_blocked_in_prod(monkeypatch):
    """Verify fallback extraction is blocked in production (ALLOW_DEV_AUTH_BYPASS=false)."""
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "false")
    mock_ctx = MagicMock()
    mock_ctx.request_context.headers = [
        (b"authorization", b"Bearer developer@sandbox.horizon")
    ]
    
    with pytest.raises(PermissionError, match="Identity context missing"):
        _extract_customer_identity(mock_ctx)

def test_mcp_ssn_ein_obfuscation_algorithms():
    """Verify that sensitive SSNs and EINs are masked to prevent LLM/context exposures."""
    assert _mask_ssn("123-45-6789") == "***-**-6789"
    assert _mask_ein("98-7654321") == "**-***4321"
    assert _mask_ssn("") == "N/A"
    assert _mask_ein(None) == "N/A"

@pytest.mark.asyncio
@patch("routers.mcp.loan._extract_customer_identity")
async def test_get_application_documents_mcp_tool_success(mock_identity, mock_bq_client):
    """Verify W-2 document audit summary fetches, parsing, and context mapping success."""
    mock_identity.return_value = "borrower@argolis.solutions"
    
    # Mock BigQuery row payload
    mock_row = MagicMock()
    mock_row.artifact_id = "art-123"
    mock_row.claimed_artifact_type = "W2"
    mock_row.actual_artifact_type = "W2"
    mock_row.status = "PROCESSED"
    mock_row.file_path_gcs = "gs://bucket/art-123.pdf"
    mock_row.extraction_payload = {
        "W2": {
            "WagesTipsOtherCompensation": {"value": "75000", "confidence": 0.98},
            "SSN": {"value": "123-45-6789", "confidence": 0.96},
            "EIN": {"value": "98-7654321", "confidence": 0.98}
        }
    }
    
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = [mock_row]
    mock_bq_client.query.return_value = mock_query_job

    mock_ctx = MagicMock()
    result = await get_loan_application_documents(application_id="app-bq-success-999", ctx=mock_ctx)
    
    assert "Verified Loan Documents Audit for Application ID: app-bq-success-999" in result
    assert "Claimed: W2 | Visual Classification: W2 | Ingestion Status: PROCESSED" in result
    assert "Wages (Box 1): $75000" in result
    # Critical Security checks: verify plain-text SSNs/EINs are securely masked!
    assert "123-45-6789" not in result
    assert "98-7654321" not in result
    assert "Borrower SSN: ***-**-6789" in result
    assert "Employer Tax ID (EIN): **-***4321" in result

@pytest.mark.asyncio
@patch("routers.mcp.loan._extract_customer_identity")
async def test_get_application_documents_mcp_tool_empty(mock_identity, mock_bq_client):
    """Verify that if no documents are found or tenant checks fail, the tool returns empty."""
    mock_identity.return_value = "borrower@argolis.solutions"
    
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = []  # empty results (unauthorized application or missing data!)
    mock_bq_client.query.return_value = mock_query_job

    mock_ctx = MagicMock()
    result = await get_loan_application_documents(application_id="app-bq-empty-999", ctx=mock_ctx)
    
    assert "No documents found under authorized profile" in result


@pytest.mark.asyncio
async def test_get_application_documents_mcp_tool_input_validation_failed():
    """Verify that malformed Application IDs are blocked by the regex input validator."""
    mock_ctx = MagicMock()
    # Inject a path traversal payload
    result = await get_loan_application_documents(application_id="../../../../etc/passwd", ctx=mock_ctx)
    assert "Access Denied: Invalid Application ID format." in result
    
    # Inject a SQL injection attempt payload
    result = await get_loan_application_documents(application_id="app-123; DROP TABLE", ctx=mock_ctx)
    assert "Access Denied: Invalid Application ID format." in result


@pytest.mark.asyncio
@patch("routers.mcp.loan._extract_customer_identity")
@patch("routers.mcp.loan.storage.Client")
async def test_generate_upload_session_url_success(mock_storage, mock_identity, mock_bq_client):
    """Verify successful temporary signed PUT upload URL generation with exact security bounds."""
    mock_identity.return_value = "borrower@argolis.solutions"
    
    # Mock BQ application ownership check
    mock_row = MagicMock()
    mock_row.artifact_id = "artifact-123"
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = [mock_row]
    mock_bq_client.query.return_value = mock_query_job
    
    # Mock GCS blob and client
    mock_blob = MagicMock()
    mock_blob.generate_signed_url.return_value = "https://storage.googleapis.com/mock-signed-url"
    
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_storage.return_value = mock_client
    
    # Trigger tool
    mock_ctx = MagicMock()
    result = await generate_upload_session_url(
        application_id="app-999",
        claimed_artifact_type="W2",
        session_id="session-xyz-789",
        ctx=mock_ctx
    )
    
    assert "🔒 Secure Document Upload Session Generated" in result
    assert "Document Type requested: W2" in result
    assert "https://storage.googleapis.com/mock-signed-url" in result
    
    # Verify GCS signing parameters
    mock_blob.generate_signed_url.assert_called_once()
    args, kwargs = mock_blob.generate_signed_url.call_args
    assert kwargs["method"] == "PUT"
    assert kwargs["content_type"] == "application/pdf"
    assert kwargs["headers"] == {"x-goog-content-length-range": "0,52428800"}

@pytest.mark.asyncio
async def test_generate_upload_session_url_input_validation_failed():
    """Verify that malformed or unwhitelisted parameters are instantly blocked."""
    mock_ctx = MagicMock()
    
    # 1. Malformed application ID (path traversal)
    result = await generate_upload_session_url(
        application_id="../../../../etc/passwd",
        claimed_artifact_type="W2",
        session_id="session-xyz-789",
        ctx=mock_ctx
    )
    assert "Access Denied: Invalid Application ID format." in result
    
    # 2. Unwhitelisted document type
    result = await generate_upload_session_url(
        application_id="app-999",
        claimed_artifact_type="TAX_RETURN_UNSUPPORTED",
        session_id="session-xyz-789",
        ctx=mock_ctx
    )
    assert "is unsupported." in result
@pytest.mark.asyncio
@patch("routers.mcp.loan._extract_customer_identity")
@patch("routers.mcp.loan.storage.Client")
async def test_generate_upload_session_url_image_success(mock_storage, mock_identity, mock_bq_client):
    """Verify successful dynamic GCS path resolution and cryptographic signed URL for image uploads."""
    mock_identity.return_value = "borrower@argolis.solutions"
    
    # Mock BQ app ownership check
    mock_row = MagicMock()
    mock_row.artifact_id = "artifact-123"
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = [mock_row]
    mock_bq_client.query.return_value = mock_query_job
    
    # Mock GCS blob and client
    mock_blob = MagicMock()
    mock_blob.generate_signed_url.return_value = "https://storage.googleapis.com/mock-png-signed-url"
    
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    storage_client = MagicMock()
    storage_client.bucket.return_value = mock_bucket
    mock_storage.return_value = storage_client
    
    mock_ctx = MagicMock()
    result = await generate_upload_session_url(
        application_id="app-999",
        claimed_artifact_type="W2",
        session_id="session-xyz-789",
        content_type="image/png",
        ctx=mock_ctx
    )
    
    assert "🔒 Secure Document Upload Session Generated" in result
    assert "https://storage.googleapis.com/mock-png-signed-url" in result
    assert "accepts image/png format uploads" in result
    
    # Verify correct dynamic path mapping (png extension resolved!)
    mock_bucket.blob.assert_called_once_with("incoming/app-999/w2.png")
    
    # Verify GCS cryptographic signed headers binding
    mock_blob.generate_signed_url.assert_called_once()
    args, kwargs = mock_blob.generate_signed_url.call_args
    assert kwargs["content_type"] == "image/png"

@pytest.mark.asyncio
async def test_generate_upload_session_url_invalid_mime_failed():
    """Verify that unwhitelisted MIME formats are blocked immediately."""
    mock_ctx = MagicMock()
    result = await generate_upload_session_url(
        application_id="app-999",
        claimed_artifact_type="W2",
        session_id="session-xyz-789",
        content_type="image/gif", # Unwhitelisted MIME type
        ctx=mock_ctx
    )
    assert "Access Denied: File format 'image/gif' is unsupported." in result
