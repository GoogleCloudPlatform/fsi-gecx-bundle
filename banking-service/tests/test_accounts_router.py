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

import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from main import app
from utils.database import SessionLocal
from models.origination import Account, AccountLedgerEntry


@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_create_checking_deposit_account_with_funding(async_client):
    """
    TC-2.5-1: Verify opening checking account with initial funding persists account row
    and posts balanced double-entry journal splits against SYSTEM_EXTERNAL_FUNDING.
    """
    db_session = SessionLocal()
    try:
        headers = {"Authorization": "Bearer TEST_USER_123"}
        payload = {
            "account_type": "CHECKING",
            "product_name": "Nova Classic Everyday",
            "member_type": "current",
            "initial_deposit_cents": 10000  # $100.00
        }

        res = await async_client.post("/api/v1/accounts/deposit", json=payload, headers=headers)
        assert res.status_code == 201
        data = res.json()
        assert "account_id" in data
        assert data["status"] == "ACTIVE"

        acc_id = uuid.UUID(data["account_id"])
        acc = db_session.query(Account).filter_by(id=acc_id).first()
        assert acc is not None
        assert acc.cleared_balance_cents == 10000

        acc_splits = db_session.query(AccountLedgerEntry).filter_by(account_id=acc.id).all()
        assert len(acc_splits) >= 1
        tx_id = acc_splits[0].transaction_id

        tx_splits = db_session.query(AccountLedgerEntry).filter_by(transaction_id=tx_id).all()
        assert len(tx_splits) == 2
        debit_sum = sum(s.amount_cents for s in tx_splits if s.entry_type == "DEBIT")
        credit_sum = sum(s.amount_cents for s in tx_splits if s.entry_type == "CREDIT")
        assert debit_sum == credit_sum == 10000
    finally:
        db_session.close()


@pytest.mark.asyncio
async def test_create_savings_deposit_account_no_funding(async_client):
    """
    TC-2.5-2: Verify opening savings account via alias path /accounts/deposit.
    """
    headers = {"Authorization": "Bearer TEST_USER_SAVINGS"}
    payload = {
        "account_type": "SAVINGS",
        "product_name": "Apex High-Yield Reserve",
        "initial_deposit_cents": 0
    }

    res = await async_client.post("/accounts/deposit", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert "account_id" in data
    assert data["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_deposit_account_validation_failure(async_client):
    """
    TC-2.5-3: Verify invalid account_type raises 400.
    """
    headers = {"Authorization": "Bearer TEST_USER_BADTYPE"}
    payload = {
        "account_type": "INVALID_TYPE",
        "product_name": "Bad Product",
        "initial_deposit_cents": 500
    }

    res = await async_client.post("/api/v1/accounts/deposit", json=payload, headers=headers)
    assert res.status_code == 400
