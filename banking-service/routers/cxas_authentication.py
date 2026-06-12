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

from models.authentication import TokenValidateRequest, ValidatedToken
from utils.auth import get_current_user, mint_cxas_token, validate_cxas_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cxas", tags=["cxas-authentication"], dependencies=[Depends(get_current_user)])


@router.post("/auth/token")
async def create_cxas_access_token(user_data: ValidatedToken = Depends(get_current_user)):
    return mint_cxas_token(user_data)


@router.post("/auth/validation", response_model=ValidatedToken)
async def validate_token(request: TokenValidateRequest):
    return validate_cxas_token(request.token)
