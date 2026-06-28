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

logger = logging.getLogger(__name__)

def initialize_db_and_seed(db: Session):
    """
    Creates SQL tables if they do not exist and populates the database with
    baseline cardholder profiles for development verification.
    """
    logger.info("Verifying credit card SQL schemas and tables...")
    
    from repositories.credit_card import CreditCardRepository
    repo = CreditCardRepository(db)
    
    # Check if a seed account already exists
    if repo.get_account_by_id("88888888-8888-4888-8888-999999999999"):
        logger.info("Database already seeded. Skipping migration initializations.")
        return

    logger.info("Seeding database with default bank-issuer profiles...")
    try:
        # 1. Create a core Financial Account
        seed_account = FinancialAccount(
            id="88888888-8888-4888-8888-999999999999",
            customer_id="cust-123",
            status="ACTIVE",
            credit_limit_cents=1000000,       # $10,000 credit limit
            cleared_balance_cents=18044,      # Total debt: $180.44 (Late Fee + Starbucks + YouTube + Whole Foods + Shell)
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
            card_token="tok_visa_jane_doe",
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
            amount_cents=-3500,               # -$35 late fee charge
            description="LATE_FEE",
            posted_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=5)
        )
        repo.save_ledger(seed_fee)

        seed_youtube = AccountLedger(
            id="00000000-0000-4000-8000-000000000002",
            account_id=seed_account.id,
            amount_cents=-1399,               # -$13.99 subscription
            description="YouTube Premium Subscription",
            posted_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=12)
        )
        repo.save_ledger(seed_youtube)

        seed_starbucks = AccountLedger(
            id="00000000-0000-4000-8000-000000000003",
            account_id=seed_account.id,
            amount_cents=-475,                 # -$4.75 coffee purchase
            description="Starbucks Coffee",
            posted_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=4)
        )
        repo.save_ledger(seed_starbucks)

        seed_grocery = AccountLedger(
            id="00000000-0000-4000-8000-000000000004",
            account_id=seed_account.id,
            amount_cents=-8420,               # -$84.20 groceries
            description="Whole Foods Market",
            posted_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=8)
        )
        repo.save_ledger(seed_grocery)

        seed_gas = AccountLedger(
            id="00000000-0000-4000-8000-000000000005",
            account_id=seed_account.id,
            amount_cents=-4250,               # -$42.50 gas station purchase
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
    db.commit()
    logger.info(f"Transaction reversed successfully. New Cleared Balance: {account.cleared_balance_cents} cents, Available Credit: {account.available_credit_cents} cents")
    return {
        "account_id": account_id,
        "reversed_amount_cents": reversal_amount,
        "cleared_balance_cents": account.cleared_balance_cents,
        "available_credit_cents": account.available_credit_cents
    }
