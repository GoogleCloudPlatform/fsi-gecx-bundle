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
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.concurrency import run_in_threadpool
from google.cloud import bigquery
from pydantic import BaseModel, Field
from utils.auth import verify_eventarc_oidc_token
from services.document_ai import ProcessingStatus

logger = logging.getLogger(__name__)
bq_client = bigquery.Client()
router = APIRouter(prefix="/internal", tags=["internal"])

class EventarcPayload(BaseModel):
    name: str = Field(..., description="GCS object name.")
    bucket: str = Field(..., description="GCS bucket name.")

@lru_cache
def get_check_status_sql() -> str:
    sql_path = Path(__file__).resolve().parent.parent / "resources" / "sql" / "check_artifact_status.sql"
    if not sql_path.exists():
        logger.critical(f"🚨 Missing SQL resource file: {sql_path}")
        raise FileNotFoundError(f"Missing SQL resource: {sql_path}")
    return sql_path.read_text()

@router.post("/process-document")
async def process_document(
    request: Request,
    payload: EventarcPayload,
    ce_subject: Annotated[str, Header(max_length=1024, alias="Ce-Subject")],
    ce_type: Annotated[str, Header(max_length=1024, alias="Ce-Type")],
    ce_source: Annotated[str, Header(max_length=1024, alias="Ce-Source")],
    token_info: dict = Depends(verify_eventarc_oidc_token)
):
    if ce_type != "google.cloud.storage.object.v1.finalized":
        logger.error(f"Unexpected CloudEvent type: {ce_type}")
        raise HTTPException(status_code=400, detail="Unsupported event type.")
    
    filename = payload.name
    
    # 1. Isolate test/CI sandbox uploads to prevent leakage into production BigQuery tables
    if filename.startswith("ci-temp/") or filename.startswith("test/"):
        logger.info(f"Ignoring test/CI artifact finalized trigger: {filename}")
        return {"message": "Skipped: test artifact.", "filename": filename}

    from services.document_ai import SUPPORTED_MIME_TYPES

    # 2. Robust MIME type resolution: fetch GCS blob content_type metadata, falling back to extension guess
    mime_type = None
    try:
        from google.cloud import storage
        storage_client = storage.Client()
        bucket = storage_client.bucket(payload.bucket)
        blob = bucket.get_blob(filename)
        if blob:
            mime_type = blob.content_type
            logger.info(f"Resolved MIME type for {filename} from GCS metadata: {mime_type}")
    except Exception as gcs_err:
        logger.warning(f"Failed to fetch GCS blob metadata for {filename}: {gcs_err}")

    if not mime_type:
        import mimetypes
        mime_type, _ = mimetypes.guess_type(filename)
        logger.info(f"Guessed MIME type for {filename} from filename: {mime_type}")

    if not mime_type or mime_type not in SUPPORTED_MIME_TYPES:
        logger.info(f"Skipping processing for non-supported GCS finalized object: {filename} (resolved MIME: {mime_type})")
        return {"message": "Skipped: object is not a supported document file.", "filename": filename}

    # 3. Check PostgreSQL ApplicationArtifact table first, falling back to BigQuery
    status_val = None
    record_found = False

    from utils.database import SessionLocal
    from models.origination import ApplicationArtifact as PGArtifact
    db = SessionLocal()
    try:
        pg_art = db.query(PGArtifact).filter(
            (PGArtifact.artifact_id == filename) | (PGArtifact.gcs_uri.endswith(filename))
        ).first()
        if pg_art:
            record_found = True
            status_val = pg_art.status
    except Exception as pg_ex:
        logger.warning(f"PostgreSQL artifact verification check failed: {pg_ex}")
    finally:
        db.close()

    if not record_found:
        logger.info(f"Artifact {filename} not found in PostgreSQL database during idempotency check.")

    if not record_found:
        delivery_attempt_str = request.headers.get("x-goog-pubsub-message-delivery-attempt") or request.headers.get("ce-deliveryattempt")
        delivery_attempt = int(delivery_attempt_str) if delivery_attempt_str and delivery_attempt_str.isdigit() else 1
        
        # Hybrid Strategy: If Pub/Sub has retried more than 3 times, or if delivery attempt tracking header is absent,
        # acknowledge terminally (HTTP 200) to drain orphaned files from Eventarc / Pub/Sub retry loops.
        if delivery_attempt > 3 or not delivery_attempt_str:
            logger.warning(f"Artifact {filename} missing from database after retries (delivery attempt: {delivery_attempt}). Terminal ACK to prevent infinite retry loop.")
            return {"status": "ignored", "reason": "artifact_metadata_not_found_after_retries", "filename": filename}
        
        logger.error(f"Artifact record not found in database for {filename} on attempt {delivery_attempt}. Raising 404 for retry.")
        raise HTTPException(status_code=404, detail="Artifact metadata not found.")

    if status_val and status_val not in ["UPLOADED", "PENDING_CLASSIFICATION", "CLASSIFYING"]:
        logger.info(f"Idempotency check: Artifact {filename} already processed (Status: {status_val}). Skipping.")
        return {"message": "Idempotent success: Artifact already processed.", "status": status_val}
    
    # Invoke the Document AI pipeline directly (synchronous/blocking inside Cloud Run to guarantee CPU allocation!)
    try:
        from services.document_ai import process_document_pipeline
        result = await run_in_threadpool(process_document_pipeline, payload.bucket, payload.name)
        return {
            "message": "Document processed and data extracted successfully.",
            "filename": filename,
            "pipeline_result": result
        }
    except Exception as pipeline_ex:
        logger.error(f"Pipeline execution failed for {filename}: {pipeline_ex}")
        raise HTTPException(status_code=500, detail=f"Document processing pipeline failed: {str(pipeline_ex)}")

@router.post("/process-outbox")
def process_outbox(batch_size: int = 50):
    """
    Drains the transactional audit outbox, publishing pending events to Google Cloud Pub/Sub
    for immediate streaming into BigQuery compliance audit tables.
    """
    from utils.database import SessionLocal
    from utils.audit import publish_pending_audit_events
    db = SessionLocal()
    try:
        count = publish_pending_audit_events(db, batch_size=batch_size)
        return {"status": "SUCCESS", "published_count": count}
    finally:
        db.close()

@router.post("/debug/reset-db")
def reset_database(purge_audit_logs: bool = False):
    """
    Deletes all rows in the database and re-seeds it with baseline cardholder data.
    Optionally purges PostgreSQL and BigQuery compliance audit logs if purge_audit_logs=True.
    """
    logger.info(f"Internal Debug request: Resetting database (purge_audit_logs={purge_audit_logs})...")
    from utils.database import SessionLocal
    from models.credit_card import FinancialAccount, IssuedCard, TransactionAuthorization, AccountLedger
    from models.support import Escalation
    from models.origination import Application, MortgageApplication, CreditCardApplication, DepositApplication, ApplicationArtifact
    from models.audit import AuditOutbox
    from services.credit_card import initialize_db_and_seed
    
    db = SessionLocal()
    try:
        db.connection().info["_ignore_rbac"] = True
        db.query(TransactionAuthorization).delete()
        db.query(AccountLedger).delete()
        db.query(IssuedCard).delete()
        db.query(Escalation).delete()
        db.query(FinancialAccount).delete()
        db.query(ApplicationArtifact).delete()
        db.query(MortgageApplication).delete()
        db.query(CreditCardApplication).delete()
        db.query(DepositApplication).delete()
        db.query(Application).delete()
        
        if purge_audit_logs:
            db.query(AuditOutbox).delete()
            logger.info("Purging PostgreSQL audit outbox...")
            try:
                project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "evo-genai-workspace")
                for tbl in ["origination_audit_log", "financial_ledger_audit_log", "identity_access_audit_log"]:
                    bq_client.query(f"DELETE FROM `{project_id}.compliance_audit.{tbl}` WHERE true").result()
                logger.info("Purged BigQuery compliance_audit tables.")
            except Exception as bq_ex:
                logger.warning(f"Could not purge BigQuery audit logs: {bq_ex}")

        db.commit()
        logger.info("Database tables cleared.")
        
        initialize_db_and_seed(db)
        logger.info("Database re-seeded.")
        msg = "Database reset and re-seeded successfully." + (" (Audit logs purged)" if purge_audit_logs else " (Audit logs preserved)")
        return {"status": "SUCCESS", "message": msg}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to reset database: {e}")
        raise HTTPException(status_code=500, detail=f"Database reset failed: {e}")
    finally:
        db.close()

