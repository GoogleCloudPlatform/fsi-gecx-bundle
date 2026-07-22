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
import uuid
from typing import Dict, Any
from sqlalchemy.orm import Session

from models.credit_card import CreditAccount, TransactionAuthorization, PostedTransaction
from models.identity import User
from repositories.credit_card import CreditCardRepository
from repositories.fraud import FraudDecisionRepository
from services.fraud_alerts import FraudAlertService
from services.fraud_scoring import FraudScoringService
from services.merchant_service import MerchantEnrichmentService
import json
from utils.audit import record_audit_event
from utils.database import enable_session_rbac_override
from services.financial_journal import (
    JournalEntrySpec,
    ensure_credit_journal_account,
    ensure_system_journal_account,
    post_financial_transaction,
)

logger = logging.getLogger(__name__)


ONLINE_DESCRIPTOR_TOKENS = ("ONLINE", ".COM", "MKTPLACE", "STREAMING", "SUBSCRIPTION", "DIGITAL", "GIFT CARD")
CARD_PRESENT_ENTRY_MODES = {"CHIP", "CONTACTLESS", "MAG_STRIPE"}
CARD_NOT_PRESENT_CHANNELS = {"CARD_NOT_PRESENT", "ECOMMERCE"}


def _uuid_or_none(value: Any) -> str | None:
    if not value:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError):
        return None


def _normalize_transaction_channel(payload: Dict[str, Any], merchant_name: str) -> tuple[str, str]:
    channel = str(payload.get("transaction_channel") or "").upper()
    entry_mode = str(payload.get("entry_mode") or "").upper()
    descriptor = merchant_name.upper()

    if not channel:
        if entry_mode in CARD_PRESENT_ENTRY_MODES:
            channel = "CARD_PRESENT"
        elif any(token in descriptor for token in ONLINE_DESCRIPTOR_TOKENS):
            channel = "ECOMMERCE"
        else:
            channel = "CARD_PRESENT"

    if not entry_mode:
        if channel == "WALLET":
            entry_mode = "CONTACTLESS"
        elif channel in CARD_NOT_PRESENT_CHANNELS or channel == "ECOMMERCE":
            entry_mode = "ECOMMERCE"
        else:
            entry_mode = "CHIP"

    return channel, entry_mode


def _build_authorization_context(db: Session, payload: Dict[str, Any], merchant_name: str, mcc: str) -> Dict[str, Any]:
    merchant_country = str(payload.get("merchant_country_code") or payload.get("country_code") or "").upper() or None
    context = {
        "merchant_id": _uuid_or_none(payload.get("merchant_id")),
        "merchant_slug": payload.get("merchant_slug"),
        "merchant_store_id": _uuid_or_none(payload.get("merchant_store_id")),
        "transaction_channel": payload.get("transaction_channel"),
        "entry_mode": payload.get("entry_mode"),
        "merchant_country_code": merchant_country,
        "merchant_city": payload.get("merchant_city"),
        "merchant_region": payload.get("merchant_region"),
        "merchant_postal_code": payload.get("merchant_postal_code"),
        "merchant_latitude": payload.get("merchant_latitude"),
        "merchant_longitude": payload.get("merchant_longitude"),
        "ip_country_code": payload.get("ip_country_code"),
        "shipping_country_code": payload.get("shipping_country_code"),
        "is_digital_goods": bool(payload.get("is_digital_goods", False)),
        "merchant_high_risk_flags": payload.get("merchant_high_risk_flags") or [],
        "merchant_intelligence": payload.get("merchant_intelligence"),
        "synthetic_fraud_label": payload.get("synthetic_fraud_label"),
        "fraud_pattern_label": payload.get("fraud_pattern_label"),
        "fraud_pattern_sequence": payload.get("fraud_pattern_sequence"),
    }

    if not merchant_country or not context["merchant_id"] or not context["merchant_store_id"]:
        try:
            enriched = MerchantEnrichmentService.enrich_transaction(db, raw_descriptor=merchant_name, mcc=mcc)
            context.update(
                {
                    "merchant_id": context["merchant_id"] or _uuid_or_none(enriched.get("merchant_id")),
                    "merchant_slug": context["merchant_slug"] or enriched.get("merchant_slug"),
                    "merchant_store_id": context["merchant_store_id"] or _uuid_or_none(enriched.get("merchant_store_id")),
                    "merchant_country_code": context["merchant_country_code"] or enriched.get("country_code"),
                    "merchant_city": context["merchant_city"] or enriched.get("city"),
                    "merchant_region": context["merchant_region"] or enriched.get("region"),
                    "merchant_postal_code": context["merchant_postal_code"] or enriched.get("postal_code"),
                    "merchant_latitude": context["merchant_latitude"] or enriched.get("latitude"),
                    "merchant_longitude": context["merchant_longitude"] or enriched.get("longitude"),
                    "is_digital_goods": context["is_digital_goods"] or ("DIGITAL_GOODS" in enriched.get("high_risk_flags", [])),
                    "merchant_high_risk_flags": context["merchant_high_risk_flags"] or enriched.get("high_risk_flags", []),
                    "merchant_intelligence": context["merchant_intelligence"] or enriched.get("merchant_intelligence"),
                }
            )
        except Exception as exc:
            logger.warning("Merchant enrichment failed during authorization for descriptor=%s: %s", merchant_name, exc)

    channel, entry_mode = _normalize_transaction_channel({**payload, **context}, merchant_name)
    context["transaction_channel"] = channel
    context["entry_mode"] = entry_mode
    return context


def _resolve_posted_transaction_description(db: Session, auth: TransactionAuthorization) -> str:
    raw_descriptor = (auth.merchant_name or "").strip()
    if raw_descriptor:
        try:
            enriched = MerchantEnrichmentService.enrich_transaction(
                db,
                raw_descriptor=raw_descriptor,
                mcc=auth.merchant_category_code,
            )
            clean_name = (enriched.get("clean_name") or "").strip()
            if clean_name:
                return clean_name
        except Exception as exc:
            logger.warning("Merchant enrichment failed during settlement for RRN=%s: %s", auth.retrieval_reference_number, exc)
        return raw_descriptor
    return "Card Purchase"

def _publish_redis_event(event_type: str, item_dict: dict):
    """Helper to publish real-time events to the Redis bus for the UI stream."""
    try:
        from utils.redis_client import execute_redis_command

        def publish(r):
            payload = json.dumps(item_dict)
            r.lpush("recent_transactions", payload)
            r.ltrim("recent_transactions", 0, 99)
            r.publish("channel:transactions:live", payload)

        execute_redis_command(publish)
    except Exception as e:
        logger.warning(f"Failed to publish transaction to Redis event bus: {e}")

def recalculate_available_credit(db: Session, account: CreditAccount) -> None:
    """Updates the available credit cents for a credit account using the system of record."""
    repo = CreditCardRepository(db)
    repo.recalculate_available_credit(account)

def process_authorization(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processes real-time swipe authorization holds.
    ISO-8583 Action Codes:
    '00' - Approved
    '51' - Insufficient Funds
    '83' - Account Frozen / Blocked
    '75' - Card Status Inactive / Blocked
    """
    enable_session_rbac_override(db)

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
                "authorization_id": str(existing_auth.id),
                "retrieval_reference_number": existing_auth.retrieval_reference_number,
                "status": existing_auth.status,
                "decline_reason": existing_auth.decline_reason
            }

        # 2. Lookup Card
        card = repo.get_card_by_token(card_token)
        if not card:
            logger.warning(f"Swipe declined: card token not found. Token: {card_token}")
            record_audit_event(db, "CREDIT_AUTHORIZATION_DECLINED", {
                "retrieval_reference_number": rrn,
                "amount_cents": amount_cents,
                "reason": "CARD_NOT_FOUND",
            })
            db.commit()
            return {
                "action_code": "75",
                "auth_code": "000000",
                "status": "DECLINED",
                "decline_reason": "CARD_NOT_FOUND"
            }

        if card.status != "ACTIVE" or not card.is_active:
            logger.warning(f"Swipe declined: card status is {card.status}. Token: {card_token}")
            record_audit_event(db, "CREDIT_AUTHORIZATION_DECLINED", {
                "card_id": str(card.id),
                "account_id": str(card.account_id),
                "retrieval_reference_number": rrn,
                "amount_cents": amount_cents,
                "reason": "CARD_BLOCKED",
            })
            db.commit()
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
            record_audit_event(db, "CREDIT_AUTHORIZATION_DECLINED", {
                "card_id": str(card.id),
                "retrieval_reference_number": rrn,
                "amount_cents": amount_cents,
                "reason": "ACCOUNT_NOT_FOUND",
            })
            db.commit()
            return {
                "action_code": "83",
                "auth_code": "000000",
                "status": "DECLINED",
                "decline_reason": "ACCOUNT_NOT_FOUND"
            }

        if account.status != "ACTIVE":
            logger.warning(f"Swipe declined: credit account status is {account.status}")
            record_audit_event(db, "CREDIT_AUTHORIZATION_DECLINED", {
                "card_id": str(card.id),
                "account_id": str(account.id),
                "retrieval_reference_number": rrn,
                "amount_cents": amount_cents,
                "reason": "ACCOUNT_FROZEN",
            })
            db.commit()
            return {
                "action_code": "83",
                "auth_code": "000000",
                "status": "DECLINED",
                "decline_reason": "ACCOUNT_FROZEN"
            }

        auth_context = _build_authorization_context(db, payload, merchant_name, mcc)

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
                merchant_id=auth_context["merchant_id"],
                merchant_slug=auth_context["merchant_slug"],
                merchant_store_id=auth_context["merchant_store_id"],
                transaction_channel=auth_context["transaction_channel"],
                entry_mode=auth_context["entry_mode"],
                merchant_country_code=auth_context["merchant_country_code"],
                merchant_city=auth_context["merchant_city"],
                merchant_region=auth_context["merchant_region"],
                merchant_postal_code=auth_context["merchant_postal_code"],
                merchant_latitude=auth_context["merchant_latitude"],
                merchant_longitude=auth_context["merchant_longitude"],
                ip_country_code=auth_context["ip_country_code"],
                shipping_country_code=auth_context["shipping_country_code"],
                is_digital_goods=auth_context["is_digital_goods"],
                expires_at=datetime.datetime.now(datetime.timezone.utc)
            )
            db.add(declined_auth)
            db.flush()
            record_audit_event(db, "CREDIT_AUTHORIZATION_DECLINED", {
                "authorization_id": str(declined_auth.id),
                "card_id": str(card.id),
                "account_id": str(account.id),
                "retrieval_reference_number": rrn,
                "amount_cents": amount_cents,
                "currency": account.currency or "USD",
                "reason": "INSUFFICIENT_FUNDS",
            })
            db.commit()
            
            return {
                "action_code": "51",
                "auth_code": "000000",
                "status": "DECLINED",
                "decline_reason": "INSUFFICIENT_FUNDS"
            }

        now = payload.get("created_at") or datetime.datetime.now(datetime.timezone.utc)

        # 5. Evaluate Fraud Risk
        recent_authorizations = repo.list_recent_authorizations(
            str(account.id),
            since=now - datetime.timedelta(hours=24),
            limit=100,
        )
        fraud_service = FraudScoringService()
        fraud_decision = fraud_service.evaluate_authorization(
            {**payload, "created_at": now},
            context=auth_context,
            recent_authorizations=recent_authorizations,
            account=account,
        )
        risk_score = fraud_decision.score
        auth_status = "FLAGGED" if fraud_decision.is_flagged else "PENDING"

        # 6. Approve Hold
        auth_code = f"{random.randint(100000, 999999)}"
        
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
            merchant_id=auth_context["merchant_id"],
            merchant_slug=auth_context["merchant_slug"],
            merchant_store_id=auth_context["merchant_store_id"],
            transaction_channel=auth_context["transaction_channel"],
            entry_mode=auth_context["entry_mode"],
            merchant_country_code=auth_context["merchant_country_code"],
            merchant_city=auth_context["merchant_city"],
            merchant_region=auth_context["merchant_region"],
            merchant_postal_code=auth_context["merchant_postal_code"],
            merchant_latitude=auth_context["merchant_latitude"],
            merchant_longitude=auth_context["merchant_longitude"],
            ip_country_code=auth_context["ip_country_code"],
            shipping_country_code=auth_context["shipping_country_code"],
            is_digital_goods=auth_context["is_digital_goods"],
            created_at=now,
            expires_at=now + datetime.timedelta(days=7)
        )
        db.add(auth_hold)
        db.flush()

        decision_record = FraudDecisionRepository(db).record_model_decision(
            authorization_id=auth_hold.id,
            customer_id=account.customer_id,
            credit_account_id=account.id,
            card_id=card.id,
            score=fraud_decision.score,
            threshold=fraud_decision.threshold,
            decision=fraud_decision.decision,
            reason_codes=fraud_decision.reason_codes,
            feature_snapshot=fraud_decision.features,
            model_version=fraud_decision.model_version,
        )
        record_audit_event(
            db,
            "FRAUD_MODEL_DECISION_RECORDED",
            {
                "decision_id": str(decision_record.id),
                "authorization_id": str(auth_hold.id),
                "customer_id": str(account.customer_id),
                "credit_account_id": str(account.id),
                "card_id": str(card.id),
                "score": fraud_decision.score,
                "threshold": fraud_decision.threshold,
                "decision": fraud_decision.decision,
                "reason_codes": fraud_decision.reason_codes,
                "model_version": fraud_decision.model_version,
            },
        )
        fraud_alert_result = None
        if (
            fraud_service.alerts_enabled
            and fraud_decision.is_flagged
            and fraud_decision.score >= fraud_service.alert_threshold
        ):
            customer = db.query(User).filter(User.id == account.customer_id).first()
            if customer:
                fraud_alert_result = FraudAlertService(db).create_or_update_alert_from_model_decision(
                    customer=customer,
                    card=card,
                    credit_account=account,
                    authorization=auth_hold,
                    decision_record=decision_record,
                )
            else:
                logger.warning("Skipping model fraud alert because customer %s was not found.", account.customer_id)
        
        # Recalculate credit balances
        recalculate_available_credit(db, account)
        record_audit_event(
            db,
            "CREDIT_AUTHORIZATION_FLAGGED" if auth_status == "FLAGGED" else "CREDIT_AUTHORIZATION_AUTHORIZED",
            {
                "authorization_id": str(auth_hold.id),
                "card_id": str(card.id),
                "account_id": str(account.id),
                "retrieval_reference_number": rrn,
                "amount_cents": amount_cents,
                "currency": account.currency or "USD",
                "status": auth_status,
            },
        )
        db.commit()

        logger.info(f"Swipe hold approved. Auth Code: {auth_code}. RRN: {rrn}. Account: {account.id}")

        # Broadcast event to UI stream
        _publish_redis_event("AUTH", {
            "id": f"AUTH_{str(auth_hold.id)[:8]}",
            "rrn": rrn or "N/A",
            "timestamp": now.strftime("%H:%M:%S"),
            "merchant_name": merchant_name,
            "transaction_channel": auth_context["transaction_channel"],
            "merchant_country_code": auth_context["merchant_country_code"],
            "amount_cents": amount_cents,
            "status": f"FLAGGED (RISK {risk_score})" if auth_status == "FLAGGED" else f"HOLD ({auth_status})",
            "fraud_risk_score": risk_score,
            "fraud_reason_codes": fraud_decision.reason_codes,
            "fraud_model_version": fraud_decision.model_version,
            "fraud_features": fraud_decision.features,
            "bq_view": "analytics_curated.international_fraud_anomalies" if fraud_decision.is_flagged else "analytics_curated.realtime_spend_velocity",
            "raw_time": now.timestamp(),
        })

        return {
            "action_code": "00",
            "auth_code": auth_code,
            "authorization_id": str(auth_hold.id),
            "retrieval_reference_number": auth_hold.retrieval_reference_number,
            "fraud_alert_id": fraud_alert_result.get("fraud_alert_id") if fraud_alert_result else None,
            "status": auth_status,
            "fraud_risk_score": risk_score,
            "fraud_decision": fraud_decision.to_dict(),
            "fraud_reason_codes": fraud_decision.reason_codes,
            "fraud_model_version": fraud_decision.model_version,
            "transaction_channel": auth_context["transaction_channel"],
            "merchant_country_code": auth_context["merchant_country_code"],
            "decline_reason": "NONE",
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error processing card network authorization hold: {e}")
        raise e

def process_settlement(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clears / captures a pending card swipe hold and posts a final PostedTransaction.
    """
    enable_session_rbac_override(db)

    try:
        repo = CreditCardRepository(db)
        rrn = payload.get("retrieval_reference_number")
        settle_amount = int(payload.get("amount_cents") or 0)
        if settle_amount <= 0:
            raise ValueError("Settlement amount must be positive.")
        # Find an active authorization hold. Fraud-scored holds may be FLAGGED
        # while still awaiting customer confirmation or network clearing.
        auth = repo.get_authorization_by_rrn(rrn, statuses=["PENDING", "FLAGGED"])

        if not auth:
            raise ValueError(f"No active authorization hold found with RRN: {rrn}")

        # Mark authorization as SETTLED
        auth.status = "SETTLED"

        # Lookup account with pessimistic row locking to prevent balance conflicts
        account = repo.get_account_by_id(str(auth.account_id), lock=True)
        if not account:
            raise ValueError("Credit account not found")

        # Append the receivable debit and merchant-clearing credit to the
        # canonical journal before writing the linked statement projection.
        posted_at_val = payload.get("posted_at") or datetime.datetime.now(datetime.timezone.utc)
        posted_description = _resolve_posted_transaction_description(db, auth)
        journal_account = ensure_credit_journal_account(db, account)
        clearing_account = ensure_system_journal_account(
            db,
            "SYSTEM_CARD_MERCHANT_CLEARING",
            "Card network merchant settlement clearing",
        )
        posting = post_financial_transaction(
            db,
            idempotency_key=f"card-settlement:{rrn}",
            user_id=account.customer_id,
            description=posted_description,
            source_type="CARD_SETTLEMENT",
            source_references={
                "authorization_id": str(auth.id),
                "retrieval_reference_number": rrn,
                "credit_account_id": str(account.id),
            },
            currency=auth.billing_currency or account.currency or "USD",
            posted_at=posted_at_val,
            entries=(
                JournalEntrySpec(journal_account.id, "DEBIT", settle_amount),
                JournalEntrySpec(clearing_account.id, "CREDIT", settle_amount),
            ),
        )
        posted_tx = PostedTransaction(
            account_id=account.id,
            authorization_id=auth.id,
            journal_transaction_id=posting.transaction.id,
            auth_code=auth.auth_code,
            retrieval_reference_number=rrn,
            amount_cents=-settle_amount, # posted card charges are negative
            description=posted_description,
            posted_at=posted_at_val
        )
        db.add(posted_tx)
        
        # Update account cleared balance debt
        account.cleared_balance_cents += settle_amount
        journal_account.cleared_balance_cents = account.cleared_balance_cents
        
        # Flush updates to DB so sum query in recalculate_available_credit captures the status change
        db.flush()
        
        # Recalculate available credit
        recalculate_available_credit(db, account)
        journal_account.available_credit_cents = account.available_credit_cents
        record_audit_event(db, "CREDIT_TRANSACTION_SETTLED", {
            "authorization_id": str(auth.id),
            "posted_transaction_id": str(posted_tx.id),
            "transaction_id": str(posting.transaction.id),
            "financial_event_id": posting.event_id,
            "account_id": str(account.id),
            "retrieval_reference_number": rrn,
            "amount_cents": settle_amount,
            "currency": auth.billing_currency or account.currency or "USD",
        })
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
            "bq_view": "analytics_curated.realtime_spend_velocity",
            "raw_time": posted_at_val.timestamp()
        })

        return {
            "status": "SETTLED",
            "posted_transaction_id": str(posted_tx.id),
            "transaction_id": str(posting.transaction.id),
            "financial_event_id": posting.event_id,
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
    enable_session_rbac_override(db)

    try:
        repo = CreditCardRepository(db)
        rrn = payload.get("retrieval_reference_number")

        auth = repo.get_authorization_by_rrn(rrn, statuses=["PENDING", "FLAGGED"])

        if not auth:
            raise ValueError(f"No active authorization hold found with RRN: {rrn} to reverse.")

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
        record_audit_event(db, "CREDIT_AUTHORIZATION_REVERSED", {
            "authorization_id": str(auth.id),
            "account_id": str(account.id),
            "retrieval_reference_number": rrn,
            "amount_cents": int(auth.billing_amount_cents or auth.transaction_amount_cents or 0),
            "currency": auth.billing_currency or account.currency or "USD",
            "reason": payload.get("reason") or "NETWORK_REVERSAL",
        })
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
