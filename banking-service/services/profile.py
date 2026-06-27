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
from typing import Dict, Any, List
from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.authentication import ValidatedToken
from models.profile import CustomerProfileCreateRequest, CustomerProfileUpdateRequest
from repositories import identity as identity_repo

logger = logging.getLogger(__name__)


class ProfileService:
    """Service layer encapsulating customer profile management and auto-provisioning."""

    def __init__(self, db: Session):
        self.db = db

    def get_or_provision_profile(self, token: ValidatedToken) -> Dict[str, Any]:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        customer = identity_repo.get_customer(self.db, user_id)
        if not customer:
            logger.info(f"User {user_id} not found in database. Auto-provisioning from token claims...")
            email = token.claims.get("email") or ""
            name = token.claims.get("name") or ""
            phone_number = token.claims.get("phone_number")

            name_parts = name.strip().split(" ", 1)
            first_name = name_parts[0] if len(name_parts) > 0 else ""
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            try:
                customer = identity_repo.create_customer(
                    self.db,
                    user_id,
                    first_name,
                    last_name,
                    email,
                    phone_number,
                )
                logger.info(f"Successfully auto-provisioned profile for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to auto-provision user {user_id}: {e}")
                raise HTTPException(status_code=500, detail="Failed to auto-provision user profile")

        return customer

    def create_profile(self, request: CustomerProfileCreateRequest, token: ValidatedToken) -> Dict[str, Any]:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        existing = identity_repo.get_customer(self.db, user_id)
        if existing:
            raise HTTPException(status_code=409, detail="Customer profile already exists")

        identity_repo.create_customer(
            self.db,
            user_id,
            request.first_name,
            request.last_name,
            token.email,
            request.phone_number
        )
        return {
            "message": "Customer profile created successfully",
            "user_id": user_id
        }

    def update_profile(self, request: CustomerProfileUpdateRequest, token: ValidatedToken) -> Dict[str, Any]:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        existing = identity_repo.get_customer(self.db, user_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Customer profile not found")

        identity_repo.update_customer(
            db=self.db,
            auth_provider_uid=user_id,
            first_name=request.first_name,
            last_name=request.last_name,
            phone_number=request.phone_number
        )
        return {
            "message": "Customer profile updated successfully",
            "user_id": user_id
        }

    def get_all_customers(self, token: ValidatedToken) -> List[Dict[str, Any]]:
        if not token.user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        customers = identity_repo.get_all_customers(self.db)
        return customers
