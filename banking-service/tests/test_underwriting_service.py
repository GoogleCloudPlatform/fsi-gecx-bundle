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
from fastapi.testclient import TestClient
from models.underwriting import UnderwritingOverrideRequest, UnderwritingDecision, DocumentVerificationStatus
from services.underwriting import (
    get_pending_exceptions,
    apply_underwriting_override,
    UnderwritingConflictError
)

@pytest.fixture
def mock_bq_client():
    """Mock BigQuery Client fixture."""
    with patch("services.underwriting.bq_client") as mock_bq:
        yield mock_bq

def test_get_pending_exceptions_success(mock_bq_client):
    """Verify that exceptions are fetched and parsed to DocumentSummaryResponse successfully."""
    # Mock BigQuery row payload
    mock_row = MagicMock()
    mock_row.artifact_id = "art-1"
    mock_row.customer_id = "cust-1"
    mock_row.application_id = "app-1"
    mock_row.claimed_artifact_type = "W2"
    mock_row.actual_artifact_type = "W2"
    mock_row.status = "MISMATCH"
    mock_row.file_path_gcs = "gs://bucket/art-1.pdf"
    mock_row.extraction_payload = {"W2": {"WagesTipsOtherCompensation": {"value": "45000", "confidence": 0.72}}}
    mock_row.audit_metadata = {"flagged_fields": ["w2.wagestipsothercompensation"]}
    mock_row.verification_tier = None
    mock_row.version_id = None
    mock_row.user_first_name = None
    mock_row.user_last_name = None
    mock_row.user_email = None
    mock_row.requested_amount = None
    mock_row.product_category = None
    mock_row.product_type = None
    
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = [mock_row]
    mock_bq_client.query.return_value = mock_query_job

    exceptions = get_pending_exceptions("mock_project.mock_dataset.application_artifact")

    
    assert len(exceptions) == 1
    record = exceptions[0]
    assert record.artifact_id == "art-1"
    assert record.customer_id == "cust-1"
    assert record.status == "MISMATCH"
    assert "W2" in record.extraction_payload
    assert record.audit_metadata["flagged_fields"] == ["w2.wagestipsothercompensation"]

def test_apply_underwriting_override_success(mock_bq_client):
    """Verify successful manual underwriting override with deep merges and OCC."""
    # 1. Mock BQ select original record row
    mock_row = MagicMock()
    mock_row.status = "MISMATCH"
    mock_row.actual_artifact_type = "W2"
    mock_row.claimed_artifact_type = "W2"
    mock_row.extraction_payload = {"W2": {"WagesTipsOtherCompensation": {"value": "45000", "confidence": 0.72}}}
    mock_row.audit_metadata = {"flagged_fields": ["w2.wagestipsothercompensation"]}
    
    mock_select_job = MagicMock()
    mock_select_job.result.return_value = [mock_row]
    
    # 2. Mock BQ update update record row
    mock_update_job = MagicMock()
    mock_update_job.num_dml_affected_rows = 1  # Successful OCC write!
    
    mock_bq_client.query.side_effect = [mock_select_job, mock_update_job]

    request = UnderwritingOverrideRequest(
        artifact_id="art-1",
        customer_id="cust-1",
        decision=UnderwritingDecision.APPROVE,
        verifications=DocumentVerificationStatus(
            ssn_verified=True,
            employer_verified=True,
            calculated_gross_monthly_income=3750.0
        ),
        corrected_payload={"WagesTipsOtherCompensation": "48000"},
        underwriter_notes="Pretax income verified.",
        underwriter_id="officer-777"
    )

    success = apply_underwriting_override("mock_table", request)
    assert success is True
    assert mock_bq_client.query.call_count == 2

    # Verify FSI chronological audit trail array was populated successfully
    assert "underwriting_overrides" in mock_row.audit_metadata
    assert len(mock_row.audit_metadata["underwriting_overrides"]) == 1
    trace = mock_row.audit_metadata["underwriting_overrides"][0]
    assert trace["underwriter_id"] == "officer-777"
    assert trace["decision"] == "APPROVE"
    assert trace["corrected_fields"] == ["WagesTipsOtherCompensation"]

def test_apply_underwriting_override_occ_conflict(mock_bq_client):
    """Verify that OCC conflicts raise UnderwritingConflictError."""
    # 1. Mock BQ select original record row
    mock_row = MagicMock()
    mock_row.status = "MISMATCH"
    mock_row.actual_artifact_type = "W2"
    mock_row.extraction_payload = {}
    mock_row.audit_metadata = {}
    
    mock_select_job = MagicMock()
    mock_select_job.result.return_value = [mock_row]
    
    # 2. Mock BQ update returning 0 affected rows (OCC conflict!)
    mock_update_job = MagicMock()
    mock_update_job.num_dml_affected_rows = 0
    
    mock_bq_client.query.side_effect = [mock_select_job, mock_update_job]

    request = UnderwritingOverrideRequest(
        artifact_id="art-1",
        customer_id="cust-1",
        decision=UnderwritingDecision.APPROVE,
        verifications=DocumentVerificationStatus(
            ssn_verified=True,
            employer_verified=True,
            calculated_gross_monthly_income=4000.0
        ),
        corrected_payload={"WagesTipsOtherCompensation": "48000"},
        underwriter_notes="Duplicate clear attempt.",
        underwriter_id="officer-777"
    )

    with pytest.raises(UnderwritingConflictError, match="This record was updated or approved by another officer"):
        apply_underwriting_override("mock_table", request)

def test_get_artifact_gcs_path_success(mock_bq_client):
    """Verify that get_artifact_gcs_path correctly retrieves the GCS path from BQ."""
    mock_row = MagicMock()
    mock_row.file_path_gcs = "gs://bucket/test-file.pdf"
    
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = [mock_row]
    mock_bq_client.query.return_value = mock_query_job

    from services.underwriting import get_artifact_gcs_path
    gcs_path = get_artifact_gcs_path("mock_table", "art-1")
    assert gcs_path == "gs://bucket/test-file.pdf"


def test_underwriting_endpoints_routing(mock_bq_client):
    """Verify HTTP APIRouter mappings (GET /exceptions and POST /override)."""
    from main import app
    from utils.auth import get_current_user
    from models.authentication import ValidatedToken
    
    # Override security dependencies ephemerally
    app.dependency_overrides[get_current_user] = lambda: ValidatedToken(
        claims={
            "identifier": "officer-999",
            "email": "underwriter@nova.horizon",
            "name": "Test Officer"
        }
    )
    client = TestClient(app)

    # 1. Test GET /exceptions
    mock_row = MagicMock()
    mock_row.artifact_id = "art-1"
    mock_row.customer_id = "cust-1"
    mock_row.application_id = "app-123"
    mock_row.claimed_artifact_type = "W2"
    mock_row.actual_artifact_type = "W2"
    mock_row.status = "MISMATCH"
    mock_row.file_path_gcs = "gs://bucket/art-1.pdf"
    mock_row.extraction_payload = {}
    mock_row.audit_metadata = {}
    mock_row.verification_tier = None
    mock_row.version_id = None
    mock_row.user_first_name = None
    mock_row.user_last_name = None
    mock_row.user_email = None
    mock_row.requested_amount = None
    mock_row.product_category = None
    mock_row.product_type = None
    
    mock_select_job = MagicMock()
    mock_select_job.result.return_value = [mock_row]
    mock_bq_client.query.return_value = mock_select_job

    response = client.get("/underwriting/exceptions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["artifact_id"] == "art-1"

    # 2. Test POST /override (Success)
    mock_update_job = MagicMock()
    mock_update_job.num_dml_affected_rows = 1
    mock_bq_client.query.side_effect = [mock_select_job, mock_update_job]

    payload = {
        "artifact_id": "art-1",
        "customer_id": "cust-1",
        "decision": "APPROVE",
        "verifications": {
            "ssn_verified": True,
            "employer_verified": True,
            "calculated_gross_monthly_income": 5000.0
        },
        "corrected_payload": {"WagesTipsOtherCompensation": "60000"},
        "underwriter_notes": "All matched perfectly.",
        "underwriter_id": "officer-999"
    }

    response = client.post("/underwriting/override", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"

    # 3. Test POST /override (OCC Conflict 409)
    mock_update_job.num_dml_affected_rows = 0
    mock_bq_client.query.side_effect = [mock_select_job, mock_update_job]

    response = client.post("/underwriting/override", json=payload)
    assert response.status_code == 409
    assert "updated or approved by another officer" in response.json()["detail"]

    # 4. Test GET /artifacts/{artifact_id}/view (Success)
    mock_bq_client.query.side_effect = None
    mock_bq_client.query.return_value = mock_select_job
    with patch("google.cloud.storage.blob.Blob.generate_signed_url") as mock_sign:
        mock_sign.return_value = "https://fake-gcs-signed-url.com/file.pdf?token=xyz"
        
        response = client.get("/underwriting/artifacts/art-1/view")
        assert response.status_code == 200
        assert response.json()["signed_url"] == "https://fake-gcs-signed-url.com/file.pdf?token=xyz"

    app.dependency_overrides.clear()


def test_apply_underwriting_override_version_mismatch(mock_bq_client):
    """Verify that a mismatch between expected_version_id and actual version_id raises UnderwritingConflictError."""
    mock_row = MagicMock()
    mock_row.status = "PENDING_REVIEW"
    mock_row.actual_artifact_type = "W2"
    mock_row.version_id = "version-abc"
    mock_row.extraction_payload = {}
    mock_row.audit_metadata = {}
    
    mock_select_job = MagicMock()
    mock_select_job.result.return_value = [mock_row]
    mock_bq_client.query.return_value = mock_select_job

    request = UnderwritingOverrideRequest(
        artifact_id="art-1",
        customer_id="cust-1",
        decision=UnderwritingDecision.APPROVE,
        verifications=DocumentVerificationStatus(
            ssn_verified=True,
            employer_verified=True,
            calculated_gross_monthly_income=4000.0
        ),
        corrected_payload={"WagesTipsOtherCompensation": "48000"},
        underwriter_notes="Duplicate clear attempt.",
        underwriter_id="officer-777",
        expected_version_id="version-xyz"  # Client expects xyz, but BQ has abc!
    )

    with pytest.raises(UnderwritingConflictError, match="This exception record was updated or accepted by another loan officer"):
        apply_underwriting_override("mock_table", request)
