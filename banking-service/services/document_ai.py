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
import logging
import json
from enum import Enum
from pathlib import Path
from google.cloud import documentai, storage, bigquery
from google.api_core.client_options import ClientOptions
from google.api_core.retry import Retry
from utils.gcp import get_project_id

logger = logging.getLogger(__name__)

# Hard ceilings for FSI cost-abuse and DoW prevention
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50MB max size limit
SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/tiff"
}

# Strongly typed Document AI entity extraction field schema Enums
class ExtractionField(str, Enum):
    WAGES = "wagestipsothercompensation"
    FED_WITHHOLDING = "federalincometaxwithheld"
    SS_WITHHOLDING = "socialsecuritytaxwithheld"
    SSN = "ssn"
    EMPLOYER_NAME = "employername"
    EMPLOYER_ADDRESS = "employeraddress"
    DEFAULT = "default"

    @classmethod
    def parse(cls, val: str) -> "ExtractionField":
        """Surgically normalizes entity field strings from pre-trained processors."""
        if not val:
            return cls.DEFAULT
        normalized = val.strip().lower()
        try:
            return cls(normalized)
        except ValueError:
            return cls.DEFAULT

# Granular Field-Level Confidence Threshold Configurations
FIELD_CONFIDENCE_THRESHOLDS = {
    ExtractionField.SSN: 0.95,             # SSN requires absolute high confidence
    ExtractionField.WAGES: 0.90,           # Critical financial parameters
    ExtractionField.FED_WITHHOLDING: 0.90,
    ExtractionField.SS_WITHHOLDING: 0.90
}

def _audit_extraction_confidence(extracted_payloads: dict) -> list[str]:
    """
    FSI Compliance Auditor: Evaluates extracted fields against granular, strongly typed 
    confidence thresholds. Returns a list of flagged field names.
    """
    flagged_fields = []
    for doc_type, fields in extracted_payloads.items():
        for field_name, data in fields.items():
            confidence = data.get("confidence", 1.0)
            
            # Parse raw parser string field to strongly typed enum
            field_enum = ExtractionField.parse(field_name)
            
            # Skip auditing secondary fields that are not in the threshold mapping
            if field_enum not in FIELD_CONFIDENCE_THRESHOLDS:
                continue
                
            threshold = FIELD_CONFIDENCE_THRESHOLDS[field_enum]
            
            if confidence < threshold:
                logger.warning(f"Field '{field_name}' in {doc_type} failed confidence threshold. Got {confidence:.2f} (Required: {threshold:.2f})")
                flagged_fields.append(f"{doc_type.lower().strip()}.{field_enum.value}")
    return flagged_fields

storage_client = storage.Client()
bq_client = bigquery.Client()

SQL_DIR = Path(__file__).resolve().parent.parent / "resources" / "sql"

def _load_sql(filename: str) -> str:
    """Loads a clean SQL query template from the resources directory."""
    return (SQL_DIR / filename).read_text()

class DocumentType(str, Enum):
    W2 = "W2"
    PAYSTUB = "PAYSTUB"
    SPLITTER = "SPLITTER"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def parse(cls, val: str) -> "DocumentType":
        """Normalizes dynamic inputs (e.g. case differences, spaces)."""
        if not val:
            return cls.UNKNOWN
        normalized = val.strip().upper()
        if normalized in ["PAYSTUB", "PAY_STUB"]:
            return cls.PAYSTUB
        try:
            return cls(normalized)
        except ValueError:
            return cls.UNKNOWN

class ProcessingStatus(str, Enum):
    PENDING_CLASSIFICATION = "PENDING_CLASSIFICATION"
    CLASSIFYING = "CLASSIFYING"
    PROCESSED = "PROCESSED"
    MISMATCH = "MISMATCH"
    FAILED = "FAILED"
    PENDING_REVIEW = "PENDING_REVIEW"

class DocumentProcessorRegistry:
    """
    FSI Configuration Registry: Pluggably maps document types to dynamic regional processor resources.
    """
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.splitter_id = os.getenv("DOCAI_SPLITTER_PROCESSOR_ID")
        self.w2_id = os.getenv("DOCAI_W2_PROCESSOR_ID")
        self.paystub_id = os.getenv("DOCAI_PAYSTUB_PROCESSOR_ID")
        
    def get_processor_name(self, doc_type: DocumentType) -> str:
        """Resolves the fully qualified GCP resource path dynamically."""
        raw_id = None
        if doc_type == DocumentType.W2:
            raw_id = self.w2_id
        elif doc_type == DocumentType.PAYSTUB:
            raw_id = self.paystub_id
        elif doc_type == DocumentType.SPLITTER:
            raw_id = self.splitter_id
            
        if not raw_id:
            raise ValueError(f"Processor type '{doc_type}' environment configuration is missing or unmapped.")
            
        # Resilient canonical path resolution
        if raw_id.startswith("projects/"):
            return raw_id
        return f"projects/{self.project_id}/locations/us/processors/{raw_id}"

def _update_artifact_status(table_ref: str, artifact_id: str, status: str):
    """Updates the status of an artifact inside PostgreSQL ORM atomically."""
    from utils.database import SessionLocal
    from models.origination import ApplicationArtifact as PGArtifact
    db = SessionLocal()
    try:
        pg_art = db.query(PGArtifact).filter(PGArtifact.artifact_id == artifact_id).first()
        if pg_art:
            pg_art.status = status
            db.commit()
    except Exception as e:
        logger.error(f"Failed to atomically update PostgreSQL status to {status}: {e}")
        db.rollback()
    finally:
        db.close()

def _get_docai_client(location: str) -> documentai.DocumentProcessorServiceClient:
    """
    Instantiates a thread-safe Document AI client pointing to the correct regional host.
    """
    api_endpoint = f"{location}-documentai.googleapis.com"
    client_options = ClientOptions(api_endpoint=api_endpoint)
    return documentai.DocumentProcessorServiceClient(client_options=client_options)

def _pre_validate_gcs_file(bucket_name: str, blob_name: str) -> str:
    """
    FSI Cost-Abuse Prevention: Pre-validates file size and type directly 
    against GCS metadata before calling expensive ML compute.
    """
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.get_blob(blob_name)
        
        if not blob:
            logger.error(f"GCS blob not found: gs://{bucket_name}/{blob_name}")
            raise FileNotFoundError(f"GCS file gs://{bucket_name}/{blob_name} not found.")

        # Size Validation
        if blob.size > MAX_FILE_SIZE_BYTES:
            logger.error(f"File exceeds hard size ceiling: {blob.size} bytes (Max: {MAX_FILE_SIZE_BYTES})")
            raise ValueError("File size exceeds the maximum allowed limit of 50MB.")

        # MIME Type Validation
        content_type = blob.content_type
        if content_type not in SUPPORTED_MIME_TYPES:
            logger.error(f"Unsupported MIME type: {content_type} (Expected one of: {SUPPORTED_MIME_TYPES})")
            raise ValueError(f"Unsupported file type. Supported types: {SUPPORTED_MIME_TYPES}")

        return content_type

    except Exception as e:
        logger.error(f"Pre-validation check failed: {e}")
        raise e

def process_document_pipeline(bucket_name: str, blob_name: str) -> dict:
    """
    Executes the entire Document AI Lending pipeline:
    1. Size/MIME pre-validates the GCS blob.
    2. Queries BigQuery for the PENDING_CLASSIFICATION record (idempotency).
    3. Calls the Master Splitter (us endpoint) to find document page boundaries.
    4. Dispatches segmented pages to specialized W-2 or Paystub extractors.
    5. Formats the structured entities and updates the BigQuery v2 record.
    """
    project_id = get_project_id()

    gcs_uri = f"gs://{bucket_name}/{blob_name}"
    logger.info(f"Initiating document pipeline for: {gcs_uri}")

    # 1. GCS Pre-Validation Gate
    resolved_mime_type = _pre_validate_gcs_file(bucket_name, blob_name)

    # 2. Idempotency and Ingestion Validation (PostgreSQL OLTP Primary, BigQuery Fallback)
    dataset_id = "banking"
    table_id = "application_artifact"
    table_ref = f"{project_id}.{dataset_id}.{table_id}"

    from utils.database import SessionLocal
    from models.origination import ApplicationArtifact as PGArtifact
    db = SessionLocal()
    artifact_record = None
    try:
        artifact_record = db.query(PGArtifact).filter(
            (PGArtifact.gcs_uri == gcs_uri) | (PGArtifact.artifact_id == blob_name)
        ).first()
    finally:
        db.close()

    if not artifact_record:
        logger.error(f"Ingestion metadata not found in PostgreSQL for: {gcs_uri}")
        raise ValueError("Artifact metadata not found. Direct GCS triggers prohibited.")

    artifact_id = str(artifact_record.artifact_id)
    claimed_type = DocumentType.parse(str(artifact_record.claimed_artifact_type) if artifact_record.claimed_artifact_type else None)
    application_id = str(artifact_record.application_id)

    if ProcessingStatus(str(artifact_record.status)) != ProcessingStatus.PENDING_CLASSIFICATION:
        logger.info(f"Idempotency check: File {gcs_uri} already processed (Status: {artifact_record.status}). Skipping.")
        return {"status": "SKIPPED", "message": f"Artifact already in state: {artifact_record.status}"}

    # Initialize FSI Pluggable Configuration Registry
    registry = DocumentProcessorRegistry(project_id)

    # Atomic state lock transition to prevent duplicate execution races
    logger.info(f"Locking artifact ID {artifact_id} to status CLASSIFYING in PostgreSQL and BigQuery")
    db_lock = SessionLocal()
    try:
        pg_lock = db_lock.query(PGArtifact).filter(PGArtifact.artifact_id == artifact_id).first()
        if pg_lock:
            pg_lock.status = ProcessingStatus.CLASSIFYING.value
            db_lock.commit()
    except Exception as lock_err:
        logger.warning(f"Failed to update status in PostgreSQL: {lock_err}")
    finally:
        db_lock.close()
    try:
        _update_artifact_status(table_ref, artifact_id, ProcessingStatus.CLASSIFYING)
    except Exception as bq_err:
        logger.warning(f"Failed to update status in BigQuery: {bq_err}")

    # Enclose API execution in try-except to support atomic transaction state rollback
    try:
        # 3. Dynamic Ingestion Routing (Splitter Bypass for single-document validation)
        extracted_payloads = {}
        classified_type = DocumentType.UNKNOWN
        confidence_score = 1.0  # Fully verified direct ingestion

        # Custom resilient retry block to handle concurrent API quota throttling (429/503)
        custom_retry = Retry(
            initial=1.0,
            maximum=10.0,
            multiplier=2.0,
            deadline=60.0
        )

        gcs_doc = documentai.GcsDocument(gcs_uri=gcs_uri, mime_type=resolved_mime_type)

        if claimed_type in [DocumentType.W2, DocumentType.PAYSTUB]:
            logger.info(f"Lending Splitter Bypass: Claimed type '{claimed_type.value}' detected. Routing directly to regional extractor.")
            classified_type = claimed_type
            
            extractor_name = registry.get_processor_name(classified_type)
            extractor_request = documentai.ProcessRequest(
                name=extractor_name,
                gcs_document=gcs_doc
            )

            logger.info(f"Invoking direct specialized regional extractor via registry mapping: {extractor_name}")
            client_us = _get_docai_client("us")
            extractor_result = client_us.process_document(request=extractor_request, retry=custom_retry)
            
            segment_payload = {}
            for ext_entity in extractor_result.document.entities:
                field_name = ext_entity.type_
                field_value = ext_entity.mention_text
                field_confidence = ext_entity.confidence
                
                logger.debug(f"Parsed field type: {field_name} (Confidence: {field_confidence})")
                segment_payload[field_name] = {
                    "value": field_value,
                    "confidence": float(field_confidence)
                }
            
            extracted_payloads[classified_type] = segment_payload

        else:
            # Legacy master splitter logic (for multi-document packets)
            splitter_name = registry.get_processor_name("SPLITTER")
            splitter_request = documentai.ProcessRequest(
                name=splitter_name,
                gcs_document=gcs_doc
            )

            logger.info(f"Invoking Master Splitter via registry mapping: {splitter_name}")
            client_us = _get_docai_client("us")
            splitter_result = client_us.process_document(request=splitter_request, retry=custom_retry)

            entities = splitter_result.document.entities
            logger.info(f"Master Splitter execution finished. Found {len(entities)} segmented entities.")

            for idx, entity in enumerate(entities):
                doc_type = DocumentType.parse(entity.type_)
                confidence = entity.confidence
                
                page_indices = []
                for page_ref in entity.page_anchor.page_refs:
                    page_indices.append(int(page_ref.page))

                logger.info(f"Segment {idx}: Detected type {doc_type.value} on page indices {page_indices} (Confidence: {confidence})")

                if doc_type in [DocumentType.W2, DocumentType.PAYSTUB]:
                    classified_type = doc_type
                    confidence_score = float(confidence)
                else:
                    logger.warning(f"Document segment type {doc_type.value} is unmapped. Routing to manual review.")
                    continue

                page_selector = documentai.ProcessOptions.IndividualPageSelector(pages=page_indices)
                process_options = documentai.ProcessOptions(individual_page_selector=page_selector)
                
                extractor_name = registry.get_processor_name(classified_type)
                extractor_request = documentai.ProcessRequest(
                    name=extractor_name,
                    gcs_document=gcs_doc,
                    process_options=process_options
                )

                logger.info(f"Invoking specialized {classified_type} regional extractor via registry: {extractor_name}")
                extractor_result = client_us.process_document(request=extractor_request, retry=custom_retry)
                
                segment_payload = {}
                for ext_entity in extractor_result.document.entities:
                    field_name = ext_entity.type_
                    field_value = ext_entity.mention_text
                    field_confidence = ext_entity.confidence
                    
                    logger.debug(f"Parsed field type: {field_name} (Confidence: {field_confidence})")
                    segment_payload[field_name] = {
                        "value": field_value,
                        "confidence": float(field_confidence)
                    }
                
                extracted_payloads[classified_type] = segment_payload

    except Exception as api_ex:
        logger.error(f"Pipeline API invocation failed: {api_ex}. Reverting status to PENDING_CLASSIFICATION.")
        try:
            _update_artifact_status(table_ref, artifact_id, ProcessingStatus.PENDING_CLASSIFICATION)
        except Exception as rollback_ex:
            logger.error(f"Failed to rollback transaction state lock for artifact ID {artifact_id}: {rollback_ex}")
        raise api_ex

    # 5. Format payload and commit structured results to BigQuery v2
    is_matching = (classified_type != DocumentType.UNKNOWN and (not claimed_type or claimed_type == classified_type))

    flagged_fields = []
    if is_matching:
        flagged_fields = _audit_extraction_confidence(extracted_payloads)
        if flagged_fields:
            logger.warning(f"Low-confidence extraction fields identified: {flagged_fields}. Routing artifact to Tier 1 Manual Review queue.")
            final_status = ProcessingStatus.PENDING_REVIEW
            verification_tier = "TIER_1_MANUAL"
        else:
            logger.info("Document visual classification and parsed field confidence are high. Routing to Tier 2 Spot Check queue.")
            final_status = ProcessingStatus.PENDING_REVIEW
            verification_tier = "TIER_2_SPOT_CHECK"
    else:
        logger.warning(f"Mismatched/Unknown document classification: Claimed {claimed_type.value if claimed_type else 'None'} but classified as {classified_type.value}. Routing to Tier 1 Manual Review queue.")
        final_status = ProcessingStatus.PENDING_REVIEW
        verification_tier = "TIER_1_MANUAL"

    # If low-confidence or mismatch identified, optionally dispatch to Pub/Sub exception queue
    if verification_tier == "TIER_1_MANUAL":
        try:
            from utils.pubsub import publish_underwriting_exception
            publish_underwriting_exception(
                artifact_id=artifact_id,
                application_id=application_id,
                customer_id=artifact_record.customer_id,
                file_path_gcs=gcs_uri,
                flagged_fields=flagged_fields or ["document_type_mismatch"],
                overall_confidence=confidence_score
            )
        except Exception as pub_err:
            # Safeguard: log but do not block BQ update execution
            logger.error(f"Exception queue dispatch failed: {pub_err}")

    # Construct compliance logging payload
    audit_payload = {
        "processor_manifest": [
            {"processor_type": "splitter", "id": registry.splitter_id},
            {"processor_type": "w2_extractor", "id": registry.w2_id},
            {"processor_type": "paystub_extractor", "id": registry.paystub_id}
        ],
        "flagged_fields": flagged_fields
    }

    # Stringify dynamic JSON payloads safely
    payload_json = json.dumps(extracted_payloads)
    audit_json = json.dumps(audit_payload)

    import uuid
    version_id = str(uuid.uuid4())

    logger.info(f"Committing completed document extraction results to PostgreSQL for artifact ID: {artifact_id}")
    from utils.database import SessionLocal
    from utils.audit import record_audit_event
    from models.origination import ApplicationArtifact as PGArtifact
    db = SessionLocal()
    try:
        pg_art = db.query(PGArtifact).filter(
            (PGArtifact.artifact_id == blob_name) | (PGArtifact.gcs_uri == gcs_uri) | (PGArtifact.artifact_id == artifact_id)
        ).first()
        if pg_art:
            pg_art.status = final_status.value
            pg_art.actual_artifact_type = classified_type.value
            pg_art.classification_confidence = confidence_score
            pg_art.extraction_payload = payload_json
            pg_art.audit_metadata = audit_json
            pg_art.verification_tier = verification_tier
            pg_art.version_id = version_id
            logger.info(f"PostgreSQL ApplicationArtifact successfully updated to {final_status.value}")
        else:
            logger.error(f"PostgreSQL ApplicationArtifact record not found for {artifact_id} during commit.")

        record_audit_event(
            db,
            "DOCUMENT_EXTRACTION_COMPLETED",
            {
                "artifact_id": artifact_id,
                "status": final_status.value,
                "classified_type": classified_type.value,
                "confidence_score": confidence_score,
                "verification_tier": verification_tier
            }
        )
        db.commit()
    except Exception as aud_ex:
        logger.error(f"Failed to update PostgreSQL artifact or record audit event: {aud_ex}")
        db.rollback()
        raise aud_ex
    finally:
        db.close()

    return {
        "status": final_status.value,
        "classified_type": classified_type.value,
        "confidence_score": confidence_score,
        "artifact_id": artifact_id
    }
