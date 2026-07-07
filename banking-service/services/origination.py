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
from typing import Dict, Any, Tuple, List
from fastapi import HTTPException
from google.auth import default
from google.auth.impersonated_credentials import Credentials as ImpersonatedCredentials
from google.cloud import storage
from sqlalchemy.orm import Session

from models.application import ApplicationCreateRequest, ApplicationUpdateRequest
from models.artifact import ArtifactUploadRequest, SignedUrlRequest
from models.authentication import ValidatedToken
from models.origination import ApplicationArtifact
from repositories import origination as origination_repo
from utils.gcp import get_project_id
from utils.gemini import extract_data
from utils.lazy_clients import LazyClient

logger = logging.getLogger(__name__)

PROJECT_ID = get_project_id()
BUCKET_NAME = f"{PROJECT_ID}_banking-interaction-artifacts"
SERVICE_ACCOUNT_EMAIL = f"banking-service-sa@{PROJECT_ID}.iam.gserviceaccount.com"

storage_client = LazyClient(storage.Client)


class OriginationService:
    """Service layer encapsulating loan origination applications and document artifacts."""

    def __init__(self, db: Session):
        self.db = db

    def create_application(self, request: ApplicationCreateRequest, token: ValidatedToken) -> Dict[str, Any]:
        application_id = origination_repo.log_application(
            self.db,
            token.user_id,
            request.product_category,
            request.product_type,
            request.requested_amount
        )
        return {
            "message": "Application created successfully",
            "application_id": application_id
        }

    def update_application(self, application_id: str, request: ApplicationUpdateRequest, token: ValidatedToken) -> Dict[str, Any]:
        origination_repo.update_application(
            db=self.db,
            application_id=application_id,
            auth_provider_uid=token.user_id,
            requested_amount=request.requested_amount,
            application_status=request.application_status
        )
        return {
            "message": "Application updated successfully",
            "application_id": application_id
        }

    async def upload_and_log_artifact(self, request: ArtifactUploadRequest, customer_id: str) -> Tuple[str, str]:
        app = origination_repo.get_application(self.db, request.application_id)
        if not app:
            raise HTTPException(
                status_code=404,
                detail=f"Application with ID {request.application_id} not found"
            )

        filename = str(uuid.uuid4())
        file_bytes = base64.b64decode(request.base64_content)

        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(file_bytes, content_type=request.content_type)
        gcs_uri = f"gs://{BUCKET_NAME}/{filename}"

        try:
            artifact_id = origination_repo.log_artifact(
                self.db,
                application_id=request.application_id,
                artifact_type=request.artifact_type.value,
                gcs_uri=gcs_uri,
                auth_provider_uid=customer_id,
                artifact_id=filename
            )
        except Exception as e:
            logger.error(f"Error in upload_and_log_artifact: {e}")
            raise e
        return artifact_id, gcs_uri

    async def upload_artifact(self, request: ArtifactUploadRequest, token: ValidatedToken) -> Dict[str, Any]:
        artifact_id, gcs_uri = await self.upload_and_log_artifact(request, customer_id=token.user_id)
        return {
            "message": "File uploaded successfully and logged to database",
            "artifact_id": artifact_id,
            "gcs_uri": gcs_uri
        }

    async def upload_and_validate(self, request: ArtifactUploadRequest, token: ValidatedToken) -> Dict[str, Any]:
        artifact_id, gcs_uri = await self.upload_and_log_artifact(request, customer_id=token.user_id)

        fields = request.artifact_type.fields_to_extract
        if not fields:
            return {
                "message": "File uploaded successfully, but no fields defined for extraction for this document type.",
                "artifact_id": artifact_id,
                "gcs_uri": gcs_uri
            }

        result = await extract_data(gcs_uri, request.content_type, fields, user_id=token.user_id)

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return {
            "message": "File uploaded and data extracted successfully",
            "artifact_id": artifact_id,
            "gcs_uri": gcs_uri,
            "extraction_result": result
        }

    async def extract_artifact_fields(self, artifact_id: str, fields: List[str], token: ValidatedToken) -> Dict[str, Any]:
        try:
            art = self.db.query(ApplicationArtifact).filter(ApplicationArtifact.artifact_id == artifact_id).first()
            if not art:
                raise HTTPException(status_code=404, detail="Artifact not found in database")

            gcs_uri = art.gcs_uri
            path_parts = gcs_uri.replace("gs://", "").split("/", 1)
            bucket_name, blob_name = path_parts[0], path_parts[1]

            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            blob.reload()

            file_type = blob.content_type
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            logger.error(f"Database lookup failed: {e}")
            raise HTTPException(status_code=500, detail=f"Database lookup failed: {str(e)}")

        result = await extract_data(gcs_uri, file_type, fields, user_id=token.user_id)
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result

    def generate_signed_url(self, request: SignedUrlRequest, token: ValidatedToken) -> Dict[str, Any]:
        app = origination_repo.get_application(self.db, request.application_id)
        if not app:
            raise HTTPException(
                status_code=404,
                detail=f"Application with ID {request.application_id} not found"
            )

        filename = str(uuid.uuid4())
        gcs_uri = f"gs://{BUCKET_NAME}/{filename}"

        try:
            origination_repo.log_artifact(
                self.db,
                application_id=request.application_id,
                artifact_type=request.artifact_type.value if request.artifact_type else "W2",
                gcs_uri=gcs_uri,
                auth_provider_uid=token.user_id,
                artifact_id=filename
            )
        except Exception as e:
            logger.error(f"Failed to log placeholder artifact to database: {e}")
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
