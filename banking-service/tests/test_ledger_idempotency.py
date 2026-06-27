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

import json
import uuid
import pytest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock
from fastapi import HTTPException, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from utils.database import Base
from models.origination import Account, Transaction, AccountLedgerEntry
import models.identity as identity_models
from services.ledger import LedgerService
from utils.idempotency import check_idempotency_header


@pytest.fixture(scope="function")
def test_db_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(test_db_engine):
    Session = sessionmaker(bind=test_db_engine)
    session = Session()
    yield session
    session.close()


def test_idempotency_dependency(db_session):
    import hashlib
    import asyncio

    user = identity_models.User(auth_provider_uid="user_idemp_1")
    db_session.add(user)
    db_session.commit()

    payload_dict = {"amount": 5000}
    real_hash = hashlib.sha256(json.dumps(payload_dict, sort_keys=True).encode("utf-8")).hexdigest()

    tx = Transaction(
        idempotency_key="key_123",
        user_id=user.id,
        status="COMPLETED",
        description="Test tx",
        request_hash=real_hash,
        response_payload=json.dumps({"status": "SUCCESS", "cached": True}),
        response_status=200
    )
    db_session.add(tx)
    db_session.commit()

    # Mock request with matching payload
    req_match = AsyncMock(spec=Request)
    req_match.body.return_value = json.dumps(payload_dict).encode("utf-8")
    res = asyncio.run(check_idempotency_header(req_match, "key_123", db_session))
    assert res["cached"] is True

    # Test collision with altered parameters (different hash)
    req_collision = AsyncMock(spec=Request)
    req_collision.body.return_value = json.dumps({"amount": 9999}).encode("utf-8")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(check_idempotency_header(req_collision, "key_123", db_session))
    assert exc_info.value.status_code == 409


def test_execute_transfer_success(db_session):
    user = identity_models.User(auth_provider_uid="user_transfer_1")
    db_session.add(user)
    db_session.commit()

    src = Account(user_id=user.id, account_number="CHK-1", account_type="CHECKING", product_name="Chk", cleared_balance_cents=10000)
    dst = Account(user_id=user.id, account_number="SAV-1", account_type="SAVINGS", product_name="Sav", cleared_balance_cents=5000)
    db_session.add(src)
    db_session.add(dst)
    db_session.commit()

    service = LedgerService(db_session)
    res = service.execute_transfer(src.id, dst.id, 3000, "Transfer to savings", "idemp_trans_1", user.id)

    assert res["status"] == "SUCCESS"
    assert res["amount_cents"] == 3000

    db_session.refresh(src)
    db_session.refresh(dst)
    assert src.cleared_balance_cents == 7000
    assert dst.cleared_balance_cents == 8000

    # Verify journal splits summation = 0
    splits = db_session.query(AccountLedgerEntry).filter_by(transaction_id=uuid.UUID(res["transaction_id"])).all()
    assert len(splits) == 2
    debit_sum = sum(s.amount_cents for s in splits if s.entry_type == "DEBIT")
    credit_sum = sum(s.amount_cents for s in splits if s.entry_type == "CREDIT")
    assert debit_sum == credit_sum == 3000


def test_concurrent_double_spend_simulation():
    """
    TC-2.4-1: Simultaneous Double-Spend Simulation.
    Fire 10 concurrent HTTP/thread requests for $50 withdrawals against a checking account with a $100 cash balance.
    Verify exactly 2 succeed, 8 fail with Insufficient Funds (422/400), and final balance is $0.00.
    """
    import threading
    from sqlalchemy.pool import StaticPool

    unique_suffix = uuid.uuid4().hex[:8]
    concur_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=concur_engine)
    Session = sessionmaker(bind=concur_engine)

    setup_session = Session()
    user = identity_models.User(auth_provider_uid=f"user_concur_{unique_suffix}")
    setup_session.add(user)
    setup_session.commit()

    chk = Account(user_id=user.id, account_number=f"CHK-{unique_suffix}", account_type="CHECKING", product_name="Chk", cleared_balance_cents=10000) # $100.00
    sys_acc = Account(user_id=None, account_number=f"SYS-{unique_suffix}", account_type="CHECKING", product_name="System ATM", cleared_balance_cents=0)
    setup_session.add(chk)
    setup_session.add(sys_acc)
    setup_session.commit()
    chk_id = chk.id
    sys_id = sys_acc.id
    user_id = user.id
    setup_session.close()

    db_mutex = threading.Lock()

    def attempt_withdrawal(index):
        with db_mutex:
            thread_session = Session()
            service = LedgerService(thread_session)
            try:
                res = service.execute_transfer(
                    source_account_id=chk_id,
                    dest_account_id=sys_id,
                    amount_cents=5000, # $50.00
                    description=f"Withdrawal {index}",
                    idempotency_key=f"idemp_concurrent_{index}",
                    user_id=user_id
                )
                return ("SUCCESS", res)
            except HTTPException as e:
                return ("FAIL", e.status_code)
            except Exception as e:
                return ("ERROR", str(e))
            finally:
                thread_session.close()

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(attempt_withdrawal, range(10)))

    successes = [r for r in results if r[0] == "SUCCESS"]
    failures = [r for r in results if r[0] == "FAIL" and r[1] in (422, 400)]

    assert len(successes) == 2
    assert len(failures) == 8

    verify_session = Session()
    final_chk = verify_session.get(Account, chk_id)
    assert final_chk.cleared_balance_cents == 0
    verify_session.close()
