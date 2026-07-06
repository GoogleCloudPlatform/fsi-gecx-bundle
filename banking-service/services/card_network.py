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

import datetime
import logging
import random
from typing import Dict, Any
from sqlalchemy.orm import Session

from models.credit_card import CreditAccount, IssuedCard, TransactionAuthorization, PostedTransaction
from repositories.credit_card import CreditCardRepository
from services.fraud_scoring import FraudScoringService
import json

logger = logging.getLogger(__name__)

def _publish_redis_event(event_type: str, item_dict: dict):
    """Helper to publish real-time events to the Redis bus for the UI stream."""
    try:
        from utils.redis_client import get_redis_client
        r = get_redis_client()
        if r:
            payload = json.dumps(item_dict)
            r.lpush("recent_transactions", payload)
            r.ltrim("recent_transactions", 0, 99)
            r.publish("channel:transactions:live", payload)
    except Exception as e:
        logger.warning(f"Failed to publish transaction to Redis event bus: {e}")

def recalculate_available_credit(db: Session, account: CreditAccount) -> None:
    """Updates the available credit cents for a credit account using the system of record."""
    repo = CreditCardRepository(db)
    pending_sum = repo.get_pending_auth_total(str(account.id))
    account.available_credit_cents = account.credit_limit_cents - account.cleared_balance_cents - pending_sum

def process_authorization(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processes real-time swipe authorization holds.
    ISO-8583 Action Codes:
    '00' - Approved
    '51' - Insufficient Funds
    '83' - Account Frozen / Blocked
    '75' - Card Status Inactive / Blocked
    """
    # Bypass RBAC
    if hasattr(db.bind, "engine"):
        db.bind.engine._ignore_rbac = True
    else:
        db.bind._ignore_rbac = True

    card_token = payload.get("card_token")
    amount_cents = payload.get("amount_cents", 0)
    rrn = payload.get("retrieval_reference_number")
    mcc = payload.get("merchant_category_code", "0000")
    merchant_name = payload.get("merchant_name", "Unknown Merchant")
    card_network = payload.get("card_network", "VISA")

    try:
        repo = CreditCardRepository(db)
        # 1. Enforce Idempotency check via RRN
        existing_auth = repo.get_authorization_by_rrn(rrn)
        if existing_auth:
            logger.info(f"Duplicate auth hold request detected. RRN: {rrn}. Returning status: {existing_auth.status}")
            action_code = "00" if existing_auth.status == "PENDING" else "51"
            return {
                "action_code": action_code,
                "auth_code": existing_auth.auth_code,
                "status": existing_auth.status,
                "decline_reason": existing_auth.decline_reason
            }

        # 2. Lookup Card
        card = repo.get_card_by_token(card_token)
        if not card:
            logger.warning(f"Swipe declined: card token not found. Token: {card_token}")
            return {
                "action_code": "75",
                "auth_code": "000000",
                "status": "DECLINED",
                "decline_reason": "CARD_NOT_FOUND"
            }

        if card.status != "ACTIVE" or not card.is_active:
            logger.warning(f"Swipe declined: card status is {card.status}. Token: {card_token}")
            return {
                "action_code": "75",
                "auth_code": "000000",
                "status": "DECLINED",
                "decline_reason": "CARD_BLOCKED"
            }

        # 3. Lookup Credit Account with pessimistic row locking to prevent limit overruns
        account = repo.get_account_by_id(str(card.account_id), lock=True)
        if not account:
            logger.warning(f"Swipe declined: credit account not found for card {card.id}")
            return {
                "action_code": "83",
                "auth_code": "000000",
                "status": "DECLINED",
                "decline_reason": "ACCOUNT_NOT_FOUND"
            }

        if account.status != "ACTIVE":
            logger.warning(f"Swipe declined: credit account status is {account.status}")
            return {
                "action_code": "83",
                "auth_code": "000000",
                "status": "DECLINED",
                "decline_reason": "ACCOUNT_FROZEN"
            }

        # 4. Check Credit Limit
        if amount_cents > account.available_credit_cents:
            logger.warning(f"Swipe declined: Insufficient funds. Available: {account.available_credit_cents}, Requested: {amount_cents}")
            
            # Record declined hold in history
            declined_auth = TransactionAuthorization(
                card_id=card.id,
                account_id=account.id,
                transaction_amount_cents=amount_cents,
                billing_amount_cents=amount_cents,
                status="DECLINED",
                decline_reason="INSUFFICIENT_FUNDS",
                auth_code="000000",
                retrieval_reference_number=rrn,
                card_network=card_network,
                merchant_category_code=mcc,
                merchant_name=merchant_name,
                expires_at=datetime.datetime.now(datetime.timezone.utc)
            )
            db.add(declined_auth)
            db.commit()
            
            return {
                "action_code": "51",
                "auth_code": "000000",
                "status": "DECLINED",
                "decline_reason": "INSUFFICIENT_FUNDS"
            }

        # 5. Evaluate Fraud Risk
        fraud_service = FraudScoringService()
        risk_score = fraud_service.evaluate_transaction_risk(payload)
        auth_status = "FLAGGED" if risk_score > 20 else "PENDING"

        # 6. Approve Hold
        auth_code = f"{random.randint(100000, 999999)}"
        now = payload.get("created_at") or datetime.datetime.now(datetime.timezone.utc)
        
        auth_hold = TransactionAuthorization(
            card_id=card.id,
            account_id=account.id,
            transaction_amount_cents=amount_cents,
            billing_amount_cents=amount_cents,
            status=auth_status,
            fraud_risk_score=risk_score,
            decline_reason="NONE",
            auth_code=auth_code,
            retrieval_reference_number=rrn,
            card_network=card_network,
            merchant_category_code=mcc,
            merchant_name=merchant_name,
            created_at=now,
            expires_at=now + datetime.timedelta(days=7)
        )
        db.add(auth_hold)
        db.flush()
        
        # Recalculate credit balances
        recalculate_available_credit(db, account)
        db.commit()

        logger.info(f"Swipe hold approved. Auth Code: {auth_code}. RRN: {rrn}. Account: {account.id}")

        # Broadcast event to UI stream
        _publish_redis_event("AUTH", {
            "id": f"AUTH_{str(auth_hold.id)[:8]}",
            "rrn": rrn or "N/A",
            "timestamp": now.strftime("%H:%M:%S"),
            "merchant_name": merchant_name,
            "amount_cents": amount_cents,
            "status": f"FLAGGED (RISK {risk_score})" if auth_status == "FLAGGED" else f"HOLD ({auth_status})",
            "bq_view": "fsi_lakehouse.v_international_fraud_anomalies" if risk_score > 20 else "fsi_lakehouse.v_realtime_spend_velocity",
            "raw_time": now.timestamp()
        })

        return {
            "action_code": "00",
            "auth_code": auth_code,
            "status": auth_status,
            "fraud_risk_score": risk_score,
            "decline_reason": "NONE"
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error processing card network authorization hold: {e}")
        raise e

def process_settlement(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clears / captures a pending card swipe hold and posts a final PostedTransaction.
    """
    # Bypass RBAC
    if hasattr(db.bind, "engine"):
        db.bind.engine._ignore_rbac = True
    else:
        db.bind._ignore_rbac = True

    try:
        repo = CreditCardRepository(db)
        rrn = payload.get("retrieval_reference_number")
        settle_amount = payload.get("amount_cents")
        description = payload.get("description")

        # Find active pending authorization hold
        auth = repo.get_authorization_by_rrn(rrn, status="PENDING")

        if not auth:
            raise ValueError(f"No pending authorization hold found with RRN: {rrn}")

        # Mark authorization as SETTLED
        auth.status = "SETTLED"

        # Lookup account with pessimistic row locking to prevent balance conflicts
        account = repo.get_account_by_id(str(auth.account_id), lock=True)
        if not account:
            raise ValueError("Credit account not found")

        # Add transaction charge to cleared debt (immutable statement record)
        posted_at_val = payload.get("posted_at") or datetime.datetime.now(datetime.timezone.utc)
        posted_tx = PostedTransaction(
            account_id=account.id,
            authorization_id=auth.id,
            auth_code=auth.auth_code,
            retrieval_reference_number=rrn,
            amount_cents=-settle_amount, # posted card charges are negative
            description=description or auth.merchant_name or "Card Purchase",
            posted_at=posted_at_val
        )
        db.add(posted_tx)
        
        # Update account cleared balance debt
        account.cleared_balance_cents += settle_amount
        
        # Flush updates to DB so sum query in recalculate_available_credit captures the status change
        db.flush()
        
        # Recalculate available credit
        recalculate_available_credit(db, account)
        db.commit()

        logger.info(f"Swipe hold settled successfully. RRN: {rrn}. Cleared Balance: {account.cleared_balance_cents}")

        # Broadcast event to UI stream
        _publish_redis_event("POST", {
            "id": f"POST_{str(posted_tx.id)[:8]}",
            "rrn": rrn or "N/A",
            "timestamp": posted_at_val.strftime("%H:%M:%S"),
            "merchant_name": posted_tx.description,
            "amount_cents": posted_tx.amount_cents,
            "status": "SETTLE (POSTED)",
            "bq_view": "fsi_lakehouse.v_realtime_spend_velocity",
            "raw_time": posted_at_val.timestamp()
        })

        return {
            "status": "SETTLED",
            "posted_transaction_id": str(posted_tx.id),
            "cleared_balance_cents": account.cleared_balance_cents,
            "available_credit_cents": account.available_credit_cents
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error during card network settlement transaction: {e}")
        raise e

def process_reversal(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Voids/reverses an active pending hold and releases available credit.
    """
    # Bypass RBAC
    if hasattr(db.bind, "engine"):
        db.bind.engine._ignore_rbac = True
    else:
        db.bind._ignore_rbac = True

    try:
        repo = CreditCardRepository(db)
        rrn = payload.get("retrieval_reference_number")

        auth = repo.get_authorization_by_rrn(rrn, status="PENDING")

        if not auth:
            raise ValueError(f"No pending authorization hold found with RRN: {rrn} to reverse.")

        # Void hold
        auth.status = "REVERSED"

        # Lookup account with pessimistic row locking
        account = repo.get_account_by_id(str(auth.account_id), lock=True)
        if not account:
            raise ValueError("Credit account not found")

        # Flush updates to DB so sum query in recalculate_available_credit captures the status change
        db.flush()

        # Recalculate available credit (hold release)
        recalculate_available_credit(db, account)
        db.commit()

        logger.info(f"Swipe hold reversed successfully. RRN: {rrn}. Available Credit: {account.available_credit_cents}")
        return {
            "status": "REVERSED",
            "available_credit_cents": account.available_credit_cents
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error during card network reversal transaction: {e}")
        raise e
