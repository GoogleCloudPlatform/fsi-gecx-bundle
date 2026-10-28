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

"""Customer-facing terms on the credit product catalog.

Makes catalog.credit_products the single source of truth for the card lineup.
Values are refreshed from resources/data/credit_products.json by the seeding
catalog sync; server defaults only keep existing rows valid until then.

No grants: catalog access is granted per schema by the database lifecycle
reconcile job (scripts/database_lifecycle.py), and new columns inherit it.
"""
from alembic import op
import sqlalchemy as sa

revision = "a3f8c1d5e902"
down_revision = "c5d1e8f2a417"
branch_labels = None
depends_on = None

SCHEMA = "catalog"
TABLE = "credit_products"

RATE_COLUMNS = (
    "purchase_apr",
    "cashback_rate",
    "intro_purchase_apr",
    "intro_balance_transfer_apr",
    "balance_transfer_fee_rate",
    "foreign_transaction_fee_rate",
    "cash_advance_apr",
    "cash_advance_fee_rate",
    "penalty_apr",
)
INTRO_OFFERS = ("intro_purchase_apr", "intro_balance_transfer_apr")


def _columns():
    rate = sa.Numeric(5, 4)
    return (
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("tagline", sa.String(160), nullable=False, server_default=""),
        sa.Column("best_for", sa.String(200), nullable=False, server_default=""),
        sa.Column("intro_purchase_apr", rate, nullable=True),
        sa.Column("intro_purchase_apr_months", sa.Integer(), nullable=True),
        sa.Column("intro_balance_transfer_apr", rate, nullable=True),
        sa.Column("intro_balance_transfer_apr_months", sa.Integer(), nullable=True),
        sa.Column("balance_transfer_fee_rate", rate, nullable=False, server_default="0"),
        sa.Column("balance_transfer_fee_minimum_minor", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("foreign_transaction_fee_rate", rate, nullable=False, server_default="0"),
        sa.Column("cash_advance_apr", rate, nullable=False, server_default="0"),
        sa.Column("cash_advance_fee_rate", rate, nullable=False, server_default="0"),
        sa.Column("cash_advance_fee_minimum_minor", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("late_fee_maximum_minor", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("returned_payment_fee_maximum_minor", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("penalty_apr", rate, nullable=True),
        sa.Column("features", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("is_secured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    )


def _check_constraints():
    checks = [
        (f"ck_credit_products_{column}_range",
         f"{column} IS NULL OR ({column} >= 0 AND {column} <= 1)")
        for column in RATE_COLUMNS
    ]
    checks += [
        (f"ck_credit_products_{offer}_months",
         f"({offer} IS NULL AND {offer}_months IS NULL) OR "
         f"({offer} IS NOT NULL AND {offer}_months IS NOT NULL AND {offer}_months > 0)")
        for offer in INTRO_OFFERS
    ]
    checks += [
        ("ck_credit_products_fee_amounts",
         "balance_transfer_fee_minimum_minor >= 0 AND cash_advance_fee_minimum_minor >= 0 "
         "AND late_fee_maximum_minor >= 0 AND returned_payment_fee_maximum_minor >= 0"),
        ("ck_credit_products_currency_code",
         "currency_code IN ('USD', 'MXN', 'JPY', 'BHD')"),
    ]
    return checks


def upgrade():
    for column in _columns():
        op.add_column(TABLE, column, schema=SCHEMA)
    for name, condition in _check_constraints():
        op.create_check_constraint(name, TABLE, condition, schema=SCHEMA)


def downgrade():
    for name, _ in reversed(_check_constraints()):
        op.drop_constraint(name, TABLE, schema=SCHEMA, type_="check")
    for column in reversed(_columns()):
        op.drop_column(TABLE, column.name, schema=SCHEMA)
