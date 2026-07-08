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
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import models.audit  # noqa: F401
import models.fraud  # noqa: F401
from models.audit import AuditOutbox
from models.fraud import FraudCaseAction
from models.credit_card import Base, FinancialAccount, IssuedCard, AccountLedger, CreditProduct, TransactionAuthorization
from models.identity import User
from repositories.credit_card import CreditCardRepository
from repositories.fraud import FraudAlertRepository
from services.credit_card import (
    apply_limit_increase,
    apply_fraud_provisional_credit,
    freeze_card,
    issue_replacement_card,
    queue_wallet_provisioning,
    reverse_posted_fee,
    unfreeze_card,
    void_fraud_authorization_hold,
)

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
        # Pre-seed CreditProduct catalog
        prod = CreditProduct(
            product_code="CASHBACK_EVERYDAY",
            product_name="Nova Cashback Everyday",
            min_credit_limit_cents=300000,
            max_credit_limit_cents=1500000,
            purchase_apr=0.2199,
            cashback_rate=0.0150,
            travel_multiplier=1,
            dining_multiplier=1,
            annual_fee_cents=0
        )
        db.add(prod)
        
        # Pre-seed User
        usr = User(
            id="88888888-8888-4888-8888-222222222222",
            auth_provider_uid="cust-test-xyz",
            first_name="John",
            last_name="Doe",
            email="john@example.com"
        )
        db.add(usr)
        db.flush()

        # Seed test profiles
        account = FinancialAccount(
            id="12300000-0000-4000-8000-000000000123",
            customer_id=usr.id,
            product_code=prod.product_code,
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


def test_unfreeze_card_success(db_session):
    """Verify that unfreezing a blocked card restores its status to ACTIVE."""
    freeze_card(db_session, card_token="tok_test_john_doe", reason="LOST")
    res = unfreeze_card(db_session, card_token="tok_test_john_doe", reason="FOUND")
    assert res["status"] == "ACTIVE"
    
    card = db_session.query(IssuedCard).filter_by(card_token="tok_test_john_doe").first()
    assert card.status == "ACTIVE"


def test_issue_replacement_card_success(db_session):
    """Verify replacement issuance deactivates the prior card and creates a new active virtual card."""
    freeze_card(db_session, card_token="tok_test_john_doe", reason="LOST")

    result = issue_replacement_card(
        db_session,
        account_id="12300000-0000-4000-8000-000000000123",
        reason="CUSTOMER_FRAUD_REISSUE",
    )

    assert result["status"] == "ACTIVE"
    assert result["replacement_status"] == "ISSUED"
    assert result["is_virtual"] is True
    assert result["new_last_four"] != "1234"

    cards = db_session.query(IssuedCard).filter_by(account_id="12300000-0000-4000-8000-000000000123").all()
    assert len(cards) == 2
    active_cards = [card for card in cards if card.is_active]
    assert len(active_cards) == 1
    assert active_cards[0].last_four == result["new_last_four"]
    old_card = next(card for card in cards if card.card_token == "tok_test_john_doe")
    assert old_card.is_active is False


def test_issue_replacement_card_records_fraud_alert_correlation(db_session):
    """Verify replacement audit events can be tied back to the originating fraud alert."""
    alert = FraudAlertRepository(db_session).create_alert(
        customer_id="88888888-8888-4888-8888-222222222222",
        auth_provider_uid="cust-test-xyz",
        credit_account_id="12300000-0000-4000-8000-000000000123",
        card_id="99900000-0000-4000-8000-000000000999",
        card_last_four="1234",
        message_thread_id="thread-fraud-1",
        suspicious_authorization_ids=["auth-1"],
        suspicious_transactions=[{"merchant_name": "Fraud Test", "amount_cents": 1000}],
    )
    db_session.commit()

    freeze_card(db_session, card_token="tok_test_john_doe", reason="LOST")
    result = issue_replacement_card(
        db_session,
        account_id="12300000-0000-4000-8000-000000000123",
        reason="CUSTOMER_FRAUD_REISSUE",
        fraud_alert_id=str(alert.id),
    )

    event = db_session.query(AuditOutbox).filter_by(event_type="CARD_REPLACED").order_by(AuditOutbox.created_at.desc()).first()
    payload = json.loads(event.payload)
    assert result["fraud_alert_id"] == str(alert.id)
    assert payload["fraud_alert_id"] == str(alert.id)
    assert payload["correlation_id"] == str(alert.id)


def test_card_repository_retrieves_card_and_account_for_customer(db_session):
    repo = CreditCardRepository(db_session)

    result = repo.get_card_and_account_by_customer_secured(
        card_id="99900000-0000-4000-8000-000000000999",
        customer_id="cust-test-xyz",
    )

    assert result is not None
    card, account = result
    assert card.last_four == "1234"
    assert account.customer_id == "88888888-8888-4888-8888-222222222222"


def test_card_repository_rejects_card_for_wrong_customer(db_session):
    other_user = User(
        id="77777777-7777-4777-8777-777777777777",
        auth_provider_uid="other-customer",
        first_name="Other",
        last_name="Customer",
        email="other@example.com",
    )
    db_session.add(other_user)
    db_session.commit()
    repo = CreditCardRepository(db_session)

    result = repo.get_card_and_account_by_customer_secured(
        card_id="99900000-0000-4000-8000-000000000999",
        customer_id="other-customer",
    )

    assert result is None


def test_issue_replacement_card_with_compromised_card_preserves_other_active_cards(db_session):
    other_card = IssuedCard(
        id="22200000-0000-4000-8000-000000000222",
        account_id="12300000-0000-4000-8000-000000000123",
        cardholder_name="John Doe",
        card_token="tok_test_backup_card",
        last_four="2222",
        exp_month=10,
        exp_year=2028,
        status="ACTIVE",
        is_active=True,
        is_virtual=False,
    )
    db_session.add(other_card)
    db_session.commit()

    result = issue_replacement_card(
        db_session,
        account_id="12300000-0000-4000-8000-000000000123",
        reason="CUSTOMER_FRAUD_REISSUE",
        compromised_card_id="99900000-0000-4000-8000-000000000999",
        fraud_alert_id="fraud-alert-123",
    )

    compromised = db_session.query(IssuedCard).filter_by(id="99900000-0000-4000-8000-000000000999").first()
    unaffected = db_session.query(IssuedCard).filter_by(id="22200000-0000-4000-8000-000000000222").first()
    replacement = db_session.query(IssuedCard).filter_by(id=result["new_card_id"]).first()
    active_cards = db_session.query(IssuedCard).filter_by(
        account_id="12300000-0000-4000-8000-000000000123",
        is_active=True,
    ).all()

    assert result["old_card_id"] == "99900000-0000-4000-8000-000000000999"
    assert result["compromised_card_id"] == "99900000-0000-4000-8000-000000000999"
    assert compromised.is_active is False
    assert compromised.status == "BLOCKED"
    assert unaffected.is_active is True
    assert unaffected.status == "ACTIVE"
    assert replacement is not None
    assert replacement.is_virtual is True
    assert {card.id for card in active_cards} == {unaffected.id, replacement.id}

    event = db_session.query(AuditOutbox).filter_by(event_type="CARD_REPLACED").order_by(AuditOutbox.created_at.desc()).first()
    payload = json.loads(event.payload)
    assert payload["old_card_id"] == "99900000-0000-4000-8000-000000000999"
    assert payload["new_card_id"] == result["new_card_id"]
    assert payload["compromised_card_id"] == "99900000-0000-4000-8000-000000000999"


def test_queue_wallet_provisioning_records_fraud_alert_correlation(db_session):
    """Verify wallet provisioning audit events include the fraud correlation identifier."""
    alert = FraudAlertRepository(db_session).create_alert(
        customer_id="88888888-8888-4888-8888-222222222222",
        auth_provider_uid="cust-test-xyz",
        credit_account_id="12300000-0000-4000-8000-000000000123",
        card_id="99900000-0000-4000-8000-000000000999",
        card_last_four="1234",
        message_thread_id="thread-fraud-2",
        suspicious_authorization_ids=["auth-2"],
        suspicious_transactions=[{"merchant_name": "Fraud Test 2", "amount_cents": 2000}],
    )
    db_session.commit()

    result = queue_wallet_provisioning(
        db_session,
        account_id="12300000-0000-4000-8000-000000000123",
        card_token="tok_test_john_doe",
        fraud_alert_id=str(alert.id),
    )

    event = db_session.query(AuditOutbox).filter_by(event_type="WALLET_PROVISIONING_QUEUED").order_by(AuditOutbox.created_at.desc()).first()
    payload = json.loads(event.payload)
    assert result["fraud_alert_id"] == str(alert.id)
    assert payload["fraud_alert_id"] == str(alert.id)
    assert payload["correlation_id"] == str(alert.id)


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


def _create_fraud_alert(db_session, *, thread_id="thread-fraud-remediation"):
    return FraudAlertRepository(db_session).create_alert(
        customer_id="88888888-8888-4888-8888-222222222222",
        auth_provider_uid="cust-test-xyz",
        credit_account_id="12300000-0000-4000-8000-000000000123",
        card_id="99900000-0000-4000-8000-000000000999",
        card_last_four="1234",
        message_thread_id=thread_id,
        suspicious_authorization_ids=["02000000-0000-4000-8000-000000000002"],
        suspicious_transactions=[{"merchant_name": "TEST FRAUD MERCHANT", "amount_cents": 4200}],
    )


def _create_pending_fraud_authorization(db_session):
    auth = TransactionAuthorization(
        id="02000000-0000-4000-8000-000000000002",
        card_id="99900000-0000-4000-8000-000000000999",
        account_id="12300000-0000-4000-8000-000000000123",
        transaction_amount_cents=4200,
        billing_amount_cents=4200,
        status="PENDING",
        auth_code="123456",
        retrieval_reference_number="123456789012",
        card_network="VISA",
        merchant_category_code="5999",
        merchant_name="TEST FRAUD MERCHANT",
        expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7),
    )
    db_session.add(auth)
    account = db_session.query(FinancialAccount).filter_by(id="12300000-0000-4000-8000-000000000123").first()
    account.available_credit_cents -= 4200
    db_session.commit()
    return auth


def test_void_fraud_authorization_hold_releases_available_credit_and_records_action(db_session):
    alert = _create_fraud_alert(db_session)
    auth = _create_pending_fraud_authorization(db_session)

    result = void_fraud_authorization_hold(
        db_session,
        account_id="12300000-0000-4000-8000-000000000123",
        authorization_id=str(auth.id),
        fraud_alert_id=str(alert.id),
    )

    refreshed_auth = db_session.query(TransactionAuthorization).filter_by(id=auth.id).first()
    action = db_session.query(FraudCaseAction).filter_by(
        fraud_alert_id=alert.id,
        action_type="FRAUD_AUTHORIZATION_VOIDED",
    ).first()
    event = db_session.query(AuditOutbox).filter_by(event_type="FRAUD_AUTHORIZATION_VOIDED").first()
    account = db_session.query(FinancialAccount).filter_by(id="12300000-0000-4000-8000-000000000123").first()

    assert result["voided_amount_cents"] == 4200
    assert refreshed_auth.status == "REVERSED"
    assert account.available_credit_cents == 496500
    assert action is not None
    assert action.status == "SUCCEEDED"
    assert event is not None
    assert str(alert.id) in event.payload


def test_void_fraud_authorization_hold_is_idempotent(db_session):
    alert = _create_fraud_alert(db_session, thread_id="thread-fraud-remediation-idempotent")
    auth = _create_pending_fraud_authorization(db_session)

    first = void_fraud_authorization_hold(
        db_session,
        account_id="12300000-0000-4000-8000-000000000123",
        authorization_id=str(auth.id),
        fraud_alert_id=str(alert.id),
    )
    second = void_fraud_authorization_hold(
        db_session,
        account_id="12300000-0000-4000-8000-000000000123",
        authorization_id=str(auth.id),
        fraud_alert_id=str(alert.id),
    )

    actions = db_session.query(FraudCaseAction).filter_by(
        fraud_alert_id=alert.id,
        action_type="FRAUD_AUTHORIZATION_VOIDED",
    ).all()
    account = db_session.query(FinancialAccount).filter_by(id="12300000-0000-4000-8000-000000000123").first()

    assert first["voided_amount_cents"] == second["voided_amount_cents"] == 4200
    assert second["idempotent_replay"] is True
    assert account.available_credit_cents == 496500
    assert len(actions) == 1


def test_apply_fraud_provisional_credit_posts_credit_and_records_action(db_session):
    alert = _create_fraud_alert(db_session)

    result = apply_fraud_provisional_credit(
        db_session,
        account_id="12300000-0000-4000-8000-000000000123",
        transaction_id="01000000-0000-4000-8000-000000000001",
        fraud_alert_id=str(alert.id),
    )

    credit_entry = db_session.query(AccountLedger).filter_by(id=result["provisional_credit_transaction_id"]).first()
    action = db_session.query(FraudCaseAction).filter_by(
        fraud_alert_id=alert.id,
        action_type="FRAUD_PROVISIONAL_CREDIT_APPLIED",
    ).first()
    event = db_session.query(AuditOutbox).filter_by(event_type="FRAUD_PROVISIONAL_CREDIT_APPLIED").first()
    account = db_session.query(FinancialAccount).filter_by(id="12300000-0000-4000-8000-000000000123").first()

    assert result["credited_amount_cents"] == 3500
    assert credit_entry.amount_cents == 3500
    assert credit_entry.description == "FRAUD_PROVISIONAL_CREDIT_REF_01000000-0000-4000-8000-000000000001"
    assert account.cleared_balance_cents == 0
    assert account.available_credit_cents == 500000
    assert action is not None
    assert action.status == "SUCCEEDED"
    assert event is not None
    assert str(alert.id) in event.payload


def test_apply_fraud_provisional_credit_is_idempotent(db_session):
    alert = _create_fraud_alert(db_session, thread_id="thread-fraud-credit-idempotent")

    first = apply_fraud_provisional_credit(
        db_session,
        account_id="12300000-0000-4000-8000-000000000123",
        transaction_id="01000000-0000-4000-8000-000000000001",
        fraud_alert_id=str(alert.id),
    )
    second = apply_fraud_provisional_credit(
        db_session,
        account_id="12300000-0000-4000-8000-000000000123",
        transaction_id="01000000-0000-4000-8000-000000000001",
        fraud_alert_id=str(alert.id),
    )

    credit_entries = db_session.query(AccountLedger).filter_by(
        description="FRAUD_PROVISIONAL_CREDIT_REF_01000000-0000-4000-8000-000000000001",
    ).all()
    account = db_session.query(FinancialAccount).filter_by(id="12300000-0000-4000-8000-000000000123").first()

    assert first["credited_amount_cents"] == second["credited_amount_cents"] == 3500
    assert second["idempotent_replay"] is True
    assert account.cleared_balance_cents == 0
    assert account.available_credit_cents == 500000
    assert len(credit_entries) == 1


def test_apply_fraud_provisional_credit_rejects_credit_transaction(db_session):
    alert = _create_fraud_alert(db_session)
    payment = AccountLedger(
        id="03000000-0000-4000-8000-000000000003",
        account_id="12300000-0000-4000-8000-000000000123",
        amount_cents=1000,
        description="PAYMENT",
        posted_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db_session.add(payment)
    db_session.commit()

    with pytest.raises(ValueError, match="is not a debit"):
        apply_fraud_provisional_credit(
            db_session,
            account_id="12300000-0000-4000-8000-000000000123",
            transaction_id="03000000-0000-4000-8000-000000000003",
            fraud_alert_id=str(alert.id),
        )


def test_void_fraud_authorization_hold_rejects_wrong_account(db_session):
    alert = _create_fraud_alert(db_session)
    auth = _create_pending_fraud_authorization(db_session)

    with pytest.raises(ValueError, match="not found"):
        void_fraud_authorization_hold(
            db_session,
            account_id="77700000-0000-4000-8000-000000000777",
            authorization_id=str(auth.id),
            fraud_alert_id=str(alert.id),
        )
