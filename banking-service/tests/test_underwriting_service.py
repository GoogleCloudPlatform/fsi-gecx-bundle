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

import json
import uuid
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from utils.database import Base
from models.origination import ApplicationArtifact, Application
from models.identity import User
from models.underwriting import UnderwritingOverrideRequest, UnderwritingDecision, DocumentVerificationStatus
from services.underwriting import (
    get_pending_exceptions,
    apply_underwriting_override,
    UnderwritingConflictError
)

@pytest.fixture(scope="function")
def test_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def attach_sqlite_schemas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        for stmt in [
            "ATTACH DATABASE 'file:identity_repo_uw?mode=memory&cache=shared' AS identity;",
            "ATTACH DATABASE 'file:origination_repo_uw?mode=memory&cache=shared' AS origination;",
            "ATTACH DATABASE 'file:audit_repo_uw?mode=memory&cache=shared' AS audit;",
            "ATTACH DATABASE 'file:kyc_repo_uw?mode=memory&cache=shared' AS kyc;",
            "ATTACH DATABASE 'file:ledger_repo_uw?mode=memory&cache=shared' AS ledger;",
            "ATTACH DATABASE 'file:cards_repo_uw?mode=memory&cache=shared' AS cards;",
            "ATTACH DATABASE 'file:operations_repo_uw?mode=memory&cache=shared' AS operations;",
            "ATTACH DATABASE 'file:admin_repo_uw?mode=memory&cache=shared' AS admin;",
            "ATTACH DATABASE 'file:catalog_repo_uw?mode=memory&cache=shared' AS catalog;",
            "ATTACH DATABASE 'file:ref_data_repo_uw?mode=memory&cache=shared' AS ref_data;",
        ]:
            try:
                cursor.execute(stmt)
            except Exception:
                pass
        cursor.close()
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    with patch("utils.database.SessionLocal", return_value=session):
        yield session
    session.close()
    Base.metadata.drop_all(bind=engine)

def _seed_artifact(session, artifact_id="art-1", status="MISMATCH", version_id="version-abc"):
    u_id = uuid.uuid4()
    app_id = uuid.uuid4()
    user = User(id=u_id, email="test@example.com", first_name="Test", last_name="User", auth_provider_uid="cust-1")
    app = Application(id=app_id, application_id="app-1", user_id=u_id, status="SUBMITTED", product_category="MORTGAGE", requested_amount_cents=10000000)
    art = ApplicationArtifact(
        artifact_id=artifact_id,
        application_id=app_id,
        customer_id=u_id,
        claimed_artifact_type="W2",
        actual_artifact_type="W2",
        status=status,
        gcs_uri=f"gs://bucket/{artifact_id}.pdf",
        extraction_payload=json.dumps({"W2": {"WagesTipsOtherCompensation": {"value": "45000", "confidence": 0.72}}}),
        audit_metadata=json.dumps({"flagged_fields": ["w2.wagestipsothercompensation"]}),
        version_id=version_id
    )
    session.add(user)
    session.add(app)
    session.add(art)
    session.commit()
    return art, u_id, app_id

def test_get_pending_exceptions_success(test_db):
    """Verify that exceptions are fetched and parsed to DocumentSummaryResponse successfully."""
    _seed_artifact(test_db, "art-1", "MISMATCH")
    exceptions = get_pending_exceptions("mock_project.mock_dataset.application_artifact", db=test_db)
    assert len(exceptions) == 1
    record = exceptions[0]
    assert record.artifact_id == "art-1"
    assert record.status == "MISMATCH"
    assert "W2" in record.extraction_payload

def test_apply_underwriting_override_success(test_db):
    """Verify successful manual underwriting override with deep merges and OCC."""
    art, u_id, app_id = _seed_artifact(test_db, "art-1", "MISMATCH", "version-abc")
    request = UnderwritingOverrideRequest(
        artifact_id="art-1",
        customer_id=str(u_id),
        decision=UnderwritingDecision.APPROVE,
        verifications=DocumentVerificationStatus(
            ssn_verified=True,
            employer_verified=True,
            calculated_gross_monthly_income=3750.0
        ),
        corrected_payload={"WagesTipsOtherCompensation": "48000"},
        underwriter_notes="Pretax income verified.",
        underwriter_id="officer-777",
        expected_version_id="version-abc"
    )
    success = apply_underwriting_override("mock_table", request, db=test_db)
    assert success is True
    test_db.refresh(art)
    assert art.status == "PROCESSED"
    audit = json.loads(art.audit_metadata)
    assert len(audit["underwriting_overrides"]) == 1
    assert audit["underwriting_overrides"][0]["underwriter_id"] == "officer-777"

def test_apply_underwriting_override_occ_conflict(test_db):
    """Verify that OCC status conflicts raise UnderwritingConflictError."""
    art, u_id, app_id = _seed_artifact(test_db, "art-1", "PROCESSED", "version-abc")
    request = UnderwritingOverrideRequest(
        artifact_id="art-1",
        customer_id=str(u_id),
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
    with pytest.raises(UnderwritingConflictError, match="already in state: PROCESSED"):
        apply_underwriting_override("mock_table", request, db=test_db)

def test_get_artifact_gcs_path_success(test_db):
    """Verify that get_artifact_gcs_path correctly retrieves the GCS path from PostgreSQL."""
    _seed_artifact(test_db, "art-1", "MISMATCH")
    from services.underwriting import get_artifact_gcs_path
    gcs_path = get_artifact_gcs_path("mock_table", "art-1", db=test_db)
    assert gcs_path == "gs://bucket/art-1.pdf"

def test_underwriting_endpoints_routing(test_db):
    """Verify HTTP APIRouter mappings (GET /exceptions and POST /override)."""
    from main import app
    from utils.auth import get_current_user
    from models.authentication import ValidatedToken
    from utils.database import get_db
    
    art, u_id, app_id = _seed_artifact(test_db, "art-1", "MISMATCH", "version-abc")

    app.dependency_overrides[get_current_user] = lambda: ValidatedToken(
        claims={
            "identifier": "officer-999",
            "email": "underwriter@nova.horizon",
            "name": "Test Officer"
        }
    )
    app.dependency_overrides[get_db] = lambda: test_db
    client = TestClient(app)

    # 1. Test GET /exceptions
    response = client.get("/underwriting/exceptions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["artifact_id"] == "art-1"

    # 2. Test POST /override (Success)
    payload = {
        "artifact_id": "art-1",
        "customer_id": str(u_id),
        "decision": "APPROVE",
        "verifications": {
            "ssn_verified": True,
            "employer_verified": True,
            "calculated_gross_monthly_income": 5000.0
        },
        "corrected_payload": {"WagesTipsOtherCompensation": "60000"},
        "underwriter_notes": "All matched perfectly.",
        "underwriter_id": "officer-999",
        "expected_version_id": "version-abc"
    }

    response = client.post("/underwriting/override", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"

    # 3. Test POST /override (OCC Conflict 409 because state is now PROCESSED)
    response = client.post("/underwriting/override", json=payload)
    assert response.status_code == 409
    assert "already in state: PROCESSED" in response.json()["detail"]

    # 4. Test GET /artifacts/{artifact_id}/view (Success)
    mock_blob = MagicMock()
    mock_blob.generate_signed_url.return_value = "https://fake-gcs-signed-url.com/file.pdf?token=xyz"
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_storage_client = MagicMock()
    mock_storage_client.bucket.return_value = mock_bucket
    with patch("routers.underwriting.storage_client", mock_storage_client), \
         patch("routers.underwriting.default", return_value=(MagicMock(), "local-test-project")), \
         patch("routers.underwriting.ImpersonatedCredentials", return_value=MagicMock()):
        response = client.get("/underwriting/artifacts/art-1/view")
        assert response.status_code == 200
        assert response.json()["signed_url"] == "https://fake-gcs-signed-url.com/file.pdf?token=xyz"

    app.dependency_overrides.clear()

def test_apply_underwriting_override_version_mismatch(test_db):
    """Verify that a mismatch between expected_version_id and actual version_id raises UnderwritingConflictError."""
    art, u_id, app_id = _seed_artifact(test_db, "art-1", "PENDING_REVIEW", "version-abc")
    request = UnderwritingOverrideRequest(
        artifact_id="art-1",
        customer_id=str(u_id),
        decision=UnderwritingDecision.APPROVE,
        verifications=DocumentVerificationStatus(
            ssn_verified=True,
            employer_verified=True,
            calculated_gross_monthly_income=4000.0
        ),
        corrected_payload={"WagesTipsOtherCompensation": "48000"},
        underwriter_notes="Duplicate clear attempt.",
        underwriter_id="officer-777",
        expected_version_id="version-xyz"  # Client expects xyz, but DB has abc!
    )
    with pytest.raises(UnderwritingConflictError, match="updated or accepted by another loan officer"):
        apply_underwriting_override("mock_table", request, db=test_db)
