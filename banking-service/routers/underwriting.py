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
import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from utils.database import get_db
from utils.audit import record_audit_event
from google.auth import default
from google.auth.impersonated_credentials import Credentials as ImpersonatedCredentials
from google.cloud import storage, bigquery
from models.underwriting import UnderwritingOverrideRequest, DocumentSummaryResponse, UnderwritingDecision
from services.underwriting import (
    get_pending_exceptions,
    apply_underwriting_override,
    get_artifact_gcs_path,
    UnderwritingConflictError
)
from services.underwriting_callback import trigger_session_propagation_flow
from utils.gcp import get_project_id
from utils.auth import get_current_user
from models.authentication import ValidatedToken
from utils.lazy_clients import LazyClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/underwriting", tags=["underwriting"])

PROJECT_ID = get_project_id()
SERVICE_ACCOUNT_EMAIL = f"banking-service-sa@{PROJECT_ID}.iam.gserviceaccount.com"

storage_client = LazyClient(storage.Client)
bq_client = LazyClient(bigquery.Client)

def _get_table_ref() -> str:
    """Constructs the fully qualified application_artifacts BigQuery path."""
    project_id = get_project_id()
    dataset_id = os.getenv("DATASET_ID", "banking")
    table_id = "application_artifact"
    return f"{project_id}.{dataset_id}.{table_id}"


@router.get("/exceptions", response_model=list[DocumentSummaryResponse])
async def get_exceptions(
    token: ValidatedToken = Depends(get_current_user)
):
    """
    Secure Endpoint: Retrieves W-2 / Paystub low-confidence exceptions currently in 'MISMATCH' status.
    """
    logger.info(f"GET exceptions endpoint invoked. User: {token.email}")
    table_ref = _get_table_ref()
    try:
        exceptions = get_pending_exceptions(table_ref)
        return exceptions
    except Exception as e:
        logger.error(f"Endpoint failed to fetch underwriting exceptions: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve exceptions from database.")

@router.post("/override")
async def post_override(
    payload: UnderwritingOverrideRequest,
    background_tasks: BackgroundTasks,
    token: ValidatedToken = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Secure Endpoint: Commits human loan officer corrections, verifications, 
    and audit notes, transitioning the status atomically to 'PROCESSED'.
    """
    logger.info(f"POST override endpoint invoked. Underwriter: {payload.underwriter_id} (Request from: {token.email})")
    table_ref = _get_table_ref()
    try:
        apply_underwriting_override(table_ref, payload)
        
        record_audit_event(
            db,
            "UNDERWRITING_OVERRIDE_APPLIED",
            {
                "artifact_id": payload.artifact_id,
                "customer_id": payload.customer_id,
                "underwriter_id": payload.underwriter_id,
                "decision": payload.decision.value,
                "verified_income": payload.verifications.calculated_gross_monthly_income
            }
        )
        db.commit()
        
        # Dispatch Asynchronous Webhook Callback to propagate verified status back to Gemini/Dialogflow CX
        background_tasks.add_task(
            trigger_session_propagation_flow,
            table_ref=table_ref,
            artifact_id=payload.artifact_id,
            wages_verified=(payload.decision == UnderwritingDecision.APPROVE),
            gross_income=payload.verifications.calculated_gross_monthly_income
        )
        
        return {
            "status": "SUCCESS",
            "message": "Underwriting override applied successfully.",
            "artifact_id": payload.artifact_id
        }
    except UnderwritingConflictError as conflict_err:
        logger.warning(f"OCC Conflict Exception raised: {conflict_err}")
        raise HTTPException(status_code=409, detail=str(conflict_err))
    except ValueError as val_err:
        logger.error(f"Invalid payload exception: {val_err}")
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as ex:
        logger.error(f"Endpoint failed to process underwriting override: {ex}")
        raise HTTPException(status_code=500, detail="Internal database commit failure.")

@router.get("/artifacts/{artifact_id}/view")
async def get_artifact_view_url(
    artifact_id: str,
    token: ValidatedToken = Depends(get_current_user)
):
    """
    Secure Endpoint: Generates a temporary (5-minute) GCS Signed URL for visual PDF/image rendering.
    """
    logger.info(f"GET view URL invoked for artifact {artifact_id} by {token.email}")
    table_ref = _get_table_ref()
    try:
        gcs_uri = get_artifact_gcs_path(table_ref, artifact_id)
        if not gcs_uri or not gcs_uri.startswith("gs://"):
            raise HTTPException(status_code=404, detail="Artifact source GCS URI is missing or malformed.")
        
        path_parts = gcs_uri.replace("gs://", "").split("/", 1)
        bucket_name, blob_name = path_parts[0], path_parts[1]
        
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        source_credentials, _ = default()
        impersonated_credentials = ImpersonatedCredentials(
            source_credentials=source_credentials,
            target_principal=SERVICE_ACCOUNT_EMAIL,
            target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=5),
            method="GET",
            credentials=impersonated_credentials,
            service_account_email=SERVICE_ACCOUNT_EMAIL
        )
        
        return {"signed_url": url}
        
    except HTTPException as http_ex:
        raise http_ex
    except Exception as ex:
        logger.error(f"Failed to generate GCS signed URL for {artifact_id}: {ex}")
        raise HTTPException(status_code=500, detail="Failed to initialize secure document viewer session.")

