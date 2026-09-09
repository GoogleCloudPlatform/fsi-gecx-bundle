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

"""Currency invariants at the durable posting boundary."""

import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

from models.money import Money
from models.origination import Account, Transaction, AccountLedgerEntry
from models.audit import AuditOutbox
from services.financial_journal import JournalEntrySpec, post_financial_transaction, ensure_system_journal_account
from services.ledger import LedgerService


def account(db, code, number=None, kind="SYSTEM", balance=0):
    a = Account(account_number=number or str(uuid.uuid4()), account_type=kind,
                product_name="Money fixture", product_code=None, currency=code,
                cleared_balance_cents=balance)
    db.add(a)
    db.flush()
    return a


def post(db, debit, credit, code, key="money-test", amount=125):
    money = Money(amount_minor=amount, currency_code=code)
    return post_financial_transaction(db, idempotency_key=key, description="Money test",
        source_type="TEST", currency=code, entries=(JournalEntrySpec(debit.id, "DEBIT", money),
                                                   JournalEntrySpec(credit.id, "CREDIT", money)))


@pytest.mark.parametrize("code", ["USD", "MXN", "JPY", "BHD"])
def test_durable_currency_and_idempotency(db_session, code):
    debit, credit = account(db_session, code), account(db_session, code)
    first = post(db_session, debit, credit, code)
    assert first.transaction.currency_code == code
    assert sum(e.amount_minor for e in first.entries if e.entry_type == "DEBIT") == 125
    again = post(db_session, debit, credit, code)
    assert again.transaction.id == first.transaction.id
    assert db_session.query(AuditOutbox).count() == 1
    with pytest.raises(ValueError, match="idempotency"):
        post(db_session, debit, credit, code, amount=126)
    other = "MXN" if code == "USD" else "USD"
    with pytest.raises(ValueError, match="idempotency"):
        post(db_session, debit, credit, other)
    assert db_session.query(Transaction).count() == 1


def test_mixed_currency_post_has_no_writes(db_session):
    debit, credit = account(db_session, "USD"), account(db_session, "MXN")
    with pytest.raises(ValueError, match="denomination"):
        post(db_session, debit, credit, "USD")
    assert db_session.query(Transaction).count() == 0
    assert db_session.query(AccountLedgerEntry).count() == 0
    assert db_session.query(AuditOutbox).count() == 0


def test_transfer_mismatch_and_replay(db_session):
    src = account(db_session, "USD", kind="CHECKING", balance=1000)
    dst = account(db_session, "MXN", kind="SAVINGS")
    service = LedgerService(db_session)
    with pytest.raises(HTTPException) as error:
        service.execute_transfer(src.id, dst.id, Money(amount_minor=125, currency_code="USD"), "test", "retry")
    assert error.value.status_code == 422
    assert src.cleared_balance_cents == 1000
    assert db_session.query(Transaction).count() == db_session.query(AuditOutbox).count() == 0
    dst.currency = "USD"
    money = Money(amount_minor=125, currency_code="USD")
    result = service.execute_transfer(src.id, dst.id, money, "test", "retry")
    assert service.execute_transfer(src.id, dst.id, money, "test", "retry") == result
    assert src.cleared_balance_cents == 875
    assert dst.cleared_balance_cents == 125
    with pytest.raises(HTTPException) as error:
        service.execute_transfer(src.id, dst.id, Money(amount_minor=126, currency_code="USD"), "test", "retry")
    assert error.value.status_code == 409


def test_clearing_accounts_are_currency_specific(db_session):
    usd = ensure_system_journal_account(db_session, "CLEARING", "test")
    mxn = ensure_system_journal_account(db_session, "CLEARING", "test", currency="MXN")
    assert usd.id != mxn.id
    assert usd.currency == "USD" and mxn.currency == "MXN"
    assert ensure_system_journal_account(db_session, "CLEARING", "test", currency="MXN").id == mxn.id


@pytest.mark.parametrize("code", ["usd", "EUR", " MXN"])
def test_db_rejects_invalid_account_currency(db_session, code):
    with pytest.raises(IntegrityError):
        account(db_session, code)
    db_session.rollback()
