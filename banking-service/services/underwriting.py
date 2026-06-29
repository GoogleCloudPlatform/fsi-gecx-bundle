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
import logging
import uuid
from typing import Optional, Any
from datetime import datetime, timezone
from pathlib import Path
from google.cloud import bigquery
from sqlalchemy.orm import Session
from models.underwriting import UnderwritingOverrideRequest, DocumentSummaryResponse, UnderwritingDecision

logger = logging.getLogger(__name__)
bq_client = bigquery.Client()

SQL_DIR = Path(__file__).resolve().parent.parent / "resources" / "sql"

class UnderwritingConflictError(Exception):
    """Raised when optimistic locking check fails during underwriting overrides."""
    pass

def _load_sql(filename: str) -> str:
    """Loads a clean SQL query template from the resources directory."""
    return (SQL_DIR / filename).read_text()

def get_pending_exceptions(table_ref: str, db: Optional[Session] = None) -> list[DocumentSummaryResponse]:
    """
    Retrieves all artifacts currently in 'MISMATCH' or 'PENDING_REVIEW' exception status from PostgreSQL OLTP database.
    """
    close_db = False
    if db is None:
        from utils.database import SessionLocal
        db = SessionLocal()
        close_db = True

    try:
        from models.origination import ApplicationArtifact
        results = db.query(ApplicationArtifact).filter(
            ApplicationArtifact.status.in_(["MISMATCH", "PENDING_REVIEW"])
        ).order_by(ApplicationArtifact.uploaded_at.desc()).all()

        exceptions = []
        if results is not None:
            for art in results:
                payload = json.loads(art.extraction_payload) if art.extraction_payload else {}
                audit = json.loads(art.audit_metadata) if art.audit_metadata else {}
                user = art.customer
                app = art.application

                exceptions.append(DocumentSummaryResponse(
                    artifact_id=art.artifact_id,
                    customer_id=str(art.customer_id),
                    application_id=str(art.application_id) if art.application_id else None,
                    claimed_artifact_type=art.claimed_artifact_type,
                    actual_artifact_type=art.actual_artifact_type,
                    status=art.status,
                    file_path_gcs=art.gcs_uri,
                    extraction_payload=payload,
                    audit_metadata=audit,
                    verification_tier=art.verification_tier,
                    version_id=art.version_id,
                    user_first_name=user.first_name if user else None,
                    user_last_name=user.last_name if user else None,
                    user_email=user.email if user else None,
                    requested_amount=getattr(app, "requested_amount", getattr(app, "requested_amount_cents", None)) if app else None,
                    product_category=getattr(app, "product_category", None) if app else None,
                    product_type=getattr(app, "product_type", None) if app else None
                ))
        logger.info(f"Found {len(exceptions)} exception records in PostgreSQL database.")
        return exceptions
    finally:
        if close_db and db:
            db.close()

def apply_underwriting_override(table_ref: str, override: UnderwritingOverrideRequest, db: Optional[Session] = None) -> bool:
    """
    Applies professional loan officer overrides, merges corrected values,
    appends compliance audit trails, and transitions status to PROCESSED
    exclusively in PostgreSQL ORM database.
    """
    logger.info(f"Processing underwriter override for artifact ID: {override.artifact_id} (Underwriter: {override.underwriter_id})")
    
    close_db = False
    if db is None:
        from utils.database import SessionLocal
        db = SessionLocal()
        close_db = True

    try:
        from models.origination import ApplicationArtifact
        from services.document_ai import ProcessingStatus
        pg_art = db.query(ApplicationArtifact).filter(
            ApplicationArtifact.artifact_id == override.artifact_id
        ).first()
        
        if not pg_art:
            logger.error(f"Underwriting record not found in PostgreSQL for artifact ID: {override.artifact_id}")
            raise ValueError(f"Exception record '{override.artifact_id}' not found.")

        if pg_art.status not in ["MISMATCH", "PENDING_REVIEW"]:
            logger.warning(f"Optimistic Lock Failure: Artifact {override.artifact_id} is already in status: {pg_art.status}")
            raise UnderwritingConflictError(f"Artifact '{override.artifact_id}' is already in state: {pg_art.status}.")

        if override.expected_version_id and pg_art.version_id and pg_art.version_id != override.expected_version_id:
            logger.warning(f"Optimistic Lock Version Conflict: Client expected version '{override.expected_version_id}' but database has '{pg_art.version_id}'")
            raise UnderwritingConflictError("This exception record was updated or accepted by another loan officer. Please refresh.")

        original_payload = json.loads(pg_art.extraction_payload) if pg_art.extraction_payload else {}
        doc_type_key = pg_art.actual_artifact_type or pg_art.claimed_artifact_type or "W2"
        doc_type_key = doc_type_key.upper()
        doc_fields = original_payload.get(doc_type_key, {})

        for field, value in override.corrected_payload.items():
            doc_fields[field] = {"value": str(value), "confidence": 1.0}
        updated_payload = {doc_type_key: doc_fields}

        original_audit = json.loads(pg_art.audit_metadata) if pg_art.audit_metadata else {}
        underwriting_trace = {
            "underwriter_id": override.underwriter_id,
            "override_timestamp": datetime.now(timezone.utc).isoformat(),
            "decision": override.decision.value,
            "verifications": override.verifications.model_dump(),
            "underwriter_notes": override.underwriter_notes,
            "corrected_fields": list(override.corrected_payload.keys())
        }
        if "underwriting_overrides" not in original_audit or not isinstance(original_audit.get("underwriting_overrides"), list):
            original_audit["underwriting_overrides"] = []
        original_audit["underwriting_overrides"].append(underwriting_trace)

        if override.decision == UnderwritingDecision.APPROVE:
            target_status = ProcessingStatus.PROCESSED.value
        elif override.decision in [UnderwritingDecision.REJECT_FRAUD, UnderwritingDecision.REJECT_LEGIBILITY]:
            target_status = ProcessingStatus.FAILED.value
        elif override.decision == UnderwritingDecision.REJECT_DATA_MISMATCH:
            target_status = ProcessingStatus.MISMATCH.value
        else:
            target_status = ProcessingStatus.FAILED.value

        new_version_id = str(uuid.uuid4())
        pg_art.status = target_status
        pg_art.extraction_payload = json.dumps(updated_payload)
        pg_art.audit_metadata = json.dumps(original_audit)
        pg_art.version_id = new_version_id
        db.commit()
        logger.info(f"PostgreSQL override committed successfully for artifact ID: {override.artifact_id}")
        return True
    except UnderwritingConflictError:
        raise
    finally:
        if close_db and db:
            db.close()

def get_artifact_gcs_path(table_ref: str, artifact_id: str, db: Optional[Session] = None) -> str:
    """
    Retrieves the GCS file path for a specific artifact ID exclusively from PostgreSQL ORM database.
    """
    logger.info(f"Retrieving GCS file path for artifact: {artifact_id}")
    close_db = False
    if db is None:
        from utils.database import SessionLocal
        db = SessionLocal()
        close_db = True

    try:
        from models.origination import ApplicationArtifact
        pg_art = db.query(ApplicationArtifact).filter(ApplicationArtifact.artifact_id == artifact_id).first()
        if not pg_art:
            raise ValueError(f"Artifact record '{artifact_id}' not found.")
        return pg_art.gcs_uri
    finally:
        if close_db and db:
            db.close()

