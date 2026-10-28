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

"""Public product catalog.

Deliberately unauthenticated: the response is marketing disclosure data (rates,
fees, benefits) rendered on logged-out UI pages and carries no per-user fields.
Read-only; there are no write routes here.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from models.credit_product_catalog import CreditProductListResponse
from services.credit_product_catalog import list_active_credit_products, present_credit_product
from utils.database import get_db

router = APIRouter(prefix="/api/v1/catalog", tags=["Product Catalog"])
v1_router = APIRouter(prefix="/v1/catalog", tags=["Product Catalog"])


@router.get("/credit-products", response_model=CreditProductListResponse)
@v1_router.get("/credit-products", response_model=CreditProductListResponse)
def list_credit_products(db: Session = Depends(get_db)) -> CreditProductListResponse:
    """Active credit card products, ordered by display_order."""
    return CreditProductListResponse(
        products=[present_credit_product(p) for p in list_active_credit_products(db)]
    )
