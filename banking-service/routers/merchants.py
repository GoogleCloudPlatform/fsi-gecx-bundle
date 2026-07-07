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

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from utils.database import get_db
from models.merchant import MerchantMaster
from services.merchant_service import MerchantEnrichmentService

router = APIRouter(prefix="/api/v1/merchants", tags=["Merchant Intelligence & Enrichment"])
v1_router = APIRouter(prefix="/v1/merchants", tags=["Merchant Intelligence & Enrichment"])
alias_router = APIRouter(prefix="/merchants", tags=["Merchant Intelligence & Enrichment"])


class MerchantResponse(BaseModel):
    merchant_id: str
    clean_name: str
    raw_descriptor_pattern: str
    mcc: str
    category: str
    country_code: str
    logo_url: Optional[str] = None
    merchant_domain: Optional[str] = None
    is_subscription: bool
    is_international: bool
    risk_score: int

    class Config:
        from_attributes = True


class EnrichRequest(BaseModel):
    raw_descriptor: str = Field(..., description="Raw POS terminal transaction descriptor string e.g. 'UBER *TRIP CDMX'")
    mcc: Optional[str] = Field(None, description="Optional raw 4-digit MCC from acquiring bank terminal e.g. '4121'")
    country_code: str = Field("USA", description="ISO 3-letter country code e.g. 'USA', 'MEX', 'GBR'")


class CreateMerchantRequest(BaseModel):
    merchant_id: str = Field(..., description="Unique MID e.g. 'MID-CUSTOM-001'")
    clean_name: str = Field(..., description="Normalized brand name e.g. 'Acme Corp'")
    raw_descriptor_pattern: str = Field(..., description="SQL LIKE regex pattern e.g. 'ACME CORP%'")
    mcc: str = Field(..., description="4-digit ISO Merchant Category Code e.g. '5311'")
    category: str = Field(..., description="Human-readable spend category e.g. 'Retail'")
    country_code: str = Field("USA", description="ISO 3-letter country code")
    logo_url: Optional[str] = Field(None, description="CDN logo URL e.g. 'https://logo.clearbit.com/acme.com'")
    merchant_domain: Optional[str] = Field(None, description="Primary website domain e.g. 'acme.com'")
    is_subscription: bool = False
    is_international: bool = False
    risk_score: int = 0


@router.get("", response_model=List[MerchantResponse], summary="List Master Merchant Catalog")
@v1_router.get("", response_model=List[MerchantResponse], summary="List Master Merchant Catalog")
@alias_router.get("", response_model=List[MerchantResponse], summary="List Master Merchant Catalog")
def list_merchants(
    category: Optional[str] = Query(None, description="Filter by spend category"),
    country: Optional[str] = Query(None, description="Filter by ISO country code"),
    is_international: Optional[bool] = Query(None, description="Filter by international anomaly status"),
    db: Session = Depends(get_db),
):
    """
    Returns filtered list of merchant entities from the Master Merchant Database (`merchants.merchant_master`).
    Backed by microsecond in-memory TTL caching.
    """
    return MerchantEnrichmentService.list_merchants(db, category=category, country=country, is_international=is_international)


@router.get("/{merchant_id}", response_model=MerchantResponse, summary="Get Single Merchant Details")
@v1_router.get("/{merchant_id}", response_model=MerchantResponse, summary="Get Single Merchant Details")
@alias_router.get("/{merchant_id}", response_model=MerchantResponse, summary="Get Single Merchant Details")
def get_merchant(merchant_id: str, db: Session = Depends(get_db)):
    """Retrieves authoritative brand intelligence and CDN logo mapping for a specific MID."""
    MerchantEnrichmentService.load_cache_if_needed(db)
    dto = MerchantEnrichmentService._merchants_by_id.get(merchant_id)
    if not dto:
        raise HTTPException(status_code=404, detail=f"Merchant ID '{merchant_id}' not found in Master Merchant Database.")
    return dto


@router.post("/enrich", response_model=Dict[str, Any], summary="Simulate Real-Time Transaction Enrichment")
@v1_router.post("/enrich", response_model=Dict[str, Any], summary="Simulate Real-Time Transaction Enrichment")
@alias_router.post("/enrich", response_model=Dict[str, Any], summary="Simulate Real-Time Transaction Enrichment")
def enrich_transaction(req: EnrichRequest, db: Session = Depends(get_db)):
    """
    Simulates a live Tier-1 enrichment API lookup (e.g. MX Atrium / Plaid Enrich / Visa VMDS).
    Cleans raw POS terminal strings, resolves entities, and returns normalized brand JSON with CDN logo URLs.
    """
    return MerchantEnrichmentService.enrich_transaction(
        db, raw_descriptor=req.raw_descriptor, mcc=req.mcc, country=req.country_code
    )


@router.post("", response_model=MerchantResponse, status_code=201, summary="Add Custom Demo Merchant")
@v1_router.post("", response_model=MerchantResponse, status_code=201, summary="Add Custom Demo Merchant")
@alias_router.post("", response_model=MerchantResponse, status_code=201, summary="Add Custom Demo Merchant")
def create_custom_merchant(req: CreateMerchantRequest, db: Session = Depends(get_db)):
    """
    Dynamically registers a custom brand entity in the Master Merchant Database.
    Ideal for live client presentations or sales engineer customizations.
    """
    from models.merchant import MerchantStore
    existing = db.query(MerchantMaster).filter(MerchantMaster.merchant_id == req.merchant_id).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Merchant ID '{req.merchant_id}' already exists.")

    merchant = MerchantMaster(
        merchant_id=req.merchant_id,
        clean_name=req.clean_name,
        default_mcc=req.mcc,
        merchant_domain=req.merchant_domain,
        logo_url=req.logo_url,
        is_subscription=req.is_subscription
    )
    db.add(merchant)
    
    store = MerchantStore(
        merchant_id=req.merchant_id,
        location_name=req.clean_name,
        raw_descriptor=req.raw_descriptor_pattern,
        country_code=req.country_code,
        is_international=req.is_international,
        risk_score=req.risk_score
    )
    db.add(store)
    db.commit()
    db.refresh(merchant)
    MerchantEnrichmentService.invalidate_cache()
    
    from services.merchant_service import MerchantDTO
    return MerchantDTO(
        id=merchant.id,
        merchant_id=merchant.merchant_id,
        clean_name=merchant.clean_name,
        location_name=store.location_name,
        raw_descriptor_pattern=store.raw_descriptor,
        mcc=merchant.default_mcc,
        category=req.category,
        country_code=store.country_code,
        logo_url=merchant.logo_url,
        merchant_domain=merchant.merchant_domain,
        is_subscription=merchant.is_subscription,
        is_international=store.is_international,
        risk_score=store.risk_score
    )
