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

import base64
import datetime
import logging
import uuid

from fastapi import APIRouter, HTTPException, Depends
from google.auth import default
from google.auth.impersonated_credentials import Credentials as ImpersonatedCredentials
from google.cloud import storage, bigquery

from models.artifact import ArtifactUploadRequest, SignedUrlRequest
from models.authentication import ValidatedToken
from utils.auth import get_current_user
from utils.bq import log_artifact_to_bigquery
from utils.gcp import get_project_id
from utils.gemini import extract_data

from pathlib import Path

logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).resolve().parent.parent / "resources" / "sql"


def _load_sql(filename: str) -> str:
    """Loads a clean SQL query template from the resources directory."""
    return (SQL_DIR / filename).read_text()


router = APIRouter(prefix="/artifacts", tags=["artifacts"], dependencies=[Depends(get_current_user)])

PROJECT_ID = get_project_id()
BUCKET_NAME = f"{PROJECT_ID}_banking-interaction-artifacts"
SERVICE_ACCOUNT_EMAIL = f"banking-service-sa@{PROJECT_ID}.iam.gserviceaccount.com"

storage_client = storage.Client()
bq_client = bigquery.Client()



async def _upload_and_log_artifact(
        request: ArtifactUploadRequest,
        customer_id: str
):
    # Validate application ID exists in BigQuery
    dataset_id = "banking"
    table_id = "application"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"

    query = _load_sql("check_loan_application_exists.sql").format(table_ref=table_ref)

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("app_id", "STRING", request.application_id)
        ]
    )
    try:
        query_job = bq_client.query(query, job_config=job_config)
        results = list(query_job.result())
        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"Application with ID {request.application_id} not found"
            )
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"BigQuery validation failed: {e}")
        raise HTTPException(status_code=500, detail="Internal database validation error")

    filename = str(uuid.uuid4())
    file_bytes = base64.b64decode(request.base64_content)

    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(file_bytes, content_type=request.content_type)
    gcs_uri = f"gs://{BUCKET_NAME}/{filename}"

    try:
        artifact_id = log_artifact_to_bigquery(
            application_id=request.application_id,
            artifact_type=request.artifact_type.value,
            gcs_uri=gcs_uri,
            customer_id=customer_id,
            artifact_id=filename
        )
    except Exception as e:
        logger.error(f"Error in _upload_and_log_artifact: {e}")
        raise e
    return artifact_id, gcs_uri


@router.post("")
async def upload_artifact(
        request: ArtifactUploadRequest,
        user_data: ValidatedToken = Depends(get_current_user)
):
    artifact_id, gcs_uri = await _upload_and_log_artifact(request, customer_id=user_data.user_id)

    return {
        "message": "File uploaded successfully and logged to BigQuery",
        "gcs_uri": gcs_uri,
        "artifact_id": artifact_id
    }


@router.post("/upload-and-validate")
async def upload_and_validate(
        request: ArtifactUploadRequest,
        user_data: ValidatedToken = Depends(get_current_user)
):
    # 1. Upload and log (using helper)
    artifact_id, gcs_uri = await _upload_and_log_artifact(request, customer_id=user_data.user_id)

    # 2. Extract data using fields from enum
    fields = request.artifact_type.fields_to_extract

    if not fields:
        return {
            "message": "File uploaded successfully, but no fields defined for extraction for this document type.",
            "artifact_id": artifact_id,
            "gcs_uri": gcs_uri
        }

    result = await extract_data(gcs_uri, request.content_type, fields, user_id=user_data.user_id)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return {
        "message": "File uploaded and data extracted successfully",
        "artifact_id": artifact_id,
        "gcs_uri": gcs_uri,
        "extraction_result": result
    }


@router.post("/{artifact_id}/extractions")
async def extract(artifact_id: str, fields: list[str], user_data: ValidatedToken = Depends(get_current_user)):
    dataset_id = "banking"
    table_id = "application_artifact"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"

    query = _load_sql("get_artifact_gcs_path.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("artifact_id", "STRING", artifact_id)
        ]
    )
    try:
        query_job = bq_client.query(query, job_config=job_config)
        results = list(query_job.result())

        if not results:
            raise HTTPException(status_code=404, detail="Artifact not found in BigQuery")

        gcs_uri = results[0].file_path_gcs

        path_parts = gcs_uri.replace("gs://", "").split("/", 1)
        bucket_name, blob_name = path_parts[0], path_parts[1]

        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.reload()

        file_type = blob.content_type

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"BigQuery lookup failed: {e}")
        raise HTTPException(status_code=500, detail=f"BigQuery lookup failed: {str(e)}")

    result = await extract_data(gcs_uri, file_type, fields, user_id=user_data.user_id)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.post("/signed-url")
async def generate_upload_url(
        request: SignedUrlRequest,
        user_data: ValidatedToken = Depends(get_current_user)
):
    # Validate application ID exists in BigQuery
    dataset_id = "banking"
    table_id = "application"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"

    query = _load_sql("check_loan_application_exists.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("app_id", "STRING", request.application_id)
        ]
    )
    try:
        query_job = bq_client.query(query, job_config=job_config)
        results = list(query_job.result())
        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"Application with ID {request.application_id} not found"
            )
    except HTTPException as http_exc:
        raise http_exc

    except Exception as e:
        logger.error(f"BigQuery validation failed: {e}")
        raise HTTPException(status_code=500, detail="Internal database validation error")

    filename = str(uuid.uuid4())
    gcs_uri = f"gs://{BUCKET_NAME}/{filename}"

    try:
        log_artifact_to_bigquery(
            application_id=request.application_id,
            artifact_type=request.artifact_type.value if request.artifact_type else "W2",
            gcs_uri=gcs_uri,
            customer_id=user_data.user_id,
            artifact_id=filename,
            status="PENDING_CLASSIFICATION"
        )
    except Exception as e:
        logger.error(f"Failed to log placeholder artifact to BigQuery: {e}")
        raise HTTPException(status_code=500, detail="Failed to register artifact placeholder in database.")

    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)

    try:
        source_credentials, _ = default()
        impersonated_credentials = ImpersonatedCredentials(
            source_credentials=source_credentials,
            target_principal=SERVICE_ACCOUNT_EMAIL,
            target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )

        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=15),
            method="PUT",
            content_type=request.content_type,
            credentials=impersonated_credentials,
            service_account_email=SERVICE_ACCOUNT_EMAIL
        )
    except Exception as e:
        logger.error(f"Failed to generate signed URL: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate signed URL: {str(e)}")

    return {
        "signed_url": url,
        "artifact_id": filename,
        "gcs_uri": gcs_uri
    }
