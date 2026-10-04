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

"""Permanently reserve a provider-qualified approval on its proposal."""
from alembic import op
import sqlalchemy as sa

revision = "a81d2c7f490b"
down_revision = "f7e0f4a9c306"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("action_proposals", sa.Column("bank_decision_ref", sa.String(193), nullable=True), schema="operations")
    op.create_unique_constraint("uq_action_proposals_bank_decision_ref", "action_proposals", ["bank_decision_ref"], schema="operations")


def downgrade():
    op.drop_constraint("uq_action_proposals_bank_decision_ref", "action_proposals", schema="operations", type_="unique")
    op.drop_column("action_proposals", "bank_decision_ref", schema="operations")
