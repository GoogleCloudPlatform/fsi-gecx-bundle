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
import uuid
import datetime
import random
import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from models.authentication import ValidatedToken
from utils.auth import get_current_user
from utils.database import get_db
from services.seeding_service import provision_user_suite, reset_user_suite
from models.identity import User
from models.credit_card import IssuedCard, CreditAccount, TransactionAuthorization
from utils.audit import record_audit_event

logger = logging.getLogger(__name__)

def verify_presenter_domain(token: ValidatedToken = Depends(get_current_user)) -> ValidatedToken:
    """Security dependency restricting simulation suite operations to authorized presenter domains."""
    email = token.email
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authenticated email not found in token claims."
        )
    email_lower = email.lower()
    allowed_domains = ["google.com", "gcp.solutions", "altostrat.com"]
    if not any(email_lower.endswith(f"@{domain}") for domain in allowed_domains):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Simulation actions are restricted to authorized presenter domains."
        )
    return token

router = APIRouter(prefix="/api/v1/simulation", tags=["simulation"], dependencies=[Depends(verify_presenter_domain)])
v1_router = APIRouter(prefix="/v1/simulation", tags=["simulation"], dependencies=[Depends(verify_presenter_domain)])
alias_router = APIRouter(prefix="/simulation", tags=["simulation"], dependencies=[Depends(verify_presenter_domain)])

@router.post("/provision-my-demo", status_code=status.HTTP_201_CREATED)
@v1_router.post("/provision-my-demo", status_code=status.HTTP_201_CREATED)
@alias_router.post("/provision-my-demo", status_code=status.HTTP_201_CREATED)
def provision_my_demo(
    token: ValidatedToken = Depends(verify_presenter_domain),
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
@v1_router.post("/reset-my-demo", status_code=status.HTTP_200_OK)
@alias_router.post("/reset-my-demo", status_code=status.HTTP_200_OK)
def reset_my_demo(
    token: ValidatedToken = Depends(verify_presenter_domain),
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
@v1_router.post("/surge", status_code=status.HTTP_200_OK)
@alias_router.post("/surge", status_code=status.HTTP_200_OK)
async def simulate_activity_surge(
    token: ValidatedToken = Depends(verify_presenter_domain),
    db: Session = Depends(get_db)
):
    """
    Commands the simulation client to immediately fire 50 rapid-fire card swipes over 10 seconds,
    passing the active presenter's card token to ensure visual feedback.
    """
    email = token.email
    uid = token.user_id
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authenticated user ID not found in token claims."
        )

    # 1. Fetch user from DB (bypass RBAC)
    db.connection().info["_ignore_rbac"] = True
    user = db.query(User).filter((User.auth_provider_uid == uid) | (User.email == email)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No seeded demo profile found. Please provision a profile first."
        )

    # 2. Fetch the user's active card details
    from models.credit_card import CreditAccount, IssuedCard
    card_info = db.query(IssuedCard, CreditAccount).join(
        CreditAccount, IssuedCard.account_id == CreditAccount.id
    ).filter(CreditAccount.customer_id == user.id, IssuedCard.status == "ACTIVE").first()

    card_payloads = []
    if card_info:
        card, cred_acc = card_info
        card_payloads.append({
            "card_token": card.card_token,
            "cardholder_name": card.cardholder_name,
            "persona": "PRIME",
            "mccs": ["5411", "5541", "5310", "4121"],
            "amount_min": 1500,
            "amount_max": 15000
        })
    else:
        logger.warning(f"No active credit card found for user={user.id}. Data-generator will use default persona list.")

    target_url = f"{DATA_GENERATOR_URL}/simulate-surge"
    logger.info(f"Forwarding surge request to data-generator at: {target_url} with {len(card_payloads)} presenter cards.")
    
    switch_token = os.getenv("CARD_NETWORK_SWITCH_TOKEN", "switch-secret-key-12345")
    headers = {"X-Card-Network-Token": switch_token}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                target_url,
                json={"active_cards": card_payloads if card_payloads else None},
                headers=headers,
                timeout=15.0
            )
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

@router.post("/inject-anomaly", status_code=status.HTTP_200_OK)
@v1_router.post("/inject-anomaly", status_code=status.HTTP_200_OK)
@alias_router.post("/inject-anomaly", status_code=status.HTTP_200_OK)
def inject_targeted_fraud(
    token: ValidatedToken = Depends(verify_presenter_domain),
    db: Session = Depends(get_db)
):
    """
    Injects a high-velocity card-not-present (CNP) and international retail fraud surge against the CE presenter's card.
    simulating someone who skimmed or found their physical card after Coco Bongo.
    """
    email = token.email
    uid = token.user_id
    if not uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User ID missing in claims.")

    db.connection().info["_ignore_rbac"] = True
    user = db.query(User).filter((User.auth_provider_uid == uid) | (User.email == email)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo profile not found.")

    card_info = db.query(IssuedCard, CreditAccount).join(
        CreditAccount, IssuedCard.account_id == CreditAccount.id
    ).filter(CreditAccount.customer_id == user.id, IssuedCard.status == "ACTIVE").first()

    if not card_info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active credit card found for user.")

    card, cred_acc = card_info
    now = datetime.datetime.now(datetime.timezone.utc)

    swipes = [
        ("GAME*TEST TOKEN ONLINE", 499, "5814", "USA", 0),
        ("APPLE.COM*ONLINE", 149900, "5310", "USA", 0),
        ("BEST BUY*MKTPLACE", 215000, "5310", "USA", 0),
        ("LUXURY BOUTIQUE CANCUN [MEX]", 320000, "5310", "MEX", 30),
    ]

    injected_auths = []
    for idx, (desc, amt, mcc, country, risk) in enumerate(swipes):
        auth = TransactionAuthorization(
            id=uuid.uuid4(),
            card_id=card.id,
            account_id=cred_acc.id,
            transaction_amount_cents=amt,
            billing_amount_cents=amt,
            status="PENDING",
            auth_code=f"FRD{random.randint(100, 999)}",
            retrieval_reference_number=f"REF{999000+idx:09d}",
            card_network="VISA",
            merchant_category_code=mcc,
            merchant_name=desc,
            created_at=now - datetime.timedelta(minutes=(3 - idx)),
            expires_at=now + datetime.timedelta(days=7)
        )
        db.add(auth)
        injected_auths.append(auth)
        record_audit_event(
            db,
            "CREDIT_TRANSACTION_AUTHORIZED",
            {
                "account_id": str(cred_acc.id),
                "authorization_id": str(auth.id),
                "amount_cents": amt,
                "merchant_name": desc,
                "is_fraud_simulation": True,
                "risk_score": risk
            },
        )

    db.commit()
    logger.info(f"Injected 4 targeted fraud anomaly swipes for user={user.id} ({email}).")
    return {
        "status": "ANOMALY_INJECTED",
        "user_id": str(user.id),
        "card_token": card.card_token,
        "injected_swipes_count": len(injected_auths),
        "total_fraud_cents": sum(amt for _, amt, _, _, _ in swipes),
        "message": "Fraud surge successfully injected into cards.transaction_authorizations."
    }
