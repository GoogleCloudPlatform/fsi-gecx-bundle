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
import time
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.concurrency import run_in_threadpool
from google.cloud import bigquery
from pydantic import BaseModel, Field
from utils.auth import require_admin_user, verify_eventarc_oidc_token
from utils.database import enable_session_rbac_override
from utils.env import is_cloud_run
from utils.lazy_clients import LazyClient
from utils.maintenance import disable_maintenance_mode, enable_maintenance_mode, maintenance_window
from utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
bq_client = LazyClient(bigquery.Client)
router = APIRouter(prefix="/internal", tags=["internal"])


def clear_operational_transaction_stream() -> None:
    redis_client = get_redis_client()
    if not redis_client:
        return

    try:
        redis_client.delete("recent_transactions", "datastream_metrics", "cdc_status")
    except Exception as exc:
        logger.warning("Could not clear Redis transaction or metrics cache during reset: %s", exc)


def _run_cloud_run_reset_job() -> dict | None:
    job_name = os.getenv("FULL_RESET_JOB_NAME")
    if not is_cloud_run() or not job_name:
        return None

    project_id = (
        os.getenv("FULL_RESET_JOB_PROJECT_ID")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCP_PROJECT")
    )
    region = os.getenv("FULL_RESET_JOB_REGION") or os.getenv("GOOGLE_CLOUD_REGION") or "us-central1"
    if not project_id:
        raise RuntimeError("FULL_RESET_JOB_PROJECT_ID or GOOGLE_CLOUD_PROJECT must be set to run the reset job.")

    import google.auth
    import google.auth.transport.requests
    import httpx

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(google.auth.transport.requests.Request())
    headers = {"Authorization": f"Bearer {credentials.token}", "Content-Type": "application/json"}

    job_path = f"projects/{project_id}/locations/{region}/jobs/{job_name}"
    run_url = f"https://run.googleapis.com/v2/{job_path}:run"

    with httpx.Client(timeout=30.0) as client:
        response = client.post(run_url, headers=headers, json={})
        response.raise_for_status()
        operation = response.json()
        if not operation.get("name"):
            raise RuntimeError(f"Cloud Run reset job did not return an operation: {operation}")
        return operation

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
def process_outbox(batch_size: int = 50, _admin=Depends(require_admin_user)):
    """
    In our WAL CDC architecture (Architecture Two), outbox ingestion occurs via zero-load Datastream WAL streaming.
    Returns operational metrics for recent append-only outbox records.
    """
    from utils.database import SessionLocal
    from utils.audit import publish_pending_audit_events
    db = SessionLocal()
    try:
        count = publish_pending_audit_events(db, batch_size=batch_size)
        return {"status": "SUCCESS", "message": "Outbox is managed via real-time WAL CDC streaming.", "recorded_count": count}
    finally:
        db.close()

@router.post("/debug/reset-db")
def reset_database(
    purge_audit_logs: bool = False,
    purge_data_lake: bool = False,
    _admin=Depends(require_admin_user),
):
    """
    Deletes all rows in the database and re-seeds it with baseline cardholder data.
    Optionally purges PostgreSQL and BigQuery compliance audit logs if purge_audit_logs=True.
    Optionally purges Apache Iceberg BigLake analytical tables if purge_data_lake=True.
    """
    logger.info(f"Internal Debug request: Resetting database (purge_audit_logs={purge_audit_logs}, purge_data_lake={purge_data_lake})...")
    from utils.database import SessionLocal
    from services.seeding_service import perform_algorithmic_seeding
    from models.audit import AuditOutbox
    
    db = SessionLocal()
    warnings: list[str] = []
    try:
        enable_session_rbac_override(db)

        if is_cloud_run() and os.getenv("FULL_RESET_JOB_NAME"):
            enable_maintenance_mode(
                reason="database_reset",
                message="Admin reset in progress. Transaction traffic is temporarily paused.",
                ttl_seconds=300,
            )
            try:
                reset_job_operation = _run_cloud_run_reset_job()
            except Exception:
                disable_maintenance_mode()
                raise
        else:
            reset_job_operation = None

        if reset_job_operation:
            time.sleep(2.0)
            clear_operational_transaction_stream()
            logger.info("Database reset started via Cloud Run job operation: %s", reset_job_operation.get("name"))
            if purge_audit_logs or purge_data_lake:
                warnings.append("Audit and data lake purge are skipped for asynchronous Cloud Run reset jobs.")
            return {
                "status": "SUCCESS",
                "message": "Database reset job started. Demo data will be rebuilt shortly.",
                "operation": reset_job_operation.get("name"),
                "warnings": warnings,
            }

        with maintenance_window(
            reason="database_reset",
            message="Admin reset in progress. Transaction traffic is temporarily paused.",
            ttl_seconds=300,
            drain_seconds=2.0,
        ):
            logger.info("Maintenance mode enabled for admin database reset.")
            clear_operational_transaction_stream()

            # Local/test fallback: seed and clean databases using the Seeding Service.
            perform_algorithmic_seeding(db)
            clear_operational_transaction_stream()

            if purge_audit_logs:
                try:
                    db.query(AuditOutbox).delete()
                    logger.info("Purging PostgreSQL audit outbox...")
                except Exception as audit_ex:
                    db.rollback()
                    logger.warning(f"Could not purge PostgreSQL audit outbox: {audit_ex}")
                    warnings.append(f"PostgreSQL audit outbox purge skipped: {audit_ex}")
                try:
                    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "evo-genai-workspace")
                    for tbl in ["origination_audit_log", "financial_ledger_audit_log", "identity_access_audit_log"]:
                        bq_client.query(f"DELETE FROM `{project_id}.compliance_audit.{tbl}` WHERE true").result()
                    logger.info("Purged BigQuery compliance_audit tables.")
                except Exception as bq_ex:
                    logger.warning(f"Could not purge BigQuery audit logs: {bq_ex}")
                    warnings.append(f"BigQuery audit purge skipped: {bq_ex}")

            if purge_data_lake:
                logger.info("Purging BigLake Apache Iceberg catalog tables...")
                try:
                    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "evo-genai-workspace")
                    candidate_tables = {
                        "cards_posted_transactions",
                        "cards_transaction_authorization",
                        "cards_issued_card",
                        "origination_applications",
                        "origination_credit_card_applications",
                        "origination_mortgage_applications",
                        "identity_users",
                    }
                    table_rows = bq_client.query(
                        f"""
                        SELECT table_name
                        FROM `{project_id}.iceberg_catalog.INFORMATION_SCHEMA.TABLES`
                        WHERE table_name IN ({", ".join(f"'{table}'" for table in sorted(candidate_tables))})
                        """
                    ).result()
                    existing_tables = [row.table_name for row in table_rows]
                    for lake_tbl in existing_tables:
                        bq_client.query(f"DELETE FROM `{project_id}.iceberg_catalog.{lake_tbl}` WHERE true").result()
                    logger.info("Purged BigLake Apache Iceberg catalog tables.")
                except Exception as lake_ex:
                    logger.warning(f"Could not purge BigLake Iceberg tables: {lake_ex}")
                    warnings.append(f"BigLake purge skipped: {lake_ex}")

            db.commit()
        msg = "Database reset and re-seeded successfully."
        if purge_audit_logs:
            msg += " (Audit logs purged)"
        if purge_data_lake:
            msg += " (Data Lake purged)"
        return {
            "status": "SUCCESS" if not warnings else "PARTIAL_SUCCESS",
            "message": msg if not warnings else f"{msg} Completed with warnings.",
            "warnings": warnings,
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to reset database: {e}")
        raise HTTPException(status_code=500, detail=f"Database reset failed: {e}")
    finally:
        db.close()
