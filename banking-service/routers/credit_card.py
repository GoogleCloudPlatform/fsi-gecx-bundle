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
import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from livekit import api as lk_api

from utils.database import get_db
from utils.auth import get_current_user, is_support_staff
from models.authentication import ValidatedToken
from models.credit_card import FinancialAccount, IssuedCard, AccountLedger
from services.credit_card import (
    freeze_card, apply_limit_increase, reverse_posted_fee, initialize_db_and_seed
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/credit-card", tags=["Credit Card Support"])

# LiveKit Server Settings (Defaults match local development Docker setup)
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")


def _get_active_customer_id(
    token: ValidatedToken = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> str:
    """Helper: Resolves active customer ID from validated Firebase token, falling back to seed profile if the user has no custom account."""
    if token and hasattr(token, "claims"):
        user_id = token.claims.get("user_id") or token.claims.get("identifier") or "cust-123"
        account = db.query(FinancialAccount).filter_by(customer_id=user_id).first()
        if account:
            return user_id
    return "cust-123"



def resolve_effective_id(target_id: str | None, current_id: str, token: ValidatedToken) -> str:
    if target_id and target_id != current_id:
        if not is_support_staff(token):
            logger.warning(f"SECURITY ALERT: User {current_id} attempted unauthorized override for customer {target_id}")
            raise HTTPException(status_code=403, detail="Unauthorized target override.")
        return target_id
    return current_id


@router.on_event("startup")
def startup_db_init():
    """Initializes tables and populates seed cardholders on application startup."""
    from utils.database import SessionLocal
    db = SessionLocal()
    try:
        initialize_db_and_seed(db)
    finally:
        db.close()


@router.get("/account")
def get_customer_account(
    target_customer_id: str | None = None,
    db: Session = Depends(get_db),
    token: ValidatedToken = Depends(get_current_user),
    customer_id: str = Depends(_get_active_customer_id)
):
    """Retrieves the customer's financial account and linked cards."""
    effective_id = resolve_effective_id(target_customer_id, customer_id, token)
    logger.info(f"Retrieving account details for customer: {effective_id}")
    account = db.query(FinancialAccount).filter_by(customer_id=effective_id).first()
    if not account:
        raise HTTPException(status_code=404, detail=f"No account found for customer '{effective_id}'")
        
    return {
        "account_id": account.id,
        "credit_limit_cents": account.credit_limit_cents,
        "cleared_balance_cents": account.cleared_balance_cents,
        "available_credit_cents": account.available_credit_cents,
        "payment_due_date": account.payment_due_date,
        "status": account.status,
        "cards": [
            {
                "card_id": card.id,
                "cardholder_name": card.cardholder_name,
                "last_four": card.last_four,
                "card_token": card.card_token,
                "status": card.status,
                "is_virtual": card.is_virtual,
                "exp_month": card.exp_month,
                "exp_year": card.exp_year
            } for card in account.cards
        ]
    }


@router.get("/transactions")
def get_transaction_history(
    target_customer_id: str | None = None,
    db: Session = Depends(get_db),
    token: ValidatedToken = Depends(get_current_user),
    customer_id: str = Depends(_get_active_customer_id)
):
    """Fetches full transaction and statement ledger lines for the customer."""
    effective_id = resolve_effective_id(target_customer_id, customer_id, token)
    account = db.query(FinancialAccount).filter_by(customer_id=effective_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="No account registered.")
        
    ledger = db.query(AccountLedger).filter_by(account_id=account.id).order_by(AccountLedger.posted_at.desc()).all()
    return [
        {
            "id": entry.id,
            "amount_cents": entry.amount_cents,
            "description": entry.description,
            "posted_at": entry.posted_at
        } for entry in ledger
    ]


@router.post("/limit")
def request_limit_increase(
    requested_limit_cents: int,
    target_customer_id: str | None = None,
    db: Session = Depends(get_db),
    token: ValidatedToken = Depends(get_current_user),
    customer_id: str = Depends(_get_active_customer_id)
):
    """Processes credit line adjustments."""
    effective_id = resolve_effective_id(target_customer_id, customer_id, token)
    account = db.query(FinancialAccount).filter_by(customer_id=effective_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="No account registered.")
        
    try:
        res = apply_limit_increase(db, account_id=account.id, requested_limit_cents=requested_limit_cents)
        return {"status": "SUCCESS", "data": res}
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))


@router.post("/fee/reverse")
def dispute_and_reverse_fee(
    transaction_id: str,
    target_customer_id: str | None = None,
    db: Session = Depends(get_db),
    token: ValidatedToken = Depends(get_current_user),
    customer_id: str = Depends(_get_active_customer_id)
):
    """Appends offsetting reversal ledger lines and adjusts balances."""
    effective_id = resolve_effective_id(target_customer_id, customer_id, token)
    account = db.query(FinancialAccount).filter_by(customer_id=effective_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="No account registered.")
        
    try:
        # FSI PM Compliance Audit: Stamp supervisor email in ledger description if reversed by supervisor
        caller_email = token.claims.get("email", "unknown_user") if token and hasattr(token, "claims") else "unknown_user"
        reason = f"REVERSED_BY_{caller_email}" if target_customer_id else "CUSTOMER_VOICE_REQUEST"
        
        res = reverse_posted_fee(db, account_id=account.id, transaction_id=transaction_id, reason=reason)
        return {"status": "SUCCESS", "data": res}
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))


@router.post("/block")
def block_card_instrument(
    card_token: str,
    target_customer_id: str | None = None,
    db: Session = Depends(get_db),
    token: ValidatedToken = Depends(get_current_user),
    customer_id: str = Depends(_get_active_customer_id)
):
    """Permantly blocks a card token."""
    effective_id = resolve_effective_id(target_customer_id, customer_id, token)
    
    # Security Validation: Verify the card token belongs to the effective customer's account to prevent BOLA/IDOR
    card = db.query(IssuedCard).join(FinancialAccount).filter(
        IssuedCard.card_token == card_token,
        FinancialAccount.customer_id == effective_id
    ).first()
    if not card:
        logger.error(f"Security Warning: Attempted unauthorized block for card token {card_token} by customer {effective_id}")
        raise HTTPException(status_code=404, detail="Card token not found or unauthorized.")

    try:
        # Stamp supervisor email in freeze reason for compliance audit
        caller_email = token.claims.get("email", "unknown_user") if token and hasattr(token, "claims") else "unknown_user"
        reason = f"FREEZE_BY_{caller_email}" if target_customer_id else "CUSTOMER_DISPATCH"
        
        res = freeze_card(db, card_token=card_token, reason=reason)
        return {"status": "SUCCESS", "data": res}
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))


def get_google_oidc_token(audience: str) -> str:
    """Fetches OIDC ID token from Google metadata server or local credentials for service-to-service auth."""
    try:
        import google.auth
        import google.auth.transport.requests
        from google.oauth2 import id_token
        
        auth_request = google.auth.transport.requests.Request()
        token = id_token.fetch_id_token(auth_request, audience)
        return token
    except Exception as e:
        logger.warning(f"Could not fetch Google OIDC token automatically: {e}")
        return None

async def trigger_voice_agent_session_async(room_name: str, customer_id: str, session_id: str, mode: str = "audio"):
    voice_service_url = os.getenv("VOICE_AGENT_SERVICE_URL")
    if not voice_service_url:
        logger.warning("VOICE_AGENT_SERVICE_URL environment variable is not defined. Skipping agent dispatch trigger.")
        return

    logger.info(f"Triggering voice agent dispatch: {voice_service_url} for room: {room_name}")
    
    headers = {}
    if voice_service_url.startswith("https"):
        token = get_google_oidc_token(voice_service_url)
        if token:
            headers["Authorization"] = f"Bearer {token}"
            logger.info("Attached Google OIDC ID token to voice agent trigger request.")

    import httpx
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{voice_service_url}/internal/comms/voice/start",
                params={
                    "room_name": room_name,
                    "customer_id": customer_id,
                    "session_id": session_id,
                    "mode": mode
                },
                headers=headers,
                timeout=5.0
            )
            if res.status_code == 200:
                logger.info(f"Voice agent dispatch trigger successful: {res.status_code} - {res.json()}")
            else:
                logger.error(f"Voice agent dispatcher returned non-success status {res.status_code}: {res.text}")
    except Exception as ex:
        logger.error(f"Failed to trigger voice agent dispatch: {ex}")

@router.get("/voice/token")
def get_voice_room_token(
    background_tasks: BackgroundTasks,
    mode: str = "audio",
    customer_id: str = Depends(_get_active_customer_id)
):
    """
    Generates a secure, temporary LiveKit access token enabling 
    the client browser to connect to the WebRTC Voice Support Room.
    
    Triggers the voice worker to dynamically join the room.
    """
    logger.info(f"Generating LiveKit token for customer: {customer_id}")
    room_name = f"room-{customer_id}"
    import uuid
    session_id = str(uuid.uuid4())
    
    try:
        token = lk_api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        token.with_identity(f"user-{customer_id}")
        token.with_grants(lk_api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True
        ))
        
        background_tasks.add_task(trigger_voice_agent_session_async, room_name, customer_id, session_id, mode)
        return {"token": token.to_jwt(), "room_name": room_name, "session_id": session_id}
    except Exception as e:
        logger.error(f"Failed to generate LiveKit token: {e}")
        raise HTTPException(status_code=500, detail="LiveKit token creation error.")
