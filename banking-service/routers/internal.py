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

