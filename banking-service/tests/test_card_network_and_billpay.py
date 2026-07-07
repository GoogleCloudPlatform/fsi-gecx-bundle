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
from models.identity import User
from models.origination import Account
from models.credit_card import CreditAccount, IssuedCard, TransactionAuthorization, PostedTransaction
from models.audit import AuditOutbox

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

@pytest.mark.asyncio
async def test_card_network_authorize_success(async_client, db_session):
    user, checking, credit_acc, card = setup_test_cardholder_suite(db_session)
    
    headers = {"X-Card-Network-Token": "switch-secret-key-12345"}
    payload = {
        "card_token": "tok_visa_swipe_tester",
        "amount_cents": 1500, # $15.00 hold
        "retrieval_reference_number": "123456789012",
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
    
    # Verify summary API
    summary_resp = await async_client.get("/api/v1/accounts/summary")
    assert summary_resp.status_code == status.HTTP_200_OK
    summary_data = summary_resp.json()
    assert len(summary_data["deposit_accounts"]) == 1
    assert summary_data["deposit_accounts"][0]["cleared_balance_cents"] == 50000
    assert len(summary_data["credit_accounts"]) == 1
    assert summary_data["credit_accounts"][0]["cleared_balance_cents"] == 15000
    
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
