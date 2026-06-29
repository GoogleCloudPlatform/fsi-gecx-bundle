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
    Retrieves all artifacts currently in 'MISMATCH' or 'PENDING_REVIEW' exception status from PostgreSQL first, falling back to BigQuery.
    """
    close_db = False
    if db is None:
        try:
            from utils.database import SessionLocal
            db = SessionLocal()
            close_db = True
        except Exception:
            db = None

    if db:
        try:
            from models.origination import ApplicationArtifact
            results = db.query(ApplicationArtifact).filter(
                ApplicationArtifact.status.in_(["MISMATCH", "PENDING_REVIEW"])
            ).order_by(ApplicationArtifact.uploaded_at.desc()).all()

            if results:
                exceptions = []
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
                        requested_amount=app.requested_amount if app else None,
                        product_category=app.product_category if app else None,
                        product_type=app.product_type if app else None
                    ))
                logger.info(f"Found {len(exceptions)} exception records in PostgreSQL database.")
                if close_db:
                    db.close()
                return exceptions
        except Exception as pg_ex:
            logger.warning(f"PostgreSQL pending exceptions query failed or returned empty, falling back to BigQuery: {pg_ex}")
        finally:
            if close_db and db:
                db.close()

    logger.info(f"Fetching pending underwriting exception records from table: {table_ref}")
    user_table_ref = table_ref.replace(".application_artifact", ".user")
    application_table_ref = table_ref.replace(".application_artifact", ".application")
    query = _load_sql("get_underwriting_exceptions.sql").format(
        table_ref=table_ref,
        user_table_ref=user_table_ref,
        application_table_ref=application_table_ref
    )
    
    try:
        query_job = bq_client.query(query)
        results = list(query_job.result())
        
        exceptions = []
        for row in results:
            # Parse JSON columns natively returned as dictionaries
            payload = row.extraction_payload if row.extraction_payload else {}
            audit = row.audit_metadata if row.audit_metadata else {}
            
            exceptions.append(DocumentSummaryResponse(
                artifact_id=row.artifact_id,
                customer_id=row.customer_id,
                application_id=row.application_id,
                claimed_artifact_type=row.claimed_artifact_type,
                actual_artifact_type=row.actual_artifact_type,
                status=row.status,
                file_path_gcs=row.file_path_gcs,
                extraction_payload=payload,
                audit_metadata=audit,
                verification_tier=getattr(row, "verification_tier", None),
                version_id=getattr(row, "version_id", None),
                user_first_name=getattr(row, "user_first_name", None),
                user_last_name=getattr(row, "user_last_name", None),
                user_email=getattr(row, "user_email", None),
                requested_amount=getattr(row, "requested_amount", None),
                product_category=getattr(row, "product_category", None),
                product_type=getattr(row, "product_type", None)
            ))
        logger.info(f"Found {len(exceptions)} exception records in database.")
        return exceptions
        
    except Exception as e:
        logger.error(f"Failed to fetch underwriting exceptions from BigQuery: {e}")
        raise e

def apply_underwriting_override(table_ref: str, override: UnderwritingOverrideRequest, db: Optional[Session] = None) -> bool:
    """
    Applies professional loan officer overrides, merges corrected values,
    appends compliance audit trails, and transitions status to PROCESSED.
    Checks PostgreSQL first, falling back to BigQuery.
    """
    logger.info(f"Processing underwriter override for artifact ID: {override.artifact_id} (Underwriter: {override.underwriter_id})")
    
    close_db = False
    if db is None:
        try:
            from utils.database import SessionLocal
            db = SessionLocal()
            close_db = True
        except Exception:
            db = None

    if db:
        try:
            from models.origination import ApplicationArtifact
            from services.document_ai import ProcessingStatus
            pg_art = db.query(ApplicationArtifact).filter(
                ApplicationArtifact.artifact_id == override.artifact_id
            ).first()
            if pg_art:
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

                try:
                    update_query = _load_sql("override_underwriting_artifact.sql").format(table_ref=table_ref)
                    verification_audit = {
                        "document_hash": override.document_hash,
                        "underwriter_id": override.underwriter_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "interactive_verifications": override.interactive_verifications or {}
                    }
                    update_config = bigquery.QueryJobConfig(
                        query_parameters=[
                            bigquery.ScalarQueryParameter("status", "STRING", target_status),
                            bigquery.ScalarQueryParameter("payload", "STRING", json.dumps(updated_payload)),
                            bigquery.ScalarQueryParameter("audit", "STRING", json.dumps(original_audit)),
                            bigquery.ScalarQueryParameter("verification_audit", "STRING", json.dumps(verification_audit)),
                            bigquery.ScalarQueryParameter("new_version_id", "STRING", new_version_id),
                            bigquery.ScalarQueryParameter("expected_version_id", "STRING", override.expected_version_id),
                            bigquery.ScalarQueryParameter("artifact_id", "STRING", override.artifact_id),
                            bigquery.ScalarQueryParameter("customer_id", "STRING", override.customer_id)
                        ]
                    )
                    bq_client.query(update_query, job_config=update_config).result()
                except Exception as bq_ex:
                    logger.warning(f"Background BQ override sync skipped or failed: {bq_ex}")

                if close_db:
                    db.close()
                return True
        except UnderwritingConflictError:
            if close_db and db:
                db.close()
            raise
        except Exception as pg_ex:
            logger.warning(f"PostgreSQL override failed or not found, falling back to BigQuery: {pg_ex}")
        finally:
            if close_db and db:
                db.close()

    # 1. Fetch the original record to load payload context
    fetch_query = f"""
        SELECT status, claimed_artifact_type, actual_artifact_type, extraction_payload, audit_metadata, version_id
        FROM `{table_ref}`
        WHERE artifact_id = @artifact_id
          AND customer_id = @customer_id
        LIMIT 1
    """
    fetch_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("artifact_id", "STRING", override.artifact_id),
            bigquery.ScalarQueryParameter("customer_id", "STRING", override.customer_id)
        ]
    )
    fetch_job = bq_client.query(fetch_query, job_config=fetch_config)
    results = list(fetch_job.result())
    
    if not results:
        logger.error(f"Underwriting record not found for artifact ID: {override.artifact_id}")
        raise ValueError(f"Exception record '{override.artifact_id}' not found.")
        
    original_row = results[0]
    
    if original_row.status not in ["MISMATCH", "PENDING_REVIEW"]:
        logger.warning(f"Optimistic Lock Failure: Artifact {override.artifact_id} is already in status: {original_row.status}")
        raise UnderwritingConflictError(f"Artifact '{override.artifact_id}' is already in state: {original_row.status}.")

    # OCC Validation Check
    original_version_id = getattr(original_row, "version_id", None)
    if override.expected_version_id and original_version_id != override.expected_version_id:
        logger.warning(f"Optimistic Lock Version Conflict: Client expected version '{override.expected_version_id}' but database has '{original_version_id}'")
        raise UnderwritingConflictError("This exception record was updated or accepted by another loan officer. Please refresh.")

    # 2. Deep merge human corrections into active payload
    original_payload = original_row.extraction_payload if original_row.extraction_payload else {}
    doc_type_key = original_row.actual_artifact_type
    
    if not doc_type_key:
        # Fallback to claimed type if visual classification was unassigned
        doc_type_key = original_row.claimed_artifact_type if original_row.claimed_artifact_type else "W2"
        
    # Normalize case
    doc_type_key = doc_type_key.upper()
    
    # Mapped fields inside original document object dictionary
    doc_fields = original_payload.get(doc_type_key, {})
    
    # Merge corrections
    for field, value in override.corrected_payload.items():
        doc_fields[field] = {
            "value": str(value),
            "confidence": 1.0  # Underwriter certified
        }
        
    updated_payload = {doc_type_key: doc_fields}

    # 3. Construct deep audit metadata trace block
    original_audit = original_row.audit_metadata if original_row.audit_metadata else {}
    
    underwriting_trace = {
        "underwriter_id": override.underwriter_id,
        "override_timestamp": datetime.now(timezone.utc).isoformat(),
        "decision": override.decision.value,
        "verifications": override.verifications.model_dump(),
        "underwriter_notes": override.underwriter_notes,
        "corrected_fields": list(override.corrected_payload.keys())
    }
    
    # FSI Audit Compliance: Maintain an immutable chronological list array of all human overrides
    if "underwriting_overrides" not in original_audit or not isinstance(original_audit["underwriting_overrides"], list):
        original_audit["underwriting_overrides"] = []
        
    original_audit["underwriting_overrides"].append(underwriting_trace)
    
    # Construct regulatory verification_audit metadata record
    verification_audit = {
        "document_hash": override.document_hash,
        "underwriter_id": override.underwriter_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "interactive_verifications": override.interactive_verifications or {}
    }

    # Resolve final database workflow status dynamically based on structural underwriting decision
    from services.document_ai import ProcessingStatus
    if override.decision == UnderwritingDecision.APPROVE:
        target_status = ProcessingStatus.PROCESSED.value
    elif override.decision in [UnderwritingDecision.REJECT_FRAUD, UnderwritingDecision.REJECT_LEGIBILITY]:
        target_status = ProcessingStatus.FAILED.value
    elif override.decision == UnderwritingDecision.REJECT_DATA_MISMATCH:
        target_status = ProcessingStatus.MISMATCH.value
    else:
        target_status = ProcessingStatus.FAILED.value

    # Generate a new UUID for this update to enforce OCC on any subsequent edits
    import uuid
    new_version_id = str(uuid.uuid4())

    # 4. Commit the override query transactional updates
    update_query = _load_sql("override_underwriting_artifact.sql").format(table_ref=table_ref)
    update_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("status", "STRING", target_status),
            bigquery.ScalarQueryParameter("payload", "STRING", json.dumps(updated_payload)),
            bigquery.ScalarQueryParameter("audit", "STRING", json.dumps(original_audit)),
            bigquery.ScalarQueryParameter("verification_audit", "STRING", json.dumps(verification_audit)),
            bigquery.ScalarQueryParameter("new_version_id", "STRING", new_version_id),
            bigquery.ScalarQueryParameter("expected_version_id", "STRING", override.expected_version_id),
            bigquery.ScalarQueryParameter("artifact_id", "STRING", override.artifact_id),
            bigquery.ScalarQueryParameter("customer_id", "STRING", override.customer_id)
        ]
    )
    
    update_job = bq_client.query(update_query, job_config=update_config)
    update_job.result()  # Wait for execution completion
    
    # 5. Optimistic Concurrency Control (OCC) Check
    num_affected = update_job.num_dml_affected_rows
    if num_affected is None or num_affected == 0:
        logger.warning(f"Optimistic Lock Conflict: Underwriting update failed for artifact ID: {override.artifact_id}")
        raise UnderwritingConflictError("Conflict occurred: This record was updated or approved by another officer.")
        
    logger.info(f"Underwriting override committed successfully for artifact ID: {override.artifact_id}")
    return True

def get_artifact_gcs_path(table_ref: str, artifact_id: str, db: Optional[Session] = None) -> str:
    """
    Retrieves the GCS file path for a specific artifact ID from PostgreSQL first, falling back to BigQuery.
    """
    logger.info(f"Retrieving GCS file path for artifact: {artifact_id}")
    close_db = False
    if db is None:
        try:
            from utils.database import SessionLocal
            db = SessionLocal()
            close_db = True
        except Exception:
            db = None

    if db:
        try:
            from models.origination import ApplicationArtifact
            pg_art = db.query(ApplicationArtifact).filter(ApplicationArtifact.artifact_id == artifact_id).first()
            if pg_art:
                res = pg_art.gcs_uri
                if close_db:
                    db.close()
                return res
        except Exception as pg_ex:
            logger.warning(f"PostgreSQL GCS path lookup failed, falling back to BigQuery: {pg_ex}")
        finally:
            if close_db and db:
                db.close()

    query = f"""
        SELECT file_path_gcs FROM `{table_ref}`
        WHERE artifact_id = @artifact_id
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("artifact_id", "STRING", artifact_id)
        ]
    )
    query_job = bq_client.query(query, job_config=job_config)
    results = list(query_job.result())
    if not results:
        raise ValueError(f"Artifact record '{artifact_id}' not found.")
    return results[0].file_path_gcs

