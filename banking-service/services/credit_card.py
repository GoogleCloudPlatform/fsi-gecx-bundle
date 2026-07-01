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
from sqlalchemy.orm import Session
from models.credit_card import FinancialAccount, IssuedCard, AccountLedger
from models.settings import SystemSetting
from utils.audit import record_audit_event
from models.fdx import (
    RealTimeBalanceResponse, PaginatedTransactionsResult, FDXTransaction,
    PaymentMeta, PaymentNetwork, PaginatedPaymentNetworksResult, FDXAccount
)
from services.taxonomy_service import TaxonomyService

logger = logging.getLogger(__name__)

def initialize_db_and_seed(db: Session):
    """
    Creates SQL tables if they do not exist and populates the database with
    baseline cardholder profiles for development verification.
    """
    logger.info("Verifying credit card SQL schemas and tables...")
    try:
        db.connection().info["_ignore_rbac"] = True
    except Exception:
        pass
    
    from repositories.credit_card import CreditCardRepository
    repo = CreditCardRepository(db)
    
    # Check if a seed account already exists
    if repo.get_account_by_id("88888888-8888-4888-8888-999999999999"):
        logger.info("Database already seeded. Skipping migration initializations.")
        return

    logger.info("Seeding database with default bank-issuer profiles...")
    try:
        # Seed credit products catalog if empty
        from models.credit_card import CreditProduct
        if db.query(CreditProduct).count() == 0:
            logger.info("Seeding CreditProduct catalog in active DB session...")
            products = [
                CreditProduct(product_code="PLATINUM_TRAVEL_REWARDS", product_name="Nova Platinum Travel", min_credit_limit_cents=1500000, max_credit_limit_cents=10000000, purchase_apr=0.1899, cashback_rate=0.0000, travel_multiplier=3, dining_multiplier=3, annual_fee_cents=9500),
                CreditProduct(product_code="CASHBACK_EVERYDAY", product_name="Nova Cashback Everyday", min_credit_limit_cents=300000, max_credit_limit_cents=1500000, purchase_apr=0.2199, cashback_rate=0.0150, travel_multiplier=1, dining_multiplier=1, annual_fee_cents=0),
                CreditProduct(product_code="BUSINESS_ADVANTAGE", product_name="Executive Business Advantage", min_credit_limit_cents=2000000, max_credit_limit_cents=15000000, purchase_apr=0.1799, cashback_rate=0.0200, travel_multiplier=2, dining_multiplier=2, annual_fee_cents=0),
                CreditProduct(product_code="SECURED_STARTER", product_name="Nova Secured Rebuilder", min_credit_limit_cents=50000, max_credit_limit_cents=250000, purchase_apr=0.2799, cashback_rate=0.0100, travel_multiplier=1, dining_multiplier=1, annual_fee_cents=0)
            ]
            db.add_all(products)
            db.flush()

        # Seed deposit products catalog if empty
        from models.origination import DepositProduct
        if db.query(DepositProduct).count() == 0:
            logger.info("Seeding DepositProduct catalog in active DB session...")
            deposits = [
                DepositProduct(product_code="CHECKING_SIGNATURE", product_name="Nova Signature Checking", annual_percentage_yield=0.0005, monthly_maintenance_fee_cents=1500),
                DepositProduct(product_code="CHECKING_EVERYDAY", product_name="Nova Everyday Checking", annual_percentage_yield=0.0000, monthly_maintenance_fee_cents=0),
                DepositProduct(product_code="SAVINGS_HIGH_YIELD", product_name="Nova High Yield Savings", annual_percentage_yield=0.0450, monthly_maintenance_fee_cents=0),
                DepositProduct(product_code="BUSINESS_CHECKING", product_name="Nova Business Checking", annual_percentage_yield=0.0010, monthly_maintenance_fee_cents=1000)
            ]
            db.add_all(deposits)
            db.flush()

        # Seed default user in identity.users if not present
        from models.identity import User
        seed_user_id = "12300000-0000-4000-8000-000000000123"
        seed_user = db.query(User).filter(User.id == seed_user_id).first()
        if not seed_user:
            logger.info("Creating default seed user record...")
            seed_user = User(
                id=seed_user_id,
                auth_provider_uid="cust-123",
                first_name="Jane",
                last_name="Doe",
                email="customer@example.com",
                phone_number="555-0199"
            )
            db.add(seed_user)
            db.flush()

        # 1. Create a core Financial Account if not already seeded
        seed_acc_id = "88888888-8888-4888-8888-999999999999"
        if not db.query(FinancialAccount).filter(FinancialAccount.id == seed_acc_id).first():
            seed_account = FinancialAccount(
                id=seed_acc_id,
                customer_id=seed_user.id,
                product_code="CASHBACK_EVERYDAY",
                status="ACTIVE",
                credit_limit_cents=1000000,       # $10,000 credit limit
                cleared_balance_cents=18044,      # Total debt: $180.44
                available_credit_cents=981956,    # $9,819.56 available credit
                payment_due_date=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=15),
                statement_close_date=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=15)
            )
            repo.save_account(seed_account)
            
            # 2. Issue a primary Credit Card linked to this account
            seed_card = IssuedCard(
                id="11111111-1111-4111-8111-222222222222",
                account_id=seed_account.id,
                cardholder_name="Jane Doe",
                card_token="tok_visa_seed_8888",
                last_four="8234",
                exp_month=12,
                exp_year=2028,
                status="ACTIVE",
                is_active=True
            )
            repo.save_card(seed_card)
            
            # 3. Post realistic transaction entries to the account ledger
            seed_fee = AccountLedger(
                id="00000000-0000-4000-8000-000000000001",
                account_id=seed_account.id,
                amount_cents=-3500,
                description="LATE_FEE",
                posted_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=5)
            )
            repo.save_ledger(seed_fee)

            seed_youtube = AccountLedger(
                id="00000000-0000-4000-8000-000000000002",
                account_id=seed_account.id,
                amount_cents=-1399,
                description="YouTube Premium Subscription",
                posted_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=12)
            )
            repo.save_ledger(seed_youtube)

            seed_starbucks = AccountLedger(
                id="00000000-0000-4000-8000-000000000003",
                account_id=seed_account.id,
                amount_cents=-475,
                description="Starbucks Coffee",
                posted_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=4)
            )
            repo.save_ledger(seed_starbucks)

            seed_grocery = AccountLedger(
                id="00000000-0000-4000-8000-000000000004",
                account_id=seed_account.id,
                amount_cents=-8420,
                description="Whole Foods Market",
                posted_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=8)
            )
            repo.save_ledger(seed_grocery)

            seed_gas = AccountLedger(
                id="00000000-0000-4000-8000-000000000005",
                account_id=seed_account.id,
                amount_cents=-4250,
                description="Shell Gasoline",
                posted_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2)
            )
            repo.save_ledger(seed_gas)
        
        # 5. Seed system settings with baseline Voice & Live Avatar configs
        from repositories.settings import SystemSettingsRepository
        settings_repo = SystemSettingsRepository(db)
        if not settings_repo.get_first():
            logger.info("Seeding baseline system settings configurations...")
            default_settings = [
                SystemSetting(key="voice_agent_hard_timeout_enabled", value="false"),
                SystemSetting(key="voice_agent_max_duration", value="300"),
                SystemSetting(key="voice_agent_warning_duration", value="240"),
                SystemSetting(key="voice_agent_avatar_selection", value="random"),
                SystemSetting(key="voice_agent_mock_avatar_enabled", value="false")
            ]
            db.add_all(default_settings)
            db.flush()

        db.commit()
        logger.info("Database successfully seeded.")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to seed credit card database: {e}")
        raise e


def freeze_card(db: Session, card_token: str, reason: str) -> dict:
    """
    Locates the card by token and sets its status to 'BLOCKED' to freeze auth checks.
    """
    logger.info(f"Freezing card token: {card_token} (Reason: {reason})")
    from repositories.credit_card import CreditCardRepository
    repo = CreditCardRepository(db)
    card = repo.get_card_by_token(card_token)
    if not card:
        logger.error(f"Card token '{card_token}' not found.")
        raise ValueError(f"Card token '{card_token}' not found.")
        
    card.status = "BLOCKED"
    repo.save_card(card)
    record_audit_event(db, "CARD_FROZEN", {"card_token": card_token, "reason": reason})
    db.commit()
    logger.info(f"Card token '{card_token}' successfully blocked.")
    return {"card_token": card_token, "status": "BLOCKED"}


def apply_limit_increase(db: Session, account_id: str, requested_limit_cents: int) -> dict:
    """
    Processes credit limit adjustments with Pessimistic Row Locking to prevent balance race conditions.
    """
    logger.info(f"Processing credit limit request for account: {account_id} to {requested_limit_cents} cents")
    
    # Acquire exclusive database lock on the financial account row until transaction commit
    from repositories.credit_card import CreditCardRepository
    repo = CreditCardRepository(db)
    account = repo.get_account_by_id(account_id, lock=True)
    if not account:
        logger.error(f"Account '{account_id}' not found.")
        raise ValueError(f"Account '{account_id}' not found.")
        
    if account.status != "ACTIVE":
        raise ValueError(f"Account is in '{account.status}' status and ineligible for credit limit changes.")

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


def reverse_posted_fee(db: Session, account_id: str, transaction_id: str, reason: str) -> dict:
    """
    Durable double-entry ledger transaction reversal. Appends an offsetting credit transaction 
    and updates balances with Pessimistic Row Locking to guarantee ledger consistency.
    Supports reversing any debit (negative amount) transaction.
    """
    logger.info(f"Processing transaction reversal for account: {account_id}, Original Tx ID: {transaction_id}")

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
