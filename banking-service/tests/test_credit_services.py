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

import pytest
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.credit_card import Base, FinancialAccount, IssuedCard, AccountLedger
from services.credit_card import freeze_card, apply_limit_increase, reverse_posted_fee

# Use an isolated, in-memory SQLite database for sub-second, side-effect-free testing
DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(name="db_session")
def fixture_db_session():
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Initialize all database tables
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    try:
        # Seed test profiles
        account = FinancialAccount(
            id="12300000-0000-4000-8000-000000000123",
            customer_id="cust-test-xyz",
            status="ACTIVE",
            credit_limit_cents=500000,       # $5,000 credit limit
            cleared_balance_cents=3500,       # Owed $35 (late fee)
            available_credit_cents=496500      # available credit
        )
        db.add(account)
        
        card = IssuedCard(
            id="99900000-0000-4000-8000-000000000999",
            account_id=account.id,
            cardholder_name="John Doe",
            card_token="tok_test_john_doe",
            last_four="1234",
            exp_month=11,
            exp_year=2027,
            status="ACTIVE",
            is_active=True
        )
        db.add(card)
        
        fee_charge = AccountLedger(
            id="01000000-0000-4000-8000-000000000001",
            account_id=account.id,
            amount_cents=-3500,               # -$35 charge (debit)
            description="LATE_FEE",
            posted_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2)
        )
        db.add(fee_charge)
        
        db.commit()
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_freeze_card_success(db_session):
    """Verify that freezing a card correctly blocked its authorization status."""
    res = freeze_card(db_session, card_token="tok_test_john_doe", reason="LOST")
    assert res["status"] == "BLOCKED"
    
    # Query database to assert persistent state
    card = db_session.query(IssuedCard).filter_by(card_token="tok_test_john_doe").first()
    assert card.status == "BLOCKED"


def test_freeze_card_not_found(db_session):
    """Verify that attempting to freeze a non-existent card raises ValueError."""
    with pytest.raises(ValueError, match="Card token 'tok_invalid' not found"):
        freeze_card(db_session, card_token="tok_invalid", reason="STOLEN")


def test_apply_limit_increase_success(db_session):
    """Verify that credit limit increases update credit limit and available balance correctly."""
    res = apply_limit_increase(db_session, account_id="12300000-0000-4000-8000-000000000123", requested_limit_cents=800000) # $8,000
    assert res["new_limit_cents"] == 800000
    assert res["available_credit_cents"] == 796500 # $8,000 - $35 debt
    
    # Assert DB persistence
    account = db_session.query(FinancialAccount).filter_by(id="12300000-0000-4000-8000-000000000123").first()
    assert account.credit_limit_cents == 800000
    assert account.available_credit_cents == 796500


def test_reverse_posted_fee_success(db_session):
    """Verify that late fee reversals post an offsetting credit and adjust balances."""
    res = reverse_posted_fee(db_session, account_id="12300000-0000-4000-8000-000000000123", transaction_id="01000000-0000-4000-8000-000000000001", reason="CUSTOMER_COURTESY")
    assert res["reversed_amount_cents"] == 3500
    assert res["cleared_balance_cents"] == 0         # Debt cleared
    assert res["available_credit_cents"] == 500000    # Back to full $5,000 available limit
    
    # Assert new offsetting ledger entry is appended to DB
    reversal_tx = db_session.query(AccountLedger).filter_by(
        account_id="12300000-0000-4000-8000-000000000123",
        description="FEE_REVERSAL_REF_01000000-0000-4000-8000-000000000001"
    ).first()
    assert reversal_tx is not None
    assert reversal_tx.amount_cents == 3500


def test_reverse_posted_fee_already_reversed(db_session):
    """Verify that attempting to reverse the same fee twice fails to prevent double adjustments."""
    # 1st reversal succeeds
    reverse_posted_fee(db_session, account_id="12300000-0000-4000-8000-000000000123", transaction_id="01000000-0000-4000-8000-000000000001", reason="FIRST_TRY")
    
    # 2nd reversal must raise ValueError
    with pytest.raises(ValueError, match="has already been reversed"):
        reverse_posted_fee(db_session, account_id="12300000-0000-4000-8000-000000000123", transaction_id="01000000-0000-4000-8000-000000000001", reason="SECOND_TRY")
