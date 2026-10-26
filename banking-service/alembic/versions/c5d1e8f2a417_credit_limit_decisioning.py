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

"""Record credit-limit cooling-off and income-confirmation facts.

Additive and nullable: existing rows keep their values and remain valid. The
income pair constraint requires confirmation time and source to be set together.
"""

from alembic import op
import sqlalchemy as sa

revision = "c5d1e8f2a417"
down_revision = "e1a7c4d2b9f0"
branch_labels = None
depends_on = None

INCOME_SOURCE_CHECK = (
    "income_source IS NULL OR income_source IN "
    "('SEEDED', 'CUSTOMER_STATED', 'DOCUMENT_VERIFIED')"
)
INCOME_PAIR_CHECK = "(income_confirmed_at IS NULL) = (income_source IS NULL)"


def upgrade():
    op.add_column(
        "credit_accounts",
        sa.Column("last_limit_increase_at", sa.DateTime(timezone=True), nullable=True),
        schema="cards",
    )
    op.add_column(
        "user_credit_profiles",
        sa.Column("income_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        schema="kyc",
    )
    op.add_column(
        "user_credit_profiles",
        sa.Column("income_source", sa.String(32), nullable=True),
        schema="kyc",
    )
    op.create_check_constraint(
        "ck_user_credit_profiles_income_source",
        "user_credit_profiles",
        INCOME_SOURCE_CHECK,
        schema="kyc",
    )
    op.create_check_constraint(
        "ck_user_credit_profiles_income_confirmation_pair",
        "user_credit_profiles",
        INCOME_PAIR_CHECK,
        schema="kyc",
    )


def downgrade():
    for name in (
        "ck_user_credit_profiles_income_confirmation_pair",
        "ck_user_credit_profiles_income_source",
    ):
        op.drop_constraint(name, "user_credit_profiles", schema="kyc", type_="check")
    op.drop_column("user_credit_profiles", "income_source", schema="kyc")
    op.drop_column("user_credit_profiles", "income_confirmed_at", schema="kyc")
    op.drop_column("credit_accounts", "last_limit_increase_at", schema="cards")
