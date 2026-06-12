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

from fastapi import APIRouter, HTTPException, Depends

from models.authentication import ValidatedToken
from models.profile import CustomerProfileCreateRequest, CustomerProfile, CustomerProfileUpdateRequest, \
    CustomerShortProfile
from utils.auth import get_current_user
from utils.bq import get_customer_from_bigquery, create_customer_in_bigquery, update_customer_in_bigquery, \
    get_all_customers_from_bigquery

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=CustomerProfile)
async def get_profile(
        token: ValidatedToken = Depends(get_current_user)
):
    try:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        customer = get_customer_from_bigquery(user_id)
        if not customer:
            logger.info(f"User {user_id} not found in database. Auto-provisioning from token claims...")
            # Extract names and email from claims
            email = token.claims.get("email") or ""
            name = token.claims.get("name") or ""
            phone_number = token.claims.get("phone_number") or "+1-555-019-9999"

            # Split display name into first and last name
            name_parts = name.strip().split(" ", 1)
            first_name = name_parts[0] if len(name_parts) > 0 else ""
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            try:
                create_customer_in_bigquery(
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

            # Retrieve again
            customer = get_customer_from_bigquery(user_id)
            if not customer:
                raise HTTPException(status_code=500, detail="Failed to retrieve auto-provisioned profile")

        return customer
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in get_profile: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.post("", response_model=dict)
async def create_profile(
        request: CustomerProfileCreateRequest,
        token: ValidatedToken = Depends(get_current_user)
):
    try:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        existing = get_customer_from_bigquery(user_id)
        if existing:
            raise HTTPException(status_code=409, detail="Customer profile already exists")

        create_customer_in_bigquery(
            user_id,
            request.first_name,
            request.last_name,
            token.email,
            request.phone_number or "+1-555-019-9999"
        )
        return {
            "message": "Customer profile created successfully",
            "user_id": user_id
        }
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in create_profile: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.put("", response_model=dict)
async def update_profile(
        request: CustomerProfileUpdateRequest,
        token: ValidatedToken = Depends(get_current_user)
):
    try:
        user_id = token.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        existing = get_customer_from_bigquery(user_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Customer profile not found")

        update_customer_in_bigquery(
            user_id=user_id,
            first_name=request.first_name,
            last_name=request.last_name,
            phone_number=request.phone_number
        )
        return {
            "message": "Customer profile updated successfully",
            "user_id": user_id
        }
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in update_profile: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")


@router.get("/customers", response_model=list[CustomerShortProfile])
async def get_all_customers(
        token: ValidatedToken = Depends(get_current_user)
):
    try:
        if not token.user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        customers = get_all_customers_from_bigquery()
        return customers
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in get_all_customers: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")
