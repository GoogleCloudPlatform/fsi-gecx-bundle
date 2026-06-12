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

    dataset_id = os.getenv("DATASET_ID", "banking")
    sql_query = get_check_status_sql().format(dataset_id=dataset_id)
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("filename", "STRING", f"%{filename}")
        ]
    )
    try:
        query_job = bq_client.query(sql_query, job_config=job_config)
        results = list(query_job.result())
        if not results:
            logger.error(f"Artifact record not found in BigQuery for {filename}")
            raise HTTPException(status_code=404, detail="Artifact metadata not found.")
        
        status = ProcessingStatus(results[0].status)
        if status != ProcessingStatus.PENDING_CLASSIFICATION:
            logger.info(f"Idempotency check: Artifact {filename} already processed (Status: {status.value}). Skipping.")
            return {"message": "Idempotent success: Artifact already processed.", "status": status.value}
            
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"BigQuery idempotency check failed: {e}")
        raise HTTPException(status_code=500, detail="Database verification error.")
    
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

@router.post("/debug/reset-db")
def reset_database():
    """
    Deletes all rows in the database and re-seeds it with baseline cardholder data.
    """
    logger.info("Internal Debug request: Resetting database...")
    from utils.database import SessionLocal
    from models.credit_card import FinancialAccount, IssuedCard, TransactionAuthorization, AccountLedger
    from models.support import Escalation
    from services.credit_card import initialize_db_and_seed
    
    db = SessionLocal()
    try:
        db.query(TransactionAuthorization).delete()
        db.query(AccountLedger).delete()
        db.query(IssuedCard).delete()
        db.query(Escalation).delete()
        db.query(FinancialAccount).delete()
        db.commit()
        logger.info("Database tables cleared.")
        
        initialize_db_and_seed(db)
        logger.info("Database re-seeded.")
        return {"status": "SUCCESS", "message": "Database reset and re-seeded successfully."}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to reset database: {e}")
        raise HTTPException(status_code=500, detail=f"Database reset failed: {e}")
    finally:
        db.close()

