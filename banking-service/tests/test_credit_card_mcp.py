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
from unittest.mock import MagicMock, patch

from routers.mcp.credit_card import (
    report_lost_stolen_card,
    unfreeze_card,
    reverse_overdraft_fee,
    request_credit_limit_increase
)
from models.credit_card import Base, FinancialAccount, IssuedCard

@pytest.fixture(autouse=True)
def run_locally_env(monkeypatch):
    """Enforce local running environment variables for tests."""
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("ENABLE_DEMO_FALLBACK", "true")

@pytest.fixture
def db_session(monkeypatch):
    """Yields an isolated, in-memory SQLite database session patched into all routers."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    Base.metadata.create_all(bind=engine)
    
    # Patch SessionLocal imports inside routers to bind to our in-memory DB
    monkeypatch.setattr("routers.mcp.utils.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("routers.mcp.credit_card.SessionLocal", TestingSessionLocal)
    
    db = TestingSessionLocal()
    from services.seeding_service import perform_algorithmic_seeding
    perform_algorithmic_seeding(db)
    
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)

@pytest.mark.asyncio
@patch("routers.mcp.utils.validate_firebase_token")
@patch("routers.mcp.credit_card.send_session_event")
async def test_report_lost_stolen_card_success(mock_send_event, mock_validate_token, db_session):
    """Verify card replacement blocks the active card and pushes WebSocket notification."""
    mock_validate_token.return_value = MagicMock(claims={"sub": "jane.doe@example.com", "email": "customer@example.com"})
    
    mock_ctx = MagicMock()
    result = await report_lost_stolen_card(
        account_id="88888888-8888-4888-8888-999999999999",
        assertion_token="valid-token",
        ctx=mock_ctx
    )
    
    assert result["success"] is True
    assert "Card reported as lost" in result["message"]
    assert "LST-" in result["confirmation_number"]
    
    # Verify DB status update
    card = db_session.query(IssuedCard).filter_by(id="11111111-1111-4111-8111-222222222222").first()
    assert card.status == "BLOCKED"
    
    # Verify WebSocket OOB sync event was dispatched
    mock_send_event.assert_called_once()
    args, kwargs = mock_send_event.call_args
    assert args[0] == "session-jane.doe@example.com"
    assert args[1]["type"] == "CARD_STATUS"
    assert args[1]["status"] == "BLOCKED"

@pytest.mark.asyncio
@patch("routers.mcp.utils.validate_firebase_token")
async def test_report_lost_stolen_card_unauthorized(mock_validate_token):
    """Verify signature verification failure blocks card replacement."""
    mock_validate_token.side_effect = ValueError("Invalid signature")
    
    mock_ctx = MagicMock()
    with pytest.raises(PermissionError, match="Invalid assertion token"):
        await report_lost_stolen_card(
            account_id="88888888-8888-4888-8888-999999999999",
            assertion_token="bad-token",
            ctx=mock_ctx
        )

@pytest.mark.asyncio
@patch("routers.mcp.utils.validate_firebase_token")
async def test_report_lost_stolen_card_bola_prevention(mock_validate_token, monkeypatch, db_session):
    """Verify BOLA prevention blocks replacement when account belongs to customer B."""
    monkeypatch.setenv("ENABLE_DEMO_FALLBACK", "false")
    # Token matches customer-B, but target account 88888888-8888-4888-8888-999999999999 is owned by jane.doe@example.com
    mock_validate_token.return_value = MagicMock(claims={"sub": "customer-B", "email": "customerB@example.com"})
    
    mock_ctx = MagicMock()
    with pytest.raises(ValueError, match="No financial account found"):
        await report_lost_stolen_card(
            account_id="88888888-8888-4888-8888-999999999999",
            assertion_token="token-customerB",
            ctx=mock_ctx
        )

@pytest.mark.asyncio
@patch("routers.mcp.utils.validate_firebase_token")
@patch("routers.mcp.credit_card.send_session_event")
async def test_unfreeze_card_success(mock_send_event, mock_validate_token, db_session):
    """Verify unfreeze_card restores a blocked card to ACTIVE and dispatches OOB sync."""
    mock_validate_token.return_value = MagicMock(claims={"sub": "jane.doe@example.com", "email": "customer@example.com"})
    
    # First block the card
    card = db_session.query(IssuedCard).filter_by(account_id="88888888-8888-4888-8888-999999999999").first()
    card.status = "BLOCKED"
    db_session.commit()
    
    mock_ctx = MagicMock()
    response = await unfreeze_card(
        account_id="88888888-8888-4888-8888-999999999999",
        assertion_token="valid-token",
        ctx=mock_ctx
    )
    
    assert response["success"] is True
    assert "successfully unblocked" in response["message"]
    
    db_session.refresh(card)
    assert card.status == "ACTIVE"
    mock_send_event.assert_called_once()


@pytest.mark.asyncio
@patch("routers.mcp.utils.validate_firebase_token")
@patch("routers.mcp.credit_card.send_session_event")
async def test_reverse_overdraft_fee_success(mock_send_event, mock_validate_token, db_session):
    """Verify overdraft fee reversal resolves account ledger credit and resets available balance."""
    mock_validate_token.return_value = MagicMock(claims={"sub": "jane.doe@example.com", "email": "customer@example.com"})
    
    # Fetch pre-reversal cleared balance ($180.44 -> 18044 cents)
    account = db_session.query(FinancialAccount).filter_by(id="88888888-8888-4888-8888-999999999999").first()
    original_balance = account.cleared_balance_cents
    
    mock_ctx = MagicMock()
    result = await reverse_overdraft_fee(
        account_id="88888888-8888-4888-8888-999999999999",
        assertion_token="valid-token",
        ctx=mock_ctx
    )
    
    assert result["success"] is True
    assert "reversed" in result["message"]
    assert result["amount_reversed"] == 35.0  # $35.00 reversed
    
    # Assert ledger balance updated in db (debt decreased by $35.00 -> 3500 cents)
    db_session.refresh(account)
    assert account.cleared_balance_cents == original_balance - 3500
    
    # Assert OOB WebSocket sync dispatched
    mock_send_event.assert_called_once()
    args, kwargs = mock_send_event.call_args
    assert args[0] == "session-jane.doe@example.com"
    assert args[1]["type"] == "FEE_REVERSED"

@pytest.mark.asyncio
@patch("routers.mcp.utils.validate_firebase_token")
async def test_reverse_overdraft_fee_annual_limit_violation(mock_validate_token, db_session):
    """Verify that a second reversal in the same calendar year is rejected."""
    mock_validate_token.return_value = MagicMock(claims={"sub": "jane.doe@example.com", "email": "customer@example.com"})
    mock_ctx = MagicMock()
    
    # Apply first reversal
    result1 = await reverse_overdraft_fee(
        account_id="88888888-8888-4888-8888-999999999999",
        assertion_token="valid-token",
        ctx=mock_ctx
    )
    assert result1["success"] is True
    
    # Apply second reversal (should trigger annual policy cap)
    result2 = await reverse_overdraft_fee(
        account_id="88888888-8888-4888-8888-999999999999",
        assertion_token="valid-token",
        ctx=mock_ctx
    )
    
    assert result2["success"] is False
    assert "Already used annual reversal limit" in result2["message"]

@pytest.mark.asyncio
@patch("routers.mcp.utils.validate_firebase_token")
@patch("routers.mcp.credit_card.send_session_event")
async def test_request_credit_limit_increase_success(mock_send_event, mock_validate_token, db_session):
    """Verify underwriting auto-approval for limits within reasonable bounds (<2x current)."""
    mock_validate_token.return_value = MagicMock(claims={"sub": "jane.doe@example.com", "email": "customer@example.com"})
    
    mock_ctx = MagicMock()
    result = await request_credit_limit_increase(
        account_id="88888888-8888-4888-8888-999999999999",
        assertion_token="valid-token",
        requested_limit=15000.0,  # $15,000 (current limit is $10,000, which is < 2x increase)
        ctx=mock_ctx
    )
    
    assert result["success"] is True
    assert "limit increase approved" in result["message"].lower()
    assert result["new_limit"] == 15000.0
    
    # Verify db updated
    account = db_session.query(FinancialAccount).filter_by(id="88888888-8888-4888-8888-999999999999").first()
    assert account.credit_limit_cents == 1500000

    # Assert OOB WebSocket sync dispatched
    mock_send_event.assert_called_once()
    args, kwargs = mock_send_event.call_args
    assert args[0] == "session-jane.doe@example.com"
    assert args[1]["type"] == "LIMIT_UPDATED"

@pytest.mark.asyncio
@patch("routers.mcp.utils.validate_firebase_token")
async def test_request_credit_limit_increase_denied(mock_validate_token, db_session):
    """Verify underwriting rejection when requested limit exceeds double the current limit (>2x)."""
    mock_validate_token.return_value = MagicMock(claims={"sub": "jane.doe@example.com", "email": "customer@example.com"})
    
    mock_ctx = MagicMock()
    result = await request_credit_limit_increase(
        account_id="88888888-8888-4888-8888-999999999999",
        assertion_token="valid-token",
        requested_limit=25000.0,  # $25,000 (current limit is $10,000, 25k is > 2x current limit)
        ctx=mock_ctx
    )
    
    assert result["success"] is False
    assert "Request denied due to credit history" in result["message"]


@pytest.mark.asyncio
@patch("routers.mcp.utils.validate_firebase_token")
@patch("routers.mcp.credit_card.send_session_event")
async def test_report_lost_stolen_card_optional_account_id(mock_send_event, mock_validate_token, db_session):
    """Verify that card replacement successfully resolves the default account when account_id is omitted."""
    mock_validate_token.return_value = MagicMock(claims={"sub": "jane.doe@example.com", "email": "customer@example.com"})
    
    mock_ctx = MagicMock()
    result = await report_lost_stolen_card(
        account_id=None,
        assertion_token="valid-token",
        ctx=mock_ctx
    )
    
    assert result["success"] is True
    assert "Card reported as lost" in result["message"]
    assert "LST-" in result["confirmation_number"]
