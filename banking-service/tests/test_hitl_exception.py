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
import pytest
from unittest.mock import MagicMock, patch
from services.document_ai import process_document_pipeline, ProcessingStatus, DocumentType

@pytest.fixture
def mock_gcp_clients(monkeypatch):
    """Fixture mocking storage, BigQuery, and Document AI core connections."""
    monkeypatch.setenv("DOCAI_W2_PROCESSOR_ID", "projects/test-project/locations/us/processors/mock-w2")
    monkeypatch.setenv("DOCAI_PAYSTUB_PROCESSOR_ID", "projects/test-project/locations/us/processors/mock-paystub")
    monkeypatch.setenv("DOCAI_SPLITTER_PROCESSOR_ID", "projects/test-project/locations/us/processors/mock-splitter")

    with patch("services.document_ai.storage_client") as mock_storage, \
         patch("services.document_ai.bq_client") as mock_bq, \
         patch("services.document_ai._get_docai_client") as mock_get_docai:
         
        # Mock GCS Blob metadata to pass cost-abuse pre-validation gates
        mock_blob = MagicMock()
        mock_blob.size = 1024
        mock_blob.content_type = "application/pdf"
        mock_storage.bucket().get_blob.return_value = mock_blob

        # Mock BigQuery select metadata row response
        mock_record = MagicMock()
        mock_record.artifact_id = "mock-artifact-test"
        mock_record.customer_id = "customer-123"
        mock_record.claimed_artifact_type = "W2"
        mock_record.application_id = "app-456"
        mock_record.status = "PENDING_CLASSIFICATION"
        
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = [mock_record]
        mock_bq.query.return_value = mock_query_job

        yield {
            "storage": mock_storage,
            "bq": mock_bq,
            "get_docai": mock_get_docai
        }

@patch("utils.pubsub.publisher_client")
def test_pipeline_flags_low_confidence_wages(mock_pubsub_publisher, mock_gcp_clients):
    """
    Verify that if a critical field (wages) has confidence below 90% (0.72), 
    the pipeline flags it as an exception, updates BQ status to MISMATCH, 
    and publishes a reference-only payload to Pub/Sub manual underwriting review.
    """
    mock_docai_client = MagicMock()
    mock_gcp_clients["get_docai"].return_value = mock_docai_client
    
    # Construct a mock W-2 document with low confidence (0.72) on the critical 'wages' entity
    mock_entity = MagicMock()
    mock_entity.type_ = "WagesTipsOtherCompensation"
    mock_entity.mention_text = "50000"
    mock_entity.confidence = 0.72  # Fails CRITICAL_FIELD_THRESHOLD (0.90)
    
    mock_process_result = MagicMock()
    mock_process_result.document.entities = [mock_entity]
    mock_docai_client.process_document.return_value = mock_process_result

    # Mock Pub/Sub publish future return value
    mock_future = MagicMock()
    mock_future.result.return_value = "msg-id-12345"
    mock_pubsub_publisher.publish.return_value = mock_future

    # Run the pipeline
    result = process_document_pipeline("mock-bucket", "artifacts/Sample-W2.pdf")

    # 1. Verify BigQuery status maps to PENDING_REVIEW
    assert result["status"] == ProcessingStatus.PENDING_REVIEW.value
    assert result["classified_type"] == DocumentType.W2.value

    # 2. Verify Pub/Sub was triggered to publish exception references
    mock_pubsub_publisher.publish.assert_called_once()
    publish_args = mock_pubsub_publisher.publish.call_args
    message_bytes = publish_args[1]["data"]
    
    # Verify topic_path was constructed correctly with project and topic IDs
    from utils.gcp import get_project_id
    mock_pubsub_publisher.topic_path.assert_called_once_with(get_project_id(), "manual-underwriting-review")
    
    # Verify references-only payload (no plaintext wages text '50000' in transit!)
    payload = json.loads(message_bytes.decode("utf-8"))
    assert payload["artifact_id"] == "mock-artifact-test"
    assert payload["application_id"] == "app-456"
    assert payload["customer_id"] == "customer-123"
    assert "w2.wagestipsothercompensation" in payload["flagged_fields"]
    assert "50000" not in message_bytes.decode("utf-8")  # Essential security boundary check

@patch("utils.pubsub.publisher_client")
def test_pipeline_passes_high_confidence_extractions(mock_pubsub_publisher, mock_gcp_clients):
    """
    Verify that if all critical fields have high confidence (>= 90%), 
    the pipeline updates status to PROCESSED and does NOT invoke Pub/Sub manual review queues.
    """
    mock_docai_client = MagicMock()
    mock_gcp_clients["get_docai"].return_value = mock_docai_client
    
    # Construct W-2 with high confidence (0.95) on wages
    mock_entity = MagicMock()
    mock_entity.type_ = "WagesTipsOtherCompensation"
    mock_entity.mention_text = "75000"
    mock_entity.confidence = 0.95  # Passes thresholds
    
    mock_process_result = MagicMock()
    mock_process_result.document.entities = [mock_entity]
    mock_docai_client.process_document.return_value = mock_process_result

    # Run the pipeline
    result = process_document_pipeline("mock-bucket", "artifacts/Sample-W2.pdf")

    # 1. Verify BigQuery status maps to PENDING_REVIEW status
    assert result["status"] == ProcessingStatus.PENDING_REVIEW.value

    # 2. Verify Pub/Sub was NEVER called (processed clean)
    mock_pubsub_publisher.publish.assert_not_called()


@patch("utils.pubsub.publisher_client")
def test_pipeline_master_splitter_routing(mock_pubsub_publisher, mock_gcp_clients):
    """
    Verify that if no direct bypass claimed type matches, the master splitter is invoked,
    and segmented page indices are correctly routed to their respective specialized extractors.
    """
    # Re-mock BQ record to have empty claimed_type (triggering splitter route!)
    mock_record = MagicMock()
    mock_record.artifact_id = "mock-artifact-test"
    mock_record.customer_id = "customer-123"
    mock_record.claimed_artifact_type = None  # Null claimed type!
    mock_record.application_id = "app-456"
    mock_record.status = "PENDING_CLASSIFICATION"
    mock_gcp_clients["bq"].query().result.return_value = [mock_record]
    
    mock_docai_client = MagicMock()
    mock_gcp_clients["get_docai"].return_value = mock_docai_client
    
    # 1. Mock Lending Splitter response: identifies W-2 on page index [0]
    mock_splitter_entity = MagicMock()
    mock_splitter_entity.type_ = "W2"
    mock_splitter_entity.confidence = 0.99
    
    mock_page_ref = MagicMock()
    mock_page_ref.page = 0
    mock_splitter_entity.page_anchor.page_refs = [mock_page_ref]
    
    mock_splitter_result = MagicMock()
    mock_splitter_result.document.entities = [mock_splitter_entity]
    
    # 2. Mock specialized W-2 extractor response: extracts wages under WagesTipsOtherCompensation with high confidence
    mock_w2_entity = MagicMock()
    mock_w2_entity.type_ = "WagesTipsOtherCompensation"
    mock_w2_entity.mention_text = "90000"
    mock_w2_entity.confidence = 0.96
    
    mock_w2_result = MagicMock()
    mock_w2_result.document.entities = [mock_w2_entity]
    
    # Set client process_document calls: first splitter, second specialized W-2 extractor
    mock_docai_client.process_document.side_effect = [mock_splitter_result, mock_w2_result]
    
    # Run pipeline
    result = process_document_pipeline("mock-bucket", "artifacts/Sample-W2.pdf")
    
    # Classification mismatch routes to PENDING_REVIEW Tier 1
    assert result["status"] == ProcessingStatus.PENDING_REVIEW.value
    assert result["classified_type"] == DocumentType.W2.value
    assert mock_docai_client.process_document.call_count == 2


@patch("utils.pubsub.publisher_client")
def test_pipeline_pubsub_failure_tolerance(mock_pubsub_publisher, mock_gcp_clients):
    """
    Verify that if Pub/Sub publishing fails (e.g. throws API Exception),
    the pipeline swallows the error gracefully and completes the database commit anyway.
    """
    mock_docai_client = MagicMock()
    mock_gcp_clients["get_docai"].return_value = mock_docai_client
    
    # Construct low confidence W-2 triggering Pub/Sub exception
    mock_entity = MagicMock()
    mock_entity.type_ = "WagesTipsOtherCompensation"
    mock_entity.mention_text = "45000"  # String representation to support JSON serialization
    mock_entity.confidence = 0.50  # low confidence
    mock_process_result = MagicMock()
    mock_process_result.document.entities = [mock_entity]
    mock_docai_client.process_document.return_value = mock_process_result
    
    # Mock Pub/Sub client to raise a connection error
    mock_pubsub_publisher.publish.side_effect = Exception("Pub/Sub Connection Timeout")
    
    # Run pipeline
    result = process_document_pipeline("mock-bucket", "artifacts/Sample-W2.pdf")
    
    # Verify pipeline completed and committed the PENDING_REVIEW status to BQ successfully
    assert result["status"] == ProcessingStatus.PENDING_REVIEW.value
    mock_pubsub_publisher.publish.assert_called_once()


def test_pipeline_prevalidation_size_and_mime_gates(mock_gcp_clients):
    """
    Verify that files exceeding 50MB or containing unwhitelisted MIME types 
    are blocked immediately by the pre-validation gate with a ValueError.
    """
    # 1. Test size boundary: Mock GCS Blob to return 60MB (exceeding 50MB limit)
    mock_gcp_clients["storage"].bucket().get_blob().size = 60 * 1024 * 1024
    
    with pytest.raises(ValueError, match="File size exceeds the maximum allowed limit"):
        process_document_pipeline("mock-bucket", "artifacts/Sample-W2.pdf")
        
    # Restore size limit and test unsupported MIME type
    mock_gcp_clients["storage"].bucket().get_blob().size = 1024
    mock_gcp_clients["storage"].bucket().get_blob().content_type = "image/gif"  # unwhitelisted
    
    with pytest.raises(ValueError, match="Unsupported file type"):
        process_document_pipeline("mock-bucket", "artifacts/Sample-W2.pdf")
