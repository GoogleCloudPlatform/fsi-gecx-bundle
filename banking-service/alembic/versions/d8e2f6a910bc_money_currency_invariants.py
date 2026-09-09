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

"""Persist Money denomination after recording legacy reconciliation evidence."""

import json
import os
from pathlib import Path
from alembic import op
import sqlalchemy as sa

revision = "d8e2f6a910bc"
down_revision = "c3a91f2b7d44"
branch_labels = None
depends_on = None


def upgrade():
    from services.money_reconciliation import reconcile_money, migration_blockers
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        # Keep headers, entries and account denominations stable until backfill
        # and constraints commit. Readers can continue during reconciliation.
        connection.execute(sa.text(
            "LOCK TABLE ledger.accounts, cards.credit_accounts, "
            "ledger.transactions, ledger.account_ledger IN SHARE ROW EXCLUSIVE MODE"))
    report = reconcile_money(connection)
    # Archive before any backfill, including reports that stop migration.
    report_path = Path(os.environ.get("MONEY_RECONCILIATION_REPORT", "money-reconciliation-before.json"))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    blockers = migration_blockers(report)
    if blockers:
        raise RuntimeError(f"Money migration stopped; inspect {report_path}: {list(blockers)}")

    op.add_column("transactions", sa.Column("currency_code", sa.String(3), nullable=True), schema="ledger")
    for schema, table, check_name in [
        ("ledger", "accounts", "ck_accounts_currency"),
        ("cards", "credit_accounts", "ck_credit_accounts_currency"),
    ]:
        connection.execute(sa.text(f"UPDATE {schema}.{table} SET currency='USD' WHERE currency IS NULL"))
        with op.batch_alter_table(table, schema=schema) as batch:
            batch.alter_column("currency", existing_type=sa.String(3), nullable=False)
            batch.create_check_constraint(check_name, "currency IN ('USD', 'MXN', 'JPY', 'BHD')")
    if connection.dialect.name == "postgresql":
        # Reconciliation proved every transaction has one denomination. A
        # set-based update avoids a database round trip for every historical ID.
        connection.execute(sa.text(
            "UPDATE ledger.transactions AS t SET currency_code=a.currency "
            "FROM ledger.account_ledger AS e JOIN ledger.accounts AS a "
            "ON a.id=e.account_id WHERE t.id=e.transaction_id"))
    else:
        for tid, code in report["inferred_transaction_currencies"].items():
            connection.execute(sa.text(
                "UPDATE ledger.transactions SET currency_code=:currency WHERE CAST(id AS TEXT)=:id"
            ), {"currency": code, "id": tid})
    with op.batch_alter_table("transactions", schema="ledger") as batch:
        batch.alter_column("currency_code", existing_type=sa.String(3), nullable=False)
        batch.create_check_constraint("ck_transactions_currency", "currency_code IN ('USD', 'MXN', 'JPY', 'BHD')")


def downgrade():
    raise RuntimeError("Money denomination is retained: fix forward or use the explicit demo reset path")
