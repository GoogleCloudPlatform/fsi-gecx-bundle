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

"""Expand support preferences to CES GA locales plus existing Mexican Spanish."""
from alembic import op

revision = "f5c8d2e7a104"
down_revision = "e4b7c9a12f63"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_users_preferred_support_locale", "users", schema="identity", type_="check")
    op.create_check_constraint("ck_users_preferred_support_locale", "users",
        "preferred_support_locale IN ('en-US', 'es-MX', 'es-ES', 'es-US', 'fr-CA', 'fr-FR', 'de-DE', 'pt-BR')", schema="identity")


def downgrade():
    # Refuse to erase customer preferences when reverting the narrower constraint.
    # The operator must explicitly change expanded preferences before downgrade.
    op.drop_constraint("ck_users_preferred_support_locale", "users", schema="identity", type_="check")
    op.create_check_constraint("ck_users_preferred_support_locale", "users",
        "preferred_support_locale IN ('en-US', 'es-MX')", schema="identity")
