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

"""Authoritative payment success, retries, and non-mutating rejection."""

import uuid
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from models.money import Money
from models.payment import BillPaymentRequest
from models.identity import User
from models.origination import Account, Transaction, AccountLedgerEntry
from models.credit_card import CreditAccount, PostedTransaction
from models.audit import AuditOutbox
from services.accounts import AccountsService


@pytest.fixture
def payment_suite(db_session):
    user = User(auth_provider_uid="money-payment-test")
    db_session.add(user)
    db_session.flush()
    source = Account(user_id=user.id, account_number="PAY-SOURCE", account_type="CHECKING",
                     product_name="Payment test", product_code=None, currency="USD", cleared_balance_cents=10000)
    card = CreditAccount(customer_id=user.id, product_code="TEST", currency="USD",
                         credit_limit_cents=10000, cleared_balance_cents=5000, available_credit_cents=5000)
    db_session.add_all([source, card])
    db_session.commit()
    return user, source, card


def execute(db, suite, code="USD", amount=125, key="payment-intent"):
    user, source, card = suite
    return AccountsService(db).execute_bill_payment_for_user(user, str(source.id), str(card.id),
        Money(amount_minor=amount, currency_code=code), key)


def snapshot(db, suite):
    _, source, card = suite
    return (source.cleared_balance_cents, card.cleared_balance_cents, card.available_credit_cents,
            *(db.query(model).count() for model in (Account, Transaction, AccountLedgerEntry, PostedTransaction, AuditOutbox)))


@pytest.mark.parametrize("code", ["USD", "MXN", "JPY", "BHD"])
def test_payment_and_original_response_replay(db_session, payment_suite, code):
    user, source, card = payment_suite
    source.currency = card.currency = code
    db_session.commit()
    first = execute(db_session, payment_suite, code)
    assert first["disposition"] == "POSTED"
    assert first["money"] == {"amount_minor": 125, "currency_code": code}
    assert first["source_cleared_balance"]["amount_minor"] == 9875
    assert first["credit_cleared_balance"]["amount_minor"] == 4875
    assert first["credit_available_credit"]["amount_minor"] == 5125
    execute(db_session, payment_suite, code, amount=100, key="second-intent")
    before = snapshot(db_session, payment_suite)
    assert execute(db_session, payment_suite, code) == first
    assert snapshot(db_session, payment_suite) == before
    assert db_session.query(Transaction).count() == db_session.query(PostedTransaction).count() == 2


@pytest.mark.parametrize("failure", ["mismatch", "request_currency", "funds", "overpayment", "wrong_owner", "wrong_source_type"])
def test_failure_does_not_mutate(db_session, payment_suite, failure):
    user, source, card = payment_suite
    code = "USD"
    if failure == "mismatch":
        card.currency = "MXN"
    if failure == "request_currency":
        code = "MXN"
    if failure == "funds":
        source.cleared_balance_cents = 100
    if failure == "overpayment":
        card.cleared_balance_cents = 100
    if failure == "wrong_owner":
        source.user_id = uuid.uuid4()
    if failure == "wrong_source_type":
        source.account_type = "SYSTEM"
    db_session.commit()
    before = snapshot(db_session, payment_suite)
    with pytest.raises(HTTPException) as error:
        execute(db_session, payment_suite, code)
    assert error.value.status_code == (404 if failure.startswith("wrong_") else 422)
    assert snapshot(db_session, payment_suite) == before


@pytest.mark.parametrize("changed", ["amount", "currency", "account"])
def test_changed_retry_conflicts(db_session, payment_suite, changed):
    execute(db_session, payment_suite)
    before = snapshot(db_session, payment_suite)
    user, source, card = payment_suite
    with pytest.raises(HTTPException) as error:
        AccountsService(db_session).execute_bill_payment_for_user(user,
            str(uuid.uuid4()) if changed == "account" else str(source.id), str(card.id),
            Money(amount_minor=126 if changed == "amount" else 125,
                  currency_code="MXN" if changed == "currency" else "USD"), "payment-intent")
    assert error.value.status_code == 409
    assert snapshot(db_session, payment_suite) == before


def test_http_contract_legacy_and_structured(db_session, payment_suite):
    from routers.credit_card import pay_credit_card
    from utils.database import get_db
    from utils.auth import get_current_user
    from models.authentication import ValidatedToken
    app = FastAPI()
    app.post("/pay")(pay_credit_card)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: ValidatedToken(claims={"sub": payment_suite[0].auth_provider_uid})
    data = {"source_account_id": str(payment_suite[1].id), "credit_account_id": str(payment_suite[2].id)}
    with TestClient(app) as client:
        result = client.post("/pay", json={**data, "amount_cents": 125})
        assert result.status_code == 200, result.text
        assert result.json()["money"] == {"amount_minor": 125, "currency_code": "USD"}
        assert result.json()["source_cleared_balance_cents"] == 9875
        money = {"amount_minor": 125, "currency_code": "USD"}
        assert client.post("/pay", json={**data, "money": money}).status_code == 400
        assert client.post("/pay", json={**data, "money": money, "amount_cents": 125}).status_code == 422
        for code in ("usd", "EUR", None, ["USD"]):
            assert client.post("/pay", json={**data, "money": {**money, "currency_code": code}}, headers={"Idempotency-Key": "test"}).status_code == 400
        assert client.post("/pay", json={**data, "money": money}, headers={"Idempotency-Key": "structured"}).status_code == 200
    assert app.openapi()["components"]["schemas"]["BillPaymentRequest"]["properties"]["money"]


def test_legacy_request_is_usd_only():
    request = BillPaymentRequest(source_account_id="source", credit_account_id="card", amount_cents=125)
    assert request.payment_money() == Money(amount_minor=125, currency_code="USD")


@pytest.fixture
def pg_payments():
    import importlib
    import os
    import sqlalchemy as sa
    from sqlalchemy.orm import Session
    from utils.database import Base
    from models.credit_card import CreditProduct
    from models.origination import DepositProduct
    url = os.environ.get("TEST_MONEY_DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL payment concurrency requires TEST_MONEY_DATABASE_URL")
    assert sa.engine.make_url(url).database.endswith("_money_test")
    for name in ("identity", "origination", "audit", "credit_card", "fraud", "support",
                 "action_proposal", "settings", "kyc", "reference", "merchant"):
        importlib.import_module(f"models.{name}")
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        for schema in {table.schema for table in Base.metadata.tables.values()}:
            connection.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            product = CreditProduct(product_code="PAYMENT_TEST", product_name="Money test",
                min_credit_limit_cents=0, max_credit_limit_cents=100000, purchase_apr=0.1, cashback_rate=0)
            user = User(auth_provider_uid="pg-payment-test")
            deposit_product = DepositProduct(product_code="CHECKING_EVERYDAY", product_name="Checking")
            db.add_all([product, deposit_product, user])
            db.flush()
            source = Account(user_id=user.id, account_number="PG-PAY-SOURCE", account_type="CHECKING",
                product_name="Money test", product_code=None, currency="USD", cleared_balance_cents=10000)
            card = CreditAccount(customer_id=user.id, product_code=product.product_code, currency="USD",
                credit_limit_cents=10000, cleared_balance_cents=5000, available_credit_cents=5000)
            db.add_all([source, card])
            db.commit()
            ids = user.id, source.id, card.id
        yield engine, ids
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_postgres_lock_conflict_is_non_mutating(pg_payments):
    from sqlalchemy.orm import Session
    engine, (uid, source_id, card_id) = pg_payments
    with Session(engine) as holder, Session(engine) as contender:
        holder.query(Account).filter(Account.id == source_id).with_for_update(nowait=True).one()
        user = contender.get(User, uid)
        with pytest.raises(HTTPException) as error:
            AccountsService(contender).execute_bill_payment_for_user(user, str(source_id), str(card_id),
                Money(amount_minor=125, currency_code="USD"), "locked")
        assert error.value.status_code == 409
        assert contender.query(Transaction).count() == 0
        assert contender.get(Account, source_id).cleared_balance_cents == 10000
        holder.rollback()
        result = AccountsService(contender).execute_bill_payment_for_user(user, str(source_id), str(card_id),
            Money(amount_minor=125, currency_code="USD"), "locked")
        assert result["source_cleared_balance"]["amount_minor"] == 9875


@pytest.mark.parametrize("same_key", [True, False])
def test_postgres_concurrent_payments_preserve_single_posting(pg_payments, same_key):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    engine, (uid, source_id, card_id) = pg_payments
    barrier = Barrier(2)
    def worker(index):
        key = "concurrent" if same_key else f"concurrent-{index}"
        with Session(engine) as db:
            user = db.get(User, uid)
            barrier.wait(timeout=10)
            try:
                result = AccountsService(db).execute_bill_payment_for_user(user, str(source_id), str(card_id),
                    Money(amount_minor=125, currency_code="USD"), key)
                return key, result
            except HTTPException as error:
                assert error.status_code == 409
                return key, None
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(worker, [1, 2]))
    with Session(engine) as db:
        user = db.get(User, uid)
        results = [result or AccountsService(db).execute_bill_payment_for_user(user, str(source_id), str(card_id),
            Money(amount_minor=125, currency_code="USD"), key) for key, result in outcomes]
        expected = 1 if same_key else 2
        assert db.query(Transaction).count() == db.query(PostedTransaction).count() == expected
        assert db.query(AccountLedgerEntry).count() == expected * 2
        assert db.query(AuditOutbox).count() == expected * 2
        assert db.get(Account, source_id).cleared_balance_cents == 10000 - expected * 125
        assert db.get(CreditAccount, card_id).cleared_balance_cents == 5000 - expected * 125
        if same_key:
            assert results[0] == results[1]


def test_mxn_http_omits_legacy_fields_and_rejects_legacy_writes(db_session, payment_suite):
    from routers.credit_card import pay_credit_card
    from utils.database import get_db
    from utils.auth import get_current_user
    from models.authentication import ValidatedToken
    user, source, card = payment_suite
    source.currency = card.currency = "MXN"
    db_session.commit()
    app = FastAPI()
    app.post("/pay")(pay_credit_card)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: ValidatedToken(claims={"sub": user.auth_provider_uid})
    data = {"source_account_id": str(source.id), "credit_account_id": str(card.id)}
    before = snapshot(db_session, payment_suite)
    with TestClient(app) as client:
        assert client.post("/pay", json={**data, "amount_cents": 125}).status_code == 422
        assert snapshot(db_session, payment_suite) == before
        response = client.post("/pay", json={**data, "money": {"amount_minor": 125, "currency_code": "MXN"}}, headers={"Idempotency-Key": "mxn"})
        assert response.status_code == 200, response.text
        assert not any(key.endswith("_cents") for key in response.json())
        summary = AccountsService(db_session).get_user_accounts_summary(ValidatedToken(claims={"sub": user.auth_provider_uid}))
        for account in summary["deposit_accounts"] + summary["credit_accounts"]:
            assert account["cleared_balance"]["currency_code"] == "MXN"
            assert not any(key.endswith("_cents") for key in account)
