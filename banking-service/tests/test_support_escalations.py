import pytest
from fastapi import status
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from main import app
from utils.database import Base, get_db
from models.support import Escalation

# In-memory SQLite with StaticPool for thread-safe session sharing
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@pytest.fixture(name="db_session", autouse=True)
def fixture_db_session():
    # Create tables
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    
    # Override FastAPI get_db dependency
    def override_get_db():
        try:
            yield db
        finally:
            pass
            
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        yield db
    finally:
        db.close()
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=test_engine)

@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

@pytest.mark.asyncio
async def test_list_pending_escalations_empty(async_client):
    """Verify list escalations returns an empty array when none exist."""
    response = await async_client.get("/support/escalations")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []

@pytest.mark.asyncio
async def test_list_pending_escalations_success(async_client, db_session):
    """Verify list escalations returns correct pending rows in order."""
    esc1 = Escalation(
        room_name="room-test-1",
        customer_id="cust-1",
        reason="Limit Dispute",
        status="PENDING",
        transcript=[{"author": "user", "text": "hello"}]
    )
    esc2 = Escalation(
        room_name="room-test-2",
        customer_id="cust-2",
        reason="Fraud Lock",
        status="PENDING",
        transcript=[]
    )
    # This one should be ignored since status is already ACCEPTED
    esc3 = Escalation(
        room_name="room-test-3",
        customer_id="cust-3",
        reason="Other",
        status="ACCEPTED",
        transcript=[]
    )
    db_session.add_all([esc1, esc2, esc3])
    db_session.commit()

    response = await async_client.get("/support/escalations")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 2
    # Ordered desc by creation, so esc2 should be first
    assert data[0]["room_name"] == "room-test-2"
    assert data[1]["room_name"] == "room-test-1"
    assert data[1]["transcript"] == [{"author": "user", "text": "hello"}]

@pytest.mark.asyncio
async def test_get_agent_token_success(async_client, db_session):
    """Verify supervisor token generation and DB state updates to ACCEPTED."""
    esc = Escalation(
        room_name="room-test-1",
        customer_id="cust-1",
        reason="Supervisor Takeover",
        status="PENDING",
        transcript=[]
    )
    db_session.add(esc)
    db_session.commit()

    # Pass mock auth bearer token
    headers = {"Authorization": "Bearer supervisor_agent"}
    response = await async_client.post("/support/token?room_name=room-test-1", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "token" in data
    assert data["room_name"] == "room-test-1"
    
    # Assert database state updated
    db_session.refresh(esc)
    assert esc.status == "ACCEPTED"
    assert esc.assigned_to == "supervisor_agent@example.com"

@pytest.mark.asyncio
async def test_get_agent_token_not_found(async_client):
    """Verify requesting token for non-existent room returns 404."""
    headers = {"Authorization": "Bearer supervisor_agent"}
    response = await async_client.post("/support/token?room_name=room-non-existent", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "No active or pending escalation found for this room."
