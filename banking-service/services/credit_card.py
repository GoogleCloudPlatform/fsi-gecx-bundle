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
from models.credit_card import FinancialAccount, IssuedCard, TransactionAuthorization, AccountLedger
from models.support import Escalation
from models.settings import SystemSetting
from utils.database import Base, engine

logger = logging.getLogger(__name__)

def initialize_db_and_seed(db: Session):
    """
    Creates SQL tables if they do not exist and populates the database with
    baseline cardholder profiles for development verification.
    """
    logger.info("Verifying credit card SQL schemas and tables...")
    Base.metadata.create_all(bind=engine)
    
    # Check if a seed account already exists
    if db.query(FinancialAccount).first():
        logger.info("Database already seeded. Skipping migration initializations.")
        return

    logger.info("Seeding database with default bank-issuer profiles...")
    try:
        # 1. Create a core Financial Account
        seed_account = FinancialAccount(
            id="acc-8888-9999",
            customer_id="cust-123",
            status="ACTIVE",
            credit_limit_cents=1000000,       # $10,000 credit limit
            cleared_balance_cents=18044,      # Total debt: $180.44 (Late Fee + Starbucks + YouTube + Whole Foods + Shell)
            available_credit_cents=981956,    # $9,819.56 available credit
            payment_due_date=datetime.datetime.utcnow() + datetime.timedelta(days=15),
            statement_close_date=datetime.datetime.utcnow() - datetime.timedelta(days=15)
        )
        db.add(seed_account)
        
        # 2. Issue a primary Credit Card linked to this account
        seed_card = IssuedCard(
            id="card-1111-2222",
            account_id=seed_account.id,
            cardholder_name="Jane Doe",
            card_token="tok_visa_jane_doe",
            last_four="8234",
            exp_month=12,
            exp_year=2028,
            status="ACTIVE",
            is_active=True
        )
        db.add(seed_card)
        
        # 3. Post realistic transaction entries to the account ledger
        seed_fee = AccountLedger(
            id="tx-fee-001",
            account_id=seed_account.id,
            amount_cents=-3500,               # -$35 late fee charge
            description="LATE_FEE",
            posted_at=datetime.datetime.utcnow() - datetime.timedelta(days=5)
        )
        db.add(seed_fee)

        seed_youtube = AccountLedger(
            id="tx-youtube-001",
            account_id=seed_account.id,
            amount_cents=-1399,               # -$13.99 subscription
            description="YouTube Premium Subscription",
            posted_at=datetime.datetime.utcnow() - datetime.timedelta(days=12)
        )
        db.add(seed_youtube)

        seed_starbucks = AccountLedger(
            id="tx-starbucks-001",
            account_id=seed_account.id,
            amount_cents=-475,                 # -$4.75 coffee purchase
            description="Starbucks Coffee",
            posted_at=datetime.datetime.utcnow() - datetime.timedelta(days=4)
        )
        db.add(seed_starbucks)

        seed_grocery = AccountLedger(
            id="tx-wholefoods-001",
            account_id=seed_account.id,
            amount_cents=-8420,               # -$84.20 groceries
            description="Whole Foods Market",
            posted_at=datetime.datetime.utcnow() - datetime.timedelta(days=8)
        )
        db.add(seed_grocery)

        seed_gas = AccountLedger(
            id="tx-shell-001",
            account_id=seed_account.id,
            amount_cents=-4250,               # -$42.50 gas station purchase
            description="Shell Gasoline",
            posted_at=datetime.datetime.utcnow() - datetime.timedelta(days=2)
        )
        db.add(seed_gas)
        
        # 5. Seed system settings with baseline Voice & Live Avatar configs
        if not db.query(SystemSetting).first():
            logger.info("Seeding baseline system settings configurations...")
            default_settings = [
                SystemSetting(key="voice_agent_hard_timeout_enabled", value="false"),
                SystemSetting(key="voice_agent_max_duration", value="300"),
                SystemSetting(key="voice_agent_warning_duration", value="240"),
                SystemSetting(key="voice_agent_avatar_selection", value="random"),
                SystemSetting(key="voice_agent_mock_avatar_enabled", value="false")
            ]
            db.add_all(default_settings)

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
    card = db.query(IssuedCard).filter_by(card_token=card_token).one_or_none()
    if not card:
        logger.error(f"Card token '{card_token}' not found.")
        raise ValueError(f"Card token '{card_token}' not found.")
        
    card.status = "BLOCKED"
    db.commit()
    logger.info(f"Card token '{card_token}' successfully blocked.")
    return {"card_token": card_token, "status": "BLOCKED"}


def apply_limit_increase(db: Session, account_id: str, requested_limit_cents: int) -> dict:
    """
    Processes credit limit adjustments with Pessimistic Row Locking to prevent balance race conditions.
    """
    logger.info(f"Processing credit limit request for account: {account_id} to {requested_limit_cents} cents")
    
    # Acquire exclusive database lock on the financial account row until transaction commit
    account = db.query(FinancialAccount).filter_by(id=account_id).with_for_update().one_or_none()
    if not account:
        logger.error(f"Account '{account_id}' not found.")
        raise ValueError(f"Account '{account_id}' not found.")
        
    if account.status != "ACTIVE":
        raise ValueError(f"Account is in '{account.status}' status and ineligible for credit limit changes.")

    limit_change = requested_limit_cents - account.credit_limit_cents
    account.credit_limit_cents = requested_limit_cents
    account.available_credit_cents += limit_change
    
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
    account = db.query(FinancialAccount).filter_by(id=account_id).with_for_update().one_or_none()
    if not account:
        logger.error(f"Account '{account_id}' not found.")
        raise ValueError(f"Account '{account_id}' not found.")
        
    # Find original transaction in ledger
    original_tx = db.query(AccountLedger).filter_by(id=transaction_id, account_id=account_id).one_or_none()
    if not original_tx:
        raise ValueError(f"Original transaction '{transaction_id}' not found in ledger.")
        
    # Verify the original transaction is a debit (charge)
    if original_tx.amount_cents >= 0:
        raise ValueError(f"Transaction '{transaction_id}' is a credit and cannot be reversed (Amount: {original_tx.amount_cents} cents).")
        
    # Verify no prior reversals exist for this transaction ID to prevent double-reversal adjustments
    reversal_description_old = f"FEE_REVERSAL_REF_{transaction_id}"
    reversal_description_new = f"REVERSAL_REF_{transaction_id}"
    
    prior_reversal = db.query(AccountLedger).filter(
        AccountLedger.account_id == account_id,
        AccountLedger.authorization_id == None,
        AccountLedger.description.in_([reversal_description_old, reversal_description_new])
    ).first()
    if prior_reversal:
        raise ValueError(f"Transaction '{transaction_id}' has already been reversed in ledger (Reversal ID: {prior_reversal.id}).")

    # Insert offsetting credit entry into account ledger (double-entry standard)
    reversal_amount = abs(original_tx.amount_cents) # Credit offset (positive)
    desc = reversal_description_old if original_tx.description == "LATE_FEE" else reversal_description_new
    
    reversal_entry = AccountLedger(
        account_id=account_id,
        amount_cents=reversal_amount,
        description=desc,
        posted_at=datetime.datetime.utcnow()
    )
    db.add(reversal_entry)

    # Recalculate account balances
    account.cleared_balance_cents -= reversal_amount   # Debt decreases
    account.available_credit_cents += reversal_amount  # Available credit increases

    db.commit()
    logger.info(f"Transaction reversed successfully. New Cleared Balance: {account.cleared_balance_cents} cents, Available Credit: {account.available_credit_cents} cents")
    return {
        "account_id": account_id,
        "reversed_amount_cents": reversal_amount,
        "cleared_balance_cents": account.cleared_balance_cents,
        "available_credit_cents": account.available_credit_cents
    }
