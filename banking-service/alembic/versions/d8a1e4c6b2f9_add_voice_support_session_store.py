"""Add the isolated ADK voice-support session schema and reset epochs.

Revision ID: d8a1e4c6b2f9
Revises: f7c8d9e0a1b2
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "d8a1e4c6b2f9"
down_revision: str | Sequence[str] | None = "f7c8d9e0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "voice_support_sessions"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA}.reset_epochs (
                scope_type VARCHAR(16) NOT NULL,
                scope_id VARCHAR(255) NOT NULL,
                epoch BIGINT NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (scope_type, scope_id)
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO {SCHEMA}.reset_epochs (scope_type, scope_id, epoch)
            VALUES ('GLOBAL', '*', 0)
            ON CONFLICT (scope_type, scope_id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
