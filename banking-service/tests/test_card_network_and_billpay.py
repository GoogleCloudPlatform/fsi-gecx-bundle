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
import uuid
import datetime
from unittest.mock import patch
from fastapi import status
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from main import app
from utils.database import Base, get_db
from utils.auth import get_current_user
from models.authentication import ValidatedToken
from models.identity import User, UserSecureMessage
from models.origination import Account
from models.credit_card import CreditAccount, IssuedCard, TransactionAuthorization, PostedTransaction
from models.audit import AuditOutbox
from models.fraud import FraudAlert, FraudModelDecision
from services.card_network import process_authorization, process_settlement
from services.credit_card import queue_wallet_provisioning

TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

mock_claims = {"sub": "uid-swipe-tester", "email": "swipe.tester@google.com"}

def mock_get_current_user():
    return ValidatedToken(claims=mock_claims)

@pytest.fixture(name="db_session", autouse=True)
def fixture_db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    
    def override_get_db():
        try:
            yield db
        finally:
            pass
            
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = mock_get_current_user
    
    try:
        yield db
    finally:
        db.close()
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        Base.metadata.drop_all(bind=test_engine)

@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

# Helper to setup a test user with deposit accounts, credit lines, and cards
def setup_test_cardholder_suite(db):
    user = User(
        id=uuid.uuid4(),
        auth_provider_uid="uid-swipe-tester",
        first_name="Swipe",
        last_name="Tester",
        email="swipe.tester@google.com"
    )
    db.add(user)
    db.flush()
    
    checking = Account(
        user_id=user.id,
        account_number="CHK-10020033",
        account_type="CHECKING",
        product_name="Nova Everyday Checking",
        cleared_balance_cents=50000, # $500.00
        routing_number="021000021",
        status="ACTIVE"
    )
    db.add(checking)
    
    credit_acc = CreditAccount(
        customer_id=user.id,
        product_code="CASHBACK_EVERYDAY",
        status="ACTIVE",
        credit_limit_cents=100000, # $1,000.00
        cleared_balance_cents=0,
        available_credit_cents=100000
    )
    db.add(credit_acc)
    db.flush()
    
    card = IssuedCard(
        account_id=credit_acc.id,
        cardholder_name="Swipe Tester",
        card_token="tok_visa_swipe_tester",
        last_four="9999",
        exp_month=12,
        exp_year=2030,
        status="ACTIVE",
        is_active=True
    )
    db.add(card)
    db.commit()
    return user, checking, credit_acc, card


def test_process_authorization_publishes_structured_fraud_decision(db_session):
    user, checking, credit_acc, card = setup_test_cardholder_suite(db_session)
    published_events = []
    now = datetime.datetime(2026, 7, 10, 12, 0, tzinfo=datetime.timezone.utc)
    prior_auth = TransactionAuthorization(
        card_id=card.id,
        account_id=credit_acc.id,
        transaction_amount_cents=1000,
        billing_amount_cents=1000,
        status="PENDING",
        decline_reason="NONE",
        auth_code="111111",
        retrieval_reference_number="777777777776",
        card_network="VISA",
        merchant_category_code="5947",
        merchant_name="GAME TEST TOKEN ONLINE",
        transaction_channel="ECOMMERCE",
        entry_mode="ECOMMERCE",
        merchant_country_code="USA",
        merchant_city="San Francisco",
        merchant_region="CA",
        merchant_latitude=37.7749,
        merchant_longitude=-122.4194,
        fraud_risk_score=3,
        created_at=now - datetime.timedelta(minutes=5),
        expires_at=now + datetime.timedelta(days=7),
    )
    db_session.add(prior_auth)
    db_session.commit()
    payload = {
        "card_token": "tok_visa_swipe_tester",
        "amount_cents": 95000,
        "retrieval_reference_number": "777777777777",
        "merchant_category_code": "5947",
        "merchant_name": "RAZER GOLD GIFT CARD",
        "card_network": "VISA",
        "transaction_channel": "ECOMMERCE",
        "entry_mode": "ECOMMERCE",
        "merchant_country_code": "USA",
        "merchant_city": "San Francisco",
        "merchant_region": "CA",
        "merchant_postal_code": "94103",
        "merchant_latitude": 37.7749,
        "merchant_longitude": -122.4194,
        "ip_country_code": "USA",
        "shipping_country_code": "USA",
        "is_digital_goods": True,
        "merchant_high_risk_flags": ["DIGITAL_GOODS", "GIFT_CARD"],
        "is_fraud_simulation": True,
        "risk_score": 91,
        "created_at": now,
    }

    with patch("services.card_network._publish_redis_event", side_effect=lambda event_type, item: published_events.append((event_type, item))):
        result = process_authorization(db_session, payload)

    assert result["action_code"] == "00"
    assert result["status"] == "FLAGGED"
    assert result["fraud_risk_score"] == 91
    assert result["fraud_reason_codes"] == ["EXPLICIT_SIMULATION_OVERRIDE"]
    assert result["fraud_model_version"] == "local-deterministic-v1"
    assert result["transaction_channel"] == "ECOMMERCE"
    assert result["merchant_country_code"] == "USA"
    assert result["fraud_decision"]["decision"] == "FLAGGED"
    assert result["fraud_decision"]["features"]["amount_cents"] == 95000
    assert result["fraud_decision"]["features"]["transaction_channel"] == "ECOMMERCE"
    assert result["fraud_decision"]["features"]["merchant_city"] == "San Francisco"
    assert result["fraud_decision"]["features"]["is_digital_goods"] is True
    assert result["fraud_decision"]["features"]["recent_auth_count_10m"] == 1
    assert result["fraud_decision"]["features"]["amount_to_recent_average_ratio"] == 95.0

    auth = db_session.query(TransactionAuthorization).filter_by(retrieval_reference_number="777777777777").first()
    assert auth is not None
    assert auth.status == "FLAGGED"
    assert auth.fraud_risk_score == 91
    assert auth.transaction_channel == "ECOMMERCE"
    assert auth.entry_mode == "ECOMMERCE"
    assert auth.merchant_country_code == "USA"
    assert auth.merchant_city == "San Francisco"
    assert auth.is_digital_goods is True

    decision_record = db_session.query(FraudModelDecision).filter_by(authorization_id=auth.id).first()
    assert decision_record is not None
    assert decision_record.score == 91
    assert decision_record.decision == "FLAGGED"
    assert decision_record.reason_codes == ["EXPLICIT_SIMULATION_OVERRIDE"]
    assert decision_record.feature_snapshot["recent_auth_count_10m"] == 1
    assert decision_record.transaction_channel == "ECOMMERCE"

    audit_event = db_session.query(AuditOutbox).filter_by(event_type="FRAUD_MODEL_DECISION_RECORDED").first()
    assert audit_event is not None
    assert str(auth.id) in audit_event.payload

    alert = db_session.query(FraudAlert).filter_by(credit_account_id=credit_acc.id).first()
    assert alert is not None
    assert alert.source == "MODEL_DETECTED_FRAUD"
    assert alert.suspicious_authorization_ids == [str(auth.id)]
    assert alert.suspicious_transactions[0]["fraud_score"] == 91
    assert alert.suspicious_transactions[0]["reason_codes"] == ["EXPLICIT_SIMULATION_OVERRIDE"]

    secure_message = db_session.query(UserSecureMessage).filter_by(thread_id=alert.message_thread_id).first()
    assert secure_message is not None
    assert secure_message.category == "Fraud Alert"
    assert "RAZER GOLD GIFT CARD" in secure_message.message

    alert_created_event = db_session.query(AuditOutbox).filter_by(event_type="FRAUD_ALERT_CREATED").first()
    assert alert_created_event is not None
    assert str(alert.id) in alert_created_event.payload

    assert len(published_events) == 1
    event_type, event_payload = published_events[0]
    assert event_type == "AUTH"
    assert event_payload["status"] == "FLAGGED (RISK 91)"
    assert event_payload["fraud_risk_score"] == 91
    assert event_payload["fraud_reason_codes"] == ["EXPLICIT_SIMULATION_OVERRIDE"]
    assert event_payload["fraud_model_version"] == "local-deterministic-v1"
    assert event_payload["transaction_channel"] == "ECOMMERCE"
    assert event_payload["merchant_country_code"] == "USA"
    assert event_payload["fraud_features"]["recent_auth_count_10m"] == 1


def test_process_settlement_allows_flagged_authorization_hold(db_session):
    user, checking, credit_acc, card = setup_test_cardholder_suite(db_session)
    payload = {
        "card_token": "tok_visa_swipe_tester",
        "amount_cents": 95000,
        "retrieval_reference_number": "888777666555",
        "merchant_category_code": "5947",
        "merchant_name": "RAZER GOLD GIFT CARD",
        "card_network": "VISA",
        "transaction_channel": "ECOMMERCE",
        "entry_mode": "ECOMMERCE",
        "merchant_country_code": "USA",
        "is_digital_goods": True,
        "is_fraud_simulation": True,
        "risk_score": 91,
        "created_at": datetime.datetime(2026, 7, 10, 12, 0, tzinfo=datetime.timezone.utc),
    }

    with patch("services.card_network._publish_redis_event"):
        auth_result = process_authorization(db_session, payload)
        settlement_result = process_settlement(
            db_session,
            {
                "retrieval_reference_number": auth_result["retrieval_reference_number"],
                "amount_cents": payload["amount_cents"],
            },
        )

    auth = db_session.query(TransactionAuthorization).filter_by(retrieval_reference_number="888777666555").first()
    posted = db_session.query(PostedTransaction).filter_by(retrieval_reference_number="888777666555").first()
    assert auth is not None
    assert auth.status == "SETTLED"
    assert posted is not None
    assert settlement_result["status"] == "SETTLED"

@pytest.mark.asyncio
async def test_card_network_authorize_success(async_client, db_session):
    user, checking, credit_acc, card = setup_test_cardholder_suite(db_session)
    merchant_id = str(uuid.uuid4())
    merchant_store_id = str(uuid.uuid4())
    
    headers = {"X-Card-Network-Token": "switch-secret-key-12345"}
    payload = {
        "card_token": "tok_visa_swipe_tester",
        "amount_cents": 1500, # $15.00 hold
        "retrieval_reference_number": "123456789012",
        "merchant_id": merchant_id,
        "merchant_slug": "local_restaurant",
        "merchant_store_id": merchant_store_id,
        "merchant_category_code": "5812",
        "merchant_name": "Local Restaurant"
    }
    
    response = await async_client.post("/api/v1/card-network/authorize", json=payload, headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["action_code"] == "00"
    assert data["status"] == "PENDING"
    assert len(data["auth_code"]) == 6
    
    # Assert credit line available balance dropped
    db_session.refresh(credit_acc)
    assert credit_acc.available_credit_cents == 98500 # $985.00 available
    
    # Verify Authorization entry in DB
    auth = db_session.query(TransactionAuthorization).filter_by(retrieval_reference_number="123456789012").first()
    assert auth is not None
    assert auth.status == "PENDING"
    assert auth.transaction_amount_cents == 1500
    assert str(auth.merchant_id) == merchant_id
    assert auth.merchant_slug == "local_restaurant"
    assert str(auth.merchant_store_id) == merchant_store_id

@pytest.mark.asyncio
async def test_card_network_authorize_returns_503_during_maintenance(async_client, db_session):
    setup_test_cardholder_suite(db_session)

    headers = {"X-Card-Network-Token": "switch-secret-key-12345"}
    payload = {
        "card_token": "tok_visa_swipe_tester",
        "amount_cents": 1500,
        "retrieval_reference_number": "123456789099",
        "merchant_category_code": "5812",
        "merchant_name": "Local Restaurant",
    }

    with patch("utils.maintenance.get_maintenance_state", return_value={"active": True, "message": "Reset in progress"}):
        response = await async_client.post("/api/v1/card-network/authorize", json=payload, headers=headers)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()["detail"]["status"] == "MAINTENANCE"

@pytest.mark.asyncio
async def test_card_network_authorize_unauthorized(async_client):
    payload = {
        "card_token": "tok_visa_swipe_tester",
        "amount_cents": 1500,
        "retrieval_reference_number": "123456789012",
        "merchant_category_code": "5812",
        "merchant_name": "Local Restaurant"
    }
    # No auth header
    response = await async_client.post("/api/v1/card-network/authorize", json=payload)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.asyncio
async def test_card_network_authorize_insufficient_funds(async_client, db_session):
    user, checking, credit_acc, card = setup_test_cardholder_suite(db_session)
    
    headers = {"X-Card-Network-Token": "switch-secret-key-12345"}
    payload = {
        "card_token": "tok_visa_swipe_tester",
        "amount_cents": 250000, # $2,500.00 (limit is $1k)
        "retrieval_reference_number": "123456789013",
        "merchant_category_code": "5812",
        "merchant_name": "Luxury Retailer"
    }
    
    response = await async_client.post("/api/v1/card-network/authorize", json=payload, headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["action_code"] == "51"
    assert data["status"] == "DECLINED"
    assert data["decline_reason"] == "INSUFFICIENT_FUNDS"

@pytest.mark.asyncio
async def test_card_network_settle_success(async_client, db_session):
    user, checking, credit_acc, card = setup_test_cardholder_suite(db_session)
    
    # Pre-auth hold
    headers = {"X-Card-Network-Token": "switch-secret-key-12345"}
    auth_payload = {
        "card_token": "tok_visa_swipe_tester",
        "amount_cents": 5000, # $50 hold
        "retrieval_reference_number": "999888777666",
        "merchant_category_code": "5411",
        "merchant_name": "Grocery Store"
    }
    await async_client.post("/api/v1/card-network/authorize", json=auth_payload, headers=headers)
    
    # Settle final capture of $55 (tip addition)
    settle_payload = {
        "retrieval_reference_number": "999888777666",
        "amount_cents": 5500, # Final capture $55
        "description": "Grocery Store Capture"
    }
    with patch(
        "services.card_network.MerchantEnrichmentService.enrich_transaction",
        return_value={"clean_name": "Grocery Store", "mcc": "5411"},
    ):
        response = await async_client.post("/api/v1/card-network/settle", json=settle_payload, headers=headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "SETTLED"
    
    # Check DB state
    db_session.refresh(credit_acc)
    assert credit_acc.cleared_balance_cents == 5500 # cleared debt is $55
    assert credit_acc.available_credit_cents == 94500 # available is $945
    
    # Check posted transaction entry
    posted = db_session.query(PostedTransaction).filter_by(retrieval_reference_number="999888777666").first()
    assert posted is not None
    assert posted.amount_cents == -5500 # Debit is negative
    assert posted.description == "Grocery Store"

@pytest.mark.asyncio
async def test_card_network_reverse_success(async_client, db_session):
    user, checking, credit_acc, card = setup_test_cardholder_suite(db_session)
    
    headers = {"X-Card-Network-Token": "switch-secret-key-12345"}
    auth_payload = {
        "card_token": "tok_visa_swipe_tester",
        "amount_cents": 2000,
        "retrieval_reference_number": "555666777888",
        "merchant_category_code": "5812",
        "merchant_name": "Coffee Shop"
    }
    await async_client.post("/api/v1/card-network/authorize", json=auth_payload, headers=headers)
    
    # Reverse
    rev_payload = {
        "retrieval_reference_number": "555666777888"
    }
    response = await async_client.post("/api/v1/card-network/reverse", json=rev_payload, headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "REVERSED"
    
    db_session.refresh(credit_acc)
    assert credit_acc.available_credit_cents == 100000 # credit restored

@pytest.mark.asyncio
async def test_accounts_summary_and_pay_success(async_client, db_session):
    user, checking, credit_acc, card = setup_test_cardholder_suite(db_session)
    
    # Pre-charge credit card cleared debt by manually posting a transaction or via settlement
    credit_acc.cleared_balance_cents = 15000 # outstanding debt $150.00
    credit_acc.available_credit_cents = 85000
    db_session.commit()

    queue_wallet_provisioning(
        db_session,
        account_id=str(credit_acc.id),
        card_token=card.card_token,
        wallet_provider="GOOGLE_WALLET",
    )
    
    # Verify summary API
    summary_resp = await async_client.get("/api/v1/accounts/summary")
    assert summary_resp.status_code == status.HTTP_200_OK
    summary_data = summary_resp.json()
    assert len(summary_data["deposit_accounts"]) == 1
    assert summary_data["deposit_accounts"][0]["cleared_balance_cents"] == 50000
    assert len(summary_data["credit_accounts"]) == 1
    assert summary_data["credit_accounts"][0]["cleared_balance_cents"] == 15000
    assert summary_data["credit_accounts"][0]["statement_balance_cents"] == 15000
    assert summary_data["credit_accounts"][0]["minimum_due_cents"] == 3500
    assert summary_data["credit_accounts"][0]["payment_due_date"] is not None
    assert summary_data["credit_accounts"][0]["statement_close_date"] is not None
    summary_card = summary_data["credit_accounts"][0]["cards"][0]
    assert summary_card["card_token"] == card.card_token
    assert summary_card["wallet_provider"] == "GOOGLE_WALLET"
    assert summary_card["wallet_provisioning_status"] == "QUEUED"
    
    # Pay credit card bill of $50.00 from checking
    pay_payload = {
        "source_account_id": str(checking.id),
        "credit_account_id": str(credit_acc.id),
        "amount_cents": 5000
    }
    pay_resp = await async_client.post("/api/v1/credit-card/pay", json=pay_payload)
    assert pay_resp.status_code == status.HTTP_200_OK
    pay_data = pay_resp.json()
    assert pay_data["status"] == "SUCCESS"
    assert pay_data["source_cleared_balance_cents"] == 45000 # checking balance: $450.00
    assert pay_data["credit_cleared_balance_cents"] == 10000 # outstanding card debt: $100.00
    assert pay_data["credit_available_credit_cents"] == 90000 # available card limit: $900.00
    
    # Verify DB updates
    db_session.refresh(checking)
    db_session.refresh(credit_acc)
    assert checking.cleared_balance_cents == 45000
    assert credit_acc.cleared_balance_cents == 10000
    
    # Verify posted card payment ledger entry
    posted = db_session.query(PostedTransaction).filter(
        PostedTransaction.account_id == credit_acc.id,
        PostedTransaction.description == "Bill Payment Received - Thank You"
    ).first()
    assert posted is not None
    assert posted.amount_cents == 5000 # credit payments are positive
    
    # Verify audit log recorded in outbox
    audit = db_session.query(AuditOutbox).filter_by(event_type="BILL_PAYMENT_EXECUTED").first()
    assert audit is not None


@pytest.mark.asyncio
async def test_internal_auto_paydown_uses_checking_then_savings(async_client, db_session):
    user, checking, credit_acc, card = setup_test_cardholder_suite(db_session)

    savings = Account(
        user_id=user.id,
        account_number="SAV-10020034",
        account_type="SAVINGS",
        product_name="Nova High Yield Savings",
        cleared_balance_cents=20000,
        routing_number="021000021",
        status="ACTIVE"
    )
    db_session.add(savings)

    credit_acc.cleared_balance_cents = 80000
    credit_acc.available_credit_cents = 20000
    checking.cleared_balance_cents = 15000
    db_session.commit()

    headers = {"X-Card-Network-Token": "switch-secret-key-12345"}
    payload = {
        "customer_id": str(user.id),
        "credit_account_id": str(credit_acc.id),
        "target_utilization": 0.35,
        "trigger_utilization": 0.65,
    }

    response = await async_client.post("/api/v1/credit-card/internal/auto-paydown", json=payload, headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["paid_amount_cents"] == 35000
    assert len(data["payments"]) == 2
    assert data["payments"][0]["source_account_type"] == "CHECKING"
    assert data["payments"][1]["source_account_type"] == "SAVINGS"

    db_session.refresh(checking)
    db_session.refresh(savings)
    db_session.refresh(credit_acc)
    assert checking.cleared_balance_cents == 0
    assert savings.cleared_balance_cents == 0
    assert credit_acc.cleared_balance_cents == 45000
