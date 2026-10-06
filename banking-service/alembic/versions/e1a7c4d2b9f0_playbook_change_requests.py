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

"""Playbook change requests and draft base revisions.

The draft base column is added with a native ALTER TABLE on both dialects. Batch
mode is deliberately avoided: on SQLite it recreates the table and would drop
the published-revision immutability triggers.
"""

from alembic import op
import sqlalchemy as sa

revision = "e1a7c4d2b9f0"
down_revision = "b92e3d8a601c"
branch_labels = None
depends_on = None

# Written only on INSERT (opening a change request, including the legacy backfill);
# lifecycle updates touch status, closure, publication, title, description and version.
IDENTITY_COLUMNS = (
    "id",
    "playbook_id",
    "revision",
    "base_revision",
    "origin",
    "previous_base_revision",
    "opened_by",
    "opened_at",
)

STRANDED_DRAFTS = """
    SELECT count(*) FROM admin.playbook_change_requests cr
    JOIN admin.playbook_revisions r
        ON r.playbook_id = cr.playbook_id AND r.revision = cr.revision
    WHERE cr.status != 'OPEN' AND r.status = 'DRAFT'
"""


def upgrade():
    op.add_column(
        "playbook_revisions",
        sa.Column("base_revision", sa.Integer(), nullable=True),
        schema="admin",
    )
    op.create_table(
        "playbook_change_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("playbook_id", sa.String(128), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=True),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("previous_base_revision", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("opened_by", sa.String(255), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_by", sa.String(255), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_revision", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["playbook_id", "revision"],
            ["admin.playbook_revisions.playbook_id", "admin.playbook_revisions.revision"],
        ),
        sa.UniqueConstraint(
            "playbook_id", "revision", name="uq_playbook_change_request_revision"
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'PUBLISHED', 'CLOSED')",
            name="ck_playbook_change_request_status",
        ),
        sa.CheckConstraint(
            "origin IN ('CREATE', 'DRAFT', 'RESTORE', 'RECREATE', 'LEGACY')",
            name="ck_playbook_change_request_origin",
        ),
        sa.CheckConstraint(
            "(status = 'OPEN' AND closed_by IS NULL AND closed_at IS NULL) OR "
            "(status != 'OPEN' AND closed_by IS NOT NULL AND closed_at IS NOT NULL)",
            name="ck_playbook_change_request_closure",
        ),
        sa.CheckConstraint(
            "(status = 'PUBLISHED' AND published_revision IS NOT NULL AND published_revision = revision) OR "
            "(status != 'PUBLISHED' AND published_revision IS NULL)",
            name="ck_playbook_change_request_publication",
        ),
        sa.CheckConstraint(
            "length(title) BETWEEN 1 AND 200 AND "
            "length(description) <= 4000 AND version > 0",
            name="ck_playbook_change_request_bounds",
        ),
        schema="admin",
    )
    op.create_index(
        "ix_playbook_change_requests_status",
        "playbook_change_requests",
        ["playbook_id", "status"],
        schema="admin",
    )
    # Legacy drafts predate change requests; their clone source was never recorded.
    # Owner decision: base them on the current head so they stay publishable.
    op.execute("""
        UPDATE admin.playbook_revisions SET base_revision = (
            SELECT h.published_revision FROM admin.playbooks h
            WHERE h.id = admin.playbook_revisions.playbook_id
        ) WHERE status = 'DRAFT'
    """)
    op.execute("""
        INSERT INTO admin.playbook_change_requests (
            playbook_id, revision, base_revision, origin, title, description,
            status, version, opened_by, opened_at
        )
        SELECT playbook_id, revision, base_revision, 'LEGACY',
            'Draft revision ' || CAST(revision AS VARCHAR(16)), '',
            'OPEN', 1, created_by, created_at
        FROM admin.playbook_revisions WHERE status = 'DRAFT'
    """)
    if op.get_bind().dialect.name == "postgresql":
        identity_changed = " OR ".join(
            f"NEW.{column} IS DISTINCT FROM OLD.{column}" for column in IDENTITY_COLUMNS
        )
        op.execute(f"""CREATE FUNCTION admin.reject_final_change_request_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Change requests cannot be deleted'; END IF;
        IF OLD.status != 'OPEN' THEN RAISE EXCEPTION 'Published or closed change requests are immutable'; END IF;
        IF {identity_changed} THEN RAISE EXCEPTION 'Change request identity is immutable'; END IF;
        RETURN NEW; END $$""")
        op.execute("""CREATE TRIGGER playbook_change_request_immutable BEFORE UPDATE OR DELETE
        ON admin.playbook_change_requests
        FOR EACH ROW EXECUTE FUNCTION admin.reject_final_change_request_mutation()""")
    else:
        op.execute("""CREATE TRIGGER admin.playbook_change_request_immutable_update
        BEFORE UPDATE ON playbook_change_requests WHEN OLD.status != 'OPEN'
        BEGIN SELECT RAISE(ABORT, 'Published or closed change requests are immutable'); END""")
        op.execute("""CREATE TRIGGER admin.playbook_change_request_immutable_delete
        BEFORE DELETE ON playbook_change_requests
        BEGIN SELECT RAISE(ABORT, 'Change requests cannot be deleted'); END""")
        op.execute(f"""CREATE TRIGGER admin.playbook_change_request_identity_immutable
        BEFORE UPDATE OF {", ".join(IDENTITY_COLUMNS)} ON playbook_change_requests
        WHEN {" OR ".join(f"NEW.{c} IS NOT OLD.{c}" for c in IDENTITY_COLUMNS)}
        BEGIN SELECT RAISE(ABORT, 'Change request identity is immutable'); END""")


def downgrade():
    # The previous schema gates drafts only on draft_version and generation, so a
    # closed change request's draft would become editable and publishable again.
    stranded = op.get_bind().execute(sa.text(STRANDED_DRAFTS)).scalar()
    if stranded:
        raise RuntimeError(
            f"Refusing to downgrade e1a7c4d2b9f0: {stranded} closed change request "
            "draft(s) would become editable and publishable again under the previous "
            "schema. Restore a backup taken before this migration, or deliberately "
            "retire those drafts out of band, before downgrading."
        )
    # DROP TABLE does not fire row triggers on either dialect.
    op.drop_table("playbook_change_requests", schema="admin")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION admin.reject_final_change_request_mutation()")
    # Native DROP COLUMN (SQLite >= 3.35) keeps the immutability triggers intact.
    op.execute("ALTER TABLE admin.playbook_revisions DROP COLUMN base_revision")
