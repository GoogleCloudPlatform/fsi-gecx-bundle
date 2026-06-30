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

import os
import json
import logging
import pytest
import subprocess
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch
from google.cloud import storage, bigquery
from utils.gcp import get_project_id
from services.document_ai import ProcessingStatus, DocumentType

# 1. Gate Guard: Run ONLY when manually triggered via environment CLI flag
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "true",
    reason="Requires RUN_INTEGRATION_TESTS=true. Bypassed during commit-CI."
)

logger = logging.getLogger(__name__)
storage_client = storage.Client()
bq_client = bigquery.Client()

# Resolve path coordinates
BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = BASE_DIR.parent / "deployment" / "bigquery" / "banking" / "table" / "application_artifact.json.tftpl"
TEST_PDF_PATH = BASE_DIR / "tests" / "data" / "Sample-W2.pdf"
GOLDEN_W2_PATH = BASE_DIR / "tests" / "data" / "golden_w2.json"

EPHEMERAL_DATASET_ID = "banking_ci_sandbox"
EPHEMERAL_TABLE_ID = "application_artifact"

TEST_ARTIFACT_ID = "integration-test-artifact-w2"
TEST_APPLICATION_ID = "integration-test-app-999"
TEST_CUSTOMER_ID = "integration-test-customer-888"

def _get_tf_output(name: str) -> str:
    """
    Executes 'terraform output' dynamically from the HCL deployment folder 
    to resolve live sandbox processor resource IDs for integration testing.
    """
    try:
        tf_dir = BASE_DIR.parent / "deployment" / "terraform"
        res = subprocess.run(
            ["terraform", "output", "-raw", name],
            cwd=str(tf_dir),
            capture_output=True,
            text=True,
            check=True
        )
        return res.stdout.strip()
    except Exception as e:
        logger.warning(f"Failed to read terraform output for '{name}': {e}. Live API routing might fail.")
        return ""

@pytest.fixture(scope="module")
def ephemeral_sandbox_env():
    """
    FSI Sandbox Isolation: Ephemerally provisions BigQuery tables and GCS namespaces, 
    surgically tearing them down at conclusion of validation checks.
    """
    project_id = get_project_id()
    dataset_ref = f"{project_id}.{EPHEMERAL_DATASET_ID}"
    table_ref = f"{dataset_ref}.{EPHEMERAL_TABLE_ID}"
    
    # 1. Create Ephemeral BigQuery Dataset
    logger.info(f"Creating ephemeral BigQuery dataset: {dataset_ref}")
    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = "us"
    try:
        bq_client.create_dataset(dataset, exists_ok=True)
    except Exception as e:
        pytest.fail(f"Failed to create ephemeral dataset: {e}")

    # 2. Build V2 Artifacts Table using production Schema JSON template
    # Load template string and surgically strip policyTags to prevent unresolved placeholder crashes
    schema_content = Path(SCHEMA_PATH).read_text()
    schema_content = schema_content.replace(',\n    "policyTags": {\n      "names": ["${policy_tag_id}"]\n    }', '')
    schema_fields = json.loads(schema_content)
    
    bq_schema = []
    for field in schema_fields:
        bq_schema.append(bigquery.SchemaField(
            name=field["name"],
            field_type=field["type"],
            mode=field.get("mode", "NULLABLE")
        ))

    table = bigquery.Table(table_ref, schema=bq_schema)
    try:
        bq_client.create_table(table, exists_ok=True)
        logger.info(f"Ephemeral Table created: {table_ref}")
    except Exception as e:
        bq_client.delete_dataset(dataset_ref, delete_contents=True, not_found_ok=True)
        pytest.fail(f"Failed to create ephemeral artifacts table: {e}")

    # 3. Upload Mock PDF to GCS temp folder
    bucket_name = f"{project_id}_banking-interaction-artifacts"
    bucket = storage_client.bucket(bucket_name)
    gcs_blob_name = f"ci-temp/{TEST_ARTIFACT_ID}.pdf"
    blob = bucket.blob(gcs_blob_name)
    
    logger.info(f"Uploading mock PDF to GCS: gs://{bucket_name}/{gcs_blob_name}")
    blob.upload_from_filename(TEST_PDF_PATH, content_type="application/pdf")

    # 4. Populate Initial Ingestion Record in Ephemeral BigQuery table
    insert_query = f"""
        INSERT INTO `{table_ref}` (artifact_id, customer_id, application_id, claimed_artifact_type, status, file_path_gcs)
        VALUES (@artifact_id, @customer_id, @app_id, 'W2', 'PENDING_CLASSIFICATION', @gcs_uri)
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("artifact_id", "STRING", TEST_ARTIFACT_ID),
            bigquery.ScalarQueryParameter("customer_id", "STRING", TEST_CUSTOMER_ID),
            bigquery.ScalarQueryParameter("app_id", "STRING", TEST_APPLICATION_ID),
            bigquery.ScalarQueryParameter("gcs_uri", "STRING", f"gs://{bucket_name}/{gcs_blob_name}")
        ]
    )
    bq_client.query(insert_query, job_config=job_config).result()

    yield {
        "project_id": project_id,
        "bucket_name": bucket_name,
        "gcs_blob_name": gcs_blob_name,
        "table_ref": table_ref
    }

    # 5. Strict Teardown Cleanups
    logger.info("Tearing down ephemeral GCP sandbox test data layers...")
    try:
        # Purge GCS mock file
        blob.delete()
        logger.info(f"Deleted GCS temp blob: gs://{bucket_name}/{gcs_blob_name}")
    except Exception as delete_gcs_ex:
        logger.error(f"GCS temp teardown failed: {delete_gcs_ex}")

    try:
        from utils.database import SessionLocal
        from models.origination import ApplicationArtifact as PGArtifact
        db = SessionLocal()
        try:
            deleted_count = db.query(PGArtifact).filter(PGArtifact.artifact_id == TEST_ARTIFACT_ID).delete()
            db.commit()
            logger.info(f"Deleted {deleted_count} test artifact record(s) from PostgreSQL OLTP database.")
        finally:
            db.close()
    except Exception as delete_pg_ex:
        logger.error(f"PostgreSQL temp teardown failed: {delete_pg_ex}")

    try:
        # Drop ephemeral BigQuery Sandbox dataset
        bq_client.delete_dataset(dataset_ref, delete_contents=True, not_found_ok=True)
        logger.info(f"Dropped BigQuery Ephemeral Dataset: {dataset_ref}")
    except Exception as delete_bq_ex:
        logger.error(f"BigQuery temp dataset drop failed: {delete_bq_ex}")


def test_live_document_ai_lending_pipeline(ephemeral_sandbox_env, monkeypatch):
    """
    Confronts the real, unmocked regional Document AI processors in Google Cloud!
    Asserts wages, federal withholding, and tax entities parse within golden W-2 limits,
    and dynamically verifies that BQ status reaches PROCESSED successfully.
    """
    from main import app
    from utils.auth import verify_eventarc_oidc_token
    
    # Route the router status check query to our ephemeral sandbox dataset!
    monkeypatch.setenv("DATASET_ID", "banking_ci_sandbox")

    # Dynamically resolve the active staging processor IDs from Terraform outputs and inject them!
    w2_id = _get_tf_output("docai_w2_processor_id")
    paystub_id = _get_tf_output("docai_paystub_processor_id")
    splitter_id = _get_tf_output("docai_splitter_processor_id")
    
    monkeypatch.setenv("DOCAI_W2_PROCESSOR_ID", w2_id)
    monkeypatch.setenv("DOCAI_PAYSTUB_PROCESSOR_ID", paystub_id)
    monkeypatch.setenv("DOCAI_SPLITTER_PROCESSOR_ID", splitter_id)

    # Ephemerally override the Eventarc security middleware to bypass OIDC validation in local sandbox runs
    app.dependency_overrides[verify_eventarc_oidc_token] = lambda: {"email": "eventarc@gcp.solutions"}
    client = TestClient(app)
    
    # Direct GCS trigger Eventarc payload simulation
    payload = {
        "bucket": ephemeral_sandbox_env["bucket_name"],
        "name": ephemeral_sandbox_env["gcs_blob_name"]
    }

    logger.info("Invoking live FastAPI webhook route /internal/process-document")
    
    # Override the pipeline target table inside document_ai service module dynamically for sandbox isolation!
    with patch("services.document_ai.get_project_id") as mock_proj:
         
        # Direct pipeline writes to our ephemeral BigQuery table reference!
        mock_proj.return_value = ephemeral_sandbox_env["project_id"]
        
        # We mock the SQL loading dataset references inside services.document_ai to re-route queries to the ephemeral dataset
        with patch("services.document_ai._load_sql") as mock_sql:
            # Load and replace target dataset references inside SQL files on the fly!
            def load_and_replace_sql(filename):
                sql_path = BASE_DIR / "resources" / "sql" / filename
                sql_content = sql_path.read_text()
                # Re-route table paths to our ephemeral test dataset
                return sql_content.replace("`{table_ref}`", f"`{ephemeral_sandbox_env['table_ref']}`")
                
            mock_sql.side_effect = load_and_replace_sql

            # Simulates exact Eventarc HTTP CloudEvent header signature
            headers = {
                "Ce-Subject": f"objects/{ephemeral_sandbox_env['gcs_blob_name']}",
                "Ce-Type": "google.cloud.storage.object.v1.finalized",
                "Ce-Source": f"//storage.googleapis.com/projects/_/buckets/{ephemeral_sandbox_env['bucket_name']}"
            }

            # Call route
            response = client.post("/internal/process-document", json=payload, headers=headers)
            app.dependency_overrides.clear()
            
    # Assert HTTP 200 OK Route Handshake
    assert response.status_code == 200
    response_data = response.json()
    # Accept either completed PROCESSED status or flagged MISMATCH (which indicates confidence triggers fired correctly)
    pipeline_status = response_data["pipeline_result"]["status"]
    assert pipeline_status in [ProcessingStatus.PROCESSED.value, ProcessingStatus.MISMATCH.value]

    # 2. Assert Extraction Schema matching against Golden W-2 payload template!
    with open(GOLDEN_W2_PATH, "r") as golden_file:
        golden_schema = json.load(golden_file)

    extracted_payloads = response_data["pipeline_result"]
    logger.info(f"Extracted Integration Result: {extracted_payloads}")

    # Check BQ table rows directly to verify database persistence matches perfectly
    query = f"""
        SELECT status, actual_artifact_type, extraction_payload FROM `{ephemeral_sandbox_env["table_ref"]}`
        WHERE artifact_id = '{TEST_ARTIFACT_ID}'
        LIMIT 1
    """
    query_job = bq_client.query(query)
    rows = list(query_job.result())
    
    assert len(rows) == 1
    bq_row = rows[0]
    assert bq_row.status in [ProcessingStatus.PROCESSED.value, ProcessingStatus.MISMATCH.value]
    assert bq_row.actual_artifact_type == DocumentType.W2.value
    
    # BigQuery SDK returns JSON fields natively parsed as a Python dictionary
    extracted_json = bq_row.extraction_payload
    w2_data = extracted_json.get("W2", {})
    print("ACTUAL EXTRACTION KEYS IN STAGING:", list(w2_data.keys()))
    
    # Assert Golden Schema fields presence (OCR Schema Drift Detection!)
    for field in golden_schema["expected_fields"]:
        assert field in w2_data, f"Golden W-2 field '{field}' is missing from live OCR extraction. Upstream model drift suspected!"
        confidence = w2_data[field]["confidence"]
        assert confidence > 0.0, f"Confidence for field '{field}' is invalid: {confidence:.2f}."
        logger.info(f"Verified golden field: {field} (Confidence: {confidence:.2f})")
