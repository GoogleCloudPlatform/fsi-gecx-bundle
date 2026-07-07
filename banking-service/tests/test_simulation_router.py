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
import respx
import httpx
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
from models.credit_card import CreditAccount, PostedTransaction

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
    accounts = db_session.query(Account).filter(Account.user_id == user.id).all()
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
    
    accounts = db_session.query(Account).filter(Account.user_id == user_id).all()
    for acc in accounts:
        if acc.account_type == "CHECKING":
            assert acc.cleared_balance_cents == 1000000
        elif acc.account_type == "SAVINGS":
            assert acc.cleared_balance_cents == 2000000

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
async def test_inject_anomaly_success(async_client, db_session):
    global mock_claims
    mock_claims = {"sub": "presenter-2", "email": "presenter.two@google.com"}
    
    # 1. Provision profile first
    prov_resp = await async_client.post("/api/v1/simulation/provision-my-demo")
    assert prov_resp.status_code == status.HTTP_201_CREATED
    
    # 2. Call inject-anomaly
    response = await async_client.post("/api/v1/simulation/inject-anomaly")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ANOMALY_INJECTED"
    assert data["injected_swipes_count"] == 4
    assert data["total_fraud_cents"] == 685399
    
    # 3. Verify in database
    from models.credit_card import TransactionAuthorization
    auths = db_session.query(TransactionAuthorization).filter(TransactionAuthorization.merchant_name == "LUXURY BOUTIQUE RIVIERA MAYA [MEX]").all()
    assert len(auths) == 1

@pytest.mark.asyncio
async def test_get_active_cards_success(async_client, db_session):
    headers = {"X-Card-Network-Token": "switch-secret-key-12345"}
    res = await async_client.get("/api/v1/credit-card/active-cards", headers=headers)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert "active_cards" in data
    assert "count" in data

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
                "bq_view": "fsi_lakehouse.v_realtime_spend_velocity",
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
