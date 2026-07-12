"""add scenario outcomes

Revision ID: c7e8d9a1b2f3
Revises: a4c2f1d8e9b0
Create Date: 2026-07-11 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import utils.database


# revision identifiers, used by Alembic.
revision: str = "c7e8d9a1b2f3"
down_revision: Union[str, Sequence[str], None] = "a4c2f1d8e9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "scenario_outcomes",
        sa.Column("id", utils.database.UniversalUUID(), nullable=False),
        sa.Column("scenario_id", sa.String(length=128), nullable=False),
        sa.Column("execution_id", sa.String(length=128), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("authorization_id", utils.database.UniversalUUID(), nullable=True),
        sa.Column("transaction_id", utils.database.UniversalUUID(), nullable=True),
        sa.Column("fraud_alert_id", utils.database.UniversalUUID(), nullable=True),
        sa.Column("customer_id", utils.database.UniversalUUID(), nullable=True),
        sa.Column("credit_account_id", utils.database.UniversalUUID(), nullable=True),
        sa.Column("card_id", utils.database.UniversalUUID(), nullable=True),
        sa.Column("card_token", sa.String(length=128), nullable=True),
        sa.Column("outcome_label", sa.String(length=64), nullable=False),
        sa.Column("expected_reason_codes", sa.JSON(), nullable=False),
        sa.Column("actual_reason_codes", sa.JSON(), nullable=False),
        sa.Column("expected_score_band", sa.String(length=64), nullable=True),
        sa.Column("actual_risk_score", sa.Integer(), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("synthetic_label", sa.Boolean(), nullable=False),
        sa.Column("operational_action", sa.String(length=64), nullable=True),
        sa.Column("operational_status", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scenario_id", "execution_id", "event_id", name="uq_scenario_outcomes_event"
        ),
        schema="operations",
    )
    op.create_index(
        "idx_scenario_outcomes_authorization",
        "scenario_outcomes",
        ["authorization_id"],
        unique=False,
        schema="operations",
    )
    op.create_index(
        "idx_scenario_outcomes_customer_created",
        "scenario_outcomes",
        ["customer_id", "created_at"],
        unique=False,
        schema="operations",
    )
    op.create_index(
        "idx_scenario_outcomes_fraud_alert",
        "scenario_outcomes",
        ["fraud_alert_id"],
        unique=False,
        schema="operations",
    )
    op.create_index(
        "idx_scenario_outcomes_scenario_execution",
        "scenario_outcomes",
        ["scenario_id", "execution_id"],
        unique=False,
        schema="operations",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "idx_scenario_outcomes_scenario_execution",
        table_name="scenario_outcomes",
        schema="operations",
    )
    op.drop_index(
        "idx_scenario_outcomes_fraud_alert",
        table_name="scenario_outcomes",
        schema="operations",
    )
    op.drop_index(
        "idx_scenario_outcomes_customer_created",
        table_name="scenario_outcomes",
        schema="operations",
    )
    op.drop_index(
        "idx_scenario_outcomes_authorization",
        table_name="scenario_outcomes",
        schema="operations",
    )
    op.drop_table("scenario_outcomes", schema="operations")
