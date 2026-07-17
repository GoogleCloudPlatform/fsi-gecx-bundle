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
import json
import uuid

import pytest
import respx
import httpx
from unittest.mock import MagicMock, patch
from fastapi import status
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from main import app
from utils.database import Base, get_db
from utils.auth import get_current_user
from models.authentication import ValidatedToken
from models.fraud import FraudAlert, FraudCaseAction, FraudModelDecision
from models.audit import AuditOutbox
from models.identity import User, UserAddress, UserSecureMessage
from models.origination import Account
from models.credit_card import CreditAccount, IssuedCard, PostedTransaction, TransactionAuthorization
from services.seeding_service import (
    _demo_account_baseline_cents,
    clean_database,
    provision_user_suite,
)

TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Global dict to store mocked auth claims dynamically across test runs
mock_claims = {"sub": "uid-tester", "email": "tester@google.com"}

def mock_get_current_user():
    return ValidatedToken(claims=mock_claims)

@pytest.fixture(name="db_session", autouse=True)
def fixture_db_session():
    # Setup schemas & tables in memory
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


def test_clean_database_removes_fraud_alerts(db_session):
    user = User(auth_provider_uid="fraud-reset-user", email="fraud-reset@example.com")
    db_session.add(user)
    db_session.flush()
    credit_account = CreditAccount(
        customer_id=user.id,
        product_code="CASHBACK_EVERYDAY",
        status="ACTIVE",
        credit_limit_cents=100000,
        available_credit_cents=100000,
    )
    db_session.add(credit_account)
    db_session.flush()
    card = IssuedCard(
        account_id=credit_account.id,
        cardholder_name="Fraud Reset",
        card_token="tok_fraud_reset",
        last_four="4242",
        exp_month=1,
        exp_year=2030,
        status="ACTIVE",
        is_active=True,
    )
    db_session.add(card)
    db_session.flush()
    fraud_alert = FraudAlert(
        customer_id=user.id,
        auth_provider_uid=user.auth_provider_uid,
        credit_account_id=credit_account.id,
        card_id=card.id,
        card_last_four=card.last_four,
        message_thread_id="thread-fraud-reset",
        suspicious_authorization_ids=[],
        suspicious_transactions=[],
    )
    db_session.add(fraud_alert)
    db_session.flush()
    db_session.add(
        FraudCaseAction(
            fraud_alert_id=fraud_alert.id,
            action_type="FRAUD_CASE_TRIAGED",
            status="SUCCEEDED",
            idempotency_key="reset-test",
            request_payload={},
            result_payload={},
        )
    )
    db_session.flush()

    clean_database(db_session)

    assert db_session.query(FraudCaseAction).count() == 0
    assert db_session.query(FraudAlert).count() == 0

@pytest.mark.asyncio
async def test_provision_my_demo_success(async_client, db_session):
    global mock_claims
    mock_claims = {"sub": "new-uid-123", "email": "new.presenter@google.com"}
    
    response = await async_client.post("/api/v1/simulation/provision-my-demo")
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["summary"]["first_name"] == "New"
    assert data["summary"]["last_name"] == "Presenter"
    
    # Assert records in DB
    user = db_session.query(User).filter(User.email == "new.presenter@google.com").first()
    assert user is not None
    assert user.auth_provider_uid == "new-uid-123"
    
    # Check deposit accounts
    accounts = db_session.query(Account).filter(
        Account.user_id == user.id,
        Account.account_type.in_(("CHECKING", "SAVINGS")),
    ).all()
    assert len(accounts) == 2
    
    # Check credit account
    cred_acc = db_session.query(CreditAccount).filter(CreditAccount.customer_id == user.id).first()
    assert cred_acc is not None
    assert cred_acc.cleared_balance_cents > 0
    from models.credit_card import TransactionAuthorization
    holds = db_session.query(TransactionAuthorization).filter(
        TransactionAuthorization.account_id == cred_acc.id,
        TransactionAuthorization.status == "PENDING"
    ).all()
    pending_sum = sum(h.transaction_amount_cents for h in holds)
    assert cred_acc.available_credit_cents == cred_acc.credit_limit_cents - cred_acc.cleared_balance_cents - pending_sum
    
    # Check historical swipes (should have exactly 10 posted retail transactions without overdraft fee)
    swipes = db_session.query(PostedTransaction).filter(PostedTransaction.account_id == cred_acc.id).all()
    assert len(swipes) == 10
    assert len(holds) == 2
    assert all(swipe.description != "Overdraft Fee" for swipe in swipes)
    assert sum("[MEX]" in swipe.description for swipe in swipes) >= 2
    assert sum("[MEX]" in hold.merchant_name for hold in holds) == 2

@pytest.mark.asyncio
async def test_provision_my_demo_conflict(async_client, db_session):
    global mock_claims
    mock_claims = {"sub": "duplicate-uid", "email": "dup@google.com"}
    
    # Provision once
    response = await async_client.post("/api/v1/simulation/provision-my-demo")
    assert response.status_code == status.HTTP_201_CREATED
    
    # Provision again -> Conflict
    response2 = await async_client.post("/api/v1/simulation/provision-my-demo")
    assert response2.status_code == status.HTTP_409_CONFLICT
    assert response2.json()["detail"] == "Profile already provisioned with active accounts."

@pytest.mark.asyncio
async def test_reset_my_demo_success(async_client, db_session):
    global mock_claims
    mock_claims = {"sub": "reset-uid", "email": "reset.presenter@google.com"}
    
    # Provision
    response = await async_client.post("/api/v1/simulation/provision-my-demo")
    assert response.status_code == status.HTTP_201_CREATED
    summary = response.json()["summary"]
    user_id = summary["user_id"]
    
    # Reset
    response2 = await async_client.post("/api/v1/simulation/reset-my-demo")
    assert response2.status_code == status.HTTP_200_OK
    assert response2.json()["status"] == "SUCCESS"
    
    # Verify balances reset to harmonized suite defaults with active transactions
    cred_acc = db_session.query(CreditAccount).filter(CreditAccount.customer_id == user_id).first()
    assert cred_acc.cleared_balance_cents > 0
    from models.credit_card import TransactionAuthorization
    holds = db_session.query(TransactionAuthorization).filter(
        TransactionAuthorization.account_id == cred_acc.id,
        TransactionAuthorization.status == "PENDING"
    ).all()
    pending_sum = sum(h.transaction_amount_cents for h in holds)
    assert cred_acc.available_credit_cents == cred_acc.credit_limit_cents - cred_acc.cleared_balance_cents - pending_sum
    
    swipes_count = db_session.query(PostedTransaction).filter(PostedTransaction.account_id == cred_acc.id).count()
    assert swipes_count == 10
    
    accounts = db_session.query(Account).filter(Account.user_id == user_id, Account.status == "ACTIVE").all()
    assert len([acc for acc in accounts if acc.account_type == "CHECKING"]) == 1
    assert len([acc for acc in accounts if acc.account_type == "SAVINGS"]) == 1
    expected_baseline = _demo_account_baseline_cents(mock_claims["email"])
    for acc in accounts:
        if acc.account_type == "CHECKING":
            assert acc.cleared_balance_cents == expected_baseline["checking"]
        elif acc.account_type == "SAVINGS":
            assert acc.cleared_balance_cents == expected_baseline["savings"]
    assert db_session.query(Account).filter(Account.user_id == user_id, Account.status == "CLOSED").count() == 2


@pytest.mark.asyncio
async def test_deprovision_my_demo_returns_to_one_click_provisioning_state(
    async_client, db_session
):
    global mock_claims
    mock_claims = {
        "sub": "deprovision-uid",
        "email": "deprovision.presenter@google.com",
    }

    provision_response = await async_client.post("/api/v1/simulation/provision-my-demo")
    assert provision_response.status_code == status.HTTP_201_CREATED
    user_id = provision_response.json()["summary"]["user_id"]
    original_deposit_account_ids = {
        str(account.id)
        for account in db_session.query(Account).filter(
            Account.user_id == user_id,
            Account.status == "ACTIVE",
            Account.account_type.in_(("CHECKING", "SAVINGS")),
        )
    }

    deprovision_response = await async_client.post(
        "/api/v1/simulation/deprovision-my-demo"
    )

    assert deprovision_response.status_code == status.HTTP_200_OK
    assert deprovision_response.json()["summary"] == {
        "deposit_accounts_closed": 2,
        "credit_accounts_closed": 1,
        "cards_deactivated": 1,
    }
    assert db_session.query(Account).filter(
        Account.user_id == user_id,
        Account.status == "ACTIVE",
    ).count() == 0
    assert db_session.query(CreditAccount).filter(
        CreditAccount.customer_id == user_id,
        CreditAccount.status == "ACTIVE",
    ).count() == 0
    assert db_session.query(IssuedCard).join(CreditAccount).filter(
        CreditAccount.customer_id == user_id,
        IssuedCard.is_active.is_(True),
    ).count() == 0
    assert db_session.query(AuditOutbox).filter(
        AuditOutbox.event_type == "DEMO_SUITE_DEPROVISIONED"
    ).count() == 1

    account_response = await async_client.get("/api/v1/credit-card/account")
    assert account_response.status_code == status.HTTP_404_NOT_FOUND
    summary_response = await async_client.get("/api/v1/accounts/summary")
    assert summary_response.status_code == status.HTTP_200_OK
    assert summary_response.json() == {
        "deposit_accounts": [],
        "credit_accounts": [],
    }
    for account_id in original_deposit_account_ids:
        transactions_response = await async_client.get(
            f"/api/v1/accounts/{account_id}/transactions"
        )
        assert transactions_response.status_code == status.HTTP_404_NOT_FOUND

    reprovision_response = await async_client.post(
        "/api/v1/simulation/provision-my-demo"
    )
    assert reprovision_response.status_code == status.HTTP_201_CREATED
    assert db_session.query(Account).filter(
        Account.user_id == user_id,
        Account.status == "ACTIVE",
        Account.account_type.in_(("CHECKING", "SAVINGS")),
    ).count() == 2
    assert db_session.query(CreditAccount).filter(
        CreditAccount.customer_id == user_id,
        CreditAccount.status == "ACTIVE",
    ).count() == 1
    assert db_session.query(IssuedCard).join(CreditAccount).filter(
        CreditAccount.customer_id == user_id,
        CreditAccount.status == "ACTIVE",
        IssuedCard.status == "ACTIVE",
        IssuedCard.is_active.is_(True),
    ).count() == 1


@pytest.mark.asyncio
async def test_accounts_summary_keeps_blocked_card_visible_on_active_account(
    async_client, db_session
):
    global mock_claims
    mock_claims = {
        "sub": "blocked-card-uid",
        "email": "blocked.card.presenter@google.com",
    }

    provision_response = await async_client.post("/api/v1/simulation/provision-my-demo")
    assert provision_response.status_code == status.HTTP_201_CREATED
    user_id = provision_response.json()["summary"]["user_id"]
    credit_account = db_session.query(CreditAccount).filter(
        CreditAccount.customer_id == user_id,
        CreditAccount.status == "ACTIVE",
    ).one()
    card = db_session.query(IssuedCard).filter(
        IssuedCard.account_id == credit_account.id
    ).one()
    card.status = "BLOCKED"
    card.is_active = False
    db_session.commit()

    summary_response = await async_client.get("/api/v1/accounts/summary")

    assert summary_response.status_code == status.HTTP_200_OK
    credit_accounts = summary_response.json()["credit_accounts"]
    assert len(credit_accounts) == 1
    assert credit_accounts[0]["status"] == "ACTIVE"
    assert len(credit_accounts[0]["cards"]) == 1
    assert credit_accounts[0]["cards"][0]["status"] == "BLOCKED"
    assert credit_accounts[0]["cards"][0]["is_active"] is False


@pytest.mark.asyncio
async def test_reset_my_demo_clears_fraud_state_and_restores_card_baseline(async_client, db_session):
    global mock_claims
    mock_claims = {"sub": "reset-fraud-uid", "email": "reset.fraud.presenter@google.com"}

    provision_response = await async_client.post("/api/v1/simulation/provision-my-demo")
    assert provision_response.status_code == status.HTTP_201_CREATED
    user_id = provision_response.json()["summary"]["user_id"]

    user = db_session.query(User).filter(User.id == user_id).first()
    cred_acc = db_session.query(CreditAccount).filter(CreditAccount.customer_id == user_id).first()
    original_card = db_session.query(IssuedCard).filter(IssuedCard.account_id == cred_acc.id).first()
    original_card_id = original_card.id
    original_card_token = original_card.card_token

    original_card.status = "BLOCKED"
    original_card.is_active = False
    replacement = IssuedCard(
        account_id=cred_acc.id,
        cardholder_name=original_card.cardholder_name,
        card_token="tok_reset_fraud_replacement",
        last_four="5188",
        exp_month=original_card.exp_month,
        exp_year=original_card.exp_year + 1,
        status="ACTIVE",
        is_active=True,
        is_virtual=True,
    )
    db_session.add(replacement)
    db_session.flush()
    replacement_card_id = replacement.id
    replacement_card_token = replacement.card_token
    fraud_alert = FraudAlert(
        customer_id=user.id,
        auth_provider_uid=user.auth_provider_uid,
        credit_account_id=cred_acc.id,
        card_id=original_card.id,
        card_last_four=original_card.last_four,
        message_thread_id="thread-reset-fraud",
        suspicious_authorization_ids=[],
        suspicious_transactions=[],
        replacement_card_id=replacement.id,
        triage_message_thread_id="thread-reset-fraud",
        triage_message_id="message-reset-fraud",
    )
    db_session.add(fraud_alert)
    db_session.flush()
    db_session.add(
        FraudCaseAction(
            fraud_alert_id=fraud_alert.id,
            action_type="FRAUD_CASE_TRIAGED",
            status="SUCCEEDED",
            idempotency_key="reset-fraud-flow",
            request_payload={},
            result_payload={},
        )
    )
    db_session.add(
        UserSecureMessage(
            message_id="message-reset-fraud",
            user_id=user.id,
            sender="bank",
            category="Fraud Alert",
            message="Fraud case pending review.",
            thread_id="thread-reset-fraud",
        )
    )
    db_session.add(
        UserSecureMessage(
            message_id="message-reset-pending-support",
            user_id=user.id,
            sender="bank",
            category="General",
            message="Pending support reply.",
            thread_id="thread-reset-support",
            is_user_read=False,
        )
    )
    db_session.commit()

    reset_response = await async_client.post("/api/v1/simulation/reset-my-demo")

    assert reset_response.status_code == status.HTTP_200_OK
    cards = db_session.query(IssuedCard).filter(IssuedCard.account_id == cred_acc.id).all()
    assert len(cards) == 1
    reset_card = cards[0]
    assert reset_card.id != original_card_id
    assert reset_card.id != replacement_card_id
    assert reset_card.card_token != original_card_token
    assert reset_card.card_token != replacement_card_token
    assert reset_card.status == "ACTIVE"
    assert reset_card.is_active is True
    assert reset_card.is_virtual is False
    assert db_session.query(FraudAlert).filter(FraudAlert.customer_id == user.id).count() == 0
    assert db_session.query(FraudCaseAction).count() == 0
    assert db_session.query(UserSecureMessage).filter(UserSecureMessage.thread_id == "thread-reset-fraud").count() == 0
    assert db_session.query(UserSecureMessage).filter(UserSecureMessage.thread_id == "thread-reset-support").count() == 0
    reset_auths = db_session.query(TransactionAuthorization).filter(TransactionAuthorization.account_id == cred_acc.id).all()
    assert len(reset_auths) >= 2
    assert {auth.card_id for auth in reset_auths} == {reset_card.id}

@pytest.mark.asyncio
async def test_reset_my_demo_not_found(async_client, db_session):
    global mock_claims
    mock_claims = {"sub": "non-existent-uid", "email": "missing@google.com"}
    
    # Reset without provisioning first -> Not Found
    response = await async_client.post("/api/v1/simulation/reset-my-demo")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "No seeded demo profile found" in response.json()["detail"]

@pytest.mark.asyncio
@respx.mock
async def test_simulate_surge_success(async_client, db_session):
    global mock_claims
    mock_claims = {"sub": "presenter-1", "email": "presenter.one@google.com"}
    
    # 1. Provision profile first
    prov_resp = await async_client.post("/api/v1/simulation/provision-my-demo")
    assert prov_resp.status_code == status.HTTP_201_CREATED
    
    # 2. Mock the data-generator surge route
    from services.simulation import DATA_GENERATOR_URL
    surge_route = respx.post(f"{DATA_GENERATOR_URL}/simulate-surge").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "SUCCESS",
                "message": "Simulation surge completed against active card pool.",
                "active_cards_count": 1,
                "swipes_attempted": 50,
                "authorizations_created": 50,
                "settlements_created": 40,
                "reversals_created": 5,
                "declines": 0,
                "failures": 0,
            },
        )
    )
    
    # 3. Call surge proxy endpoint
    response = await async_client.post("/api/v1/simulation/surge")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "SUCCESS"
    
    # 4. Assert data-generator received the active-card payload
    assert surge_route.called
    payload = surge_route.calls.last.request.read().decode()
    data = httpx.Response(200, content=payload).json()
    assert "active_cards" in data
    assert len(data["active_cards"]) >= 1
    assert data["active_cards"][0]["card_token"].startswith("tok_visa_")


@pytest.mark.asyncio
@respx.mock
async def test_simulate_surge_returns_accepted_when_generator_response_times_out(async_client, db_session):
    global mock_claims
    mock_claims = {"sub": "presenter-accepted", "email": "presenter.accepted@google.com"}

    prov_resp = await async_client.post("/api/v1/simulation/provision-my-demo")
    assert prov_resp.status_code == status.HTTP_201_CREATED

    from services.simulation import DATA_GENERATOR_URL
    respx.post(f"{DATA_GENERATOR_URL}/simulate-surge").mock(side_effect=httpx.ReadTimeout("timed out"))

    response = await async_client.post("/api/v1/simulation/surge")

    assert response.status_code == status.HTTP_202_ACCEPTED
    data = response.json()
    assert data["status"] == "ACCEPTED"
    assert "accepted" in data["message"].lower()


@pytest.mark.asyncio
@respx.mock
async def test_plan_generation_scenario_proxies_to_data_generator(async_client, db_session):
    del db_session
    global mock_claims
    mock_claims = {"sub": "scenario-planner", "email": "scenario.planner@google.com"}

    from services.simulation import DATA_GENERATOR_URL
    scenario_route = respx.post(f"{DATA_GENERATOR_URL}/scenarios/plan").mock(
        return_value=httpx.Response(
            200,
            json={
                "scenario_id": "scenario-test-plan",
                "scenario_type": "cnp_gift_card_campaign",
                "mode": "dry_run",
                "timeline": [],
                "personas": [],
                "behavior_policies": [],
                "expected_validations": [],
                "limits": {"max_customers": 1, "max_cards": 1, "max_authorizations": 10, "max_settlements": 10, "max_duration_seconds": 120, "max_fraud_events": 10},
                "seed": 1841,
                "template_version": "test",
                "planner_version": "test",
                "goal": "Create a gift card fraud campaign.",
            },
        )
    )

    response = await async_client.post(
        "/api/v1/simulation/scenarios/plan",
        json={
            "goal": "Create a gift card fraud campaign.",
            "scenario_type": "cnp_gift_card_campaign",
            "mode": "dry_run",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["scenario_id"] == "scenario-test-plan"
    assert scenario_route.called


@pytest.mark.asyncio
@respx.mock
async def test_execute_generation_scenario_attaches_eligible_cards(async_client, db_session):
    global mock_claims
    mock_claims = {"sub": "scenario-executor", "email": "scenario.executor@google.com"}

    prov_resp = await async_client.post("/api/v1/simulation/provision-my-demo")
    assert prov_resp.status_code == status.HTTP_201_CREATED
    provision_user_suite(db_session, "regular.scenario.customer@example.com", "regular-scenario-customer")

    from services.simulation import DATA_GENERATOR_URL
    scenario_route = respx.post(f"{DATA_GENERATOR_URL}/scenarios/execute").mock(
        return_value=httpx.Response(
            200,
            json={
                "scenario_id": "scenario-test-execute",
                "execution_id": "scenario-exec-test",
                "idempotency_key": "ui-scenario-test",
                "mode": "execute",
                "status": "succeeded",
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T00:00:01Z",
                "planned_events": 1,
                "attempted_events": 1,
                "succeeded_events": 1,
                "skipped_events": 0,
                "failed_events": 0,
                "outcomes": [],
                "steps": [],
            },
        )
    )

    response = await async_client.post(
        "/api/v1/simulation/scenarios/execute",
        json={
            "plan": {
                "scenario_id": "scenario-test-execute",
                "scenario_type": "cnp_gift_card_campaign",
                "mode": "dry_run",
                "seed": 1841,
                "template_version": "test",
                "planner_version": "test",
                "goal": "Execute a gift card fraud campaign.",
                "personas": [],
                "behavior_policies": [],
                "timeline": [],
                "expected_validations": [],
                "limits": {"max_customers": 1, "max_cards": 1, "max_authorizations": 10, "max_settlements": 10, "max_duration_seconds": 120, "max_fraud_events": 10},
            },
            "mode": "execute",
            "idempotency_key": "ui-scenario-test",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    assert scenario_route.called
    forwarded = httpx.Response(200, content=scenario_route.calls.last.request.read()).json()
    assert forwarded["default_card_tokens"]
    assert forwarded["default_card_tokens"][0].startswith("tok_visa_")

@pytest.mark.asyncio
@patch("services.messaging.messaging.send")
@patch("services.messaging.messaging.send_each_for_multicast")
@patch("services.messaging.identity_repo.get_device_tokens_for_customer")
async def test_inject_anomaly_success(mock_get_tokens, mock_send_multicast, mock_send, async_client, db_session):
    global mock_claims
    mock_claims = {"sub": "presenter-2", "email": "presenter.two@google.com"}
    mock_get_tokens.return_value = ["device_token_xyz"]
    mock_send.return_value = "topic-message-id"
    mock_batch = MagicMock()
    mock_batch.success_count = 1
    mock_batch.failure_count = 0
    mock_send_multicast.return_value = mock_batch
    
    # 1. Provision profile first
    prov_resp = await async_client.post("/api/v1/simulation/provision-my-demo")
    assert prov_resp.status_code == status.HTTP_201_CREATED
    
    # 2. Call inject-anomaly
    response = await async_client.post("/api/v1/simulation/inject-anomaly")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ANOMALY_INJECTED"
    assert data["injected_swipes_count"] == 5
    assert data["flagged_authorizations_count"] == 5
    assert data["superseded_open_alerts_count"] == 0
    assert data["total_fraud_cents"] == 585399
    assert data["fraud_alert_id"]
    assert data["secure_message_thread_id"]
    
    # 3. Verify in database
    from models.credit_card import TransactionAuthorization
    from models.identity import UserSecureMessage
    auths = db_session.query(TransactionAuthorization).filter(TransactionAuthorization.merchant_name == "TARGET.COM GIFT CARDS").all()
    assert len(auths) == 1
    anomaly_auths = {
        auth.merchant_name: auth.merchant_category_code
        for auth in db_session.query(TransactionAuthorization)
        .filter(TransactionAuthorization.merchant_name.in_([
            "GAME*TEST TOKEN ONLINE",
            "APPLE.COM*ONLINE",
            "BEST BUY*MKTPLACE",
            "RAZER GOLD GIFT CARD",
            "TARGET.COM GIFT CARDS",
        ]))
        .all()
    }
    assert anomaly_auths == {
        "GAME*TEST TOKEN ONLINE": "5817",
        "APPLE.COM*ONLINE": "5816",
        "BEST BUY*MKTPLACE": "5732",
        "RAZER GOLD GIFT CARD": "5947",
        "TARGET.COM GIFT CARDS": "5311",
    }
    fraud_alert = db_session.query(FraudAlert).filter(FraudAlert.id == data["fraud_alert_id"]).first()
    assert fraud_alert is not None
    assert fraud_alert.status == "OPEN"
    assert fraud_alert.auth_provider_uid == "presenter-2"
    assert len(fraud_alert.suspicious_authorization_ids) == 5
    assert len(fraud_alert.suspicious_transactions) == 5
    assert all(txn["authorization_id"] for txn in fraud_alert.suspicious_transactions)
    suspicious_auths = db_session.query(TransactionAuthorization).filter(
        TransactionAuthorization.id.in_(fraud_alert.suspicious_authorization_ids)
    ).all()
    assert all(auth.fraud_risk_score and auth.fraud_risk_score > 0 for auth in suspicious_auths)
    fraud_decisions = db_session.query(FraudModelDecision).filter(
        FraudModelDecision.authorization_id.in_(fraud_alert.suspicious_authorization_ids)
    ).all()
    assert len(fraud_decisions) == 5
    assert sum(decision.score >= 70 for decision in fraud_decisions) == 4
    assert all(decision.reason_codes == ["SIMULATED_FRAUD_ANOMALY"] for decision in fraud_decisions)
    assert all(decision.model_version == "targeted-fraud-simulation-v1" for decision in fraud_decisions)
    with patch(
        "services.cdc_monitoring.CdcMonitoringService.get_cached_datastream_metrics",
        return_value={"status": "SUCCESS"},
    ), patch(
        "services.cdc_monitoring.CdcMonitoringService.get_cached_cdc_status",
        return_value={"status": "SUCCESS"},
    ), patch(
        "services.cdc_monitoring.CdcMonitoringService.get_operational_stream_metrics",
        return_value={},
    ):
        monitor_response = await async_client.get(
            "/api/v1/simulation/operations-summary?window_minutes=15"
        )
    assert monitor_response.status_code == status.HTTP_200_OK
    monitor_impact = monitor_response.json()["impact"]
    assert monitor_impact["high_risk_transactions"] == 4
    assert monitor_impact["peak_risk_score"] == 91
    assert monitor_impact["rules_triggered"] == 1
    account_after_injection = db_session.query(CreditAccount).filter(CreditAccount.id == fraud_alert.credit_account_id).first()
    pending_sum = sum(auth.transaction_amount_cents for auth in db_session.query(TransactionAuthorization).filter(
        TransactionAuthorization.account_id == fraud_alert.credit_account_id,
        TransactionAuthorization.status == "PENDING",
    ).all())
    assert account_after_injection.available_credit_cents == max(
        0,
        min(
            account_after_injection.credit_limit_cents,
            account_after_injection.credit_limit_cents - account_after_injection.cleared_balance_cents - pending_sum,
        ),
    )

    fraud_created_event = db_session.query(AuditOutbox).filter(AuditOutbox.event_type == "FRAUD_ALERT_CREATED").order_by(AuditOutbox.created_at.desc()).first()
    fraud_notified_event = db_session.query(AuditOutbox).filter(AuditOutbox.event_type == "FRAUD_ALERT_CUSTOMER_NOTIFIED").order_by(AuditOutbox.created_at.desc()).first()
    assert fraud_created_event is not None
    assert fraud_notified_event is not None
    assert data["fraud_alert_id"] in fraud_created_event.payload
    assert data["fraud_alert_id"] in fraud_notified_event.payload

    user = db_session.query(User).filter(User.auth_provider_uid == "presenter-2").first()
    secure_messages = db_session.query(UserSecureMessage).filter(
        UserSecureMessage.user_id == user.id,
        UserSecureMessage.thread_id == data["secure_message_thread_id"],
    ).all()
    assert len(secure_messages) == 1
    assert "credit card ending in" in secure_messages[0].message.lower()
    assert "/support/voice?entry=fraud-alert" in secure_messages[0].message

    push_message = mock_send_multicast.call_args.args[0]
    assert push_message.data["title"] == "Fraud alert: review recent card activity"
    assert push_message.data["thread_id"] == data["secure_message_thread_id"]
    assert push_message.data["entry"] == "fraud-alert"

    voice_context_response = await async_client.get("/credit-card/voice/context")
    assert voice_context_response.status_code == status.HTTP_200_OK
    voice_context = voice_context_response.json()
    assert voice_context["has_active_fraud_alert"] is True
    assert voice_context["fraud_alert"]["fraud_alert_id"] == data["fraud_alert_id"]
    assert voice_context["fraud_alert"]["card_last_four"]
    assert "active fraud alert" in voice_context["fraud_alert"]["summary"].lower()

    mock_claims = {"sub": "voice-agent-sa", "email": "support.agent@google.com"}
    support_context_response = await async_client.get(
        "/credit-card/voice/context",
        headers={"x-target-customer-id": "presenter-2"},
    )
    assert support_context_response.status_code == status.HTTP_200_OK
    support_voice_context = support_context_response.json()
    assert support_voice_context["has_active_fraud_alert"] is True
    assert support_voice_context["fraud_alert"]["fraud_alert_id"] == data["fraud_alert_id"]

    mock_claims = {"sub": "presenter-2", "email": "presenter.two@google.com"}
    acknowledge_response = await async_client.post("/credit-card/fraud-alert/acknowledge")
    assert acknowledge_response.status_code == status.HTTP_200_OK
    acknowledged = acknowledge_response.json()
    assert acknowledged["success"] is True
    assert acknowledged["fraud_alert"]["status"] == "RESOLVED_CUSTOMER_RECOGNIZED"


@pytest.mark.asyncio
@patch("services.messaging.messaging.send")
@patch("services.messaging.messaging.send_each_for_multicast")
@patch("services.messaging.identity_repo.get_device_tokens_for_customer")
async def test_inject_anomaly_supersedes_prior_open_simulation_alert(mock_get_tokens, mock_send_multicast, mock_send, async_client, db_session):
    global mock_claims
    mock_claims = {"sub": "presenter-repeat", "email": "presenter.repeat@google.com"}
    mock_get_tokens.return_value = ["device_token_xyz"]
    mock_send.return_value = "topic-message-id"
    mock_batch = MagicMock()
    mock_batch.success_count = 1
    mock_batch.failure_count = 0
    mock_send_multicast.return_value = mock_batch

    provision_response = await async_client.post("/api/v1/simulation/provision-my-demo")
    assert provision_response.status_code == status.HTTP_201_CREATED

    first_response = await async_client.post("/api/v1/simulation/inject-anomaly")
    assert first_response.status_code == status.HTTP_200_OK
    first_alert_id = first_response.json()["fraud_alert_id"]

    second_response = await async_client.post("/api/v1/simulation/inject-anomaly")
    assert second_response.status_code == status.HTTP_200_OK
    second_data = second_response.json()

    assert second_data["fraud_alert_id"] != first_alert_id
    assert second_data["injected_swipes_count"] == 5
    assert second_data["flagged_authorizations_count"] == 5
    assert second_data["superseded_open_alerts_count"] == 1

    first_alert = db_session.query(FraudAlert).filter(FraudAlert.id == first_alert_id).first()
    second_alert = db_session.query(FraudAlert).filter(FraudAlert.id == second_data["fraud_alert_id"]).first()
    assert first_alert.status == "SUPERSEDED_BY_NEW_SIMULATION"
    assert first_alert.resolved_at is not None
    assert second_alert.status == "OPEN"
    assert len(second_alert.suspicious_authorization_ids) == 5
    assert db_session.query(FraudAlert).filter(
        FraudAlert.auth_provider_uid == "presenter-repeat",
        FraudAlert.status == "OPEN",
    ).count() == 1

    superseded_event = db_session.query(AuditOutbox).filter_by(event_type="FRAUD_ALERT_SUPERSEDED").first()
    assert superseded_event is not None


@pytest.mark.asyncio
async def test_get_active_cards_success(async_client, db_session):
    headers = {"X-Card-Network-Token": "switch-secret-key-12345"}
    res = await async_client.get("/api/v1/credit-card/active-cards", headers=headers)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert "active_cards" in data
    assert "count" in data


@pytest.mark.asyncio
async def test_get_active_cards_marks_demo_script_accounts_ineligible_for_generator(async_client, db_session):
    global mock_claims

    mock_claims = {"sub": "presenter-uid", "email": "demo.presenter@gcp.solutions"}
    presenter_resp = await async_client.post("/api/v1/simulation/provision-my-demo")
    assert presenter_resp.status_code == status.HTTP_201_CREATED

    provision_user_suite(db_session, "vip.persona@nova.horizon.test", "vip-uid")
    provision_user_suite(db_session, "regular.customer@example.com", "customer-uid")

    headers = {"X-Card-Network-Token": "switch-secret-key-12345"}
    res = await async_client.get("/api/v1/credit-card/active-cards", headers=headers)
    assert res.status_code == status.HTTP_200_OK

    cards_by_name = {card["cardholder_name"]: card for card in res.json()["active_cards"]}

    presenter_card = cards_by_name["Demo Presenter"]
    assert presenter_card["is_presenter_account"] is True
    assert presenter_card["is_demo_script_account"] is True
    assert presenter_card["generator_eligible"] is False

    vip_card = cards_by_name["Vip Persona"]
    assert vip_card["is_vip_demo_account"] is True
    assert vip_card["is_demo_script_account"] is True
    assert vip_card["generator_eligible"] is False

    regular_card = cards_by_name["Regular Customer"]
    assert regular_card["is_demo_script_account"] is False
    assert regular_card["generator_eligible"] is True


@pytest.mark.asyncio
async def test_ensure_vip_mexico_leaders_tops_configured_vips_idempotently(async_client, db_session, respx_mock):
    global mock_claims
    mock_claims = {"sub": "leaderboard-presenter", "email": "leaderboard.presenter@google.com"}

    provision_user_suite(db_session, "larry.page@nova.horizon.test", "vip-larry")
    provision_user_suite(db_session, "sergey.brin@nova.horizon.test", "vip-sergey")
    provision_user_suite(db_session, "generic.customer@example.com", "generic-customer")

    now = datetime.datetime.now(datetime.timezone.utc)
    generic_user = db_session.query(User).filter_by(email="generic.customer@example.com").one()
    latest_address = (
        db_session.query(UserAddress)
        .filter_by(user_id=generic_user.id, is_primary=True)
        .order_by(UserAddress.created_at.desc(), UserAddress.id.desc())
        .first()
    )
    for index in range(2):
        db_session.add(
            UserAddress(
                id=uuid.uuid4(),
                user_id=generic_user.id,
                address_type="PREVIOUS",
                is_primary=True,
                street_line_1=f"{index + 1}00 Previous Street",
                city=latest_address.city,
                state=latest_address.state,
                postal_code=latest_address.postal_code,
                country_code=latest_address.country_code,
                created_at=now - datetime.timedelta(days=index + 2),
            )
        )
    generic_account = db_session.query(CreditAccount).filter_by(customer_id=generic_user.id, status="ACTIVE").one()
    generic_card = db_session.query(IssuedCard).filter_by(account_id=generic_account.id, status="ACTIVE").one()
    authorization_id = uuid.uuid4()
    db_session.add(
        TransactionAuthorization(
            id=authorization_id,
            card_id=generic_card.id,
            account_id=generic_account.id,
            transaction_amount_cents=400_000,
            billing_amount_cents=400_000,
            status="SETTLED",
            decline_reason="NONE",
            auth_code="444444",
            retrieval_reference_number="GENMEX000001",
            card_network="VISA",
            merchant_category_code="7011",
            merchant_name="GENERIC MEXICO RESORT [MEX]",
            transaction_channel="CARD_PRESENT",
            entry_mode="CHIP",
            merchant_country_code="MEX",
            merchant_city="Cancun",
            merchant_region="ROO",
            fraud_risk_score=0,
            created_at=now - datetime.timedelta(hours=1),
            expires_at=now + datetime.timedelta(days=7),
        )
    )
    db_session.add(
        PostedTransaction(
            id=uuid.uuid4(),
            account_id=generic_account.id,
            authorization_id=authorization_id,
            auth_code="444444",
            retrieval_reference_number="GENMEX000001",
            amount_cents=-400_000,
            description="GENERIC MEXICO RESORT [MEX]",
            posted_at=now,
        )
    )
    db_session.commit()

    captured_targets = []

    def generate_top_offs(request):
        payload = json.loads(request.content)
        captured_targets.extend(payload["targets"])
        total_added_cents = 0
        for index, target in enumerate(payload["targets"]):
            card = db_session.query(IssuedCard).filter_by(card_token=target["card_token"]).one()
            account = db_session.query(CreditAccount).filter_by(id=card.account_id).one()
            amount_cents = target["top_off_cents"]
            authorization_id = uuid.uuid4()
            rrn = f"VIPT{index:08d}"
            db_session.add(
                TransactionAuthorization(
                    id=authorization_id,
                    card_id=card.id,
                    account_id=account.id,
                    transaction_amount_cents=amount_cents,
                    billing_amount_cents=amount_cents,
                    status="SETTLED",
                    decline_reason="NONE",
                    auth_code=f"{index:06d}",
                    retrieval_reference_number=rrn,
                    card_network="VISA",
                    merchant_category_code="7011",
                    merchant_name="GENERATOR MEXICO TOP OFF [MEX]",
                    transaction_channel="CARD_PRESENT",
                    entry_mode="CHIP",
                    merchant_country_code="MEX",
                    merchant_city="Cancun",
                    merchant_region="ROO",
                    fraud_risk_score=0,
                    created_at=now,
                    expires_at=now + datetime.timedelta(days=7),
                )
            )
            db_session.add(
                PostedTransaction(
                    id=uuid.uuid4(),
                    account_id=account.id,
                    authorization_id=authorization_id,
                    auth_code=f"{index:06d}",
                    retrieval_reference_number=rrn,
                    amount_cents=-amount_cents,
                    description="GENERATOR MEXICO TOP OFF [MEX]",
                    posted_at=now,
                )
            )
            account.available_credit_cents -= amount_cents
            account.cleared_balance_cents += amount_cents
            total_added_cents += amount_cents
        db_session.commit()
        return httpx.Response(
            status.HTTP_200_OK,
            json={
                "status": "SUCCESS",
                "customers_topped_off": len(payload["targets"]),
                "transactions_created": len(payload["targets"]),
                "total_added_cents": total_added_cents,
            },
        )

    respx_mock.post("http://localhost:8001/ensure-vip-mexico-leaders").mock(side_effect=generate_top_offs)

    first_response = await async_client.post("/api/v1/simulation/ensure-vip-mexico-leaders")
    assert first_response.status_code == status.HTTP_200_OK
    first_result = first_response.json()
    assert first_result["vip_customers_considered"] == 2
    assert first_result["vip_customers_topped_off"] == 2
    assert first_result["generic_ceiling_cents"] == 400_000
    assert first_result["transactions_created"] == 2
    assert len(captured_targets) == 2

    for vip_email in ("larry.page@nova.horizon.test", "sergey.brin@nova.horizon.test"):
        vip_user = db_session.query(User).filter_by(email=vip_email).one()
        vip_spend = (
            db_session.query(PostedTransaction)
            .join(TransactionAuthorization, TransactionAuthorization.id == PostedTransaction.authorization_id)
            .join(CreditAccount, CreditAccount.id == PostedTransaction.account_id)
            .filter(
                CreditAccount.customer_id == vip_user.id,
                TransactionAuthorization.merchant_country_code == "MEX",
                PostedTransaction.amount_cents < 0,
                PostedTransaction.posted_at >= now - datetime.timedelta(days=14),
            )
            .all()
        )
        assert sum(-transaction.amount_cents for transaction in vip_spend) > 400_000

    second_response = await async_client.post("/api/v1/simulation/ensure-vip-mexico-leaders")
    assert second_response.status_code == status.HTTP_200_OK
    assert second_response.json()["transactions_created"] == 0


@pytest.mark.asyncio
async def test_sse_stream_does_not_hold_request_db_session(async_client):
    async def one_event_stream(token):
        del token
        yield 'data: {"status":"SUCCESS","event_kind":"snapshot"}\n\n'

    def fail_if_route_requests_db():
        raise AssertionError("SSE stream should not allocate a request-scoped DB session")
        yield

    app.dependency_overrides[get_db] = fail_if_route_requests_db
    with patch("routers.simulation.SimulationService.stream_payload", one_event_stream):
        async with async_client.stream("GET", "/api/v1/simulation/stream-sse") as response:
            body = await response.aread()

    assert response.status_code == status.HTTP_200_OK
    assert b'"event_kind":"snapshot"' in body


@pytest.mark.asyncio
async def test_inject_late_fee_and_global_stream(async_client, db_session):
    global mock_claims
    mock_claims = {"sub": "stream-uid", "email": "stream.presenter@google.com"}
    
    # Provision demo
    resp = await async_client.post("/api/v1/simulation/provision-my-demo")
    assert resp.status_code == status.HTTP_201_CREATED
    
    # Inject late fee
    resp_fee = await async_client.post("/api/v1/simulation/inject-late-fee")
    assert resp_fee.status_code == status.HTTP_200_OK
    assert resp_fee.json()["status"] == "LATE_FEE_INJECTED"
    assert resp_fee.json()["amount_cents"] == 3500
    
    # Check global stream
    mocked_stream = {
        "status": "SUCCESS",
        "stream": [
            {
                "id": "AUTH_fee_001",
                "rrn": "FEE_0376d_57",
                "timestamp": "12:00:00",
                "merchant_name": "LATE_FEE",
                "amount_cents": 3500,
                "status": "HOLD (PENDING)",
                "bq_view": "analytics_curated.realtime_spend_velocity",
                "raw_time": 1_720_000_000.0,
            }
        ],
    }
    mocked_metrics = {
        "events_per_minute": 1,
        "authorization_events_per_minute": 1,
        "posted_events_per_minute": 0,
        "flagged_events_per_minute": 0,
        "latest_event_age_ms": 250,
        "latest_event_timestamp": "2026-07-06T12:00:00+00:00",
        "recent_buffered_events": 1,
    }
    mocked_cdc_metrics = {
        "system_lag_ms": 0,
        "data_freshness_ms": 0,
        "total_bytes_processed": 0,
        "active_anomalies": 0,
        "status": "SUCCESS",
    }

    with patch("services.simulation.CdcMonitoringService.get_operational_stream", return_value=mocked_stream), \
         patch("services.simulation.CdcMonitoringService.get_operational_stream_metrics", return_value=mocked_metrics), \
         patch("services.simulation.CdcMonitoringService.get_cached_datastream_metrics", return_value=mocked_cdc_metrics):
        resp_stream = await async_client.get("/api/v1/simulation/global-stream")
    assert resp_stream.status_code == status.HTTP_200_OK
    data = resp_stream.json()
    assert data["status"] == "SUCCESS"
    assert "stream" in data
    assert len(data["stream"]) > 0
    merchant_names = [item["merchant_name"] for item in data["stream"]]
    assert "LATE_FEE" in merchant_names


@pytest.mark.asyncio
async def test_operations_summary_accepts_window_parameter(async_client):
    mocked_summary = {
        "status": "SUCCESS",
        "window_minutes": 60,
        "replication_health": {"events_per_minute": 12},
        "impact": {"open_fraud_alerts": 1},
        "event_mix": [],
        "risk_distribution": [],
        "risk_signals": [],
        "scenario_impact": [],
        "activity_series": [],
        "transactions": [],
        "system_health": [],
    }

    with patch(
        "routers.simulation.SimulationService.get_operations_monitor_summary",
        return_value=mocked_summary,
    ) as mock_summary:
        response = await async_client.get("/api/v1/simulation/operations-summary?window_minutes=60")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["window_minutes"] == 60
    mock_summary.assert_called_once_with(60)
