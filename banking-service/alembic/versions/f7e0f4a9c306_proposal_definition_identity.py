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

"""Reset disposable proposals and require immutable definition identity.

Deploy with proposal traffic stopped and begin fresh support sessions afterward.
Existing proposal IDs intentionally cease to resolve; no legacy rows are migrated.
"""

from alembic import op
import sqlalchemy as sa

revision = "f7e0f4a9c306"
down_revision = "f6d9e3f8b205"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DELETE FROM operations.action_proposals")
    for name, kind in [
        ("definition_id", sa.String(128)),
        ("definition_revision", sa.Integer()),
        ("definition_digest", sa.String(64)),
    ]:
        op.add_column(
            "action_proposals",
            sa.Column(name, kind, nullable=False),
            schema="operations",
        )


def downgrade():
    op.execute("DELETE FROM operations.action_proposals")
    for name in ("definition_digest", "definition_revision", "definition_id"):
        op.drop_column("action_proposals", name, schema="operations")
