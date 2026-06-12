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

from unittest.mock import MagicMock
from google.cloud import bigquery

def test_bq_v2_schema_valid_insert():
    client = MagicMock(spec=bigquery.Client)
    client.insert_rows_json.return_value = []
    
    rows = [
        {
            "artifact_id": "123e4567-e89b-12d3-a456-426614174000",
            "customer_id": "cust_999",
            "application_id": "app_555",
            "claimed_artifact_type": "W2",
            "actual_artifact_type": "W2",
            "classification_confidence": 0.98,
            "status": "PROCESSED",
            "file_path_gcs": "gs://my-bucket/file.pdf",
            "extraction_payload": {"employer_name": {"value": "Acme Corp", "source_snippet": "Acme Corp", "llm_confidence": 0.99}},
            "audit_metadata": {"prompt_version": "1.0", "model_version": "gemini-2.5-flash", "trace_id": "trace_777"}
        }
    ]
    
    errors = client.insert_rows_json("project.dataset.application_artifact", rows)
    assert errors == []

def test_bq_v2_schema_missing_required_fields():
    client = MagicMock(spec=bigquery.Client)
    client.insert_rows_json.return_value = [{"index": 0, "errors": [{"message": "Missing required field: status"}]}]
    
    rows = [
        {
            "artifact_id": "123e4567-e89b-12d3-a456-426614174000",
            "customer_id": "cust_999"
        }
    ]
    
    errors = client.insert_rows_json("project.dataset.application_artifact", rows)

    assert len(errors) == 1
    assert "Missing required field: status" in errors[0]["errors"][0]["message"]
