"""Runtime-neutral consequential action proposals.

Revision ID: 91d7b4a6c2ef
Revises: 7c4f2a9d1e63
Create Date: 2026-07-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import utils.database


revision: str = "91d7b4a6c2ef"
down_revision: Union[str, Sequence[str], None] = "7c4f2a9d1e63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "action_proposals",
        sa.Column("id", utils.database.UniversalUUID(), nullable=False),
        sa.Column("contract_version", sa.String(length=32), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="PROPOSED",
        ),
        sa.Column("customer_id", utils.database.UniversalUUID(), nullable=False),
        sa.Column("account_id", utils.database.UniversalUUID(), nullable=True),
        sa.Column("support_session_id", sa.String(length=255), nullable=False),
        sa.Column("runtime_name", sa.String(length=64), nullable=False),
        sa.Column("runtime_session_id", sa.String(length=255), nullable=False),
        sa.Column(
            "originating_customer_turn_id", sa.String(length=255), nullable=False
        ),
        sa.Column("reset_generation", sa.String(length=64), nullable=False),
        sa.Column("confirmation_policy", sa.String(length=32), nullable=False),
        sa.Column("action_payload", sa.JSON(), nullable=False),
        sa.Column("payload_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("customer_safe_summary", sa.String(length=2000), nullable=False),
        sa.Column("catalog_snapshot_id", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("presented_assistant_turn_id", sa.String(length=255), nullable=True),
        sa.Column(
            "confirmation_customer_turn_id", sa.String(length=255), nullable=True
        ),
        sa.Column("confirmation_evidence", sa.JSON(), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("invalidation_reason", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("presented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("commit_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'PRESENTED', 'CONFIRMED', 'COMMITTING', "
            "'COMMITTED', 'DECLINED', 'INVALIDATED', 'EXPIRED')",
            name="ck_action_proposals_status",
        ),
        sa.CheckConstraint(
            "confirmation_policy IN ('NONE', 'EXPLICIT_VERBAL', 'EXPLICIT_UI', "
            "'STEP_UP', 'HUMAN_APPROVAL')",
            name="ck_action_proposals_confirmation_policy",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "customer_id",
            "support_session_id",
            "action_type",
            "idempotency_key",
            name="uq_action_proposals_scope_idempotency",
        ),
        schema="operations",
    )
    op.create_index(
        "idx_action_proposals_customer_status",
        "action_proposals",
        ["customer_id", "status"],
        unique=False,
        schema="operations",
    )
    op.create_index(
        "idx_action_proposals_session_status",
        "action_proposals",
        ["support_session_id", "status"],
        unique=False,
        schema="operations",
    )
    op.create_index(
        "idx_action_proposals_expires_at",
        "action_proposals",
        ["expires_at"],
        unique=False,
        schema="operations",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_action_proposals_expires_at",
        table_name="action_proposals",
        schema="operations",
    )
    op.drop_index(
        "idx_action_proposals_session_status",
        table_name="action_proposals",
        schema="operations",
    )
    op.drop_index(
        "idx_action_proposals_customer_status",
        table_name="action_proposals",
        schema="operations",
    )
    op.drop_table("action_proposals", schema="operations")
