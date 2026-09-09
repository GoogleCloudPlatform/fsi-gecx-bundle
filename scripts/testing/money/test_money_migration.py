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

"""Exercise the actual additive migration on legacy SQLite and PostgreSQL rows."""

import importlib.util
import json
import os
from pathlib import Path
import uuid

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from services.money_reconciliation import reconcile_money, migration_blockers

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(params=["sqlite", "postgresql"])
def legacy_db(request, monkeypatch, tmp_path):
    if request.param == "postgresql":
        url = os.environ.get("TEST_MONEY_DATABASE_URL")
        if not url:
            pytest.skip("Set TEST_MONEY_DATABASE_URL to a disposable database ending in _money_test")
        assert sa.engine.make_url(url).database.endswith("_money_test")
        engine = sa.create_engine(url)
    else:
        engine = sa.create_engine("sqlite:///:memory:")
    connection = engine.connect()
    if request.param == "sqlite":
        # Avoid depending on the app's attached schemas for this legacy fixture.
        existing = {row[1] for row in connection.exec_driver_sql("PRAGMA database_list")}
        for schema in ("ledger", "cards"):
            if schema not in existing:
                connection.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS {schema}")
    else:
        for schema in ("ledger", "cards"):
            connection.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    metadata = sa.MetaData()
    accounts = sa.Table("accounts", metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("currency", sa.String(3)), sa.Column("credit_account_id", sa.String(36)),
        sa.Column("account_type", sa.String(30)), sa.Column("cleared_balance_cents", sa.BigInteger), schema="ledger")
    sa.Table("credit_accounts", metadata,
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("currency", sa.String(3)), schema="cards")
    transactions = sa.Table("transactions", metadata, sa.Column("id", sa.String(36), primary_key=True), schema="ledger")
    entries = sa.Table("account_ledger", metadata,
        sa.Column("entry_id", sa.String(36), primary_key=True), sa.Column("account_id", sa.String(36)),
        sa.Column("transaction_id", sa.String(36)), sa.Column("entry_type", sa.String(10)),
        sa.Column("amount_cents", sa.BigInteger), schema="ledger")
    metadata.create_all(connection)
    ids = {name: str(uuid.uuid4()) for name in ("debit", "credit", "transaction", "card")}
    connection.execute(accounts.insert(), [
        {"id": ids["debit"], "currency": None, "credit_account_id": None,
         "account_type": "CHECKING", "cleared_balance_cents": -125},
        {"id": ids["credit"], "currency": "USD", "credit_account_id": None,
         "account_type": "SAVINGS", "cleared_balance_cents": 125}])
    connection.execute(transactions.insert(), {"id": ids["transaction"]})
    connection.execute(entries.insert(), [
        {"entry_id": str(uuid.uuid4()), "account_id": ids[a], "transaction_id": ids["transaction"],
         "entry_type": direction, "amount_cents": 125}
        for a, direction in [("debit", "DEBIT"), ("credit", "CREDIT")]])
    connection.commit()
    monkeypatch.setenv("MONEY_RECONCILIATION_REPORT", str(tmp_path / "before.json"))
    try:
        yield connection, ids, tmp_path / "before.json"
    finally:
        connection.rollback()
        # Migration changes metadata; reflect the final schema before cleanup.
        for schema, name in [("ledger", "account_ledger"), ("ledger", "transactions"),
                             ("ledger", "accounts"), ("cards", "credit_accounts")]:
            connection.exec_driver_sql(f"DROP TABLE IF EXISTS {schema}.{name}")
        connection.commit()
        connection.close()
        engine.dispose()


def upgrade(connection):
    spec = importlib.util.spec_from_file_location("money_migration", ROOT / "banking-service/alembic/versions/d8e2f6a910bc_money_currency_invariants.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(connection)):
        module.upgrade()


def test_backfill_preserves_history_and_reconciles(legacy_db):
    connection, ids, report_path = legacy_db
    before_entries = connection.exec_driver_sql("SELECT * FROM ledger.account_ledger ORDER BY entry_id").all()
    before = reconcile_money(connection)
    upgrade(connection)
    after = reconcile_money(connection)
    assert json.loads(report_path.read_text())["null_accounts"][0]["id"] == ids["debit"]
    assert len(json.loads(report_path.read_text())["null_accounts"][0]["entry_ids"]) == 1
    assert not migration_blockers(after)
    assert not after["null_accounts"]
    assert before["balance_differences"] == after["balance_differences"] == []
    assert connection.exec_driver_sql("SELECT * FROM ledger.account_ledger ORDER BY entry_id").all() == before_entries
    assert connection.exec_driver_sql("SELECT currency_code FROM ledger.transactions").scalar_one() == "USD"
    connection.commit()
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(sa.text("UPDATE ledger.accounts SET currency=NULL WHERE id=:id"), {"id": ids["debit"]})
    connection.rollback()
    with pytest.raises(sa.exc.IntegrityError):
        connection.exec_driver_sql("UPDATE ledger.accounts SET currency='usd'")
    connection.rollback()
    with pytest.raises(sa.exc.IntegrityError):
        connection.exec_driver_sql("UPDATE ledger.transactions SET currency_code='EUR'")
    connection.rollback()


@pytest.mark.parametrize("problem", ["mixed", "invalid", "mirror", "orphan", "unbalanced", "unresolved"])
def test_ambiguous_data_stops_before_mutation(legacy_db, problem):
    connection, ids, report_path = legacy_db
    if problem in ("mixed", "invalid"):
        code = "MXN" if problem == "mixed" else "usd"
        connection.execute(sa.text("UPDATE ledger.accounts SET currency=:code WHERE id=:id"), {"code": code, "id": ids["credit"]})
    elif problem == "mirror":
        connection.execute(sa.text("INSERT INTO cards.credit_accounts(id,currency) VALUES (:id,'MXN')"), {"id": ids["card"]})
        connection.execute(sa.text("UPDATE ledger.accounts SET credit_account_id=:card WHERE id=:id"), {"card": ids["card"], "id": ids["credit"]})
    elif problem == "orphan":
        connection.execute(sa.text("UPDATE ledger.account_ledger SET account_id=:orphan WHERE account_id=:id"), {"orphan": str(uuid.uuid4()), "id": ids["credit"]})
    elif problem == "unbalanced":
        connection.exec_driver_sql("UPDATE ledger.account_ledger SET amount_cents=126 WHERE entry_type='DEBIT'")
    else:
        connection.execute(sa.text("INSERT INTO ledger.transactions(id) VALUES (:id)"), {"id": str(uuid.uuid4())})
    connection.commit()
    with pytest.raises(RuntimeError, match="stopped"):
        upgrade(connection)
    assert report_path.exists()
    assert "currency_code" not in {c["name"] for c in sa.inspect(connection).get_columns("transactions", schema="ledger")}
    assert connection.execute(sa.text("SELECT currency FROM ledger.accounts WHERE id=:id"), {"id": ids["debit"]}).scalar_one() is None
