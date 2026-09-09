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

"""Persist the customer default for bilingual support consultations."""
from alembic import op
import sqlalchemy as sa

revision = "e4b7c9a12f63"
down_revision = "d8e2f6a910bc"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("preferred_support_locale", sa.String(5),
                  nullable=False, server_default="en-US"), schema="identity")
    op.create_check_constraint("ck_users_preferred_support_locale", "users",
                               "preferred_support_locale IN ('en-US', 'es-MX')",
                               schema="identity")


def downgrade():
    op.drop_constraint("ck_users_preferred_support_locale", "users", schema="identity", type_="check")
    op.drop_column("users", "preferred_support_locale", schema="identity")
