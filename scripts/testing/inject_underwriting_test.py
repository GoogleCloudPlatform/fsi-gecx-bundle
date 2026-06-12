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
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from google.cloud import storage, bigquery

# Resolve top-level banking-service directory from scripts/testing context
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = REPO_ROOT / "banking-service"
sys.path.append(str(BACKEND_DIR))

from utils.gcp import get_project_id  # noqa: E402

def main():
    print("Initializing Visual Underwriting Mock Exception Injector...")
    project_id = get_project_id()
    print(f"Resolved Active Project ID: {project_id}")

    # 1. Retrieve dynamic GCS bucket name from Terraform outputs
    tf_dir = REPO_ROOT / "deployment" / "terraform"
    print(f"Reading Terraform outputs from: {tf_dir}")
    try:
        tf_process = subprocess.run(
            ["terraform", "output", "-json"],
            cwd=str(tf_dir),
            capture_output=True,
            text=True,
            check=True
        )
        tf_outputs = json.loads(tf_process.stdout)
        bucket_name = tf_outputs["banking_interaction_artifacts_bucket"]["value"]
        print(f"Resolved Live GCS Bucket: {bucket_name}")
    except Exception as e:
        print(f"Error: Failed to load Terraform outputs: {e}")
        print("Please ensure you run 'terraform init' first.")
        sys.exit(1)

    # 2. Upload the local Sample W-2 PDF to GCS
    local_pdf = BACKEND_DIR / "tests" / "data" / "Sample-W2.pdf"
    gcs_blob_name = "test-exceptions/Sample-W2.pdf"
    
    if not local_pdf.exists():
        print(f"Error: Local sample PDF not found at: {local_pdf}")
        sys.exit(1)

    print(f"Uploading local W-2 PDF '{local_pdf.name}' to GCS bucket...")
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(gcs_blob_name)
    blob.upload_from_filename(str(local_pdf), content_type="application/pdf")
    print(f"Successfully uploaded to GCS path: gs://{bucket_name}/{gcs_blob_name}")

    # 3. Ingress Mock exceptions rows into BigQuery
    print("Connecting to BigQuery to ingress mock exceptions...")
    bq_client = bigquery.Client()
    dataset_id = os.getenv("DATASET_ID", "banking")
    table_id = "interaction_artifacts_v2"
    table_ref = f"{project_id}.{dataset_id}.{table_id}"

    # We assign the customer_id to 'erikvoit@google.com' so it matches your logged-in portal credentials!
    target_customer_id = "erikvoit@google.com"
    file_path_gcs = f"gs://{bucket_name}/{gcs_blob_name}"
    current_timestamp = datetime.now(timezone.utc).isoformat()

    mock_exceptions = [
        {
            "artifact_id": "exception-ssn-111",
            "customer_id": target_customer_id,
            "application_id": "app-ssn-101",
            "claimed_artifact_type": "W2",
            "actual_artifact_type": "W2",
            "status": "MISMATCH",
            "file_path_gcs": file_path_gcs,
            "extraction_payload": json.dumps({
                "W2": {
                    "WagesTipsOtherCompensation": {"value": "75000.00", "confidence": 0.98},
                    "FederalIncomeTaxWithheld": {"value": "15000.00", "confidence": 0.95},
                    "SocialSecurityTaxWithheld": {"value": "4650.00", "confidence": 0.92},
                    "SSN": {"value": "123-45-6789", "confidence": 0.45}  # Low-confidence SSN!
                }
            }),
            "audit_metadata": json.dumps({
                "flagged_fields": ["w2.ssn"],
                "low_confidence_triggers": ["w2.ssn"]
            }),
            "uploaded_at": current_timestamp
        },
        {
            "artifact_id": "exception-wages-222",
            "customer_id": target_customer_id,
            "application_id": "app-wages-202",
            "claimed_artifact_type": "W2",
            "actual_artifact_type": "W2",
            "status": "MISMATCH",
            "file_path_gcs": file_path_gcs,
            "extraction_payload": json.dumps({
                "W2": {
                    "WagesTipsOtherCompensation": {"value": "42000.00", "confidence": 0.52},  # Low-confidence Wages!
                    "FederalIncomeTaxWithheld": {"value": "8000.00", "confidence": 0.95},
                    "SocialSecurityTaxWithheld": {"value": "2600.00", "confidence": 0.92},
                    "SSN": {"value": "987-65-4321", "confidence": 0.98}
                }
            }),
            "audit_metadata": json.dumps({
                "flagged_fields": ["w2.wagestipsothercompensation"],
                "low_confidence_triggers": ["w2.wagestipsothercompensation"]
            }),
            "uploaded_at": current_timestamp
        }
    ]

    print(f"Ingressing {len(mock_exceptions)} rows into {table_ref} BigQuery table...")
    errors = bq_client.insert_rows_json(table_ref, mock_exceptions)
    
    if errors:
        print(f"Error: BigQuery row insertion failed: {errors}")
        sys.exit(1)

    print("\n🎉 Success! Mock exceptions successfully ingressed in BigQuery!")
    print(f"  -> Target Customer Profile: {target_customer_id}")
    print("  -> Exception Artifact 1: exception-ssn-111 (SSN Low-Confidence Trigger)")
    print("  -> Exception Artifact 2: exception-wages-222 (Wages Low-Confidence Trigger)")
    print("\nOpen your Underwriting GUI browser, refresh, and launch the review session!")

if __name__ == "__main__":
    main()
