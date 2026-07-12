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
import datetime
import json
import secrets
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from models.audit import AuditOutbox
from models.credit_card import AccountLedger, IssuedCard
from utils.audit import record_audit_event
from models.fdx import (
    RealTimeBalanceResponse, PaginatedTransactionsResult, FDXTransaction,
    PaymentMeta, PaymentNetwork, PaginatedPaymentNetworksResult, FDXAccount
)
from services.taxonomy_service import TaxonomyService

logger = logging.getLogger(__name__)


def _generate_card_token() -> str:
    return f"tok_visa_reissue_{secrets.token_hex(8)}"


def _generate_last_four() -> str:
    return f"{secrets.randbelow(10_000):04d}"


def get_wallet_status_by_card_token(db: Session, account_id: str) -> dict[str, dict[str, Any]]:
    """Builds a lightweight card-token wallet status map from the durable audit outbox."""
    rows = (
        db.query(AuditOutbox)
        .filter(AuditOutbox.event_type == "WALLET_PROVISIONING_QUEUED")
        .order_by(AuditOutbox.created_at.asc())
        .all()
    )
    statuses: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            payload = json.loads(row.payload or "{}")
        except json.JSONDecodeError:
            continue
        if str(payload.get("account_id")) != str(account_id):
            continue
        card_token = payload.get("card_token")
        if not card_token:
            continue
        statuses[card_token] = {
            "wallet_provider": payload.get("wallet_provider", "GOOGLE_WALLET"),
            "wallet_provisioning_status": payload.get("status", "QUEUED"),
            "wallet_queued_at": row.created_at.isoformat() if row.created_at else None,
        }
    return statuses


def queue_wallet_provisioning(
    db: Session,
    *,
    account_id: str,
    card_token: str,
    wallet_provider: str = "GOOGLE_WALLET",
    initiated_by: str = "CUSTOMER_VOICE_SUPPORT",
    fraud_alert_id: str | None = None,
) -> dict:
    """
    Records a mocked wallet-provisioning request for an issued card.
    """
    logger.info(
        "Queueing wallet provisioning for account=%s card_token=%s wallet_provider=%s",
        account_id,
        card_token,
        wallet_provider,
    )
    try:
        from repositories.credit_card import CreditCardRepository

        repo = CreditCardRepository(db)
        account = repo.get_account_by_id(account_id, lock=True)
        if not account:
            raise ValueError(f"Account '{account_id}' not found.")

        card = repo.get_card_by_token(card_token)
        if not card or str(card.account_id) != str(account.id):
            raise ValueError("Card not found for the specified account.")

        if not card.is_active or card.status != "ACTIVE":
            raise ValueError("Only active cards can be provisioned to a wallet.")

        record_audit_event(
            db,
            "WALLET_PROVISIONING_QUEUED",
            {
                "account_id": str(account.id),
                "card_token": card.card_token,
                "wallet_provider": wallet_provider,
                "status": "QUEUED",
                "initiated_by": initiated_by,
                "fraud_alert_id": fraud_alert_id,
                "correlation_id": fraud_alert_id or card.card_token,
            },
        )
        db.commit()
        return {
            "account_id": str(account.id),
            "card_token": card.card_token,
            "wallet_provider": wallet_provider,
            "wallet_provisioning_status": "QUEUED",
            "fraud_alert_id": fraud_alert_id,
            "message": "Digital wallet provisioning queued successfully.",
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error queueing wallet provisioning: {e}")
        raise e

def freeze_card(db: Session, card_token: str, reason: str) -> dict:
    """
    Locates the card by token and sets its status to 'BLOCKED' to freeze auth checks.
    """
    logger.info(f"Freezing card token: {card_token} (Reason: {reason})")
    try:
        from repositories.credit_card import CreditCardRepository
        repo = CreditCardRepository(db)
        card = repo.get_card_by_token(card_token)
        if not card:
            logger.error(f"Card token '{card_token}' not found.")
            raise ValueError(f"Card token '{card_token}' not found.")
            
        card.status = "BLOCKED"
        repo.save_card(card)
        record_audit_event(db, "CARD_FROZEN", {"account_id": str(card.account_id), "card_token": card_token, "reason": reason})
        db.commit()
        logger.info(f"Card token '{card_token}' successfully blocked.")
        return {"card_token": card_token, "status": "BLOCKED"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error freezing card: {e}")
        raise e


def unfreeze_card(db: Session, card_token: str, reason: str) -> dict:
    """
    Locates the card by token and sets its status to 'ACTIVE' to reactivate auth checks.
    """
    logger.info(f"Unfreezing card token: {card_token} (Reason: {reason})")
    try:
        from repositories.credit_card import CreditCardRepository
        repo = CreditCardRepository(db)
        card = repo.get_card_by_token(card_token)
        if not card:
            logger.error(f"Card token '{card_token}' not found.")
            raise ValueError(f"Card token '{card_token}' not found.")
            
        card.status = "ACTIVE"
        repo.save_card(card)
        record_audit_event(db, "CARD_UNFROZEN", {"account_id": str(card.account_id), "card_token": card_token, "reason": reason})
        db.commit()
        logger.info(f"Card token '{card_token}' successfully unblocked and reactivated.")
        return {"card_token": card_token, "status": "ACTIVE"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error unfreezing card: {e}")
        raise e


def issue_replacement_card(
    db: Session,
    account_id: str,
    reason: str,
    *,
    wallet_provider: str = "GOOGLE_WALLET",
    issue_virtual_card: bool = True,
    fraud_alert_id: str | None = None,
    compromised_card_id: str | None = None,
) -> dict:
    """
    Issues a replacement card for an account after fraud or loss workflows.
    When compromised_card_id is supplied, only that card is deactivated.
    Legacy callers without a card id keep the prior account-level replacement behavior.
    """
    logger.info(
        "Issuing replacement card for account=%s reason=%s wallet_provider=%s",
        account_id,
        reason,
        wallet_provider,
    )
    try:
        from repositories.credit_card import CreditCardRepository

        repo = CreditCardRepository(db)
        account = repo.get_account_by_id(account_id, lock=True)
        if not account:
            raise ValueError(f"Account '{account_id}' not found.")

        cards = repo.list_cards_by_account(account.id)
        if compromised_card_id:
            current_card = repo.get_card_by_id_for_account(compromised_card_id, account.id)
            if not current_card:
                raise ValueError("Compromised card not found for the specified account.")
            if current_card.status not in {"ACTIVE", "BLOCKED", "REPORTED_STOLEN"}:
                raise ValueError(f"Card '{compromised_card_id}' is not eligible for replacement.")
        else:
            current_card = next((card for card in cards if card.is_active), None)
            if not current_card:
                current_card = next((card for card in cards if card.status in {"BLOCKED", "REPORTED_STOLEN"}), None)
        if not current_card:
            raise ValueError("No existing card found for replacement.")

        cards_to_deactivate = [current_card] if compromised_card_id else [card for card in cards if card.is_active]
        for card in cards_to_deactivate:
            card.is_active = False
            if card.status == "ACTIVE":
                card.status = "BLOCKED"
            repo.save_card(card)

        exp_month = current_card.exp_month
        exp_year = max(current_card.exp_year, datetime.datetime.now(datetime.timezone.utc).year + 4)
        replacement_card = IssuedCard(
            account_id=account.id,
            cardholder_name=current_card.cardholder_name,
            card_token=_generate_card_token(),
            last_four=_generate_last_four(),
            exp_month=exp_month,
            exp_year=exp_year,
            status="ACTIVE",
            is_active=True,
            is_virtual=issue_virtual_card,
        )
        repo.save_card(replacement_card)

        record_audit_event(
            db,
            "CARD_REPLACED",
            {
                "account_id": str(account.id),
                "old_card_id": str(current_card.id),
                "old_card_token": current_card.card_token,
                "new_card_id": str(replacement_card.id),
                "new_card_token": replacement_card.card_token,
                "new_last_four": replacement_card.last_four,
                "reason": reason,
                "is_virtual": issue_virtual_card,
                "fraud_alert_id": fraud_alert_id,
                "compromised_card_id": str(compromised_card_id) if compromised_card_id else None,
                "correlation_id": fraud_alert_id or replacement_card.card_token,
            },
        )
        db.commit()
        return {
            "account_id": str(account.id),
            "old_card_id": str(current_card.id),
            "old_card_token": current_card.card_token,
            "new_card_id": str(replacement_card.id),
            "new_card_token": replacement_card.card_token,
            "new_last_four": replacement_card.last_four,
            "status": replacement_card.status,
            "replacement_status": "ISSUED",
            "is_virtual": replacement_card.is_virtual,
            "fraud_alert_id": fraud_alert_id,
            "compromised_card_id": str(compromised_card_id) if compromised_card_id else None,
            "message": "Replacement virtual card issued.",
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error issuing replacement card: {e}")
        raise e


def apply_limit_increase(db: Session, account_id: str, requested_limit_cents: int) -> dict:
    """
    Processes credit limit adjustments with Pessimistic Row Locking to prevent balance race conditions.
    """
    logger.info(f"Processing credit limit request for account: {account_id} to {requested_limit_cents} cents")
    try:
        # Acquire exclusive database lock on the financial account row until transaction commit
        from repositories.credit_card import CreditCardRepository
        repo = CreditCardRepository(db)
        account = repo.get_account_by_id(account_id, lock=True)
        if not account:
            logger.error(f"Account '{account_id}' not found.")
            raise ValueError(f"Account '{account_id}' not found.")
            
        if account.status != "ACTIVE":
            raise ValueError(f"Account is in '{account.status}' status and ineligible for credit limit changes.")

        # Product Constraint Check: Validate requested limit against CreditProduct catalog parameters
        product = repo.get_credit_product(account.product_code)
        if product:
            if requested_limit_cents < product.min_credit_limit_cents or requested_limit_cents > product.max_credit_limit_cents:
                raise ValueError(
                    f"Requested limit {requested_limit_cents} cents is out of bounds for credit product '{account.product_code}'. "
                    f"Allowed range: {product.min_credit_limit_cents} to {product.max_credit_limit_cents} cents."
                )

        limit_change = requested_limit_cents - account.credit_limit_cents
        account.credit_limit_cents = requested_limit_cents
        account.available_credit_cents += limit_change
        
        repo.save_account(account)
        record_audit_event(db, "CREDIT_LIMIT_INCREASED", {"account_id": str(account_id), "new_limit_cents": account.credit_limit_cents})
        db.commit()
        logger.info(f"Limit updated. New Limit: {account.credit_limit_cents} cents, Available Credit: {account.available_credit_cents} cents")
        return {
            "account_id": account_id,
            "new_limit_cents": account.credit_limit_cents,
            "available_credit_cents": account.available_credit_cents
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error applying credit limit increase: {e}")
        raise e


def reverse_posted_fee(db: Session, account_id: str, transaction_id: str, reason: str) -> dict:
    """
    Durable double-entry ledger transaction reversal. Appends an offsetting credit transaction 
    and updates balances with Pessimistic Row Locking to guarantee ledger consistency.
    Supports reversing any debit (negative amount) transaction.
    """
    logger.info(f"Processing transaction reversal for account: {account_id}, Original Tx ID: {transaction_id}")
    try:
        # Acquire exclusive database lock on the financial account row to lock balances
        from repositories.credit_card import CreditCardRepository
        repo = CreditCardRepository(db)
        account = repo.get_account_by_id(account_id, lock=True)
        if not account:
            logger.error(f"Account '{account_id}' not found.")
            raise ValueError(f"Account '{account_id}' not found.")
            
        # Find original transaction in ledger
        original_tx = repo.get_ledger_entry_by_id(transaction_id)
        if not original_tx or original_tx.account_id != account_id:
            raise ValueError(f"Original transaction '{transaction_id}' not found in ledger.")
            
        # Verify the original transaction is a debit (charge)
        if original_tx.amount_cents >= 0:
            raise ValueError(f"Transaction '{transaction_id}' is a credit and cannot be reversed (Amount: {original_tx.amount_cents} cents).")
            
        # Verify no prior reversals exist for this transaction ID to prevent double-reversal adjustments
        reversal_description_old = f"FEE_REVERSAL_REF_{transaction_id}"
        reversal_description_new = f"REVERSAL_REF_{transaction_id}"
        
        prior_reversal = repo.get_reversal_entry(account_id, transaction_id)
        if prior_reversal:
            raise ValueError(f"Transaction '{transaction_id}' has already been reversed in ledger (Reversal ID: {prior_reversal.id}).")

        # Insert offsetting credit entry into account ledger (double-entry standard)
        reversal_amount = abs(original_tx.amount_cents) # Credit offset (positive)
        desc = reversal_description_old if original_tx.description == "LATE_FEE" else reversal_description_new
        
        reversal_entry = AccountLedger(
            account_id=account_id,
            amount_cents=reversal_amount,
            description=desc,
            posted_at=datetime.datetime.now(datetime.timezone.utc)
        )
        repo.save_ledger(reversal_entry)

        # Recalculate account balances
        account.cleared_balance_cents -= reversal_amount   # Debt decreases
        account.available_credit_cents += reversal_amount  # Available credit increases

        repo.save_account(account)
        record_audit_event(db, "FEE_REVERSED", {"account_id": str(account_id), "reversal_amount_cents": reversal_amount})
        db.commit()
        logger.info(f"Transaction reversed successfully. New Cleared Balance: {account.cleared_balance_cents} cents, Available Credit: {account.available_credit_cents} cents")
        return {
            "account_id": account_id,
            "reversed_amount_cents": reversal_amount,
            "cleared_balance_cents": account.cleared_balance_cents,
            "available_credit_cents": account.available_credit_cents
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error reversing posted transaction: {e}")
        raise e


def void_fraud_authorization_hold(
    db: Session,
    *,
    account_id: str,
    authorization_id: str,
    fraud_alert_id: str,
    reason: str = "CUSTOMER_CONFIRMED_FRAUD",
) -> dict:
    """
    Releases a disputed pending card authorization and records fraud-specific audit/action state.
    """
    logger.info(
        "Voiding fraud authorization hold account=%s authorization=%s fraud_alert=%s",
        account_id,
        authorization_id,
        fraud_alert_id,
    )
    try:
        from repositories.credit_card import CreditCardRepository
        from repositories.fraud import FraudAlertRepository

        repo = CreditCardRepository(db)
        fraud_repo = FraudAlertRepository(db)
        idempotency_key = f"fraud-auth-void:{authorization_id}"
        existing_action = fraud_repo.get_case_action_by_idempotency_key(
            fraud_alert_id=fraud_alert_id,
            idempotency_key=idempotency_key,
        )
        if existing_action and existing_action.status == "SUCCEEDED":
            result = dict(existing_action.result_payload or {})
            result["idempotent_replay"] = True
            return result

        account = repo.get_account_by_id(account_id, lock=True)
        if not account:
            raise ValueError(f"Account '{account_id}' not found.")

        auth = repo.get_authorization_by_id_for_account(authorization_id, account.id)
        if not auth:
            raise ValueError(f"Authorization '{authorization_id}' not found for account.")
        if auth.status != "PENDING":
            raise ValueError(f"Authorization '{authorization_id}' is not pending and cannot be voided.")

        action = fraud_repo.create_case_action(
            fraud_alert_id=fraud_alert_id,
            action_type="FRAUD_AUTHORIZATION_VOIDED",
            status="PENDING",
            idempotency_key=idempotency_key,
            request_payload={
                "account_id": str(account.id),
                "authorization_id": str(auth.id),
                "reason": reason,
            },
        )

        release_amount = int(auth.billing_amount_cents or auth.transaction_amount_cents or 0)
        auth.status = "REVERSED"
        repo.save_authorization(auth)
        repo.recalculate_available_credit(account)

        result = {
            "account_id": str(account.id),
            "authorization_id": str(auth.id),
            "fraud_alert_id": fraud_alert_id,
            "voided_amount_cents": release_amount,
            "authorization_status": auth.status,
            "available_credit_cents": account.available_credit_cents,
            "message": "Pending fraud authorization reversed.",
        }
        record_audit_event(
            db,
            "FRAUD_AUTHORIZATION_VOIDED",
            {
                "fraud_alert_id": fraud_alert_id,
                "correlation_id": fraud_alert_id,
                "account_id": str(account.id),
                "card_id": str(auth.card_id),
                "authorization_id": str(auth.id),
                "amount_cents": release_amount,
                "reason": reason,
            },
        )
        fraud_repo.complete_case_action(
            action_id=action.id,
            status="SUCCEEDED",
            result_payload=result,
        )
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        logger.error(f"Error voiding fraud authorization hold: {e}")
        raise e


def apply_fraud_provisional_credit(
    db: Session,
    *,
    account_id: str,
    transaction_id: str,
    fraud_alert_id: str,
    reason: str = "CUSTOMER_CONFIRMED_FRAUD",
) -> dict:
    """
    Applies an offsetting provisional credit for a disputed posted debit transaction.
    """
    logger.info(
        "Applying fraud provisional credit account=%s transaction=%s fraud_alert=%s",
        account_id,
        transaction_id,
        fraud_alert_id,
    )
    try:
        from repositories.credit_card import CreditCardRepository
        from repositories.fraud import FraudAlertRepository

        repo = CreditCardRepository(db)
        fraud_repo = FraudAlertRepository(db)
        idempotency_key = f"fraud-provisional-credit:{transaction_id}"
        existing_action = fraud_repo.get_case_action_by_idempotency_key(
            fraud_alert_id=fraud_alert_id,
            idempotency_key=idempotency_key,
        )
        if existing_action and existing_action.status == "SUCCEEDED":
            result = dict(existing_action.result_payload or {})
            result["idempotent_replay"] = True
            return result

        account = repo.get_account_by_id(account_id, lock=True)
        if not account:
            raise ValueError(f"Account '{account_id}' not found.")

        original_tx = repo.get_ledger_entry_by_id_for_account(transaction_id, account.id)
        if not original_tx:
            raise ValueError(f"Posted transaction '{transaction_id}' not found for account.")
        if original_tx.amount_cents >= 0:
            raise ValueError(f"Posted transaction '{transaction_id}' is not a debit and cannot receive a provisional credit.")
        prior_credit = repo.get_fraud_provisional_credit_entry(account.id, transaction_id)
        if prior_credit:
            raise ValueError(f"Posted transaction '{transaction_id}' already has a provisional fraud credit.")

        action = fraud_repo.create_case_action(
            fraud_alert_id=fraud_alert_id,
            action_type="FRAUD_PROVISIONAL_CREDIT_APPLIED",
            status="PENDING",
            idempotency_key=idempotency_key,
            request_payload={
                "account_id": str(account.id),
                "transaction_id": str(original_tx.id),
                "reason": reason,
            },
        )

        credit_amount = abs(int(original_tx.amount_cents))
        credit_entry = AccountLedger(
            account_id=account.id,
            amount_cents=credit_amount,
            description=f"FRAUD_PROVISIONAL_CREDIT_REF_{transaction_id}",
            posted_at=datetime.datetime.now(datetime.timezone.utc),
        )
        repo.save_ledger(credit_entry)
        account.cleared_balance_cents -= credit_amount
        repo.recalculate_available_credit(account)

        result = {
            "account_id": str(account.id),
            "transaction_id": str(original_tx.id),
            "provisional_credit_transaction_id": str(credit_entry.id),
            "fraud_alert_id": fraud_alert_id,
            "credited_amount_cents": credit_amount,
            "cleared_balance_cents": account.cleared_balance_cents,
            "available_credit_cents": account.available_credit_cents,
            "message": "Provisional fraud credit applied pending investigation.",
        }
        record_audit_event(
            db,
            "FRAUD_PROVISIONAL_CREDIT_APPLIED",
            {
                "fraud_alert_id": fraud_alert_id,
                "correlation_id": fraud_alert_id,
                "account_id": str(account.id),
                "posted_transaction_id": str(original_tx.id),
                "provisional_credit_transaction_id": str(credit_entry.id),
                "amount_cents": credit_amount,
                "reason": reason,
            },
        )
        fraud_repo.complete_case_action(
            action_id=action.id,
            status="SUCCEEDED",
            result_payload=result,
        )
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        logger.error(f"Error applying fraud provisional credit: {e}")
        raise e


def get_fdx_account(db: Session, account_id: str, customer_id: str) -> FDXAccount:
    from repositories.credit_card import CreditCardRepository
    repo = CreditCardRepository(db)
    account = repo.get_account_by_id(account_id)
    resolved_uid = repo._resolve_user_id(customer_id)
    if not account or str(account.customer_id) != resolved_uid:
        raise ValueError("Account not found or access denied.")
    
    cards = repo.list_cards_by_account(account_id)
    mask = "3333"
    if cards and cards[0].last_four:
        mask = cards[0].last_four
        
    return FDXAccount(
        account_id=str(account.id),
        account_number_display=mask,
        product_name="Nova Horizon Elite Credit Card",
        status=account.status,
        account_type="CREDIT_CARD",
        current_balance=round(account.cleared_balance_cents / 100.0, 2),
        available_credit=round(account.available_credit_cents / 100.0, 2),
        credit_line=round(account.credit_limit_cents / 100.0, 2),
        iso_currency_code="USD"
    )


def get_realtime_balance(db: Session, account_id: str, customer_id: str) -> RealTimeBalanceResponse:
    from repositories.credit_card import CreditCardRepository
    repo = CreditCardRepository(db)
    account = repo.get_account_by_id(account_id)
    resolved_uid = repo._resolve_user_id(customer_id)
    if not account or str(account.customer_id) != resolved_uid:
        raise ValueError("Account not found or access denied.")
        
    pending_auths = repo.list_pending_authorizations(account_id)
    pending_amount_cents = sum(auth.transaction_amount_cents for auth in pending_auths)
    realtime_available_cents = account.credit_limit_cents - account.cleared_balance_cents - pending_amount_cents
    
    return RealTimeBalanceResponse(
        account_id=str(account.id),
        credit_limit=round(account.credit_limit_cents / 100.0, 2),
        cleared_balance=round(account.cleared_balance_cents / 100.0, 2),
        pending_authorizations_amount=round(pending_amount_cents / 100.0, 2),
        realtime_available_credit=round(realtime_available_cents / 100.0, 2),
        iso_currency_code="USD"
    )


def get_unified_transactions(db: Session, account_id: str, customer_id: str, offset: int = 0, limit: int = 50) -> PaginatedTransactionsResult:
    from repositories.credit_card import CreditCardRepository
    repo = CreditCardRepository(db)
    account = repo.get_account_by_id(account_id)
    resolved_uid = repo._resolve_user_id(customer_id)
    if not account or str(account.customer_id) != resolved_uid:
        raise ValueError("Account not found or access denied.")
        
    pending_auths = repo.list_pending_authorizations(account_id)
    posted_txs = repo.list_ledger_entries(account_id)
    
    unified: list[FDXTransaction] = []
    for auth in pending_auths:
        cat = TaxonomyService.get_category(auth.merchant_category_code)
        meta = PaymentMeta(reference_number=auth.retrieval_reference_number, auth_code=auth.auth_code, payment_method=auth.card_network)
        unified.append(FDXTransaction(
            account_id=str(account_id),
            transaction_id=str(auth.id),
            pending_transaction_id=str(auth.id),
            pending=True,
            amount=round(auth.transaction_amount_cents / 100.0, 2),
            iso_currency_code=auth.transaction_currency or "USD",
            description=auth.merchant_name or "Pending Charge",
            transaction_type="CREDITCARD",
            posted_timestamp=None,
            transaction_timestamp=auth.created_at.isoformat() if auth.created_at else "",
            personal_finance_category=cat,
            payment_meta=meta
        ))
        
    for tx in posted_txs:
        tx_type = "DIRECTDEPOSIT" if tx.amount_cents > 0 else "CREDITCARD"
        if "FEE" in (tx.description or "").upper() or "REVERSAL" in (tx.description or "").upper():
            tx_type = "ADJUSTMENT"
            
        pending_id = str(tx.authorization_id) if tx.authorization_id else None
        meta = PaymentMeta(reference_number=tx.retrieval_reference_number, auth_code=tx.auth_code)
        
        mcc = "5411"
        if tx.authorization and tx.authorization.merchant_category_code:
            mcc = tx.authorization.merchant_category_code
        cat = TaxonomyService.get_category(mcc)
        
        unified.append(FDXTransaction(
            account_id=str(account_id),
            transaction_id=str(tx.id),
            pending_transaction_id=pending_id,
            pending=False,
            amount=round(abs(tx.amount_cents) / 100.0, 2),
            iso_currency_code="USD",
            description=tx.description or "Posted Transaction",
            transaction_type=tx_type,
            posted_timestamp=tx.posted_at.isoformat() if tx.posted_at else "",
            transaction_timestamp=tx.posted_at.isoformat() if tx.posted_at else "",
            personal_finance_category=cat,
            payment_meta=meta
        ))
        
    unified.sort(key=lambda x: x.transaction_timestamp or "", reverse=True)
    paginated = unified[offset:offset + limit]
    return PaginatedTransactionsResult(transactions=paginated, total=len(unified))


def get_payment_networks(db: Session, account_id: str, customer_id: str) -> PaginatedPaymentNetworksResult:
    from repositories.credit_card import CreditCardRepository
    repo = CreditCardRepository(db)
    account = repo.get_account_by_id(account_id)
    resolved_uid = repo._resolve_user_id(customer_id)
    if not account or str(account.customer_id) != resolved_uid:
        raise ValueError("Account not found or access denied.")
        
    net = PaymentNetwork(
        bank_id="010088889",
        identifier="1111222233335820",
        type="US_ACH",
        transfer_in=True,
        transfer_out=True
    )
    return PaginatedPaymentNetworksResult(payment_networks=[net], total=1)


def get_account_summary_dto(repo: Any, customer_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves credit account summary and formatted cards list DTO for a customer."""
    account = repo.get_account_by_customer(customer_id)
    if not account:
        return None
    repo.recalculate_available_credit(account)
    wallet_statuses = get_wallet_status_by_card_token(repo.db, str(account.id))
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
                "exp_year": card.exp_year,
                **wallet_statuses.get(card.card_token, {}),
            } for card in account.cards
        ]
    }


def get_transaction_history_dto(repo: Any, customer_id: str) -> Optional[List[Dict[str, Any]]]:
    """Retrieves unified transaction ledger and pending authorization history DTO for a customer."""
    account = repo.get_account_by_customer(customer_id)
    if not account:
        return None
        
    auths = repo.list_authorizations(account.id, status="PENDING")
    ledger = repo.list_ledger_entries(account.id)
    
    results = []
    for auth in auths:
        cat = TaxonomyService.get_category(auth.merchant_category_code)
        results.append({
            "id": str(auth.id),
            "amount_cents": auth.transaction_amount_cents,
            "amount": auth.transaction_amount_cents / 100.0,
            "description": auth.merchant_name or auth.auth_code,
            "posted_at": auth.created_at.isoformat() if auth.created_at else None,
            "pending": True,
            "personal_finance_category": {
                "primary": cat.primary,
                "detailed": cat.detailed,
                "confidence_level": cat.confidence_level
            },
            "merchant_category_code": auth.merchant_category_code,
            "merchant_id": str(auth.merchant_id) if auth.merchant_id else None,
            "merchant_slug": auth.merchant_slug,
            "merchant_store_id": str(auth.merchant_store_id) if auth.merchant_store_id else None,
            "cardholder_name": auth.card.cardholder_name if auth.card else "Cardholder",
            "last_four": auth.card.last_four if auth.card else None,
        })
        
    for entry in ledger:
        mcc = entry.authorization.merchant_category_code if entry.authorization else "5411"
        cat = TaxonomyService.get_category(mcc)
        results.append({
            "id": str(entry.id),
            "amount_cents": entry.amount_cents,
            "amount": abs(entry.amount_cents) / 100.0,
            "description": entry.description,
            "posted_at": entry.posted_at.isoformat() if entry.posted_at else None,
            "posted_timestamp": entry.posted_at.isoformat() if entry.posted_at else None,
            "pending": False,
            "personal_finance_category": {
                "primary": cat.primary,
                "detailed": cat.detailed,
                "confidence_level": cat.confidence_level
            },
            "merchant_category_code": mcc,
            "merchant_id": str(entry.authorization.merchant_id) if entry.authorization and entry.authorization.merchant_id else None,
            "merchant_slug": entry.authorization.merchant_slug if entry.authorization else None,
            "merchant_store_id": str(entry.authorization.merchant_store_id) if entry.authorization and entry.authorization.merchant_store_id else None,
            "cardholder_name": entry.authorization.card.cardholder_name if entry.authorization and entry.authorization.card else "Cardholder",
            "last_four": entry.authorization.card.last_four if entry.authorization and entry.authorization.card else None,
        })
        
    return results
