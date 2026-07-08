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
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from livekit import api as lk_api
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models.authentication import ValidatedToken
from models.fdx import PersonalFinanceCategory
from repositories.credit_card import CreditCardRepository
from services.credit_card import (
    apply_limit_increase,
    freeze_card,
    get_account_summary_dto,
    get_transaction_history_dto,
    reverse_posted_fee,
    unfreeze_card,
)
from services.fraud_alerts import FraudAlertService
from services.taxonomy_service import TaxonomyService
from services.simulation import SimulationService
from utils.auth import get_current_user, is_support_staff
from utils.database import get_db
from utils.internal_auth import is_valid_internal_switch_token
from utils.internal_execution import InternalServiceContext, require_internal_simulation_context
from utils.maintenance import ensure_system_writable

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/credit-card", tags=["Credit Card Support"])
apiv1_router = APIRouter(prefix="/api/v1/credit-card", tags=["Credit Card Support"])
v1_router = APIRouter(prefix="/v1/credit-card", tags=["Credit Card Support"])

# LiveKit Server Settings (Defaults match local development Docker setup)
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")


def get_credit_card_repo(db: Session = Depends(get_db)) -> CreditCardRepository:
    """Dependency provider resolving the CreditCardRepository."""
    return CreditCardRepository(db)


def _get_active_customer_id(
    token: ValidatedToken = Depends(get_current_user),
    x_target_customer_id: str | None = Header(None),
    repo: CreditCardRepository = Depends(get_credit_card_repo),
    fallback: bool = False
) -> str:
    """Helper: Resolves active customer ID from validated Firebase token."""
    if x_target_customer_id and is_support_staff(token):
        return x_target_customer_id

    if token and hasattr(token, "claims"):
        user_id = token.user_id or token.claims.get("user_id") or token.claims.get("identifier") or token.claims.get("sub")
        if user_id:
            account = repo.get_account_by_customer(user_id)
            if account:
                return user_id
    if fallback:
        accounts = repo.get_all_accounts()
        if accounts:
            return str(accounts[0].customer_id)
    raise HTTPException(status_code=404, detail="No active credit card account found for the current user.")



def resolve_effective_id(target_id: str | None, current_id: str, token: ValidatedToken) -> str:
    if target_id and target_id != current_id:
        if not is_support_staff(token):
            logger.warning(f"SECURITY ALERT: User {current_id} attempted unauthorized override for customer {target_id}")
            raise HTTPException(status_code=403, detail="Unauthorized target override.")
        return target_id
    return current_id


async def verify_admin_or_internal_secret(
    request: Request,
    x_card_network_token: str | None = Header(None, alias="X-Card-Network-Token")
):
    if is_valid_internal_switch_token(x_card_network_token):
        return True
        
    try:
        auth_header = request.headers.get("Authorization")
        forwarded_header = request.headers.get("X-Forwarded-Authorization")
        token = await get_current_user(
            request=request,
            auth=HTTPAuthorizationCredentials(scheme="Bearer", credentials=auth_header.split(" ", 1)[1])
            if auth_header and auth_header.startswith("Bearer ")
            else None,
            forwarded_auth=HTTPAuthorizationCredentials(scheme="Bearer", credentials=forwarded_header.split(" ", 1)[1])
            if forwarded_header and forwarded_header.startswith("Bearer ")
            else None,
        )
        if token and token.email:
            email_lower = token.email.lower()
            allowed_domains = [
                domain.strip().lower()
                for domain in os.getenv("ADMIN_EMAIL_DOMAINS", "google.com,gcp.solutions,altostrat.com").split(",")
                if domain.strip()
            ]
            if any(email_lower.endswith(f"@{domain}") for domain in allowed_domains):
                return True
    except Exception as e:
        logger.warning(f"Presenter auth check failed in active-cards: {e}")
        
    raise HTTPException(status_code=401, detail="Unauthorized access to active cards list.")


@router.get("/active-cards")
@apiv1_router.get("/active-cards")
@v1_router.get("/active-cards")
def get_active_cards(
    db: Session = Depends(get_db),
    _auth: bool = Depends(verify_admin_or_internal_secret)
):
    """Returns all active credit card tokens and basic persona metadata for synthetic data simulation."""
    ensure_system_writable("active card discovery")
    return SimulationService(db).list_active_cards_for_simulation()


def list_active_cards_for_simulation(db: Session) -> dict:
    """Compatibility wrapper for synthetic transaction tooling."""
    return SimulationService(db).list_active_cards_for_simulation()





@router.get("/account")
def get_customer_account(
    target_customer_id: str | None = None,
    x_target_customer_id: str | None = Header(None),
    repo: CreditCardRepository = Depends(get_credit_card_repo),
    token: ValidatedToken = Depends(get_current_user),
    customer_id: str = Depends(_get_active_customer_id)
):
    """Retrieves the customer's financial account and linked cards."""
    target_id = target_customer_id or x_target_customer_id
    effective_id = resolve_effective_id(target_id, customer_id, token)
    logger.info(f"Retrieving account details for customer: {effective_id}")
    dto = get_account_summary_dto(repo, effective_id)
    if not dto:
        raise HTTPException(status_code=404, detail=f"No account found for customer '{effective_id}'")
    return dto


@router.get("/transactions")
def get_transaction_history(
    target_customer_id: str | None = None,
    repo: CreditCardRepository = Depends(get_credit_card_repo),
    token: ValidatedToken = Depends(get_current_user),
    customer_id: str = Depends(_get_active_customer_id)
):
    """Fetches full transaction and statement ledger lines for the customer, including pending authorizations."""
    effective_id = resolve_effective_id(target_customer_id, customer_id, token)
    dto = get_transaction_history_dto(repo, effective_id)
    if dto is None:
        raise HTTPException(status_code=404, detail="No account registered.")
    return dto


@router.get("/taxonomies", response_model=Dict[str, Dict[str, str]])
def list_internal_taxonomies(token: ValidatedToken = Depends(get_current_user)):
    """Returns authoritative MCC-to-taxonomy mapping for internal analytics and UI dashboards."""
    return TaxonomyService.get_taxonomy_map()


@router.get("/taxonomies/{mcc}", response_model=PersonalFinanceCategory)
def get_internal_taxonomy_by_mcc(mcc: str, token: ValidatedToken = Depends(get_current_user)):
    """Returns granular category object for a specific MCC code."""
    return TaxonomyService.get_category(mcc)


@router.post("/limit")
def request_limit_increase(
    requested_limit_cents: int,
    target_customer_id: str | None = None,
    db: Session = Depends(get_db),
    repo: CreditCardRepository = Depends(get_credit_card_repo),
    token: ValidatedToken = Depends(get_current_user),
    customer_id: str = Depends(_get_active_customer_id)
):
    """Processes credit line adjustments."""
    effective_id = resolve_effective_id(target_customer_id, customer_id, token)
    account = repo.get_account_by_customer(effective_id)
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
    repo: CreditCardRepository = Depends(get_credit_card_repo),
    token: ValidatedToken = Depends(get_current_user),
    customer_id: str = Depends(_get_active_customer_id)
):
    """Appends offsetting reversal ledger lines and adjusts balances."""
    effective_id = resolve_effective_id(target_customer_id, customer_id, token)
    account = repo.get_account_by_customer(effective_id)
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
    repo: CreditCardRepository = Depends(get_credit_card_repo),
    token: ValidatedToken = Depends(get_current_user),
    customer_id: str = Depends(_get_active_customer_id)
):
    """Permantly blocks a card token."""
    effective_id = resolve_effective_id(target_customer_id, customer_id, token)
    
    # Security Validation: Verify the card token belongs to the effective customer's account to prevent BOLA/IDOR
    card = repo.get_card_by_token_secured(card_token, effective_id)
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


@router.post("/unfreeze")
def unfreeze_card_instrument(
    card_token: str,
    target_customer_id: str | None = None,
    db: Session = Depends(get_db),
    repo: CreditCardRepository = Depends(get_credit_card_repo),
    token: ValidatedToken = Depends(get_current_user),
    customer_id: str = Depends(_get_active_customer_id)
):
    """Unblocks and reactivates a card token."""
    effective_id = resolve_effective_id(target_customer_id, customer_id, token)
    
    # Security Validation: Verify the card token belongs to the effective customer's account to prevent BOLA/IDOR
    card = repo.get_card_by_token_secured(card_token, effective_id)
    if not card:
        logger.error(f"Security Warning: Attempted unauthorized unblock for card token {card_token} by customer {effective_id}")
        raise HTTPException(status_code=404, detail="Card token not found or unauthorized.")

    try:
        caller_email = token.claims.get("email", "unknown_user") if token and hasattr(token, "claims") else "unknown_user"
        reason = f"UNFREEZE_BY_{caller_email}" if target_customer_id else "CUSTOMER_DISPATCH"
        
        res = unfreeze_card(db, card_token=card_token, reason=reason)
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
    db: Session = Depends(get_db),
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
        fraud_context = FraudAlertService(db).get_active_voice_context(auth_provider_uid=customer_id)
        background_tasks.add_task(trigger_voice_agent_session_async, room_name, customer_id, session_id, mode)
        return {
            "token": token.to_jwt(),
            "room_name": room_name,
            "session_id": session_id,
            "fraud_context": fraud_context,
        }
    except Exception as e:
        logger.error(f"Failed to generate LiveKit token: {e}")
        raise HTTPException(status_code=500, detail="LiveKit token creation error.")


@router.get("/voice/context")
def get_voice_session_context(
    db: Session = Depends(get_db),
    customer_id: str = Depends(_get_active_customer_id),
):
    """Returns customer-specific fraud or support context that should be available at voice-session start."""
    return FraudAlertService(db).get_active_voice_context(auth_provider_uid=customer_id)


@router.post("/fraud-alert/acknowledge")
@apiv1_router.post("/fraud-alert/acknowledge")
@v1_router.post("/fraud-alert/acknowledge")
def acknowledge_fraud_alert_false_positive(
    db: Session = Depends(get_db),
    customer_id: str = Depends(_get_active_customer_id),
):
    """Resolves the customer's latest open fraud alert as recognized card activity."""
    return FraudAlertService(db).resolve_open_alert_for_customer(
        auth_provider_uid=customer_id,
        resolution="CUSTOMER_RECOGNIZED",
    )


class BillPaymentRequest(BaseModel):
    source_account_id: str = Field(..., description="Deposit account UUID to debit")
    credit_account_id: str = Field(..., description="Credit account UUID to credit")
    amount_cents: int = Field(..., gt=0, description="Amount in cents")


class AutoPaydownRequest(BaseModel):
    customer_id: str = Field(..., description="Target customer UUID")
    credit_account_id: str = Field(..., description="Target credit account UUID")
    target_utilization: float = Field(0.35, gt=0, lt=1, description="Desired post-payment utilization ratio")
    trigger_utilization: float = Field(0.65, gt=0, lt=1, description="Utilization ratio that triggers auto-paydown")

@router.post("/pay", status_code=status.HTTP_200_OK)
@apiv1_router.post("/pay", status_code=status.HTTP_200_OK)
@v1_router.post("/pay", status_code=status.HTTP_200_OK)
def pay_credit_card(
    request: BillPaymentRequest,
    db: Session = Depends(get_db),
    token: ValidatedToken = Depends(get_current_user)
):
    """
    Executes an inter-account bill payment from checking/savings deposit account to pay down credit card balance.
    """
    from services.accounts import AccountsService
    service = AccountsService(db)
    return service.execute_bill_payment(
        token=token,
        source_account_id=request.source_account_id,
        credit_account_id=request.credit_account_id,
        amount_cents=request.amount_cents
    )


@router.post("/internal/auto-paydown", status_code=status.HTTP_200_OK)
@apiv1_router.post("/internal/auto-paydown", status_code=status.HTTP_200_OK)
@v1_router.post("/internal/auto-paydown", status_code=status.HTTP_200_OK)
def auto_paydown_credit_card(
    request: AutoPaydownRequest,
    db: Session = Depends(get_db),
    internal_context: InternalServiceContext = Depends(require_internal_simulation_context),
):
    """
    Executes an internal auto-paydown from the target customer's checking or savings account
    to reduce credit-card utilization for continuous simulation traffic.
    """
    ensure_system_writable("automatic credit-card paydown")
    service = SimulationService(db)
    return service.execute_internal_auto_paydown(
        context=internal_context,
        customer_id=request.customer_id,
        credit_account_id=request.credit_account_id,
        target_utilization=request.target_utilization,
        trigger_utilization=request.trigger_utilization,
    )
