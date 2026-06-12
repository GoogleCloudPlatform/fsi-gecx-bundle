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
import os
import time

from fastapi import APIRouter, Depends, HTTPException
from joserfc import jwt, jwk

from models.authentication import ValidatedToken
from utils.auth import get_current_user
from utils.gcp import get_secret

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ccai", tags=["ccai-authentication"], dependencies=[Depends(get_current_user)])


@router.post("/auth/token")
async def chat_auth_token(user_data: ValidatedToken = Depends(get_current_user)):
    company_name = os.getenv("COMPANY_NAME", "Nova Horizon Credit Union")

    try:
        company_secret = get_secret("ccai-company-secret")
    except Exception as e:
        logger.error(f"Error getting ccai-company-secret: {e}")
        raise HTTPException(status_code=500, detail="Error getting CCAI configuration.")

    secret_key = jwk.OctKey.import_key(company_secret)

    now = int(time.time())
    payload = {
        'iss': company_name,
        'iat': now,
        'exp': now + 3600,
    }

    # Use values from verified IAP JWT
    if user_data:
        payload['identifier'] = user_data.user_id
        payload['name'] = user_data.name
        payload['email'] = user_data.email

    token = jwt.encode({'alg': 'HS256'}, payload, secret_key)
    return {'token': token}
