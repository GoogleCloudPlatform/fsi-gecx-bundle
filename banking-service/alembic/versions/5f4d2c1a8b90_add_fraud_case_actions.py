"""add fraud case actions

Revision ID: 5f4d2c1a8b90
Revises: 7fb3570a7d09
Create Date: 2026-07-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import utils.database


# revision identifiers, used by Alembic.
revision: str = "5f4d2c1a8b90"
down_revision: Union[str, Sequence[str], None] = "7fb3570a7d09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "fraud_alerts",
        sa.Column("remediation_status", sa.String(length=32), nullable=False, server_default="NOT_STARTED"),
        schema="operations",
    )
    op.add_column("fraud_alerts", sa.Column("triaged_at", sa.DateTime(), nullable=True), schema="operations")
    op.add_column("fraud_alerts", sa.Column("triage_summary", sa.String(length=512), nullable=True), schema="operations")
    op.add_column(
        "fraud_alerts",
        sa.Column("selected_disputed_authorization_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        schema="operations",
    )
    op.add_column(
        "fraud_alerts",
        sa.Column("selected_disputed_transaction_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        schema="operations",
    )
    op.add_column(
        "fraud_alerts",
        sa.Column("provisional_credit_cents", sa.BigInteger(), nullable=False, server_default="0"),
        schema="operations",
    )
    op.add_column("fraud_alerts", sa.Column("replacement_card_id", utils.database.UniversalUUID(), nullable=True), schema="operations")
    op.add_column("fraud_alerts", sa.Column("triage_message_thread_id", sa.String(length=128), nullable=True), schema="operations")
    op.add_column("fraud_alerts", sa.Column("triage_message_id", sa.String(length=128), nullable=True), schema="operations")

    op.alter_column(
        "fraud_alerts",
        "remediation_status",
        existing_type=sa.String(length=32),
        server_default=None,
        schema="operations",
    )
    op.alter_column(
        "fraud_alerts",
        "selected_disputed_authorization_ids",
        existing_type=sa.JSON(),
        server_default=None,
        schema="operations",
    )
    op.alter_column(
        "fraud_alerts",
        "selected_disputed_transaction_ids",
        existing_type=sa.JSON(),
        server_default=None,
        schema="operations",
    )
    op.alter_column(
        "fraud_alerts",
        "provisional_credit_cents",
        existing_type=sa.BigInteger(),
        server_default=None,
        schema="operations",
    )

    op.create_table(
        "fraud_case_actions",
        sa.Column("id", utils.database.UniversalUUID(), nullable=False),
        sa.Column("fraud_alert_id", utils.database.UniversalUUID(), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fraud_alert_id", "idempotency_key", name="uq_fraud_case_actions_idempotency"),
        schema="operations",
    )
    op.create_index("idx_fraud_case_actions_alert", "fraud_case_actions", ["fraud_alert_id"], unique=False, schema="operations")
    op.create_index("idx_fraud_case_actions_status", "fraud_case_actions", ["status"], unique=False, schema="operations")
    op.create_index("idx_fraud_case_actions_type", "fraud_case_actions", ["action_type"], unique=False, schema="operations")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_fraud_case_actions_type", table_name="fraud_case_actions", schema="operations")
    op.drop_index("idx_fraud_case_actions_status", table_name="fraud_case_actions", schema="operations")
    op.drop_index("idx_fraud_case_actions_alert", table_name="fraud_case_actions", schema="operations")
    op.drop_table("fraud_case_actions", schema="operations")

    op.drop_column("fraud_alerts", "triage_message_id", schema="operations")
    op.drop_column("fraud_alerts", "triage_message_thread_id", schema="operations")
    op.drop_column("fraud_alerts", "replacement_card_id", schema="operations")
    op.drop_column("fraud_alerts", "provisional_credit_cents", schema="operations")
    op.drop_column("fraud_alerts", "selected_disputed_transaction_ids", schema="operations")
    op.drop_column("fraud_alerts", "selected_disputed_authorization_ids", schema="operations")
    op.drop_column("fraud_alerts", "triage_summary", schema="operations")
    op.drop_column("fraud_alerts", "triaged_at", schema="operations")
    op.drop_column("fraud_alerts", "remediation_status", schema="operations")
