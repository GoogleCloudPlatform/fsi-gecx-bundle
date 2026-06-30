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
from models.kyc import KYCRecord, UserCreditProfile
from models.origination import Account
from models.credit_card import CreditAccount, IssuedCard, PostedTransaction

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
    assert cred_acc.available_credit_cents == cred_acc.credit_limit_cents - cred_acc.cleared_balance_cents
    
    # Check historical swipes (should have exactly 12 posted transactions)
    swipes = db_session.query(PostedTransaction).filter(PostedTransaction.account_id == cred_acc.id).all()
    assert len(swipes) == 12

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
    assert response2.json()["detail"] == "Profile already provisioned."

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
    
    # Verify balances reset to default
    cred_acc = db_session.query(CreditAccount).filter(CreditAccount.customer_id == user_id).first()
    assert cred_acc.cleared_balance_cents == 0
    assert cred_acc.available_credit_cents == cred_acc.credit_limit_cents
    
    swipes_count = db_session.query(PostedTransaction).filter(PostedTransaction.account_id == cred_acc.id).count()
    assert swipes_count == 0
    
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
