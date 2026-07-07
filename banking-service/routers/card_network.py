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

import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from utils.database import get_db
from utils.maintenance import ensure_system_writable
from services.card_network import process_authorization, process_settlement, process_reversal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/card-network", tags=["Card Network Switch"])
v1_router = APIRouter(prefix="/v1/card-network", tags=["Card Network Switch"])

CARD_NETWORK_TOKEN = os.getenv("CARD_NETWORK_SWITCH_TOKEN", "switch-secret-key-12345")

def verify_network_switch_secret(x_card_network_token: str = Header(None, alias="X-Card-Network-Token")):
    if not x_card_network_token or x_card_network_token != CARD_NETWORK_TOKEN:
        logger.warning(f"Unauthorized switch access attempt with token: {x_card_network_token}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized card network switch credentials."
        )

# Pydantic Schemas
class CardAuthHoldRequest(BaseModel):
    card_token: str = Field(..., description="PCI-DSS card reference token")
    amount_cents: int = Field(..., gt=0, description="Hold request amount in cents")
    retrieval_reference_number: str = Field(..., max_length=12, description="Retrieval reference number (RRN)")
    merchant_category_code: str = Field(..., max_length=4, description="Merchant category code (MCC)")
    merchant_name: str = Field(..., description="Merchant name")
    card_network: str = Field("VISA", description="Card network provider")

class CardSettlementRequest(BaseModel):
    retrieval_reference_number: str = Field(..., max_length=12, description="RRN matching the hold authorization")
    amount_cents: int = Field(..., gt=0, description="Final settlement amount in cents")
    description: str | None = Field(None, description="Optional transaction details")

class CardReversalRequest(BaseModel):
    retrieval_reference_number: str = Field(..., max_length=12, description="RRN matching the hold authorization to void")

@router.post("/authorize", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_network_switch_secret)])
@v1_router.post("/authorize", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_network_switch_secret)])
def card_network_authorize(
    request: CardAuthHoldRequest,
    db: Session = Depends(get_db)
):
    """
    Simulates real-time merchant swipe hold authorization requests from network switch.
    """
    ensure_system_writable("card authorization")
    res = process_authorization(db, request.model_dump())
    return res

@router.post("/settle", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_network_switch_secret)])
@v1_router.post("/settle", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_network_switch_secret)])
def card_network_settle(
    request: CardSettlementRequest,
    db: Session = Depends(get_db)
):
    """
    Simulates clearing card swipes and posting transactions from network switch.
    """
    ensure_system_writable("card settlement")
    try:
        return process_settlement(db, request.model_dump())
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err)
        )
    except Exception as e:
        logger.error(f"Settlement failed for RRN={request.retrieval_reference_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Settlement execution failure: {e}"
        )

@router.post("/reverse", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_network_switch_secret)])
@v1_router.post("/reverse", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_network_switch_secret)])
def card_network_reverse(
    request: CardReversalRequest,
    db: Session = Depends(get_db)
):
    """
    Simulates hold voids / reversal clearing.
    """
    ensure_system_writable("card reversal")
    try:
        return process_reversal(db, request.model_dump())
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err)
        )
    except Exception as e:
        logger.error(f"Reversal failed for RRN={request.retrieval_reference_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reversal execution failure: {e}"
        )
