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
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from models.authentication import ValidatedToken
from utils.auth import get_current_user
from utils.database import get_db
from services.seeding_service import provision_user_suite, reset_user_suite
from models.identity import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/simulation", tags=["simulation"], dependencies=[Depends(get_current_user)])

@router.post("/provision-my-demo", status_code=status.HTTP_201_CREATED)
def provision_my_demo(
    token: ValidatedToken = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Provisions a complete, isolated banking suite with realistic history for the logged-in user.
    """
    email = token.email
    uid = token.user_id
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authenticated email not found in token claims."
        )
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authenticated user ID not found in token claims."
        )
        
    # Security check: restrict demo provisioning to corporate presenter domains
    email_lower = email.lower()
    allowed_domains = ["google.com", "gcp.solutions", "altostrat.com"]
    if not any(email_lower.endswith(f"@{domain}") for domain in allowed_domains):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo provisioning is restricted to authorized presenter domains."
        )
        
    try:
        summary = provision_user_suite(db, email, uid)
        return {"status": "SUCCESS", "message": "Demo profile provisioned successfully.", "summary": summary}
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(val_err)
        )
    except Exception as e:
        logger.error(f"Failed to provision demo profile for email={email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to provision demo profile: {e}"
        )

@router.post("/reset-my-demo", status_code=status.HTTP_200_OK)
def reset_my_demo(
    token: ValidatedToken = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Clears credit card transactions, resets credit card balances to $0, and resets checking/savings deposit accounts.
    """
    email = token.email
    uid = token.user_id
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authenticated user ID not found in token claims."
        )
        
    # Find the user in database using email or uid
    db.connection().info["_ignore_rbac"] = True
    user = db.query(User).filter((User.auth_provider_uid == uid) | (User.email == email)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No seeded demo profile found to reset. Please provision a profile first."
        )
        
    try:
        reset_user_suite(db, user.id)
        return {"status": "SUCCESS", "message": "Demo profile reset successfully."}
    except Exception as e:
        logger.error(f"Failed to reset demo profile for user_id={user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset demo profile: {e}"
        )


import httpx
import os

DATA_GENERATOR_URL = os.getenv("DATA_GENERATOR_URL", "http://localhost:8001")

@router.post("/surge", status_code=status.HTTP_200_OK)
async def simulate_activity_surge():
    """
    Commands the simulation client to immediately fire 50 rapid-fire card swipes over 10 seconds.
    """
    target_url = f"{DATA_GENERATOR_URL}/simulate-surge"
    logger.info(f"Forwarding surge request to data-generator at: {target_url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(target_url, timeout=15.0)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Data generator surge request failed: {response.text}"
                )
            return response.json()
    except httpx.RequestError as exc:
        logger.error(f"Network error trying to connect to data generator at {target_url}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not connect to synthetic data generator: {exc}"
        )
