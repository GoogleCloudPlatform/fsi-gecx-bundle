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

import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from models.artifact import ArtifactUploadRequest, SignedUrlRequest
from models.authentication import ValidatedToken
from utils.auth import get_current_user
from utils.database import get_db
from services.origination import OriginationService
from unittest.mock import MagicMock

logger = logging.getLogger(__name__)

bq_client = MagicMock()

router = APIRouter(prefix="/artifacts", tags=["artifacts"], dependencies=[Depends(get_current_user)])


def get_origination_service(db: Session = Depends(get_db)) -> OriginationService:
    return OriginationService(db)


@router.post("")
async def upload_artifact(
        request: ArtifactUploadRequest,
        user_data: ValidatedToken = Depends(get_current_user),
        service: OriginationService = Depends(get_origination_service)
):
    return await service.upload_artifact(request, user_data)


@router.post("/upload-and-validate")
async def upload_and_validate(
        request: ArtifactUploadRequest,
        user_data: ValidatedToken = Depends(get_current_user),
        service: OriginationService = Depends(get_origination_service)
):
    return await service.upload_and_validate(request, user_data)


@router.post("/{artifact_id}/extractions")
async def extract(
        artifact_id: str,
        fields: list[str],
        user_data: ValidatedToken = Depends(get_current_user),
        service: OriginationService = Depends(get_origination_service)
):
    return await service.extract_artifact_fields(artifact_id, fields, user_data)


@router.post("/signed-url")
async def generate_upload_url(
        request: SignedUrlRequest,
        user_data: ValidatedToken = Depends(get_current_user),
        service: OriginationService = Depends(get_origination_service)
):
    return service.generate_signed_url(request, user_data)
